"""Enhanced Transformer model with improved architecture.

This is an improved pure Transformer model without LSTM,
using modern techniques for better performance on time series.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import torch
import torch.nn as nn


class PositionalEncoding(nn.Module):
    """Sinusoidal positional encoding for transformers."""

    def __init__(self, d_model: int, max_len: int = 5000, dropout: float = 0.1) -> None:
        super().__init__()
        self.dropout = nn.Dropout(p=dropout)
        
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model))
        
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        
        pe = pe.unsqueeze(0)
        self.register_buffer('pe', pe)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = x + self.pe[:, :x.size(1), :]
        return self.dropout(x)


class EnhancedTransformer(nn.Module):
    """Enhanced pure Transformer model for time series.
    
    Improvements over LSTM-Transformer:
    - Pure attention (no LSTM bottleneck)
    - Deeper network (can handle longer sequences)
    - Better normalization (LayerNorm before attention)
    - Residual connections
    - Multi-scale temporal convolutions (optional)
    """

    def __init__(
        self,
        input_size: int,
        d_model: int = 256,
        nhead: int = 8,
        num_layers: int = 4,
        dim_feedforward: int = 1024,
        dropout: float = 0.2,
        output_size: int = 1,
    ) -> None:
        """Initialize Enhanced Transformer.

        Args:
            input_size: Number of input features
            d_model: Model dimension (embedding size)
            nhead: Number of attention heads
            num_layers: Number of transformer layers
            dim_feedforward: Dimension of feedforward network
            dropout: Dropout rate
            output_size: Output dimension
        """
        super().__init__()
        
        self.input_size = input_size
        self.d_model = d_model
        self.nhead = nhead
        self.num_layers = num_layers
        self.output_size = output_size
        
        # Input projection
        self.input_proj = nn.Linear(input_size, d_model)
        
        # Positional encoding
        self.pos_encoder = PositionalEncoding(d_model, dropout=dropout)
        
        # Transformer encoder
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=nhead,
            dim_feedforward=dim_feedforward,
            dropout=dropout,
            activation='gelu',  # GELU is better than ReLU for transformers
            batch_first=True,
            norm_first=True,  # Pre-normalization (modern practice)
        )
        self.transformer = nn.TransformerEncoder(
            encoder_layer,
            num_layers=num_layers,
        )
        
        # Output head with multiple layers
        self.output_head = nn.Sequential(
            nn.Linear(d_model, d_model // 2),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(d_model // 2, d_model // 4),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(d_model // 4, output_size),
        )
        
        # Initialize weights
        self._init_weights()

    def _init_weights(self):
        """Initialize weights with Xavier initialization."""
        for p in self.parameters():
            if p.dim() > 1:
                nn.init.xavier_uniform_(p)

    def forward(self, x: torch.Tensor, mask: Optional[torch.Tensor] = None) -> torch.Tensor:
        """Forward pass.

        Args:
            x: Input tensor of shape (batch, seq_len, input_size)
            mask: Optional attention mask

        Returns:
            Output tensor of shape (batch, output_size)
        """
        # Project input to model dimension
        x = self.input_proj(x)  # (batch, seq_len, d_model)
        
        # Add positional encoding
        x = self.pos_encoder(x)
        
        # Transformer forward pass
        x = self.transformer(x, mask=mask)  # (batch, seq_len, d_model)
        
        # Use the last timestep for prediction
        x = x[:, -1, :]  # (batch, d_model)
        
        # Output head
        out = self.output_head(x)  # (batch, output_size)
        
        return out


class EnhancedTransformerModel:
    """Wrapper for Enhanced Transformer with training and prediction."""

    def __init__(
        self,
        input_size: Optional[int] = None,
        d_model: int = 256,
        nhead: int = 8,
        num_layers: int = 4,
        dim_feedforward: int = 1024,
        dropout: float = 0.2,
        learning_rate: float = 0.0001,
        device: Optional[str] = None,
    ) -> None:
        """Initialize model wrapper.

        Args:
            input_size: Number of input features (inferred from data if None)
            d_model: Model dimension (larger = more capacity)
            nhead: Number of attention heads (must divide d_model)
            num_layers: Number of transformer layers (deeper = more complex patterns)
            dim_feedforward: Feedforward network dimension
            dropout: Dropout rate for regularization
            learning_rate: Learning rate for optimizer
            device: Device to use ('cuda', 'cpu', or None for auto)
        """
        self.input_size = input_size
        self.d_model = d_model
        self.nhead = nhead
        self.num_layers = num_layers
        self.dim_feedforward = dim_feedforward
        self.dropout = dropout
        self.learning_rate = learning_rate
        
        # Set device
        if device is None:
            self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        else:
            self.device = torch.device(device)
        
        # Will be initialized in fit()
        self.model: Optional[EnhancedTransformer] = None
        self.optimizer: Optional[torch.optim.Optimizer] = None
        self.scheduler: Optional[torch.optim.lr_scheduler._LRScheduler] = None
        self.criterion = nn.MSELoss()
        
        # Normalization parameters
        self.feature_mean: Optional[np.ndarray] = None
        self.feature_std: Optional[np.ndarray] = None

    def prepare_sequences(
        self,
        features: np.ndarray,
        targets: np.ndarray,
        seq_length: int = 50,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """Prepare sequences for training.

        Args:
            features: Feature array (n_samples, n_features)
            targets: Target array (n_samples,)
            seq_length: Sequence length (can be longer than LSTM!)

        Returns:
            Tuple of (X_sequences, y_sequences) as tensors
        """
        X_seq, y_seq = [], []
        
        for i in range(len(features) - seq_length):
            X_seq.append(features[i:i + seq_length])
            y_seq.append(targets[i + seq_length])
        
        X_tensor = torch.FloatTensor(np.array(X_seq)).to(self.device)
        y_tensor = torch.FloatTensor(np.array(y_seq)).unsqueeze(1).to(self.device)
        
        return X_tensor, y_tensor

    def fit(
        self,
        features: pd.DataFrame,
        target: pd.Series,
        epochs: int = 100,
        batch_size: int = 64,
        seq_length: int = 50,
        validation_split: float = 0.2,
        verbose: bool = True,
    ) -> dict[str, list[float]]:
        """Train the model.

        Args:
            features: Feature DataFrame
            target: Target series
            epochs: Number of training epochs
            batch_size: Batch size
            seq_length: Sequence length (50-100 recommended for Transformer)
            validation_split: Fraction for validation
            verbose: Print training progress

        Returns:
            Dictionary with training history
        """
        # Convert to numpy
        feature_array = features.values
        target_array = target.values
        
        # Infer input size if not set
        if self.input_size is None:
            self.input_size = feature_array.shape[1]
        
        # Normalize features
        self.feature_mean = feature_array.mean(axis=0)
        self.feature_std = feature_array.std(axis=0)
        features_norm = (feature_array - self.feature_mean) / (self.feature_std + 1e-8)
        
        # Create sequences
        X, y = self.prepare_sequences(features_norm, target_array, seq_length)
        
        # Train/validation split
        n_train = int(len(X) * (1 - validation_split))
        X_train, X_val = X[:n_train], X[n_train:]
        y_train, y_val = y[:n_train], y[n_train:]
        
        # Initialize model
        self.model = EnhancedTransformer(
            input_size=self.input_size,
            d_model=self.d_model,
            nhead=self.nhead,
            num_layers=self.num_layers,
            dim_feedforward=self.dim_feedforward,
            dropout=self.dropout,
        ).to(self.device)
        
        # Optimizer with weight decay
        self.optimizer = torch.optim.AdamW(
            self.model.parameters(),
            lr=self.learning_rate,
            weight_decay=0.01,
        )
        
        # Learning rate scheduler (cosine annealing)
        self.scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
            self.optimizer,
            T_max=epochs,
            eta_min=self.learning_rate * 0.01,
        )
        
        if verbose:
            print(f"Enhanced Transformer Model")
            print(f"  d_model: {self.d_model}, heads: {self.nhead}, layers: {self.num_layers}")
            print(f"  Sequence length: {seq_length} (longer than LSTM!)")
            print(f"  Parameters: {sum(p.numel() for p in self.model.parameters()):,}")
            print(f"  Training samples: {len(X_train)}, Validation: {len(X_val)}")
        
        # Training loop
        history = {'train_loss': [], 'val_loss': []}
        best_val_loss = float('inf')
        patience = 20
        patience_counter = 0
        
        for epoch in range(epochs):
            self.model.train()
            epoch_loss = 0
            n_batches = 0
            
            # Mini-batch training
            for i in range(0, len(X_train), batch_size):
                batch_X = X_train[i:i + batch_size]
                batch_y = y_train[i:i + batch_size]
                
                # Forward pass
                self.optimizer.zero_grad()
                outputs = self.model(batch_X)
                loss = self.criterion(outputs, batch_y)
                
                # Backward pass
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)
                self.optimizer.step()
                
                epoch_loss += loss.item()
                n_batches += 1
            
            avg_train_loss = epoch_loss / n_batches
            history['train_loss'].append(avg_train_loss)
            
            # Validation
            self.model.eval()
            with torch.no_grad():
                val_outputs = self.model(X_val)
                val_loss = self.criterion(val_outputs, y_val).item()
                history['val_loss'].append(val_loss)
            
            # Learning rate scheduler
            self.scheduler.step()
            
            # Early stopping
            if val_loss < best_val_loss:
                best_val_loss = val_loss
                patience_counter = 0
            else:
                patience_counter += 1
                if patience_counter >= patience:
                    if verbose:
                        print(f"Early stopping at epoch {epoch + 1}")
                    break
            
            if verbose and (epoch + 1) % 10 == 0:
                current_lr = self.scheduler.get_last_lr()[0]
                print(f"Epoch {epoch + 1}/{epochs} - "
                      f"Train Loss: {avg_train_loss:.6f}, Val Loss: {val_loss:.6f}, "
                      f"LR: {current_lr:.6f}")
        
        return history

    def predict(
        self,
        features: pd.DataFrame,
        seq_length: int = 50,
    ) -> np.ndarray:
        """Make predictions.

        Args:
            features: Feature DataFrame
            seq_length: Sequence length (must match training)

        Returns:
            Array of predictions
        """
        if self.model is None:
            raise ValueError("Model must be fitted before prediction")
        
        # Convert to numpy and normalize
        feature_array = features.values
        features_norm = (feature_array - self.feature_mean) / (self.feature_std + 1e-8)
        
        # Create sequences
        X_seq = []
        for i in range(len(features_norm) - seq_length + 1):
            X_seq.append(features_norm[i:i + seq_length])
        
        X_tensor = torch.FloatTensor(np.array(X_seq)).to(self.device)
        
        # Predict
        self.model.eval()
        with torch.no_grad():
            predictions = self.model(X_tensor).cpu().numpy().flatten()
        
        return predictions

    def save(self, path: str) -> None:
        """Save model to disk."""
        if self.model is None:
            raise ValueError("Model must be fitted before saving")
        
        save_dict = {
            'model_state': self.model.state_dict(),
            'input_size': self.input_size,
            'd_model': self.d_model,
            'nhead': self.nhead,
            'num_layers': self.num_layers,
            'dim_feedforward': self.dim_feedforward,
            'dropout': self.dropout,
            'learning_rate': self.learning_rate,
            'feature_mean': self.feature_mean,
            'feature_std': self.feature_std,
        }
        
        torch.save(save_dict, path)

    def load(self, path: str) -> None:
        """Load model from disk."""
        checkpoint = torch.load(path, map_location=self.device, weights_only=False)
        
        self.input_size = checkpoint['input_size']
        self.d_model = checkpoint['d_model']
        self.nhead = checkpoint['nhead']
        self.num_layers = checkpoint['num_layers']
        self.dim_feedforward = checkpoint['dim_feedforward']
        self.dropout = checkpoint['dropout']
        self.learning_rate = checkpoint['learning_rate']
        self.feature_mean = checkpoint['feature_mean']
        self.feature_std = checkpoint['feature_std']
        
        # Recreate model
        self.model = EnhancedTransformer(
            input_size=self.input_size,
            d_model=self.d_model,
            nhead=self.nhead,
            num_layers=self.num_layers,
            dim_feedforward=self.dim_feedforward,
            dropout=self.dropout,
        ).to(self.device)
        
        self.model.load_state_dict(checkpoint['model_state'])
        self.model.eval()

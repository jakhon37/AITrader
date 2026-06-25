"""LSTM-Transformer hybrid model for sequence modeling with attention.

Combines LSTM's ability to capture long-term dependencies with Transformer's
attention mechanism for modeling complex temporal patterns in financial data.
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
    """Positional encoding for transformer."""

    def __init__(self, d_model: int, max_len: int = 5000) -> None:
        """Initialize positional encoding.

        Args:
            d_model: Model dimension
            max_len: Maximum sequence length
        """
        super().__init__()
        
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model))
        
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        
        pe = pe.unsqueeze(0)
        self.register_buffer('pe', pe)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Add positional encoding to input.

        Args:
            x: Input tensor of shape (batch, seq_len, d_model)

        Returns:
            Tensor with positional encoding added
        """
        return x + self.pe[:, :x.size(1), :]


class LSTMTransformer(nn.Module):
    """LSTM-Transformer hybrid model.
    
    Architecture:
    1. LSTM processes sequence to capture temporal patterns
    2. Transformer encoder adds attention mechanism
    3. Dense layers output prediction
    """

    def __init__(
        self,
        input_size: int,
        hidden_size: int = 128,
        num_lstm_layers: int = 2,
        num_transformer_layers: int = 2,
        num_heads: int = 4,
        dropout: float = 0.2,
        output_size: int = 1,
    ) -> None:
        """Initialize LSTM-Transformer model.

        Args:
            input_size: Number of input features
            hidden_size: Hidden dimension size
            num_lstm_layers: Number of LSTM layers
            num_transformer_layers: Number of transformer layers
            num_heads: Number of attention heads
            dropout: Dropout rate
            output_size: Output dimension
        """
        super().__init__()
        
        self.input_size = input_size
        self.hidden_size = hidden_size
        self.num_lstm_layers = num_lstm_layers
        self.num_transformer_layers = num_transformer_layers
        self.num_heads = num_heads
        self.output_size = output_size
        
        # LSTM layers
        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_lstm_layers,
            batch_first=True,
            dropout=dropout if num_lstm_layers > 1 else 0,
        )
        
        # Positional encoding
        self.pos_encoder = PositionalEncoding(hidden_size)
        
        # Transformer encoder
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=hidden_size,
            nhead=num_heads,
            dim_feedforward=hidden_size * 4,
            dropout=dropout,
            batch_first=True,
        )
        self.transformer = nn.TransformerEncoder(
            encoder_layer,
            num_layers=num_transformer_layers,
        )
        
        # Output layers
        self.fc1 = nn.Linear(hidden_size, hidden_size // 2)
        self.relu = nn.ReLU()
        self.dropout = nn.Dropout(dropout)
        self.fc2 = nn.Linear(hidden_size // 2, output_size)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward pass.

        Args:
            x: Input tensor of shape (batch, seq_len, input_size)

        Returns:
            Output tensor of shape (batch, output_size)
        """
        # LSTM forward pass
        lstm_out, _ = self.lstm(x)
        
        # Add positional encoding
        lstm_out = self.pos_encoder(lstm_out)
        
        # Transformer forward pass
        transformer_out = self.transformer(lstm_out)
        
        # Take last time step
        last_out = transformer_out[:, -1, :]
        
        # Output layers
        out = self.fc1(last_out)
        out = self.relu(out)
        out = self.dropout(out)
        out = self.fc2(out)
        
        return out


class LSTMTransformerModel:
    """Wrapper for LSTM-Transformer model with training and prediction methods."""

    def __init__(
        self,
        input_size: Optional[int] = None,
        hidden_size: int = 128,
        num_lstm_layers: int = 2,
        num_transformer_layers: int = 2,
        num_heads: int = 4,
        dropout: float = 0.2,
        learning_rate: float = 0.001,
        device: Optional[str] = None,
    ) -> None:
        """Initialize model wrapper.

        Args:
            input_size: Number of input features (inferred from data if None)
            hidden_size: Hidden dimension size
            num_lstm_layers: Number of LSTM layers
            num_transformer_layers: Number of transformer layers
            num_heads: Number of attention heads
            dropout: Dropout rate
            learning_rate: Learning rate for optimizer
            device: Device to use ('cuda', 'cpu', or None for auto)
        """
        self.input_size = input_size
        self.hidden_size = hidden_size
        self.num_lstm_layers = num_lstm_layers
        self.num_transformer_layers = num_transformer_layers
        self.num_heads = num_heads
        self.dropout = dropout
        self.learning_rate = learning_rate
        
        # Set device
        if device is None:
            self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        else:
            self.device = torch.device(device)
        
        # Will be initialized in fit()
        self.model: Optional[LSTMTransformer] = None
        self.optimizer: Optional[torch.optim.Optimizer] = None
        self.criterion = nn.MSELoss()
        
        # Normalization parameters
        self.feature_mean: Optional[np.ndarray] = None
        self.feature_std: Optional[np.ndarray] = None

    def prepare_sequences(
        self,
        features: np.ndarray,
        targets: np.ndarray,
        seq_length: int = 20,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """Prepare sequences for training.

        Args:
            features: Feature array (n_samples, n_features)
            targets: Target array (n_samples,)
            seq_length: Sequence length

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
        batch_size: int = 32,
        seq_length: int = 20,
        validation_split: float = 0.2,
        verbose: bool = True,
    ) -> dict[str, list[float]]:
        """Train the model.

        Args:
            features: Feature DataFrame
            target: Target series (e.g., future returns)
            epochs: Number of training epochs
            batch_size: Batch size
            seq_length: Sequence length for LSTM
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
        self.model = LSTMTransformer(
            input_size=self.input_size,
            hidden_size=self.hidden_size,
            num_lstm_layers=self.num_lstm_layers,
            num_transformer_layers=self.num_transformer_layers,
            num_heads=self.num_heads,
            dropout=self.dropout,
        ).to(self.device)
        
        self.optimizer = torch.optim.Adam(self.model.parameters(), lr=self.learning_rate)
        
        # Training loop
        history = {'train_loss': [], 'val_loss': []}
        
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
            
            if verbose and (epoch + 1) % 10 == 0:
                print(f"Epoch {epoch + 1}/{epochs} - "
                      f"Train Loss: {avg_train_loss:.6f}, Val Loss: {val_loss:.6f}")
        
        return history

    def predict(
        self,
        features: pd.DataFrame,
        seq_length: int = 20,
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
        """Save model to disk.

        Args:
            path: Path to save model
        """
        if self.model is None:
            raise ValueError("Model must be fitted before saving")
        
        save_dict = {
            'model_state': self.model.state_dict(),
            'input_size': self.input_size,
            'hidden_size': self.hidden_size,
            'num_lstm_layers': self.num_lstm_layers,
            'num_transformer_layers': self.num_transformer_layers,
            'num_heads': self.num_heads,
            'dropout': self.dropout,
            'learning_rate': self.learning_rate,
            'feature_mean': self.feature_mean,
            'feature_std': self.feature_std,
        }
        
        torch.save(save_dict, path)

    def load(self, path: str) -> None:
        """Load model from disk.

        Args:
            path: Path to load model from
        """
        checkpoint = torch.load(path, map_location=self.device, weights_only=False)
        
        self.input_size = checkpoint['input_size']
        self.hidden_size = checkpoint['hidden_size']
        self.num_lstm_layers = checkpoint['num_lstm_layers']
        self.num_transformer_layers = checkpoint['num_transformer_layers']
        self.num_heads = checkpoint['num_heads']
        self.dropout = checkpoint['dropout']
        self.learning_rate = checkpoint['learning_rate']
        self.feature_mean = checkpoint['feature_mean']
        self.feature_std = checkpoint['feature_std']
        
        # Recreate model
        self.model = LSTMTransformer(
            input_size=self.input_size,
            hidden_size=self.hidden_size,
            num_lstm_layers=self.num_lstm_layers,
            num_transformer_layers=self.num_transformer_layers,
            num_heads=self.num_heads,
            dropout=self.dropout,
        ).to(self.device)
        
        self.model.load_state_dict(checkpoint['model_state'])
        self.model.eval()

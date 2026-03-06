"""GARCH-GRU hybrid model for volatility-aware time series forecasting.

Combines GARCH volatility modeling with GRU neural networks for return prediction.
The GARCH component captures volatility clustering while GRU handles sequential patterns.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from arch import arch_model


class GARCHGRU(nn.Module):
    """GARCH-GRU hybrid model.
    
    Architecture:
    1. GARCH(1,1) models volatility
    2. GRU processes returns + volatility forecasts
    3. Dense layer outputs prediction
    """

    def __init__(
        self,
        input_size: int = 2,  # returns + volatility
        hidden_size: int = 64,
        num_layers: int = 2,
        output_size: int = 1,
        dropout: float = 0.2,
    ) -> None:
        """Initialize GARCH-GRU model.

        Args:
            input_size: Number of input features
            hidden_size: GRU hidden units
            num_layers: Number of GRU layers
            output_size: Output dimension (1 for return prediction)
            dropout: Dropout rate
        """
        super().__init__()
        
        self.input_size = input_size
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        self.output_size = output_size
        
        # GRU layers
        self.gru = nn.GRU(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0,
        )
        
        # Output layer
        self.fc = nn.Linear(hidden_size, output_size)
        
        # GARCH model (fitted separately)
        self.garch_model: Optional[object] = None

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward pass.

        Args:
            x: Input tensor of shape (batch, seq_len, input_size)

        Returns:
            Output tensor of shape (batch, output_size)
        """
        # GRU forward pass
        gru_out, _ = self.gru(x)
        
        # Take last time step
        last_out = gru_out[:, -1, :]
        
        # Final prediction
        output = self.fc(last_out)
        
        return output


class GARCHGRUModel:
    """Wrapper for GARCH-GRU model with training and prediction methods."""

    def __init__(
        self,
        hidden_size: int = 64,
        num_layers: int = 2,
        dropout: float = 0.2,
        learning_rate: float = 0.001,
        device: Optional[str] = None,
    ) -> None:
        """Initialize model wrapper.

        Args:
            hidden_size: GRU hidden size
            num_layers: Number of GRU layers
            dropout: Dropout rate
            learning_rate: Learning rate for optimizer
            device: Device to use ('cuda', 'cpu', or None for auto)
        """
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        self.dropout = dropout
        self.learning_rate = learning_rate
        
        # Set device
        if device is None:
            self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        else:
            self.device = torch.device(device)
        
        # Will be initialized in fit()
        self.model: Optional[GARCHGRU] = None
        self.optimizer: Optional[torch.optim.Optimizer] = None
        self.criterion = nn.MSELoss()
        
        # Normalization parameters
        self.feature_mean: Optional[np.ndarray] = None
        self.feature_std: Optional[np.ndarray] = None

    def fit_garch(self, returns: pd.Series) -> np.ndarray:
        """Fit GARCH model and get volatility forecasts.

        Args:
            returns: Return series

        Returns:
            Array of volatility forecasts
        """
        # Fit GARCH(1,1) model
        garch = arch_model(returns * 100, vol='Garch', p=1, q=1, rescale=False)
        garch_fit = garch.fit(disp='off')
        
        # Get conditional volatility
        volatility = garch_fit.conditional_volatility / 100
        
        return volatility.values

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
        returns: pd.Series,
        epochs: int = 100,
        batch_size: int = 32,
        seq_length: int = 20,
        validation_split: float = 0.2,
        verbose: bool = True,
    ) -> dict[str, list[float]]:
        """Train the model.

        Args:
            returns: Return series to train on
            epochs: Number of training epochs
            batch_size: Batch size
            seq_length: Sequence length for GRU
            validation_split: Fraction for validation
            verbose: Print training progress

        Returns:
            Dictionary with training history
        """
        # Fit GARCH and get volatility
        volatility = self.fit_garch(returns)
        
        # Prepare features
        features = np.column_stack([returns.values, volatility])
        targets = returns.values
        
        # Normalize
        self.feature_mean = features.mean(axis=0)
        self.feature_std = features.std(axis=0)
        features_norm = (features - self.feature_mean) / (self.feature_std + 1e-8)
        
        # Create sequences
        X, y = self.prepare_sequences(features_norm, targets, seq_length)
        
        # Train/validation split
        n_train = int(len(X) * (1 - validation_split))
        X_train, X_val = X[:n_train], X[n_train:]
        y_train, y_val = y[:n_train], y[n_train:]
        
        # Initialize model
        self.model = GARCHGRU(
            input_size=features.shape[1],
            hidden_size=self.hidden_size,
            num_layers=self.num_layers,
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
        returns: pd.Series,
        seq_length: int = 20,
    ) -> np.ndarray:
        """Make predictions.

        Args:
            returns: Return series
            seq_length: Sequence length (must match training)

        Returns:
            Array of predictions
        """
        if self.model is None:
            raise ValueError("Model must be fitted before prediction")
        
        # Fit GARCH and get volatility
        volatility = self.fit_garch(returns)
        
        # Prepare features
        features = np.column_stack([returns.values, volatility])
        features_norm = (features - self.feature_mean) / (self.feature_std + 1e-8)
        
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
            'hidden_size': self.hidden_size,
            'num_layers': self.num_layers,
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
        
        self.hidden_size = checkpoint['hidden_size']
        self.num_layers = checkpoint['num_layers']
        self.dropout = checkpoint['dropout']
        self.learning_rate = checkpoint['learning_rate']
        self.feature_mean = checkpoint['feature_mean']
        self.feature_std = checkpoint['feature_std']
        
        # Recreate model
        input_size = 2  # returns + volatility
        self.model = GARCHGRU(
            input_size=input_size,
            hidden_size=self.hidden_size,
            num_layers=self.num_layers,
            dropout=self.dropout,
        ).to(self.device)
        
        self.model.load_state_dict(checkpoint['model_state'])
        self.model.eval()

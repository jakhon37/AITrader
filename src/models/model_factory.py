"""Model factory for creating and managing different model types.

Provides a unified interface for creating, training, and using
different model architectures (neural networks, gradient boosting, etc.)
"""

from __future__ import annotations

from typing import Any, Optional

# Import existing models
from models.garch_gru import GARCHGRUModel
from models.lstm_transformer import LSTMTransformerModel

# Import new models
try:
    from models.lightgbm_model import LightGBMModel
    LIGHTGBM_AVAILABLE = True
except ImportError:
    LIGHTGBM_AVAILABLE = False

try:
    from models.xgboost_model import XGBoostModel
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False

try:
    from models.enhanced_transformer import EnhancedTransformerModel
    ENHANCED_TRANSFORMER_AVAILABLE = True
except ImportError:
    ENHANCED_TRANSFORMER_AVAILABLE = False


# Model registry mapping
MODEL_REGISTRY = {
    # Neural Network Models
    'garch_gru': GARCHGRUModel,
    'lstm_transformer': LSTMTransformerModel,
    'enhanced_transformer': EnhancedTransformerModel if ENHANCED_TRANSFORMER_AVAILABLE else None,
    
    # Tree-based Models
    'lightgbm': LightGBMModel if LIGHTGBM_AVAILABLE else None,
    'lgb': LightGBMModel if LIGHTGBM_AVAILABLE else None,  # Alias
    'xgboost': XGBoostModel if XGBOOST_AVAILABLE else None,
    'xgb': XGBoostModel if XGBOOST_AVAILABLE else None,  # Alias
}

# Model categories for different use cases
MODEL_CATEGORIES = {
    'neural': ['garch_gru', 'lstm_transformer', 'enhanced_transformer'],
    'tree': ['lightgbm', 'xgboost'],
    'sequence': ['garch_gru', 'lstm_transformer', 'enhanced_transformer'],  # Need sequences
    'tabular': ['lightgbm', 'xgboost'],  # Direct feature input
    'fast': ['lightgbm', 'xgboost'],  # Quick training
    'accurate': ['enhanced_transformer', 'xgboost', 'lightgbm'],  # Best performance
}


def get_available_models() -> list[str]:
    """Get list of available model types.
    
    Returns:
        List of model type names that can be instantiated
    """
    return [name for name, model_class in MODEL_REGISTRY.items() if model_class is not None]


def get_model_info(model_type: str) -> dict[str, Any]:
    """Get information about a model type.
    
    Args:
        model_type: Model type name
        
    Returns:
        Dictionary with model information
    """
    model_class = MODEL_REGISTRY.get(model_type)
    
    if model_class is None:
        return {
            'available': False,
            'reason': f'Model {model_type} not found or dependencies not installed'
        }
    
    info = {
        'available': True,
        'class': model_class.__name__,
        'type': 'neural' if model_type in MODEL_CATEGORIES['neural'] else 'tree',
        'needs_sequences': model_type in MODEL_CATEGORIES['sequence'],
        'gpu_accelerated': model_type not in MODEL_CATEGORIES['tabular'],
    }
    
    # Add model-specific info
    if model_type in ['lightgbm', 'xgboost']:
        info['training_speed'] = 'fast'
        info['feature_importance'] = True
        info['handles_missing'] = True
    elif model_type in ['garch_gru', 'lstm_transformer']:
        info['training_speed'] = 'medium'
        info['feature_importance'] = False
    elif model_type == 'enhanced_transformer':
        info['training_speed'] = 'slow'
        info['capacity'] = 'high'
        info['sequence_length'] = 'long (50-100)'
    
    return info


def create_model(
    model_type: str,
    device: Optional[str] = None,
    **kwargs
) -> Any:
    """Create a model instance.
    
    Args:
        model_type: Type of model to create
        device: Device to use ('cpu', 'cuda', or None for auto)
        **kwargs: Additional model-specific parameters
        
    Returns:
        Model instance
        
    Raises:
        ValueError: If model type is not available
        
    Example:
        >>> model = create_model('lightgbm', n_estimators=500)
        >>> model = create_model('lstm_transformer', hidden_size=128, device='cuda')
        >>> 
        >>> # From config
        >>> from config import load_config
        >>> cfg = load_config()
        >>> model = create_model_from_config(cfg)
    """
    model_class = MODEL_REGISTRY.get(model_type)
    
    if model_class is None:
        available = get_available_models()
        raise ValueError(
            f"Model type '{model_type}' not available. "
            f"Available models: {', '.join(available)}"
        )
    
    # Add device parameter for models that support it
    if device is not None and model_type not in ['lightgbm', 'xgboost']:
        kwargs['device'] = device
    elif device is not None:
        kwargs['device'] = device
    
    return model_class(**kwargs)


def create_model_from_config(config: Any, model_type: Optional[str] = None) -> Any:
    """Create a model instance from AppConfig.
    
    Args:
        config: AppConfig instance (from load_config())
        model_type: Override model type (uses config.model.model_type if None)
        
    Returns:
        Model instance configured with parameters from config
        
    Example:
        >>> from config import load_config
        >>> cfg = load_config('config/dev.yaml')
        >>> model = create_model_from_config(cfg)
        >>> 
        >>> # Override model type
        >>> model = create_model_from_config(cfg, model_type='lightgbm')
    """
    model_cfg = config.model
    model_type = model_type or model_cfg.model_type
    
    # Detect device
    try:
        import torch
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
    except ImportError:
        device = 'cpu'
    
    # Build kwargs based on model type
    if model_type in ['lightgbm', 'lgb']:
        kwargs = {
            'n_estimators': model_cfg.n_estimators,
            'learning_rate': model_cfg.tree_learning_rate,
            'max_depth': model_cfg.max_depth,
            'subsample': model_cfg.subsample,
            'colsample_bytree': model_cfg.colsample_bytree,
            'reg_alpha': model_cfg.reg_alpha,
            'reg_lambda': model_cfg.reg_lambda,
            'device': device,
        }
    
    elif model_type in ['xgboost', 'xgb']:
        kwargs = {
            'n_estimators': model_cfg.n_estimators,
            'learning_rate': model_cfg.tree_learning_rate,
            'max_depth': model_cfg.max_depth,
            'subsample': model_cfg.subsample,
            'colsample_bytree': model_cfg.colsample_bytree,
            'reg_alpha': model_cfg.reg_alpha,
            'reg_lambda': model_cfg.reg_lambda,
            'device': device,
        }
    
    elif model_type == 'enhanced_transformer':
        kwargs = {
            'd_model': model_cfg.d_model,
            'nhead': model_cfg.nhead,
            'num_layers': model_cfg.num_transformer_layers,
            'dim_feedforward': model_cfg.dim_feedforward,
            'dropout': model_cfg.dropout,
            'learning_rate': model_cfg.learning_rate,
            'device': device,
        }
    
    elif model_type == 'lstm_transformer':
        kwargs = {
            'hidden_size': model_cfg.hidden_size,
            'num_lstm_layers': model_cfg.num_layers,
            'num_transformer_layers': 2,  # Fixed for this model
            'dropout': model_cfg.dropout,
            'learning_rate': model_cfg.learning_rate,
            'device': device,
        }
    
    elif model_type == 'garch_gru':
        kwargs = {
            'hidden_size': model_cfg.hidden_size,
            'num_layers': model_cfg.num_layers,
            'learning_rate': model_cfg.learning_rate,
            'device': device,
        }
    
    else:
        # Unknown model, use minimal kwargs
        kwargs = {'device': device}
    
    return create_model(model_type, **kwargs)


def get_recommended_hyperparameters(
    model_type: str,
    use_case: str = 'general',
    gpu_available: bool = False,
) -> dict[str, Any]:
    """Get recommended hyperparameters for a model type.
    
    Args:
        model_type: Model type name
        use_case: 'general', 'fast', 'accurate', 'production'
        gpu_available: Whether GPU is available
        
    Returns:
        Dictionary of recommended hyperparameters
    """
    if model_type == 'lightgbm':
        base = {
            'n_estimators': 500,
            'learning_rate': 0.01,
            'max_depth': 7,
            'num_leaves': 127,
            'min_child_samples': 20,
            'subsample': 0.8,
            'colsample_bytree': 0.8,
            'reg_alpha': 0.1,
            'reg_lambda': 0.1,
        }
        if use_case == 'fast':
            base.update({'n_estimators': 200, 'learning_rate': 0.05})
        elif use_case == 'accurate':
            base.update({'n_estimators': 1000, 'learning_rate': 0.005, 'num_leaves': 255})
        return base
    
    elif model_type == 'xgboost':
        base = {
            'n_estimators': 500,
            'learning_rate': 0.01,
            'max_depth': 7,
            'min_child_weight': 1,
            'subsample': 0.8,
            'colsample_bytree': 0.8,
            'reg_alpha': 0.1,
            'reg_lambda': 1.0,
        }
        if use_case == 'fast':
            base.update({'n_estimators': 200, 'learning_rate': 0.05})
        elif use_case == 'accurate':
            base.update({'n_estimators': 1000, 'learning_rate': 0.005, 'max_depth': 9})
        if gpu_available:
            base['tree_method'] = 'gpu_hist'
        return base
    
    elif model_type == 'lstm_transformer':
        base = {
            'hidden_size': 128,
            'num_lstm_layers': 2,
            'num_transformer_layers': 2,
            'num_heads': 4,
            'dropout': 0.2,
            'learning_rate': 0.001,
        }
        if use_case == 'accurate':
            base.update({'hidden_size': 256, 'num_lstm_layers': 3, 'num_transformer_layers': 3})
        elif use_case == 'fast':
            base.update({'hidden_size': 64, 'num_lstm_layers': 1, 'num_transformer_layers': 1})
        return base
    
    elif model_type == 'enhanced_transformer':
        base = {
            'd_model': 256,
            'nhead': 8,
            'num_layers': 4,
            'dim_feedforward': 1024,
            'dropout': 0.2,
            'learning_rate': 0.0001,
        }
        if use_case == 'accurate':
            base.update({'d_model': 512, 'num_layers': 6, 'dim_feedforward': 2048})
        elif use_case == 'fast':
            base.update({'d_model': 128, 'num_layers': 2, 'dim_feedforward': 512})
        return base
    
    elif model_type == 'garch_gru':
        base = {
            'hidden_size': 64,
            'num_layers': 2,
            'learning_rate': 0.001,
        }
        if use_case == 'accurate':
            base.update({'hidden_size': 128, 'num_layers': 3})
        return base
    
    return {}


def print_model_comparison() -> None:
    """Print a comparison table of available models."""
    print("\n" + "="*80)
    print("AVAILABLE MODELS COMPARISON")
    print("="*80)
    
    models = get_available_models()
    
    print(f"\n{'Model Type':<25} {'Speed':<12} {'GPU':<8} {'Sequences':<12} {'Best For'}")
    print("-"*80)
    
    model_descriptions = {
        'lightgbm': ('Fast', 'Optional', 'No', 'Tabular data, feature importance'),
        'xgboost': ('Fast', 'Yes', 'No', 'Kaggle-style problems, robust'),
        'garch_gru': ('Medium', 'Yes', 'Yes', 'Volatility modeling'),
        'lstm_transformer': ('Medium', 'Yes', 'Yes', 'Balanced neural approach'),
        'enhanced_transformer': ('Slow', 'Yes', 'Yes', 'Maximum accuracy, long sequences'),
    }
    
    for model in sorted(set(models)):  # Remove duplicates
        if model in ['lgb', 'xgb']:  # Skip aliases
            continue
        desc = model_descriptions.get(model, ('?', '?', '?', '?'))
        print(f"{model:<25} {desc[0]:<12} {desc[1]:<8} {desc[2]:<12} {desc[3]}")
    
    print("\n" + "="*80)
    print("RECOMMENDATIONS:")
    print("  • Quick win: lightgbm or xgboost (fastest training, good accuracy)")
    print("  • Best accuracy: enhanced_transformer (slowest, highest capacity)")
    print("  • Balanced: lstm_transformer (current default)")
    print("  • Ensemble: Use multiple models and average predictions")
    print("="*80 + "\n")


# Convenience functions
def create_lightgbm(**kwargs) -> Any:
    """Create LightGBM model with defaults."""
    return create_model('lightgbm', **kwargs)


def create_xgboost(**kwargs) -> Any:
    """Create XGBoost model with defaults."""
    return create_model('xgboost', **kwargs)


def create_enhanced_transformer(**kwargs) -> Any:
    """Create Enhanced Transformer model with defaults."""
    return create_model('enhanced_transformer', **kwargs)


if __name__ == '__main__':
    # Print comparison when run directly
    print_model_comparison()

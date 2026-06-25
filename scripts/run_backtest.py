"""Run backtest on trained models."""

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from backtest.engine import BacktestConfig, BacktestEngine
from backtest.metrics import calculate_metrics, print_metrics
from data.loaders.csv_loader import load_ohlcv_csv
from trainer.feature_engine import FeatureEngine
from trainer.models.model_registry import ModelRegistry
from trainer.models.garch_gru import GARCHGRUModel
from trainer.models.lstm_transformer import LSTMTransformerModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(message)s")
logger = logging.getLogger(__name__)


def load_model(model_type: str, model_version: str, registry: ModelRegistry):
    """Load model from registry with GPU auto-detection."""
    import torch
    
    # Auto-detect device
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    device_str = str(device)
    
    if torch.cuda.is_available():
        logger.info(f"🎮 Using GPU: {torch.cuda.get_device_name(0)}")
    else:
        logger.info("💻 Using CPU")
    
    metadata = registry.get_metadata(model_type, model_version)
    model_path = registry.get_model_path(model_type, model_version)

    if model_type == "garch_gru":
        model = GARCHGRUModel(device=device_str)
        model.load(model_path)
    elif model_type == "lstm_transformer":
        model = LSTMTransformerModel(device=device_str)
        model.load(model_path)
    else:
        raise ValueError(f"Unknown model: {model_type}")

    logger.info(f"Loaded {model_type}:{model_version}")
    return model


def run_backtest(symbol, model_type, model_version, data_dir="data/raw", 
                 registry_path="models/registry", backtest_config=None, timeframe="1d"):
    """Run backtest."""
    logger.info(f"Backtest: {symbol} with {model_type}:{model_version} on {timeframe} data")

    # Load data (support both daily and intraday)
    data_path = Path(data_dir) / f"{symbol}_{timeframe}.csv"
    if not data_path.exists():
        data_path = Path(data_dir) / f"{symbol}_daily.csv"  # Fallback
    data = load_ohlcv_csv(data_path)
    logger.info(f"Loaded {len(data)} bars from {data_path.name}")

    # Features
    feature_engine = FeatureEngine()
    features = feature_engine.compute_features(data)
    features = features.dropna()  # Remove NaN rows
    logger.info(f"Computed {len(features.columns)} features, {len(features)} valid rows")

    # Load model
    registry = ModelRegistry(base_path=registry_path)
    model = load_model(model_type, model_version, registry)

    # Predictions
    predictions = model.predict(features)
    
    # Models may return fewer predictions due to lookback windows
    # Align index properly
    if len(predictions) != len(features):
        # Take the last N predictions
        predictions = pd.Series(predictions, index=features.index[-len(predictions):])
    elif not isinstance(predictions, pd.Series):
        predictions = pd.Series(predictions, index=features.index)
    
    signals = pd.Series(0, index=predictions.index)
    signals[predictions > 0] = 1
    signals[predictions < 0] = -1

    logger.info(f"Signals: Long={(signals==1).sum()}, Short={(signals==-1).sum()}")

    # Align data with signals
    data = data.loc[signals.index]

    # Backtest
    config = backtest_config or BacktestConfig()
    engine = BacktestEngine(config)
    result = engine.run(data, signals)
    metrics = calculate_metrics(result)

    print(f"\n{'='*70}")
    print(f"BACKTEST: {model_type}:{model_version} on {symbol.upper()}")
    print('='*70)
    print_metrics(metrics)

    return result, metrics


def main():
    # Load universal config for defaults
    from core.config import load_config
    try:
        cfg = load_config()
        default_symbol = cfg.get_primary_symbol()
        default_timeframe = cfg.data.timeframe
        default_model = cfg.model.model_type
    except Exception:
        # Fallback if config fails
        default_symbol = "eurusd"
        default_timeframe = "1d"
        default_model = "lstm_transformer"
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default=default_symbol,
                       help=f"Symbol to backtest (default: {default_symbol} from config)")
    parser.add_argument("--model", default=default_model, 
                        choices=["garch_gru", "lstm_transformer"],
                        help=f"Model type (default: {default_model} from config)")
    parser.add_argument("--model-version")
    parser.add_argument("--timeframe", "-t", default=default_timeframe,
                       choices=["1m", "5m", "15m", "30m", "1h", "1d"],
                       help=f"Data timeframe (default: {default_timeframe} from config)")
    parser.add_argument("--all-models", action="store_true")
    parser.add_argument("--initial-capital", type=float, default=10000.0)
    parser.add_argument("--commission", type=float, default=0.001)
    parser.add_argument("--slippage", type=float, default=0.0005)
    args = parser.parse_args()

    config = BacktestConfig(
        initial_capital=args.initial_capital,
        commission_pct=args.commission,
        slippage_pct=args.slippage,
    )

    registry = ModelRegistry(base_path="models/registry")

    if args.all_models:
        models_to_run = []
        for model_type in ["garch_gru", "lstm_transformer"]:
            if model_type in registry.index["models"]:
                for version in registry.index["models"][model_type]:
                    models_to_run.append((model_type, version))
    else:
        version = args.model_version
        if not version:
            # Get latest
            if args.model in registry.index["models"]:
                versions = registry.index["models"][args.model]
                if versions:
                    version = versions[-1]
                else:
                    logger.error(f"No versions for {args.model}")
                    return 1
            else:
                logger.error(f"{args.model} not found")
                return 1
        models_to_run = [(args.model, version)]

    results = []
    for model_type, version in models_to_run:
        try:
            _, metrics = run_backtest(args.symbol, model_type, version, 
                                       backtest_config=config, timeframe=args.timeframe)
            results.append({
                "model": f"{model_type}:{version}",
                "sharpe": metrics.sharpe_ratio,
                "return": metrics.total_return,
                "max_dd": metrics.max_drawdown,
                "win_rate": metrics.win_rate,
            })
        except Exception as e:
            logger.error(f"Failed {model_type}:{version}: {e}")

    if len(results) > 1:
        print(f"\n{'='*70}")
        print("SUMMARY")
        print('='*70)
        print(pd.DataFrame(results).to_string(index=False))
        print('='*70 + '\n')

    return 0


if __name__ == "__main__":
    sys.exit(main())

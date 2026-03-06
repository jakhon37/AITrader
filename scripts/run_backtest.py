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
from features.feature_engine import FeatureEngine
from models.model_registry import ModelRegistry
from models.garch_gru import GARCHGRUModel
from models.lstm_transformer import LSTMTransformerModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(message)s")
logger = logging.getLogger(__name__)


def load_model(model_type: str, model_version: str, registry: ModelRegistry):
    """Load model from registry."""
    metadata = registry.get_metadata(model_type, model_version)
    model_path = registry.get_model_path(model_type, model_version)

    if model_type == "garch_gru":
        model = GARCHGRUModel()
        model.load(model_path)
    elif model_type == "lstm_transformer":
        model = LSTMTransformerModel()
        model.load(model_path)
    else:
        raise ValueError(f"Unknown model: {model_type}")

    logger.info(f"Loaded {model_type}:{model_version}")
    return model


def run_backtest(symbol, model_type, model_version, data_dir="data/raw", 
                 registry_path="models/registry", backtest_config=None):
    """Run backtest."""
    logger.info(f"Backtest: {symbol} with {model_type}:{model_version}")

    # Load data
    data_path = Path(data_dir) / f"{symbol}_daily.csv"
    data = load_ohlcv_csv(data_path)
    logger.info(f"Loaded {len(data)} bars")

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
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="eurusd")
    parser.add_argument("--model", default="lstm_transformer", 
                        choices=["garch_gru", "lstm_transformer"])
    parser.add_argument("--model-version")
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
                                       backtest_config=config)
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

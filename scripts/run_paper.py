"""Paper trading script.

Runs paper trading loop:
1. Fetch latest data
2. Generate signals from models
3. Execute via sim broker
4. Log results
"""

import argparse
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from data.loaders.csv_loader import load_ohlcv_csv
from execution.brokers.sim import SimBroker, OrderSide, OrderType
from execution.engine import ExecutionEngine, ExecutionConfig
from features.feature_engine import FeatureEngine
from models.model_registry import ModelRegistry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class PaperTrader:
    """Paper trading orchestrator."""

    def __init__(
        self,
        initial_capital: float = 100000,
        model_name: str = "lstm_transformer",
        symbols: list = None,
    ):
        """Initialize paper trader."""
        self.initial_capital = initial_capital
        self.model_name = model_name
        self.symbols = symbols or ["eurusd"]

        # Initialize components
        logger.info("Initializing paper trader...")

        # Broker
        self.broker = SimBroker(initial_cash=initial_capital)

        # Execution engine (using sim broker state)
        config = ExecutionConfig(
            initial_capital=initial_capital,
            dry_run=False,
            enable_audit_log=True,
        )
        self.engine = ExecutionEngine(config)

        # Feature engine
        self.feature_engine = FeatureEngine()

        # Model registry
        self.registry = ModelRegistry()

        # Load model
        self.model = self._load_model()

        logger.info(f"✅ Paper trader initialized: ${initial_capital:,.0f}")

    def _load_model(self):
        """Load the best model from registry."""
        try:
            # Find latest model file
            model_dir = Path("models/registry/models") / self.model_name
            if not model_dir.exists():
                logger.error(f"Model directory not found: {model_dir}")
                return None

            model_files = sorted(model_dir.glob("*.pt"))
            if not model_files:
                logger.error(f"No model files found in {model_dir}")
                return None

            model_path = model_files[-1]  # Use latest

            # Load model
            from models.lstm_transformer import LSTMTransformer

            model = LSTMTransformer()
            model.load(str(model_path))

            logger.info(f"✅ Loaded model: {model_path.name}")
            return model

        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            import traceback
            traceback.print_exc()
            return None

    def fetch_data(self, symbol: str, lookback_days: int = 90) -> pd.DataFrame:
        """Fetch latest data for a symbol."""
        try:
            df = load_ohlcv_csv(f"data/raw/{symbol}_daily.csv")

            # Take last N days
            df = df.tail(lookback_days).copy()

            logger.info(f"✅ Fetched {len(df)} days of {symbol} data")
            return df

        except Exception as e:
            logger.error(f"Failed to fetch data for {symbol}: {e}")
            return pd.DataFrame()

    def generate_signal(self, symbol: str, data: pd.DataFrame) -> tuple:
        """Generate trading signal.

        Returns:
            (signal, confidence, features) where signal is 1 (buy), -1 (sell), or 0 (hold)
        """
        if self.model is None:
            return 0, 0.0, None

        try:
            # Compute features
            features = self.feature_engine.compute_features(data, {})

            if len(features) == 0:
                logger.warning(f"No features computed for {symbol}")
                return 0, 0.0, None

            # Get latest features
            latest_features = features.iloc[-1:].copy()

            # Predict
            predictions = self.model.predict(latest_features)

            if len(predictions) == 0:
                logger.warning(f"No prediction for {symbol}")
                return 0, 0.0, latest_features

            # Convert to signal
            signal = predictions.iloc[-1]  # -1, 0, or 1
            confidence = abs(signal)  # Simple confidence

            logger.info(
                f"✅ Signal for {symbol}: {signal} (confidence={confidence:.2f})"
            )
            return int(signal), float(confidence), latest_features

        except Exception as e:
            logger.error(f"Failed to generate signal for {symbol}: {e}")
            return 0, 0.0, None

    def execute_signal(self, symbol: str, signal: int, data: pd.DataFrame) -> None:
        """Execute trading signal."""
        if signal == 0:
            logger.info(f"No action for {symbol}")
            return

        # Get current price
        current_price = data["close"].iloc[-1]

        # Update broker prices
        self.broker.update_price(symbol.upper(), current_price)

        # Determine position size (simple: $10k per trade)
        position_size = 10000 / current_price

        # Execute via engine
        result = self.engine.execute_signal(
            symbol.upper(), signal, current_price, position_size
        )

        # Also execute in broker for tracking
        if result == "opened":
            side = OrderSide.BUY if signal == 1 else OrderSide.SELL
            order = self.broker.submit_order(
                symbol.upper(), side, position_size, OrderType.MARKET
            )
            logger.info(f"✅ Executed: {order.status.value}")

        elif result == "closed":
            order = self.broker.close_position(symbol.upper())
            if order:
                logger.info(f"✅ Closed: {order.status.value}")

    def run_iteration(self) -> None:
        """Run one paper trading iteration."""
        logger.info("=" * 60)
        logger.info(f"Paper Trading Iteration: {datetime.now()}")
        logger.info("=" * 60)

        for symbol in self.symbols:
            logger.info(f"\n--- Processing {symbol.upper()} ---")

            # Fetch data
            data = self.fetch_data(symbol)
            if data.empty:
                continue

            # Generate signal
            signal, confidence, features = self.generate_signal(symbol, data)

            # Execute signal
            self.execute_signal(symbol, signal, data)

        # Print stats
        logger.info("\n" + "=" * 60)
        logger.info("Broker Stats")
        logger.info("=" * 60)

        stats = self.broker.get_stats()
        for key, value in stats.items():
            if isinstance(value, float):
                logger.info(f"{key}: ${value:,.2f}" if "pnl" in key or "value" in key or "cash" in key else f"{key}: {value:.2%}" if "rate" in key else f"{key}: {value:.4f}")
            else:
                logger.info(f"{key}: {value}")

        engine_status = self.engine.get_status()
        logger.info(f"\nEngine: running={engine_status['is_running']}, halted={engine_status['is_halted']}")

    def run(self, iterations: int = None, interval_seconds: int = 3600) -> None:
        """Run paper trading loop.

        Args:
            iterations: Number of iterations (None = infinite)
            interval_seconds: Seconds between iterations (default: 1 hour)
        """
        logger.info(f"🚀 Starting paper trading: {iterations or 'infinite'} iterations")

        self.engine.start()

        try:
            iteration = 0
            while iterations is None or iteration < iterations:
                self.run_iteration()

                iteration += 1

                if iterations is None or iteration < iterations:
                    logger.info(f"\n💤 Sleeping for {interval_seconds}s...")
                    time.sleep(interval_seconds)

        except KeyboardInterrupt:
            logger.info("\n⚠️ Interrupted by user")

        finally:
            self.engine.stop()
            logger.info("✅ Paper trading stopped")

            # Final stats
            final_stats = self.broker.get_stats()
            logger.info(f"\n📊 Final Stats:")
            logger.info(f"  Portfolio Value: ${final_stats['portfolio_value']:,.2f}")
            logger.info(f"  Total PnL: ${final_stats['total_pnl']:,.2f}")
            logger.info(f"  Return: {(final_stats['total_pnl'] / self.initial_capital) * 100:.2f}%")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Run paper trading")
    parser.add_argument(
        "--capital", type=float, default=100000, help="Initial capital (default: $100k)"
    )
    parser.add_argument(
        "--model",
        type=str,
        default="lstm_transformer",
        help="Model to use (default: lstm_transformer)",
    )
    parser.add_argument(
        "--symbols",
        type=str,
        nargs="+",
        default=["eurusd"],
        help="Symbols to trade (default: eurusd)",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=None,
        help="Number of iterations (default: infinite)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=3600,
        help="Seconds between iterations (default: 3600 = 1 hour)",
    )

    args = parser.parse_args()

    # Create trader
    trader = PaperTrader(
        initial_capital=args.capital, model_name=args.model, symbols=args.symbols
    )

    # Run
    trader.run(iterations=args.iterations, interval_seconds=args.interval)


if __name__ == "__main__":
    main()

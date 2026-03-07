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

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from data.loaders.csv_loader import load_ohlcv_csv
from data.loaders.live_data import LiveDataFetcher
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
        use_live_data: bool = True,
        timeframe: str = "1d",
    ):
        """Initialize paper trader.
        
        Args:
            initial_capital: Starting capital
            model_name: Name of model to use
            symbols: List of symbols to trade
            use_live_data: Whether to use live data
            timeframe: Timeframe for data (1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w, 1mo)
        """
        self.initial_capital = initial_capital
        self.model_name = model_name
        self.symbols = symbols or ["eurusd"]
        self.use_live_data = use_live_data
        self.timeframe = timeframe

        # Initialize components
        logger.info("Initializing paper trader...")
        
        # Detect GPU availability
        import torch
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        if torch.cuda.is_available():
            logger.info(f"🎮 GPU detected: {torch.cuda.get_device_name(0)}")
        else:
            logger.info("💻 Using CPU (no GPU detected)")

        # Live data fetcher
        if use_live_data:
            self.live_fetcher = LiveDataFetcher(source="yfinance", timeframe=timeframe)
            logger.info(f"✅ Using LIVE market data (timeframe: {timeframe})")
        else:
            self.live_fetcher = None
            logger.info("ℹ️  Using historical CSV data")

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
        """Load the best model from registry with GPU support."""
        try:
            # Determine which symbol to match (use first symbol if multiple)
            target_symbol = self.symbols[0] if self.symbols else "eurusd"
            
            # Try registry first
            model_dir = Path("models/registry/models") / self.model_name
            model_files = []
            
            if model_dir.exists():
                model_files = sorted(model_dir.glob("*.pt"))
                logger.info(f"Found {len(model_files)} models in registry: {model_dir}")
            
            # If no models in registry, or to include newer models, also check temp/
            temp_dir = Path("models/temp")
            if temp_dir.exists():
                # Look for models matching the model_name pattern (including timeframe variants like _1m_)
                temp_files = sorted(temp_dir.glob(f"{self.model_name}*.pt"))
                if temp_files:
                    logger.info(f"Found {len(temp_files)} models in temp: {temp_dir}")
                    model_files.extend(temp_files)
            
            # Sort all files by name (timestamp) and use latest
            if not model_files:
                logger.error(f"No model files found for {self.model_name} in registry or temp")
                return None

            # Filter by symbol and timeframe match if available
            symbol_matches = [f for f in model_files if f"_{target_symbol}_" in f.name]
            timeframe_matches = [f for f in model_files if f"_{self.timeframe}_" in f.name]
            
            # Priority: symbol + timeframe match > symbol match > timeframe match > any model
            if symbol_matches and timeframe_matches:
                candidates = [f for f in symbol_matches if f in timeframe_matches]
                if candidates:
                    model_files = candidates
                    logger.info(f"✅ Found {len(candidates)} models matching {target_symbol} + {self.timeframe}")
            elif symbol_matches:
                model_files = symbol_matches
                logger.info(f"✅ Found {len(symbol_matches)} models matching {target_symbol}")
            elif timeframe_matches:
                model_files = timeframe_matches
                logger.info(f"✅ Found {len(timeframe_matches)} models matching {self.timeframe}")
            else:
                logger.warning(f"⚠️ No exact match for {target_symbol}/{self.timeframe}, using any {self.model_name} model")

            model_files = sorted(model_files)  # Re-sort all together
            model_path = model_files[-1]  # Use latest

            # Load model with auto-detected device
            if "garch" in self.model_name.lower():
                from models.garch_gru import GARCHGRUModel
                model = GARCHGRUModel(device=str(self.device))
                model.load(str(model_path))
            else:
                from models.lstm_transformer import LSTMTransformerModel
                model = LSTMTransformerModel(device=str(self.device))
                model.load(str(model_path))

            logger.info(f"✅ Loaded model: {model_path.name} on {self.device}")
            return model

        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            import traceback
            traceback.print_exc()
            return None

    def fetch_data(self, symbol: str, lookback_days: int = 90) -> pd.DataFrame:
        """Fetch latest data for a symbol."""
        try:
            # Use live data if enabled
            if self.use_live_data and self.live_fetcher:
                df = self.live_fetcher.fetch_latest(symbol, lookback_days)
                
                if not df.empty:
                    # Ensure datetime index for feature computation
                    if 'timestamp' in df.columns:
                        df = df.set_index('timestamp')
                    elif not isinstance(df.index, pd.DatetimeIndex):
                        # Try to convert index to datetime if it's not already
                        try:
                            df.index = pd.to_datetime(df.index)
                        except:
                            logger.warning(f"Could not convert index to DatetimeIndex for {symbol}")
                    
                    unit = "bars" if self.timeframe != "1d" else "days"
                    logger.info(f"✅ Fetched {len(df)} {unit} of LIVE data for {symbol}")
                    return df
                else:
                    logger.warning(f"No live data for {symbol}, falling back to CSV")
            
            # Fallback to CSV (support both daily and intraday)
            csv_filename = f"data/raw/{symbol}_{self.timeframe}.csv"
            if not Path(csv_filename).exists():
                csv_filename = f"data/raw/{symbol}_daily.csv"  # Fallback to daily
            df = load_ohlcv_csv(csv_filename)

            # Take last N days
            df = df.tail(lookback_days).copy()

            unit = "bars" if self.timeframe != "1d" else "days"
            logger.info(f"✅ Fetched {len(df)} {unit} of CSV data for {symbol}")
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

            # Model needs enough data for sequences (typically 20+ rows)
            # Pass ALL features to the model, it will return prediction for the latest point
            predictions = self.model.predict(features)

            if len(predictions) == 0:
                logger.warning(f"No prediction for {symbol}")
                return 0, 0.0, features

            # Get latest prediction (models return predictions for all valid sequences)
            signal = predictions[-1]  # -1, 0, or 1
            
            # Handle NaN predictions (mismatched model/data)
            if np.isnan(signal) or not np.isfinite(signal):
                logger.warning(f"Model produced NaN/inf for {symbol} - model may be mismatched with data")
                return 0, 0.0, features.iloc[-1:].copy()
            
            confidence = abs(signal)  # Simple confidence

            logger.info(
                f"✅ Signal for {symbol}: {signal} (confidence={confidence:.2f})"
            )
            
            # Return latest features for debugging/logging
            latest_features = features.iloc[-1:].copy()
            return int(signal), float(confidence), latest_features

        except Exception as e:
            logger.error(f"Failed to generate signal for {symbol}: {e}")
            return 0, 0.0, None
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
    # Load config for defaults
    from config import load_config
    try:
        cfg = load_config()
        default_symbols = cfg.get_symbols_normalized()
        default_timeframe = cfg.data.timeframe
        default_model = cfg.model.model_type
        
        # Auto-calculate interval based on timeframe
        timeframe_to_seconds = {
            "1m": 60,
            "5m": 300,
            "15m": 900,
            "30m": 1800,
            "1h": 3600,
            "4h": 14400,
            "1d": 3600,  # Check daily markets every hour
            "1w": 3600,  # Check weekly markets every hour
            "1mo": 3600, # Check monthly markets every hour
        }
        default_interval = timeframe_to_seconds.get(default_timeframe, 3600)
    except Exception:
        # Fallback if config fails
        default_symbols = ["eurusd"]
        default_timeframe = "1d"
        default_model = "lstm_transformer"
        default_interval = 3600
    
    parser = argparse.ArgumentParser(description="Run paper trading")
    parser.add_argument(
        "--capital", type=float, default=100000, help="Initial capital (default: $100k)"
    )
    parser.add_argument(
        "--model",
        type=str,
        default=default_model,
        help=f"Model to use (default: from config or {default_model})",
    )
    parser.add_argument(
        "--symbols",
        type=str,
        nargs="+",
        default=default_symbols,
        help=f"Symbols to trade (default: from config or {default_symbols[0]})",
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
        default=default_interval,
        help=f"Seconds between iterations (default: {default_interval}s based on {default_timeframe} timeframe)",
    )
    parser.add_argument(
        "--timeframe",
        type=str,
        default=default_timeframe,
        choices=["1m", "2m", "5m", "15m", "30m", "1h", "90m", "4h", "1d", "1w", "1mo"],
        help=f"Data timeframe for analysis (default: from config or {default_timeframe})",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        default=True,
        help="Use live market data (default: True)",
    )
    parser.add_argument(
        "--no-live",
        action="store_true",
        help="Use historical CSV data instead of live",
    )

    args = parser.parse_args()

    # Determine if using live data
    use_live_data = not args.no_live

    # Create trader
    trader = PaperTrader(
        initial_capital=args.capital, 
        model_name=args.model, 
        symbols=args.symbols,
        use_live_data=use_live_data,
        timeframe=args.timeframe,
    )

    # Run
    trader.run(iterations=args.iterations, interval_seconds=args.interval)


if __name__ == "__main__":
    main()

"""Technical analysis engine for AITrader.

Subscribes to OHLCVBar events on the bus, runs indicators, detects regimes,
combines signals across timeframes, and publishes TechnicalSignal.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from src.core.bus import Bus
from src.core.contracts import (
    BusChannel,
    Instrument,
    MarketRegime,
    Timeframe,
    OHLCVBar,
    TechnicalSignal,
    TimeframeBias,
)
from src.core.config import InstrumentConfig, load_instruments
from src.core.logging import get_logger
from src.technical.loader import TechnicalDataLoader, timeframe_to_timedelta
from src.technical.indicators import compute_indicators, compute_all_indicators, compute_returns
from src.technical.regime import detect_regime
from src.technical.confluence import compute_tf_bias, ConfluenceCombiner
from src.technical.signal_builder import TechnicalSignalBuilder

_log = get_logger("D04-TECHNICAL")


class TechnicalEngine:
    """Orchestrates the technical analysis pipeline on primary timeframe candle closes."""

    def __init__(
        self,
        bus: Bus,
        store: Any,  # DataStore
        instruments_config: dict[Instrument, InstrumentConfig] | None = None,
        enable_causal_filter: bool = False,
        enable_order_flow: bool = False,
    ) -> None:
        self.bus = bus
        self.store = store
        # instruments_config loaded fresh via property for hot-reload support
        self.enable_causal_filter = enable_causal_filter
        self.enable_order_flow = enable_order_flow

        self.loader = TechnicalDataLoader(store)
        self.is_running = False
        self.enabled = True

    @property
    def instruments_config(self) -> dict[Instrument, InstrumentConfig]:
        """Always fresh from cache to support hot-reload on Apply."""
        try:
            return load_instruments()
        except Exception:
            return {}

    async def start(self) -> None:
        """Start the engine and subscribe to OHLCV_BAR channel."""
        if self.is_running:
            return
        
        await self.bus.subscribe(BusChannel.OHLCV_BAR, self.on_ohlcv_bar)
        self.is_running = True
        _log.info("technical_engine_started", message="Technical analysis engine started.")

    async def stop(self) -> None:
        """Stop the engine and unsubscribe from OHLCV_BAR channel."""
        if not self.is_running:
            return
        
        await self.bus.unsubscribe(BusChannel.OHLCV_BAR, self.on_ohlcv_bar)
        self.is_running = False
        _log.info("technical_engine_stopped", message="Technical analysis engine stopped.")

    async def on_ohlcv_bar(self, payload: Any) -> None:
        """Handle incoming OHLCVBar from the bus."""
        if not getattr(self, "enabled", True):
            return
        if not isinstance(payload, OHLCVBar):
            # Parse or validate if needed (Pydantic v2 validation is handled at bus layer)
            return

        instrument = payload.instrument
        timeframe = payload.timeframe

        # 1. Fetch instrument config
        inst_config = self.instruments_config.get(instrument)
        if not inst_config:
            _log.debug("ignored_instrument_no_config", instrument=instrument.value)
            return

        primary_tf = inst_config.primary_timeframe
        
        # 2. Trigger on primary timeframe closes only
        if timeframe != primary_tf:
            return

        # Candle close time is open time + timeframe duration
        delta = timeframe_to_timedelta(primary_tf)
        current_time = payload.timestamp + delta

        _log.info(
            "primary_bar_received",
            instrument=instrument.value,
            timeframe=timeframe.value,
            timestamp=payload.timestamp.isoformat(),
            close_time=current_time.isoformat(),
        )

        try:
            # 3. Load multi-timeframe dataset
            dataset = self.loader.load(
                instrument=instrument,
                timeframes=inst_config.active_timeframes,
                current_time=current_time,
                num_bars=250,
            )

            # 4. Compute indicators
            tf_indicators = compute_indicators(dataset.timeframes)

            # 5. Optional Causal Filter
            if self.enable_causal_filter:
                for tf in inst_config.active_timeframes:
                    df = dataset.timeframes.get(tf)
                    if df is not None and len(df) > 30:
                        try:
                            # Target is close returns
                            target = compute_returns(df, price_col="close", periods=1)
                            df_inds = compute_all_indicators(df)
                            
                            from src.technical.causal import select_causal_features
                            causal_cols = select_causal_features(target, df_inds)
                            
                            # Filter TF indicators to drop non-causal ones
                            # Keep essential metadata keys
                            essential_keys = {"close", "atr", "support", "resistance"}
                            tf_indicators[tf] = {
                                k: v if (k in causal_cols or k in essential_keys) else 0.0
                                for k, v in tf_indicators[tf].items()
                            }
                        except Exception as e:
                            _log.error("causal_filtering_failed", error=str(e), timeframe=tf.value)

            # 6. Detect regimes and build TF biases
            biases = []
            primary_regime = None
            
            for tf in inst_config.active_timeframes:
                df = dataset.timeframes.get(tf)
                if df is None or df.empty:
                    continue

                regime_val = detect_regime(df)
                if tf == primary_tf:
                    primary_regime = regime_val

                bias_dir, bias_conf = compute_tf_bias(tf, tf_indicators[tf], regime_val)
                biases.append(
                    TimeframeBias(
                        timeframe=tf,
                        direction=bias_dir,
                        confidence=bias_conf,
                        regime=regime_val,
                        indicators=tf_indicators[tf],
                        support=tf_indicators[tf].get("support"),
                        resistance=tf_indicators[tf].get("resistance"),
                    )
                )

            if primary_regime is None:
                primary_regime = MarketRegime.UNKNOWN

            # 7. Confluence combiner
            combiner = ConfluenceCombiner(primary_tf)
            consensus_dir, consensus_conf, confluence_score = combiner.combine(biases)

            # 8. Build TechnicalSignal
            builder = TechnicalSignalBuilder(primary_tf)
            signal = builder.build(
                instrument=instrument,
                timestamp=current_time,
                direction=consensus_dir,
                confidence=consensus_conf,
                confluence_score=confluence_score,
                per_timeframe=biases,
                primary_indicators=tf_indicators[primary_tf],
                primary_regime=primary_regime,
            )

            # 9. Publish onto bus
            await self.bus.publish(BusChannel.TECHNICAL_SIGNAL, signal)

            _log.info(
                "technical_signal_published",
                signal_id=signal.signal_id,
                instrument=instrument.value,
                direction=signal.direction.value,
                confidence=signal.confidence,
                regime=signal.regime.value,
            )

        except Exception as e:
            _log.error(
                "technical_engine_pipeline_failed",
                instrument=instrument.value,
                error=str(e),
            )

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
    Direction,
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
from src.technical.indicators import (
    compute_indicators,
    compute_all_indicators,
    compute_returns,
)
from src.technical.regime import detect_regime
from src.technical.confluence import compute_tf_bias, ConfluenceCombiner, confluence_weights
from src.technical.signal_builder import TechnicalSignalBuilder
from src.technical.scalping.scoring import compute_scalping_tf_bias
from src.technical.scalping.sessions import is_scalping_session_open

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
        # Skip re-processing the same primary bar close (chart focus / store replay).
        self._last_processed_bar_close: dict[Instrument, datetime] = {}

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

    async def bootstrap_latest_signals(self) -> None:
        """Seed technical cache from the latest stored primary-TF bar after restart."""
        from src.core.instruments import get_enabled_instruments
        from src.data.scheduler.store_ops import bars_from_store

        for inst in get_enabled_instruments():
            cfg = self.instruments_config.get(inst)
            if cfg is None:
                continue
            primary_tf = cfg.primary_timeframe
            try:
                completed, _ = bars_from_store(self.store, inst, primary_tf)
                await self.on_ohlcv_bar(completed)
            except Exception as exc:  # noqa: BLE001
                _log.warning(
                    "technical_bootstrap_skip",
                    instrument=inst.value,
                    timeframe=primary_tf.value,
                    error=str(exc),
                )

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

        last_close = self._last_processed_bar_close.get(instrument)
        if last_close is not None and current_time <= last_close:
            _log.debug(
                "technical_bar_deduped",
                instrument=instrument.value,
                bar_close=current_time.isoformat(),
            )
            return

        _log.info(
            "primary_bar_received",
            instrument=instrument.value,
            timeframe=timeframe.value,
            timestamp=payload.timestamp.isoformat(),
            close_time=current_time.isoformat(),
        )

        try:
            scalping_mode = inst_config.scalping_mode

            # 3. Load multi-timeframe dataset
            lookback_bars = 300 if scalping_mode else 250
            dataset = self.loader.load(
                instrument=instrument,
                timeframes=inst_config.active_timeframes,
                current_time=current_time,
                num_bars=lookback_bars,
            )

            # 4. Compute indicators
            tf_indicators = compute_indicators(
                dataset.timeframes,
                instrument=instrument,
                scalping=scalping_mode,
            )

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

                inds = tf_indicators.get(tf, {})
                if scalping_mode and inds:
                    bias_dir, bias_conf, meta = compute_scalping_tf_bias(inds, regime_val)
                    inds = {**inds, **meta}
                else:
                    bias_dir, bias_conf = compute_tf_bias(tf, inds, regime_val)

                biases.append(
                    TimeframeBias(
                        timeframe=tf,
                        direction=bias_dir,
                        confidence=bias_conf,
                        regime=regime_val,
                        indicators=inds,
                        support=inds.get("support"),
                        resistance=inds.get("resistance"),
                    )
                )

            if primary_regime is None:
                primary_regime = MarketRegime.UNKNOWN

            # 7. Confluence combiner
            combiner = ConfluenceCombiner(
                primary_tf,
                weights=confluence_weights(primary_tf, scalping=scalping_mode),
            )
            consensus_dir, consensus_conf, confluence_score = combiner.combine(biases)

            # Session gate for MT4 scalping template (i-Sessions)
            if scalping_mode and consensus_dir != Direction.NEUTRAL:
                if not is_scalping_session_open(current_time):
                    _log.debug(
                        "scalping_session_closed",
                        instrument=instrument.value,
                        timestamp=current_time.isoformat(),
                    )
                    consensus_dir = Direction.NEUTRAL
                    consensus_conf = 0.0
                    confluence_score = 0.0

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
            self._last_processed_bar_close[instrument] = current_time
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

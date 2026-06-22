"""D05-DECISION — Decision Engine coordinator.

Subscribes to signal bus channels, maintains rolling state, fuses inputs,
and publishes generated TradeSignals.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from src.core.clock import now
from src.core.config import AppConfig, InstrumentConfig, load_instruments
from src.core.contracts import (
    BusChannel,
    Direction,
    FundamentalSignal,
    Instrument,
    OrderSide,
    PortfolioState,
    SignalSource,
    SignalStrength,
    TechnicalSignal,
    TradeSignal,
)
from src.core.ids import new_signal_id
from src.core.logging import get_logger
from src.decision.expiry import is_valid
from src.decision.fusion import combine
from src.decision.narrator import build_narrative
from src.decision.sizer import compute_suggested_size
from src.decision.state import SignalState

_log = get_logger("D05-DECISION")


class DecisionEngine:
    """Orchestrates F+T signal subscriptions and runs the decision fusion pipeline."""

    def __init__(
        self,
        config: AppConfig,
        bus: Any,
        state: SignalState | None = None,
    ) -> None:
        self.config = config
        self.bus = bus
        self.state = state or SignalState()

        # Cache portfolio state for position sizer equity references
        self._portfolio_cache: Optional[PortfolioState] = None

        # Load instrument configurations
        try:
            self.instrument_configs = load_instruments()
        except Exception:
            _log.warning(
                "decision_engine_instruments_load_fallback",
                details="Could not load config/instruments.yaml, using empty configs.",
            )
            self.instrument_configs = {}

        self._running = False

    async def start(self) -> None:
        """Start subscriptions to necessary bus channels."""
        if self._running:
            return
        self._running = True

        # Subscribe to signal bus channels
        await self.bus.subscribe(BusChannel.FUNDAMENTAL_SIGNAL, self.handle_fundamental_signal)
        await self.bus.subscribe(BusChannel.TECHNICAL_SIGNAL, self.handle_technical_signal)
        await self.bus.subscribe(BusChannel.PORTFOLIO_UPDATE, self.handle_portfolio_update)

        _log.info("decision_engine_started")

    async def stop(self) -> None:
        """Unsubscribe from bus channels."""
        if not self._running:
            return
        self._running = False

        # Unsubscribe
        await self.bus.unsubscribe(BusChannel.FUNDAMENTAL_SIGNAL, self.handle_fundamental_signal)
        await self.bus.unsubscribe(BusChannel.TECHNICAL_SIGNAL, self.handle_technical_signal)
        await self.bus.unsubscribe(BusChannel.PORTFOLIO_UPDATE, self.handle_portfolio_update)

        _log.info("decision_engine_stopped")

    async def handle_fundamental_signal(self, signal: FundamentalSignal) -> None:
        """Callback to store incoming fundamental signals in rolling state memory."""
        self.state.fundamental[signal.instrument] = signal
        _log.debug(
            "decision_engine_fundamental_stored",
            instrument=signal.instrument.value,
            direction=signal.direction.value,
        )

    async def handle_portfolio_update(self, state: PortfolioState) -> None:
        """Callback to cache the current portfolio status."""
        self._portfolio_cache = state

    async def handle_technical_signal(self, signal: TechnicalSignal) -> None:
        """Main pipeline trigger. Fuses inputs, calculates sizing, and publishes decisions."""
        instrument = signal.instrument
        self.state.technical[instrument] = signal

        # 1. Retrieve states
        f_sig = self.state.fundamental.get(instrument)
        t_sig = signal

        current_time = now()

        # 2. Expiry check on fundamental signal
        if f_sig is not None and not is_valid(f_sig, current_time):
            _log.debug("decision_engine_fundamental_expired", instrument=instrument.value)
            f_sig = None

        # 3. Retrieve config
        inst_config = self.instrument_configs.get(instrument)
        if not inst_config:
            # Fallback configuration block
            inst_config = InstrumentConfig(
                pip_size=0.0001,
                lot_size=100000.0,
                session_hours={"open": "22:00", "close": "22:00"},
                active_timeframes=[],
                primary_timeframe=signal.primary_tf,
            )

        # 4. Run combination fusion
        fusion = combine(f_sig, t_sig, inst_config, current_time)

        # Determine side mapping
        suggested_side = None
        if fusion.direction == Direction.LONG:
            suggested_side = OrderSide.BUY
        elif fusion.direction == Direction.SHORT:
            suggested_side = OrderSide.SELL

        # 5. Handle cancellation and emission rules
        prior_directional = self.state.prior_was_directional.get(instrument, False)

        if fusion.direction == Direction.NEUTRAL:
            if prior_directional:
                # Prior signal was directional, now NEUTRAL: Publish cancellation signal
                self.state.prior_was_directional[instrument] = False
                await self._publish_trade_signal(
                    instrument=instrument,
                    direction=Direction.NEUTRAL,
                    confidence=0.0,
                    strength=SignalStrength.WEAK,
                    f_weight=fusion.fundamental_weight,
                    t_weight=fusion.technical_weight,
                    suggested_side=None,
                    suggested_entry=None,
                    suggested_sl=None,
                    suggested_tp=None,
                    suggested_size=None,
                    narrative="Signal cancelled. Market direction returned to neutral.",
                    f_sig=f_sig,
                    t_sig=t_sig,
                    valid_until=t_sig.valid_until,
                    timestamp=current_time,
                )
            else:
                # Silence neutral spam if the prior state was already neutral
                _log.debug("decision_engine_silence_neutral", instrument=instrument.value)
            return

        # Fused direction is directional (LONG or SHORT)
        self.state.prior_was_directional[instrument] = True

        # 6. Sizer calculation
        suggested_size = compute_suggested_size(
            entry_price=t_sig.entry_price,
            sl_price=t_sig.stop_loss,
            inst_config=inst_config,
            portfolio_state=self._portfolio_cache,
            risk_pct=self.config.risk.max_position_pct if hasattr(self.config, "risk") else 0.01,
        )

        # 7. Narrative building
        narrative = build_narrative(f_sig, t_sig, fusion.direction)

        # 8. Publish the trade decision
        await self._publish_trade_signal(
            instrument=instrument,
            direction=fusion.direction,
            confidence=fusion.confidence,
            strength=fusion.strength,
            f_weight=fusion.fundamental_weight,
            t_weight=fusion.technical_weight,
            suggested_side=suggested_side,
            suggested_entry=t_sig.entry_price,
            suggested_sl=t_sig.stop_loss,
            suggested_tp=t_sig.take_profit,
            suggested_size=suggested_size,
            narrative=narrative,
            f_sig=f_sig,
            t_sig=t_sig,
            valid_until=t_sig.valid_until,
            timestamp=current_time,
        )

    async def _publish_trade_signal(
        self,
        instrument: Instrument,
        direction: Direction,
        confidence: float,
        strength: SignalStrength,
        f_weight: float,
        t_weight: float,
        suggested_side: OrderSide | None,
        suggested_entry: float | None,
        suggested_sl: float | None,
        suggested_tp: float | None,
        suggested_size: float | None,
        narrative: str,
        f_sig: FundamentalSignal | None,
        t_sig: TechnicalSignal,
        valid_until: datetime,
        timestamp: datetime,
    ) -> None:
        """Instantiate and publish a TradeSignal on the bus."""
        trade_signal = TradeSignal(
            signal_id=new_signal_id(),
            instrument=instrument,
            timestamp=timestamp,
            valid_until=valid_until,
            direction=direction,
            confidence=confidence,
            strength=strength,
            fundamental_weight=f_weight,
            technical_weight=t_weight,
            suggested_side=suggested_side,
            suggested_entry=suggested_entry,
            suggested_sl=suggested_sl,
            suggested_tp=suggested_tp,
            suggested_size=suggested_size,
            narrative=narrative,
            sources=SignalSource(fundamental=f_sig, technical=t_sig),
            model_version=None,
        )

        await self.bus.publish(BusChannel.TRADE_SIGNAL, trade_signal)
        _log.info(
            "trade_signal_published",
            instrument=instrument.value,
            direction=direction.value,
            confidence=f"{confidence:.2f}",
            size=suggested_size,
        )

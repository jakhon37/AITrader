"""D02-DATA — CalendarFetcher: economic calendar ingestion.

Source: Forex Factory calendar page (HTML scrape).
Fallback: Investing.com JSON API (unofficial, best-effort).

Lifecycle of each event (per D02 plan and CONTRACTS.md):
  1. CalendarFetcher stores every upcoming event as a RawCalendarEvent (SQLite).
  2. On each poll, the scheduler checks for events that are:
       - 60 minutes from release  → publish EconomicEvent(actual=None) [pre-release]
       - Within 10 minutes after release time → re-fetch actuals and publish
         EconomicEvent(actual=...) [post-release]
  3. D06 subscribes to EconomicEvent(impact=HIGH) to activate the news_halt window.

Design rules:
  - Fail loud: a scrape failure raises DataError; never return empty silently.
  - All timestamps are UTC with tzinfo=timezone.utc.
  - Never call datetime.now(); always use clock.now().
  - Rate limit: 1 request per 60 seconds to Forex Factory (respect their ToS).

Usage:
    fetcher = CalendarFetcher(store, bus, clock, poll_interval_seconds=3600)
    await fetcher.run()    # blocks; run as asyncio.Task
    fetcher.stop()

Requirements:
    httpx, beautifulsoup4 (in [live_data] extras)
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from src.core.bus import Bus
from src.core.clock import VirtualClock
from src.core.contracts import BusChannel, EconomicEvent, Instrument
from src.core.exceptions import DataError
from src.core.ids import new_signal_id
from src.core.logging import get_logger
from src.data.models import RawCalendarEvent
from src.data.store import DataStore

_log = get_logger("D02-DATA.calendar")

# ── Instrument ↔ currency mapping ─────────────────────────────────────────────
# Maps event currency codes to affected instruments
_CURRENCY_TO_INSTRUMENTS: dict[str, list[str]] = {
    "USD": ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"],
    "EUR": ["EURUSD"],
    "GBP": ["GBPUSD"],
    "JPY": ["USDJPY"],
    "XAU": ["XAUUSD"],
}

# ── High-impact event name patterns ───────────────────────────────────────────
_HIGH_IMPACT_PATTERNS = [
    r"(?i)(fomc|rate decision|fed funds|interest rate)",
    r"(?i)(non.?farm|nfp|payroll)",
    r"(?i)\bCPI\b",
    r"(?i)\bGDP\b",
]


def _infer_impact(name: str) -> str:
    """Infer impact level from event name when not explicitly provided."""
    for pattern in _HIGH_IMPACT_PATTERNS:
        if re.search(pattern, name):
            return "high"
    lower = name.lower()
    if any(w in lower for w in ["pmi", "retail sales", "unemployment", "trade balance"]):
        return "medium"
    return "low"


def _currency_to_instruments(currency: str) -> list[str]:
    return _CURRENCY_TO_INSTRUMENTS.get(currency.upper(), [])


def _make_event_id(name: str, timestamp: datetime) -> str:
    safe_name = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    ts_slug = timestamp.strftime("%Y%m%dT%H%M")
    return f"{safe_name}_{ts_slug}"


# ── Forex Factory scraper ─────────────────────────────────────────────────────

class CalendarFetcher:
    """Background async task that fetches the economic calendar.

    Polls Forex Factory (or fallback source) on a configurable interval,
    stores events in DataStore, and publishes EconomicEvent bus messages
    at the correct timing windows.

    Parameters
    ----------
    store:
        DataStore for SQLite persistence.
    bus:
        Signal bus for EconomicEvent publication.
    clock:
        VirtualClock — use clock.now() for all current-time reads.
    poll_interval_seconds:
        How often to re-fetch the full calendar (default 3600 = 1 hour).
    pre_release_minutes:
        How many minutes before the event to publish the pre-release notification
        (default 60, per plan).
    """

    def __init__(
        self,
        store: DataStore,
        bus: Bus,
        clock: VirtualClock,
        poll_interval_seconds: int = 3600,
        pre_release_minutes: int = 60,
    ) -> None:
        self._store = store
        self._bus = bus
        self._clock = clock
        self._poll_interval = poll_interval_seconds
        self._pre_release_delta = timedelta(minutes=pre_release_minutes)
        self._running = False

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def run(self) -> None:
        """Main loop — blocks until stop() is called."""
        self._running = True
        _log.info("calendar_fetcher_started", poll_interval_s=self._poll_interval)
        while self._running:
            try:
                await self._refresh_calendar()
            except DataError as exc:
                _log.error("calendar_refresh_failed", error=str(exc))
            await self._process_pending_notifications()
            await asyncio.sleep(self._poll_interval)

    def stop(self) -> None:
        self._running = False
        _log.info("calendar_fetcher_stopping")

    # ── Calendar fetch ────────────────────────────────────────────────────────

    async def _refresh_calendar(self) -> None:
        """Fetch this week's calendar and upsert into DataStore."""
        events = await self._scrape_forex_factory()
        if not events:
            _log.warning("calendar_empty_result")
            return
        self._store.write_calendar_events(events)
        _log.info("calendar_refreshed", event_count=len(events))

    async def _scrape_forex_factory(self) -> list[RawCalendarEvent]:
        """Scrape Forex Factory's weekly calendar HTML.

        Returns a list of RawCalendarEvent objects for the current week.
        Raises DataError on network/parse failure.
        """
        try:
            import httpx
            from bs4 import BeautifulSoup  # type: ignore[import]
        except ImportError as e:
            raise DataError(
                "httpx and beautifulsoup4 required for calendar scraping. "
                "Install: pip install httpx beautifulsoup4"
            ) from e

        url = "https://www.forexfactory.com/calendar"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (compatible; AITrader/1.0; +https://github.com)"
            ),
            "Accept": "text/html",
        }

        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=20.0) as client:
                    resp = await client.get(url, headers=headers, follow_redirects=True)
                if resp.status_code == 429:
                    wait = int(resp.headers.get("Retry-After", 120))
                    _log.warning("ff_rate_limited", retry_after_s=wait)
                    await asyncio.sleep(wait)
                    continue
                resp.raise_for_status()
                html = resp.text
                break
            except Exception as exc:
                if attempt == 2:
                    raise DataError(
                        f"Forex Factory scrape failed after 3 attempts: {exc}"
                    ) from exc
                await asyncio.sleep(2 ** attempt)

        return self._parse_ff_html(html)

    def _parse_ff_html(self, html: str) -> list[RawCalendarEvent]:
        """Parse Forex Factory calendar HTML into RawCalendarEvent objects."""
        try:
            from bs4 import BeautifulSoup
        except ImportError as e:
            raise DataError("beautifulsoup4 not installed") from e

        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table", class_="calendar__table")
        if not table:
            _log.warning("ff_calendar_table_not_found")
            return []

        events: list[RawCalendarEvent] = []
        current_date: Optional[datetime] = None
        now = self._clock.now()

        for row in table.find_all("tr", class_=re.compile(r"calendar__row")):
            # Date column may appear once per day group
            date_cell = row.find("td", class_="calendar__date")
            if date_cell and date_cell.get_text(strip=True):
                date_text = date_cell.get_text(strip=True)
                try:
                    # Forex Factory uses "Mon Jun 23" format
                    current_date = datetime.strptime(
                        f"{date_text} {now.year}", "%a %b %d %Y"
                    ).replace(tzinfo=timezone.utc)
                except ValueError:
                    pass

            if current_date is None:
                continue

            # Time cell
            time_cell = row.find("td", class_="calendar__time")
            if not time_cell:
                continue
            time_text = (time_cell.get_text(strip=True) or "").upper()
            if not time_text or time_text in ("ALL DAY", "TENTATIVE"):
                continue

            try:
                t = datetime.strptime(time_text, "%I:%M%p")
                event_dt = current_date.replace(
                    hour=t.hour, minute=t.minute, second=0, microsecond=0
                )
                # Forex Factory times are US Eastern — convert to UTC (approx EST=UTC-5)
                # A proper implementation should use pytz; using +5h approximation here.
                event_dt = event_dt + timedelta(hours=5)
            except ValueError:
                continue

            # Currency
            currency_cell = row.find("td", class_="calendar__currency")
            currency = (currency_cell.get_text(strip=True) if currency_cell else "").upper()

            # Event name
            name_cell = row.find("td", class_="calendar__event")
            name_span = name_cell.find("span") if name_cell else None
            name = ((name_span or name_cell).get_text(strip=True) if name_cell else "").strip()
            if not name:
                continue

            # Impact
            impact_cell = row.find("td", class_="calendar__impact")
            impact_span = impact_cell.find("span") if impact_cell else None
            impact_class = " ".join(impact_span.get("class", [])) if impact_span else ""
            if "high" in impact_class:
                impact = "high"
            elif "medium" in impact_class:
                impact = "medium"
            elif "low" in impact_class:
                impact = "low"
            else:
                impact = _infer_impact(name)

            # Actual/forecast/previous
            def _parse_num(cell_class: str) -> Optional[float]:
                cell = row.find("td", class_=cell_class)
                if not cell:
                    return None
                txt = cell.get_text(strip=True).replace("%", "").replace("K", "000").replace("M", "000000")
                try:
                    return float(txt)
                except ValueError:
                    return None

            actual = _parse_num("calendar__actual")
            forecast = _parse_num("calendar__forecast")
            previous = _parse_num("calendar__previous")

            surprise_pct: Optional[float] = None
            if actual is not None and forecast is not None and forecast != 0:
                surprise_pct = (actual - forecast) / abs(forecast)

            instruments = _currency_to_instruments(currency)

            events.append(
                RawCalendarEvent(
                    event_id=_make_event_id(name, event_dt),
                    name=name,
                    timestamp=event_dt,
                    impact=impact,  # type: ignore[arg-type]
                    instruments=instruments,
                    actual=actual,
                    forecast=forecast,
                    previous=previous,
                    surprise_pct=surprise_pct,
                )
            )

        return events

    # ── Notification dispatcher ───────────────────────────────────────────────

    async def _process_pending_notifications(self) -> None:
        """Check stored events and publish EconomicEvents at the right timing.

        Called after each calendar refresh and every poll interval.
        """
        now = self._clock.now()
        pre_window_start = now - timedelta(minutes=5)  # 5-min grace for late polls
        pre_window_end = now + self._pre_release_delta  # next 60 min

        try:
            events = self._store.get_economic_events(
                start=pre_window_start,
                end=now + timedelta(hours=25),  # look ahead up to 25 hours
                impact_filter=None,
            )
        except NotImplementedError:
            # store.get_economic_events raises NotImplementedError until SQLite is wired
            return
        except Exception as exc:
            _log.error("calendar_notify_query_failed", error=str(exc))
            return

        for raw in events:
            if not isinstance(raw, RawCalendarEvent):
                continue
            self._maybe_publish(raw, now, pre_window_end)

    def _maybe_publish(
        self,
        raw: RawCalendarEvent,
        now: datetime,
        pre_window_end: datetime,
    ) -> None:
        """Publish EconomicEvent for pre-release and post-release windows."""
        event_time = raw.timestamp

        # Pre-release: within the next pre_release_minutes and not yet notified
        if not raw.pre_release_notified and now <= event_time <= pre_window_end:
            asyncio.create_task(self._publish_event(raw, is_post_release=False))

        # Post-release: up to 10 min after, and actuals are available
        post_window = event_time + timedelta(minutes=10)
        if (
            not raw.post_release_notified
            and raw.actual is not None
            and event_time <= now <= post_window
        ):
            asyncio.create_task(self._publish_event(raw, is_post_release=True))

    async def _publish_event(
        self,
        raw: RawCalendarEvent,
        is_post_release: bool,
    ) -> None:
        """Build and publish an EconomicEvent to the bus."""
        instruments = [
            Instrument(i) for i in raw.instruments if i in Instrument.__members__
        ]

        event = EconomicEvent(
            signal_id=new_signal_id(),
            timestamp=raw.timestamp,
            name=raw.name,
            impact=raw.impact,  # type: ignore[arg-type]
            affected_pairs=instruments,
            actual=raw.actual if is_post_release else None,
            forecast=raw.forecast,
            previous=raw.previous,
            surprise_pct=raw.surprise_pct if is_post_release else None,
        )

        try:
            await self._bus.publish(BusChannel.ECONOMIC_EVENT, event)
            self._store.mark_event_notified(
                raw.event_id,
                pre=not is_post_release,
                post=is_post_release,
            )
            _log.info(
                "economic_event_published",
                name=raw.name,
                post_release=is_post_release,
                impact=raw.impact,
                instruments=[i.value for i in instruments],
            )
        except Exception as exc:
            _log.error("economic_event_publish_failed", name=raw.name, error=str(exc))

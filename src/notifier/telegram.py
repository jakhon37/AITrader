"""D07-NOTIFIER — Telegram Bot API client.

Handles outbound messaging with rate-limiting and inbound command polling
using direct httpx calls.
"""

from __future__ import annotations

import asyncio
import os
from collections import deque
from datetime import datetime
from typing import Any, Callable, Dict, List, Set

import httpx

from src.core.clock import now
from src.core.logging import get_logger

_log = get_logger("D07-NOTIFIER")


class TelegramClient:
    """Outbound and inbound Telegram interface with token-bucket rate limiting."""

    def __init__(
        self,
        token: str | None = None,
        chat_id: str | None = None,
        allowed_users: List[int] | None = None,
        refill_rate: float = 0.33,  # 1 token every ~3 seconds
        max_tokens: float = 20.0,
    ) -> None:
        self.token = token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")

        # Parse allowed users from environment if not supplied
        self.allowed_users: Set[int] = set(allowed_users or [])
        if not self.allowed_users:
            allowed_env = os.getenv("ALLOWED_TELEGRAM_USER_IDS", "")
            if allowed_env:
                try:
                    self.allowed_users = {
                        int(uid.strip()) for uid in allowed_env.split(",") if uid.strip()
                    }
                except ValueError:
                    _log.warning("telegram_invalid_allowed_users_env", env=allowed_env)

        # Outbound message queue (max size 50, oldest dropped on overflow)
        self.queue: deque[tuple[str, str]] = deque(maxlen=50)

        # Rate Limiting parameters (Token Bucket)
        self.max_tokens = max_tokens
        self.tokens = max_tokens
        self.refill_rate = refill_rate  # tokens added per second
        self.last_refill_time = now()

        self._running = False
        self._send_task: asyncio.Task | None = None
        self._poll_task: asyncio.Task | None = None
        self._handlers: List[Callable[[Dict[str, Any]], Any]] = []

    def register_inbound_handler(self, handler: Callable[[Dict[str, Any]], Any]) -> None:
        """Register a callback for processing authorized inbound messages."""
        self._handlers.append(handler)

    async def start(self) -> None:
        """Start the background outbound sending loop and inbound updates poll."""
        if self._running:
            return
        self._running = True

        self.last_refill_time = now()
        self._send_task = asyncio.create_task(self._send_loop())
        self._poll_task = asyncio.create_task(self._poll_loop())
        _log.info("telegram_client_started", allowed_users_count=len(self.allowed_users))

    async def stop(self) -> None:
        """Shutdown background tasks."""
        if not self._running:
            return
        self._running = False

        if self._send_task:
            self._send_task.cancel()
            try:
                await self._send_task
            except asyncio.CancelledError:
                pass
            self._send_task = None

        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None

        _log.info("telegram_client_stopped")

    async def send_message(self, text: str, chat_id: str | None = None) -> bool:
        """Queue a message to be sent to Telegram. Safe to call from any thread."""
        target_chat = chat_id or self.chat_id
        if not self.token or not target_chat:
            _log.warning("telegram_cannot_send_missing_credentials")
            return False

        if len(self.queue) >= 50:
            # Log overflow and pop oldest
            dropped_text, _ = self.queue.popleft()
            _log.warning("telegram_overflow", dropped_prefix=dropped_text[:50])

        self.queue.append((text, target_chat))
        return True

    async def _send_loop(self) -> None:
        """Worker loop that fetches items from queue and transmits them respecting rate limits."""
        while self._running:
            if not self.queue:
                await asyncio.sleep(0.1)
                continue

            await self._consume_token()

            text, target_chat = self.queue[0]
            success = await self._post_message_with_retries(text, target_chat)
            if success:
                self.queue.popleft()
            else:
                # If unsuccessful, sleep before retrying
                await asyncio.sleep(2.0)

    async def _consume_token(self) -> None:
        """Sleep until at least one token is available in the rate limiter."""
        while self._running:
            current_time = now()
            elapsed = (current_time - self.last_refill_time).total_seconds()
            self.last_refill_time = current_time
            self.tokens = min(self.max_tokens, self.tokens + elapsed * self.refill_rate)

            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return

            await asyncio.sleep(0.1)

    async def _post_message_with_retries(self, text: str, chat_id: str, retries: int = 3) -> bool:
        """Call Telegram API using HTTPX, handling retries and 429 constraints."""
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
        }

        delay = 1.0
        for attempt in range(retries):
            if not self._running:
                return False

            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.post(url, json=payload)

                    if response.status_code == 200:
                        return True
                    elif response.status_code == 429:
                        # Handle rate limit (429) backoff instructions
                        data = response.json()
                        retry_after = float(
                            data.get("parameters", {}).get("retry_after", 5.0)
                        )
                        _log.warning("telegram_api_429", retry_after=retry_after)
                        await asyncio.sleep(retry_after)
                        continue
                    else:
                        _log.error(
                            "telegram_api_error_code",
                            status=response.status_code,
                            body=response.text[:200],
                        )
                        return False

            except httpx.HTTPError as e:
                _log.warning(
                    "telegram_post_network_error",
                    attempt=attempt + 1,
                    error=str(e),
                )
                await asyncio.sleep(delay)
                delay *= 2

        return False

    async def _poll_loop(self) -> None:
        """Long-poll Telegram servers for inbound user commands."""
        offset = 0
        while self._running:
            if not self.token:
                await asyncio.sleep(5.0)
                continue

            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    url = f"https://api.telegram.org/bot{self.token}/getUpdates"
                    params = {"offset": offset, "timeout": 10}
                    response = await client.get(url, params=params)

                    if response.status_code == 200:
                        data = response.json()
                        for update in data.get("result", []):
                            offset = max(offset, update["update_id"] + 1)
                            await self._route_inbound_message(update)
            except Exception as e:
                _log.error("telegram_poll_exception", error=str(e))

            await asyncio.sleep(2.0)

    async def _route_inbound_message(self, update: Dict[str, Any]) -> None:
        """Filter updates to authorized text messages and distribute to registered handlers."""
        message = update.get("message")
        if not message or "text" not in message:
            return

        from_user = message.get("from") or {}
        user_id = from_user.get("id")

        if not user_id:
            return

        # Security check: Ignore commands from unknown user IDs
        if self.allowed_users and user_id not in self.allowed_users:
            _log.warning(
                "telegram_security_blocked_user",
                user_id=user_id,
                username=from_user.get("username"),
            )
            return

        for handler in self._handlers:
            try:
                await handler(message)
            except Exception as e:
                _log.error("telegram_handler_error", error=str(e))

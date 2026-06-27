"""OpenRouter free-model discovery, live validation, and failover."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

import httpx

from src.core.clock import now
from src.core.logging import get_logger
from src.fundamental.synthesizer import (
    PREFERRED_FREE_MODELS,
    extract_openrouter_content,
    get_available_free_models,
    is_chat_suitable_model,
)
from src.fundamental.text_utils import is_safety_classifier_response

_log = get_logger("D03-FUNDAMENTAL")

_VALIDATION_PROMPT = "Reply with exactly the word OK."
_VALIDATION_CACHE_TTL = timedelta(minutes=30)
_FAILED_SOFT_TTL = timedelta(seconds=90)
_FAILED_HARD_TTL = timedelta(minutes=5)
_MAX_VALIDATE_PER_CALL = 8

_validated_at: dict[str, datetime] = {}
_failed_at: dict[str, datetime] = {}
_failure_hard: set[str] = set()
_active_models: dict[str, str] = {}
_last_success_at: dict[str, datetime] = {}


def is_narrative_suitable_model(model_id: str) -> bool:
    """Narrative/chat share the same unsuitable-model filter."""
    return is_chat_suitable_model(model_id)


def mark_model_failed(model_id: str, *, hard: bool = False) -> None:
    """Record a model failure. Soft = brief cooldown (empty/rate-limit); hard = 404/429."""
    _failed_at[model_id] = now()
    if hard:
        _failure_hard.add(model_id)
    for purpose, active in list(_active_models.items()):
        if active == model_id:
            _active_models.pop(purpose, None)


def mark_model_success(model_id: str, *, purpose: str = "chat") -> None:
    """Pin a model that just answered successfully."""
    ts = now()
    _validated_at[model_id] = ts
    _last_success_at[model_id] = ts
    _failed_at.pop(model_id, None)
    _failure_hard.discard(model_id)
    _active_models[purpose] = model_id


def mark_model_validated(model_id: str) -> None:
    mark_model_success(model_id)


def _recently_failed(model_id: str) -> bool:
    failed = _failed_at.get(model_id)
    if failed is None:
        return False
    ttl = _FAILED_HARD_TTL if model_id in _failure_hard else _FAILED_SOFT_TTL
    if now() - failed > ttl:
        _failed_at.pop(model_id, None)
        _failure_hard.discard(model_id)
        return False
    return True


def _recently_succeeded(model_id: str) -> bool:
    ts = _last_success_at.get(model_id)
    if ts is None:
        return False
    return now() - ts <= timedelta(minutes=30)


def _recently_validated(model_id: str) -> bool:
    validated = _validated_at.get(model_id)
    if validated is None:
        return False
    return now() - validated <= _VALIDATION_CACHE_TTL


async def validate_openrouter_model(
    model_id: str,
    api_key: str,
    *,
    timeout: float = 10.0,
) -> bool:
    """Ping OpenRouter with a tiny prompt; True when the model returns real text."""
    if not api_key:
        return False
    if not is_narrative_suitable_model(model_id):
        return False

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/jakhon37/AITrader",
        "X-Title": "AITrader System",
    }
    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": _VALIDATION_PROMPT}],
        "temperature": 0.0,
        "max_tokens": 8,
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
            )
        if response.status_code != 200:
            _log.info(
                "openrouter_model_validation_failed",
                model=model_id,
                status_code=response.status_code,
            )
            return False

        raw = extract_openrouter_content(response.json())
        if not raw or is_safety_classifier_response(raw):
            _log.info(
                "openrouter_model_validation_empty",
                model=model_id,
                safety_only=bool(raw and is_safety_classifier_response(raw)),
            )
            return False

        mark_model_validated(model_id)
        _log.info("openrouter_model_validated", model=model_id)
        return True
    except Exception as exc:  # noqa: BLE001
        _log.warning("openrouter_model_validation_error", model=model_id, error=str(exc))
        return False


async def select_validated_free_model(
    api_key: str,
    *,
    preferred: Optional[list[str]] = None,
    exclude: Optional[set[str]] = None,
    purpose: str = "narrative",
    suitable_only: bool = True,
    force_refresh: bool = False,
) -> Optional[str]:
    """Pick a free model that responds to a live probe, with cached failover."""
    if not api_key:
        return None

    prefs = preferred or PREFERRED_FREE_MODELS
    blocked = exclude or set()
    active = _active_models.get(purpose)
    if active and active not in blocked and not _recently_failed(active):
        if _recently_validated(active) or _recently_succeeded(active):
            return active

    available = await get_available_free_models(api_key, force_refresh=force_refresh)

    def _eligible(model_id: str) -> bool:
        if model_id in blocked or _recently_failed(model_id):
            return False
        if model_id not in available:
            return False
        if suitable_only and not is_narrative_suitable_model(model_id):
            return False
        return True

    candidates: list[str] = []
    seen: set[str] = set()
    for model_id in prefs:
        if _eligible(model_id) and model_id not in seen:
            candidates.append(model_id)
            seen.add(model_id)
    for model_id in available:
        if _eligible(model_id) and model_id not in seen:
            candidates.append(model_id)
            seen.add(model_id)

    validated_probe = 0
    for model_id in candidates:
        if _recently_validated(model_id):
            _active_models[purpose] = model_id
            return model_id
        if validated_probe >= _MAX_VALIDATE_PER_CALL:
            break
        validated_probe += 1
        if await validate_openrouter_model(model_id, api_key):
            _active_models[purpose] = model_id
            return model_id
        mark_model_failed(model_id, hard=True)

    # Last resort: try an eligible model without pre-probe (validates on real use).
    for model_id in candidates:
        if model_id in blocked:
            continue
        if suitable_only and not is_narrative_suitable_model(model_id):
            continue
        if model_id not in available and available:
            continue
        if _recently_failed(model_id):
            continue
        _log.info("openrouter_unvalidated_fallback", model=model_id, purpose=purpose)
        _active_models[purpose] = model_id
        return model_id

    _log.warning(
        "openrouter_no_validated_model",
        purpose=purpose,
        candidates=len(candidates),
        probed=validated_probe,
    )
    return None


def clear_model_registry() -> None:
    """Test helper — reset validation caches."""
    _validated_at.clear()
    _failed_at.clear()
    _failure_hard.clear()
    _active_models.clear()
    _last_success_at.clear()
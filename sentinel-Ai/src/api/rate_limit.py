"""
Per-user in-process rate limiting for the Sentinel AI Engine.

Keyed by the Spring-asserted user_id after service-token auth.
Protects LLM spend even if the Java layer is bypassed on the network.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, status

from src.api.schemas.requests import (
    ChatApiRequest,
    DocumentApiRequest,
    KnowledgeApiRequest,
)

logger = logging.getLogger(__name__)

_lock = threading.Lock()
# key -> deque of request timestamps (seconds)
_windows: dict[str, deque[float]] = defaultdict(deque)


def _limit_for(bucket: str) -> int:
    defaults = {
        "chat": 30,
        "document": 10,
        "knowledge": 10,
    }
    env_keys = {
        "chat": "RATE_LIMIT_CHAT_PER_MIN",
        "document": "RATE_LIMIT_DOC_PER_MIN",
        "knowledge": "RATE_LIMIT_DOC_PER_MIN",
    }
    raw = os.getenv(env_keys[bucket], str(defaults[bucket]))
    try:
        value = int(raw)
    except ValueError:
        value = defaults[bucket]
    return max(1, value)


def _window_seconds() -> float:
    raw = os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60")
    try:
        return max(1.0, float(raw))
    except ValueError:
        return 60.0


def check_rate_limit(user_id: str, bucket: str) -> None:
    """
    Sliding-window limiter. Raises HTTP 429 when the user exceeds the budget.
    """
    if not user_id or not user_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="user_id is required for rate limiting.",
        )

    limit = _limit_for(bucket)
    window = _window_seconds()
    key = f"{bucket}:{user_id.strip()}"
    now = time.monotonic()

    with _lock:
        stamps = _windows[key]
        cutoff = now - window
        while stamps and stamps[0] < cutoff:
            stamps.popleft()

        if len(stamps) >= limit:
            retry_after = max(1, int(window - (now - stamps[0])) + 1)
            logger.warning(
                "Rate limit exceeded user_id=%s bucket=%s limit=%d",
                user_id,
                bucket,
                limit,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded for {bucket}. Try again later.",
                headers={"Retry-After": str(retry_after)},
            )

        stamps.append(now)


def reset_rate_limits() -> None:
    """Test helper — clear all in-memory windows."""
    with _lock:
        _windows.clear()


async def enforce_chat_rate_limit(body: ChatApiRequest) -> None:
    check_rate_limit(body.user_id, "chat")


async def enforce_document_rate_limit(body: DocumentApiRequest) -> None:
    check_rate_limit(body.user_id, "document")


async def enforce_knowledge_rate_limit(body: KnowledgeApiRequest) -> None:
    check_rate_limit(body.user_id, "knowledge")

"""
Service-to-service authentication for the Sentinel AI Engine.

Spring Boot is the only trusted caller. Every /v1/* request must present
the shared secret via the X-Service-Token header. User JWT/RBAC stays in
Spring; this layer only verifies service identity.

mTLS can be terminated at a reverse proxy in front of this process as
defense-in-depth — the shared secret remains required at the application layer.
"""

from __future__ import annotations

import hmac
import logging
import os

from fastapi import Header, HTTPException, status

logger = logging.getLogger(__name__)

SERVICE_TOKEN_HEADER = "X-Service-Token"
_ENV_TOKEN_KEY = "SENTINEL_INTERNAL_SERVICE_TOKEN"


def _expected_token() -> str:
    return os.getenv(_ENV_TOKEN_KEY, "").strip()


def require_service_token(
    x_service_token: str | None = Header(default=None, alias=SERVICE_TOKEN_HEADER),
) -> None:
    """
    FastAPI dependency — reject requests without a valid shared secret.

    Fail closed when SENTINEL_INTERNAL_SERVICE_TOKEN is unset so a
    misconfigured deployment cannot leave /v1 open.
    """
    expected = _expected_token()
    if not expected:
        logger.error(
            "Rejecting request: %s is not configured.",
            _ENV_TOKEN_KEY,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service authentication is not configured.",
        )

    if not x_service_token or not hmac.compare_digest(x_service_token, expected):
        logger.warning("Rejected request with missing or invalid service token.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )

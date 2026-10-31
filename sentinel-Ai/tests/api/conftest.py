"""
Shared fixtures for FastAPI API tests.

Sets a deterministic service token and attaches X-Service-Token to TestClient
requests so router tests exercise the authenticated /v1 surface.
"""

from __future__ import annotations

import os

import pytest

from src.api.rate_limit import reset_rate_limits
from src.api.security import SERVICE_TOKEN_HEADER

TEST_SERVICE_TOKEN = "test-sentinel-internal-service-token"


@pytest.fixture(autouse=True)
def _configure_service_auth(monkeypatch):
    monkeypatch.setenv("SENTINEL_INTERNAL_SERVICE_TOKEN", TEST_SERVICE_TOKEN)
    monkeypatch.setenv("RATE_LIMIT_CHAT_PER_MIN", "1000")
    monkeypatch.setenv("RATE_LIMIT_DOC_PER_MIN", "1000")
    reset_rate_limits()
    yield
    reset_rate_limits()


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {SERVICE_TOKEN_HEADER: TEST_SERVICE_TOKEN}


@pytest.fixture
def authed_post(auth_headers):
    """Helper: client.post with service token attached."""

    def _post(client, url: str, **kwargs):
        headers = dict(kwargs.pop("headers", {}) or {})
        headers.update(auth_headers)
        return client.post(url, headers=headers, **kwargs)

    return _post

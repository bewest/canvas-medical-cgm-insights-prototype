"""Nightscout HTTP client (dependency-injected, SDK-free).

The actual HTTP call is injected as a callable so this module stays free of
``canvas_sdk`` and is unit-testable with a fake. In the plugin, the handler
passes ``canvas_sdk.utils.http.Http(base_url).get``; in tests, a fake getter
returns canned responses.

The injected getter must accept ``(url, headers)`` and return an object with
``.status_code`` (int) and ``.json()`` (-> parsed payload), matching the
``requests.Response`` / Canvas ``Http`` contract.
"""

from __future__ import annotations

from typing import Any, Callable, Protocol

from .nightscout import NightscoutData, parse_nightscout

# How many readings to request (14 days at 5-min cadence ~= 4032).
DEFAULT_COUNT = 4500


class _ResponseLike(Protocol):
    status_code: int

    def json(self) -> Any:  # pragma: no cover - structural typing only
        ...


HttpGet = Callable[[str, dict], _ResponseLike]


def _auth_headers(token: str | None) -> dict:
    """Build Nightscout auth headers.

    Nightscout accepts an ``api-secret`` header (a hashed secret) or a token.
    For a read-only access token the simplest portable approach is a header;
    callers may also embed ``?token=`` in the base URL instead.
    """
    if token:
        return {"api-secret": token}
    return {}


def _get_json(http_get: HttpGet, url: str, headers: dict) -> Any:
    """Perform a GET and return parsed JSON, or None on any non-200/parse error."""
    try:
        resp = http_get(url, headers)
    except Exception:  # network errors must not crash the plugin
        return None
    if getattr(resp, "status_code", 0) != 200:
        return None
    try:
        return resp.json()
    except Exception:
        return None


def fetch_nightscout(
    http_get: HttpGet,
    token: str | None = None,
    count: int = DEFAULT_COUNT,
) -> NightscoutData:
    """Fetch and parse the Nightscout feeds needed for CGM analysis.

    ``http_get`` is bound to a base URL by the caller (e.g. ``Http(base_url).get``),
    so only the path portion is passed here. Each feed degrades gracefully to
    empty when unavailable, so a glucose-only (T2D) site still yields metrics.
    """
    headers = _auth_headers(token)

    entries = _get_json(http_get, f"/api/v1/entries/sgv.json?count={count}", headers)
    device_status = _get_json(
        http_get, f"/api/v1/devicestatus.json?count={count}", headers
    )
    profile = _get_json(http_get, "/api/v1/profile.json", headers)

    return parse_nightscout(
        entries=entries if isinstance(entries, list) else [],
        device_status=device_status if isinstance(device_status, list) else [],
        profile=profile,
    )

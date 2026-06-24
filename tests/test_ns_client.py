"""Tests for cgm_insights.core.ns_client (dependency-injected HTTP)."""

from __future__ import annotations

import json
import os

from cgm_insights.core.ns_client import fetch_nightscout

FIXTURE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "fixtures", "synthetic"
)


class FakeResponse:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def make_getter(bundle: dict, *, fail_devicestatus=False, fail_all=False):
    """Build a fake http_get that routes by URL path to fixture sections."""

    def getter(url: str, headers: dict):
        if fail_all:
            return FakeResponse(500, None)
        if "entries" in url:
            return FakeResponse(200, bundle["entries"])
        if "devicestatus" in url:
            if fail_devicestatus:
                return FakeResponse(404, None)
            return FakeResponse(200, bundle["devicestatus"])
        if "profile" in url:
            return FakeResponse(200, bundle["profile"])
        return FakeResponse(404, None)

    return getter


def _bundle(name="at_goal"):
    with open(os.path.join(FIXTURE_DIR, f"{name}.json")) as fh:
        return json.load(fh)


def test_fetch_parses_entries():
    bundle = _bundle("at_goal")
    nd = fetch_nightscout(make_getter(bundle))
    assert len(nd.entries) > 1000
    assert nd.has_aid is False


def test_fetch_degrades_when_devicestatus_unavailable():
    bundle = _bundle("hypo_prone")
    nd = fetch_nightscout(make_getter(bundle, fail_devicestatus=True))
    # Entries still parsed even though devicestatus 404'd.
    assert len(nd.entries) > 1000
    assert nd.device_status == []


def test_fetch_all_failures_yield_empty():
    bundle = _bundle("at_goal")
    nd = fetch_nightscout(make_getter(bundle, fail_all=True))
    assert nd.entries == []
    assert nd.sgv_values == []


def test_fetch_handles_exception_from_getter():
    def boom(url, headers):
        raise ConnectionError("network down")

    nd = fetch_nightscout(boom)
    assert nd.entries == []

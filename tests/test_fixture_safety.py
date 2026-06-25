"""Anonymization / no-PHI safety guards for the committed fixtures.

The fixtures in fixtures/synthetic/ are de-identified hybrid data (fuzzed real
days blended with synthetic). These tests assert that no real identifiers,
metadata, or real calendar dates leak into the committed repo.
"""

from __future__ import annotations

import glob
import json
import os
from datetime import datetime, timezone

FIXTURE_GLOB = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "fixtures", "synthetic", "*.json"
)

# Fields that would indicate raw Nightscout/Loop records leaked through.
FORBIDDEN_FIELDS = {
    "_id", "sysTime", "uploader", "pump", "loop", "mbg", "override",
    "utcOffset", "isCalibration",
}

# All synthetic data is anchored to a fixed synthetic year (see build_fixtures).
SYNTHETIC_YEAR = 2025
ALLOWED_DEVICE = "synthetic://cgm_insights"


def _fixtures():
    return sorted(glob.glob(FIXTURE_GLOB))


def test_fixtures_exist():
    assert _fixtures(), "no committed fixtures found"


def test_no_forbidden_fields():
    for path in _fixtures():
        bundle = json.load(open(path))
        for entry in bundle["entries"]:
            leaked = FORBIDDEN_FIELDS & set(entry.keys())
            assert not leaked, f"{path}: entry leaks raw fields {leaked}"


def test_device_is_deidentified():
    for path in _fixtures():
        bundle = json.load(open(path))
        for entry in bundle["entries"]:
            assert entry.get("device") == ALLOWED_DEVICE, (
                f"{path}: non-synthetic device {entry.get('device')!r}"
            )


def test_dates_are_in_synthetic_window():
    for path in _fixtures():
        bundle = json.load(open(path))
        for entry in bundle["entries"]:
            year = datetime.fromtimestamp(entry["date"] / 1000.0, tz=timezone.utc).year
            assert year == SYNTHETIC_YEAR, (
                f"{path}: real calendar date leaked (year {year})"
            )


def test_only_glucose_value_fields():
    # Each entry should carry only the small, fixed, de-identified field set.
    allowed = {"type", "sgv", "date", "dateString", "direction", "device"}
    for path in _fixtures():
        bundle = json.load(open(path))
        for entry in bundle["entries"]:
            extra = set(entry.keys()) - allowed
            assert not extra, f"{path}: unexpected entry fields {extra}"


def test_fixtures_are_substantial():
    # ~20 days at 5-min cadence; gaps/blending reduce the count but it stays large.
    for path in _fixtures():
        bundle = json.load(open(path))
        assert len(bundle["entries"]) > 3000, f"{path}: too few readings"

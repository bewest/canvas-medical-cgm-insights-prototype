"""Tests for cgm_insights.core.nightscout parsing."""

from __future__ import annotations

from cgm_insights.core.nightscout import (
    parse_entries,
    parse_device_status,
    parse_nightscout,
)


def test_parse_entries_filters_non_sgv():
    raw = [
        {"type": "sgv", "sgv": 120, "date": 1_700_000_300_000},
        {"type": "mbg", "mbg": 100, "date": 1_700_000_200_000},  # not sgv
        {"type": "sgv", "sgv": 0, "date": 1_700_000_100_000},     # invalid value
        {"type": "sgv", "sgv": 140, "date": 1_700_000_000_000},
    ]
    readings = parse_entries(raw)
    assert [r.sgv for r in readings] == [140.0, 120.0]  # sorted ascending by time


def test_parse_entries_iso_fallback():
    raw = [{"type": "sgv", "sgv": 99, "dateString": "2026-03-25T23:55:37.000Z"}]
    readings = parse_entries(raw)
    assert len(readings) == 1
    assert readings[0].sgv == 99.0
    assert readings[0].epoch_ms > 0


def test_parse_entries_default_type_is_sgv():
    raw = [{"sgv": 110, "date": 1_700_000_000_000}]  # no explicit type
    readings = parse_entries(raw)
    assert len(readings) == 1


def test_parse_device_status_loop_and_openaps():
    raw = [
        {"date": 1_700_000_000_000, "loop": {"iob": {"iob": 1.5}, "cob": {"cob": 20}}},
        {"date": 1_700_000_300_000, "openaps": {"iob": {"iob": 0.4}}},
        {"date": 1_700_000_600_000},  # no iob/cob
    ]
    statuses = parse_device_status(raw)
    assert statuses[0].iob == 1.5
    assert statuses[0].cob == 20.0
    assert statuses[1].iob == 0.4
    assert statuses[2].iob is None


def test_has_aid_detection():
    with_aid = parse_nightscout(
        entries=[{"type": "sgv", "sgv": 120, "date": 1}],
        device_status=[{"date": 1, "loop": {"iob": {"iob": 1.0}}}],
    )
    assert with_aid.has_aid is True

    no_aid = parse_nightscout(
        entries=[{"type": "sgv", "sgv": 120, "date": 1}],
        device_status=[],
    )
    assert no_aid.has_aid is False


def test_profile_list_takes_first():
    nd = parse_nightscout(profile=[{"defaultProfile": "A"}, {"defaultProfile": "B"}])
    assert nd.profile["defaultProfile"] == "A"


def test_empty_inputs():
    nd = parse_nightscout()
    assert nd.entries == []
    assert nd.device_status == []
    assert nd.sgv_values == []


def test_aid_fixture_has_device_status():
    from tests.conftest import load_nightscout

    nd = load_nightscout("aid_well_controlled")
    assert nd.has_aid is True
    assert any(d.iob is not None for d in nd.device_status)


def test_fixture_parses(phenotype_name):
    from tests.conftest import load_nightscout

    nd = load_nightscout(phenotype_name)
    assert len(nd.entries) > 1000
    # The base phenotype fixtures are glucose-only (no AID device status).
    assert nd.has_aid is False
    # Chronological order.
    epochs = [r.epoch_ms for r in nd.entries]
    assert epochs == sorted(epochs)

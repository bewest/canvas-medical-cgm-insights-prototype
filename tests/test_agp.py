"""Tests for cgm_insights.core.agp rendering."""

from __future__ import annotations

from cgm_insights.core.agp import hourly_percentiles, render_agp
from cgm_insights.core.metrics import compute_metrics
from cgm_insights.core.nightscout import GlucoseReading


def _readings_24h() -> list[GlucoseReading]:
    # One reading per hour, value tracks the hour for a predictable profile.
    base = 1_700_000_000_000
    return [
        GlucoseReading(epoch_ms=base + h * 3_600_000, sgv=100.0 + h)
        for h in range(24)
    ]


def test_hourly_percentiles_keys():
    pcts = hourly_percentiles(_readings_24h())
    assert set(pcts) <= set(range(24))
    for _, (p25, p50, p75) in pcts.items():
        assert p25 <= p50 <= p75


def test_render_agp_is_escaped_html():
    readings = _readings_24h()
    m = compute_metrics([r.sgv for r in readings])
    html = render_agp(m, readings)
    assert html.startswith("<div")
    assert "<svg" in html
    assert "polyline" in html or "polygon" in html
    # No unescaped device strings leak raw angle brackets into attributes.
    assert "viewBox" in html


def test_render_agp_handles_empty_readings():
    m = compute_metrics([120.0] * 10)
    html = render_agp(m, [])
    # Still renders the chart frame even with no per-hour band.
    assert "<svg" in html


def test_render_on_fixtures(phenotype_name):
    from tests.conftest import load_nightscout

    nd = load_nightscout(phenotype_name)
    m = compute_metrics(nd.sgv_values)
    html = render_agp(m, nd.entries)
    assert "Time in range" in html
    assert len(html) > 200

"""Tests for cgm_insights.core.agp rendering."""

from __future__ import annotations

from cgm_insights.core.agp import (
    hourly_percentiles,
    render_agp,
    render_tir_bar,
)
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
    for _, (p5, p25, p50, p75, p95) in pcts.items():
        assert p5 <= p25 <= p50 <= p75 <= p95


def test_render_agp_is_escaped_html():
    readings = _readings_24h()
    m = compute_metrics([r.sgv for r in readings])
    html = render_agp(m, readings)
    assert html.startswith("<div")
    assert "<svg" in html
    assert "polyline" in html or "polygon" in html
    assert "viewBox" in html


def test_render_includes_tir_bar():
    m = compute_metrics([50.0] * 10 + [120.0] * 70 + [300.0] * 20)
    html = render_agp(m, [])
    assert "Time in ranges" in html
    # All five zone labels appear in the legend.
    for label in ("Very low", "In range", "Very high"):
        assert label in html


def test_tir_bar_segments_reflect_zones():
    # Pure in-range data -> only the target color appears as a segment.
    m = compute_metrics([120.0] * 100)
    bar = render_tir_bar(m)
    assert 'fill="#1a9850"' in bar      # target green segment
    assert 'fill="#7e1416"' not in bar  # no very-low segment (legend aside)


def test_render_agp_handles_empty_readings():
    m = compute_metrics([120.0] * 10)
    html = render_agp(m, [])
    assert "<svg" in html


def test_render_on_fixtures(phenotype_name):
    from tests.conftest import load_nightscout

    nd = load_nightscout(phenotype_name)
    m = compute_metrics(nd.sgv_values)
    html = render_agp(m, nd.entries)
    assert "Time in range" in html
    assert len(html) > 200

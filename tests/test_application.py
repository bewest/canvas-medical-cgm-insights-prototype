"""Tests for the CGM chart Application view renderer."""

import pytest

pytest.importorskip("canvas_sdk")

from cgm_insights.applications.cgm_app import render_view  # noqa: E402
from cgm_insights.core.demo_data import demo_nightscout  # noqa: E402
from cgm_insights.core.nightscout import NightscoutData  # noqa: E402


def test_render_view_with_demo_data():
    html = render_view(demo_nightscout())
    assert "CGM Insights" in html
    assert "<svg" in html
    assert "Glycemic phenotype" in html
    # Demo data is hypo-prone -> safety banner present.
    assert "Review hypo safety plan" in html


def test_render_view_no_data():
    html = render_view(NightscoutData())
    assert "No Nightscout CGM data" in html


def test_application_imports_and_identifier():
    from cgm_insights.applications.cgm_app import CGMChartApp, CGMGlobalApp

    # Application classes expose a stable identifier property.
    assert CGMChartApp.__name__ == "CGMChartApp"
    assert CGMGlobalApp.__name__ == "CGMGlobalApp"

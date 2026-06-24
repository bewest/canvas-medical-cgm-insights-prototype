"""Patient-chart Application: a launchable CGM Insights view.

Registers an application icon in the patient chart. When opened, it renders the
AGP-style CGM summary in a right-hand chart pane via ``LaunchModalEffect``.

This is a non-intrusive alternative to the chart-summary custom section: it adds
a launcher the clinician can click, without replacing the global chart-summary
layout (``SHOW_PATIENT_CHART_SUMMARY_SECTIONS``), which would affect every
patient on the instance.
"""

from canvas_sdk.effects import Effect
from canvas_sdk.effects.launch_modal import LaunchModalEffect
from canvas_sdk.handlers.application import Application
from logger import log

from cgm_insights.core.agp import render_agp
from cgm_insights.core.metrics import compute_metrics
from cgm_insights.core.nightscout import NightscoutData
from cgm_insights.core.triage import classify, hypo_safety_check
from cgm_insights.handlers._data import load_patient_cgm

_NO_DATA_HTML = (
    '<div style="font-family:sans-serif;color:#6b7280;font-size:13px;padding:16px">'
    "No Nightscout CGM data available for this patient. "
    "Configure NIGHTSCOUT_URL or set DEMO_MODE.</div>"
)


def render_view(data: NightscoutData) -> str:
    """Render the full CGM view HTML (metrics + AGP + triage) from CGM data."""
    metrics = compute_metrics(data.sgv_values)
    if metrics is None:
        return _NO_DATA_HTML

    triage = classify(metrics)
    hypo = hypo_safety_check(metrics)
    banner = (
        f'<div style="background:#fffbeb;border:1px solid #fde68a;padding:8px;'
        f'border-radius:6px;margin:0 0 8px;font-size:13px">&#9888; {hypo.narrative}</div>'
        if hypo.triggered
        else ""
    )
    return (
        f'<div style="font-family:sans-serif;padding:16px;max-width:760px">'
        f'<h3 style="margin:0 0 4px">CGM Insights</h3>'
        f'<div style="font-size:13px;color:#374151;margin-bottom:8px">'
        f"Glycemic phenotype: <strong>{triage.label}</strong>. {triage.reason}</div>"
        f"{banner}{render_agp(metrics, data.entries)}</div>"
    )


class CGMChartApp(Application):
    """A patient-chart application that opens the CGM Insights view."""

    def on_open(self) -> Effect:
        """Render the CGM view in a right-hand chart pane."""
        data = load_patient_cgm(self.secrets)
        log.info(f"cgm_insights: chart app opened ({len(data.entries)} readings)")
        return LaunchModalEffect(
            content=render_view(data),
            target=LaunchModalEffect.TargetType.RIGHT_CHART_PANE_LARGE,
            title="CGM Insights",
        ).apply()


class CGMGlobalApp(Application):
    """A global (app-drawer) application that opens the CGM Insights view.

    Scoped globally so it appears in the top-level app drawer (alongside other
    global apps) without requiring a patient context. Renders the same view; in
    demo mode it shows the synthetic series.
    """

    def on_open(self) -> Effect:
        """Render the CGM view as a full page from the global app drawer."""
        data = load_patient_cgm(self.secrets)
        log.info(f"cgm_insights: global app opened ({len(data.entries)} readings)")
        return LaunchModalEffect(
            content=render_view(data),
            target=LaunchModalEffect.TargetType.PAGE,
            title="CGM Insights",
        ).apply()

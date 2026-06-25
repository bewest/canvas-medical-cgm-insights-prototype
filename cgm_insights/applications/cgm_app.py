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
from cgm_insights.core.demo_data import (
    DEMO_PHENOTYPES,
    PHENOTYPE_LABELS,
    demo_nightscout,
)
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


def render_cohort() -> str:
    """Render a gallery of every demo phenotype (AGP + triage + metrics).

    Lets a reviewer see each phenotype at high fidelity in one scrollable view,
    rendered from the embedded synthetic series (no Nightscout, no PHI).
    """
    cards = []
    for name in DEMO_PHENOTYPES:
        nd = demo_nightscout(name)
        metrics = compute_metrics(nd.sgv_values)
        if metrics is None:
            continue
        triage = classify(metrics)
        label = PHENOTYPE_LABELS.get(name, name)
        cards.append(
            f'<section style="border:1px solid #e5e7eb;border-radius:12px;'
            f'padding:16px;margin:0 0 16px">'
            f'<h3 style="margin:0 0 2px">{label}'
            f'<span style="font-size:12px;color:#6b7280;font-weight:400"> &middot; '
            f"triage: {triage.label}</span></h3>"
            f'<div style="font-size:12px;color:#6b7280;margin-bottom:8px">{triage.reason}</div>'
            f"{render_agp(metrics, nd.entries)}</section>"
        )
    return (
        '<div style="font-family:sans-serif;padding:16px;max-width:820px">'
        '<h2 style="margin:0 0 4px">CGM Insights &mdash; phenotype cohort</h2>'
        '<p style="font-size:13px;color:#6b7280;margin:0 0 16px">Synthetic, '
        "de-identified demo cohort. Each panel is an Ambulatory Glucose Profile "
        "(median + IQR by time of day) with the computed triage.</p>"
        + "".join(cards)
        + "</div>"
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
    """A global (app-drawer) application that opens the CGM phenotype cohort.

    Scoped globally so it appears in the top-level app drawer. Renders every
    demo phenotype at high fidelity in one page, so each can be inspected in the
    sandbox without per-patient configuration.
    """

    def on_open(self) -> Effect:
        """Render the full phenotype cohort gallery as a page."""
        log.info(f"cgm_insights: global cohort opened ({len(DEMO_PHENOTYPES)} phenotypes)")
        return LaunchModalEffect(
            content=render_cohort(),
            target=LaunchModalEffect.TargetType.PAGE,
            title="CGM Insights — cohort",
        ).apply()

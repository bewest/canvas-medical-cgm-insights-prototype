"""CGM summary display: a custom patient-chart section (NS/AGP style).

Renders the inline AGP + metrics HTML produced by ``core.agp`` into a
``PatientChartSummaryCustomSection`` effect.
"""

from __future__ import annotations

from canvas_sdk.effects import Effect
from canvas_sdk.effects.patient_chart_summary_custom_section import (
    PatientChartSummaryCustomSection,
)
from canvas_sdk.handlers.patient_chart_summary_custom_section_handler import (
    PatientChartSummaryCustomSectionHandler,
)

from cgm_insights.core.agp import render_agp
from cgm_insights.core.metrics import compute_metrics
from cgm_insights.handlers._data import load_patient_cgm

_NO_DATA_HTML = (
    '<div style="font-family:sans-serif;color:#6b7280;font-size:13px">'
    "No Nightscout CGM data available for this patient.</div>"
)


class CGMSummarySection(PatientChartSummaryCustomSectionHandler):
    """Custom chart section showing an AGP-style CGM summary."""

    SECTION_KEY = "cgm_insights_summary"

    def handle(self) -> list[Effect]:
        """Fetch CGM data, compute metrics, render the AGP section."""
        data = load_patient_cgm(self.secrets)
        metrics = compute_metrics(data.sgv_values)

        if metrics is None:
            content = _NO_DATA_HTML
        else:
            content = render_agp(metrics, data.entries)

        return [
            PatientChartSummaryCustomSection(
                content=content,
                icon="activity",
            ).apply()
        ]

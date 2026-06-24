"""Glycemic phenotype triage: surfaces a ProtocolCard and an optional
hypoglycemia-safety banner when an encounter note is created.

Triggered on ``NOTE_STATE_CHANGE_EVENT_CREATED`` (i.e., a visit), which is
permitted to emit protocol cards and banner alerts. ``PATIENT_CHART_SUMMARY__
SECTION_CONFIGURATION`` is deliberately NOT used here because the platform
forbids these effect types from that event.
"""

from __future__ import annotations

from canvas_sdk.effects import Effect
from canvas_sdk.effects.banner_alert import AddBannerAlert
from canvas_sdk.effects.protocol_card import ProtocolCard, Recommendation
from canvas_sdk.events import EventType
from canvas_sdk.handlers import BaseHandler

from cgm_insights.core.metrics import compute_metrics
from cgm_insights.core.triage import Phenotype, classify, hypo_safety_check
from cgm_insights.handlers._data import load_patient_cgm

# Suggested next action per phenotype (title shown on the card recommendation).
_RECOMMENDATIONS: dict[Phenotype, list[tuple[str, str]]] = {
    Phenotype.HYPO_PRONE: [
        ("Review hypoglycemia safety plan", "Review"),
        ("Consider loosening glucose targets / glucagon Rx", "Plan"),
    ],
    Phenotype.HYPER_PRONE: [
        ("Order HbA1c", "Order"),
        ("Settings review / therapy intensification", "Review"),
    ],
    Phenotype.HIGH_VARIABILITY: [
        ("Investigate meal timing, missed boluses, pump-site issues", "Review"),
    ],
    Phenotype.AT_GOAL: [
        ("At goal \u2014 reinforce current management", "Acknowledge"),
    ],
}

_CARD_KEY = "cgm_insights_triage"
_BANNER_KEY = "cgm_insights_hypo"


class CGMTriageProtocol(BaseHandler):
    """Compute a glycemic phenotype and surface triage effects."""

    RESPONDS_TO = EventType.Name(EventType.NOTE_STATE_CHANGE_EVENT_CREATED)

    def compute(self) -> list[Effect]:
        """Fetch CGM data, classify phenotype, emit card + optional banner."""
        patient_id = (self.context or {}).get("patient_id")
        if not patient_id:
            return []

        data = load_patient_cgm(self.secrets)
        metrics = compute_metrics(data.sgv_values)
        if metrics is None:
            return []

        result = classify(metrics)
        if result.phenotype == Phenotype.INSUFFICIENT_DATA:
            return []

        effects = build_triage_effects(patient_id, metrics, result_phenotype=result.phenotype,
                                       result_reason=result.reason,
                                       result_label=result.label,
                                       hypo=hypo_safety_check(metrics))
        return effects


def build_triage_effects(patient_id, metrics, *, result_phenotype, result_reason,
                         result_label, hypo) -> list[Effect]:
    """Build the ProtocolCard (+ optional banner) effects for a triage result.

    Separated from ``compute`` so the effect construction is unit-testable
    without a full event/handler instance.
    """
    narrative = (
        f"{result_label}. {result_reason} "
        f"TIR {metrics.tir:.0f}%, GMI {metrics.gmi:.1f}%, %CV {metrics.cv:.0f}%."
    )

    card = ProtocolCard(
        patient_id=str(patient_id),
        key=_CARD_KEY,
        title=f"CGM triage: {result_label}",
        narrative=narrative,
        status=ProtocolCard.Status.DUE,
    )
    for title, button in _RECOMMENDATIONS.get(result_phenotype, []):
        card.recommendations.append(Recommendation(title=title, button=button))

    effects: list[Effect] = [card.apply()]

    if hypo.triggered:
        effects.append(
            AddBannerAlert(
                patient_id=str(patient_id),
                key=_BANNER_KEY,
                narrative=hypo.narrative,
                placement=[AddBannerAlert.Placement.CHART],
                intent=AddBannerAlert.Intent.WARNING,
            ).apply()
        )

    return effects

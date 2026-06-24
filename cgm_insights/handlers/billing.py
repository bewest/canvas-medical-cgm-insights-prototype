"""Billing-readiness documentation (M2).

On encounter creation, when CGM data-sufficiency thresholds are met, emits:
  * a codified CGM summary ``Observation`` (the billable derived data), and
  * a review/sign ``ProtocolCard`` surfacing the eligible CPT code(s) and the
    interpretation, routing the clinician to review and sign.

Honest boundaries (see docs/plan.html):
  * No raw CGM stream is written; only a low-cardinality summary panel.
  * No claim is submitted and no billing line item is auto-added. The eligible
    code is surfaced for clinician confirmation; the practice's billing logic
    decides. CGM/RPM codes carry bundling rules.
"""


from datetime import datetime, timezone

from canvas_sdk.effects import Effect
from canvas_sdk.effects.observation.base import (
    CodingData,
    Observation,
    ObservationComponentData,
)
from canvas_sdk.effects.protocol_card import ProtocolCard, Recommendation
from canvas_sdk.events import EventType
from canvas_sdk.handlers import BaseHandler
from logger import log

from cgm_insights.core.billing import (
    BillingArtifacts,
    assess_sufficiency,
    build_billing_artifacts,
)
from cgm_insights.core.metrics import compute_metrics
from cgm_insights.handlers._data import load_patient_cgm

_CARD_KEY = "cgm_insights_billing"


class CGMBillingDocumentation(BaseHandler):
    """Emit codified CGM summary + a review/sign prompt when data-sufficient."""

    RESPONDS_TO = EventType.Name(EventType.NOTE_STATE_CHANGE_EVENT_CREATED)

    def compute(self) -> list[Effect]:
        """Gate on sufficiency, then emit the summary Observation + card."""
        ctx = self.context or {}
        patient_id = ctx.get("patient_id")
        if not patient_id:
            return []

        data = load_patient_cgm(self.secrets)
        metrics = compute_metrics(data.sgv_values)
        if metrics is None:
            return []

        suff = assess_sufficiency(data.entries)
        if not suff.any_eligible:
            # Not enough data to support any billing code yet; emit nothing.
            log.info(
                f"cgm_insights: billing skipped, data not yet sufficient "
                f"({suff.hours:.0f}h, {suff.days_with_data}d)"
            )
            return []

        log.info(f"cgm_insights: billing-ready, eligible CPT {suff.eligible_codes}")
        artifacts = build_billing_artifacts(metrics, suff)
        return build_billing_effects(str(patient_id), artifacts)


def _observation_effect(patient_id: str, artifacts: BillingArtifacts) -> Effect:
    """Build the codified CGM summary Observation effect from artifacts."""
    panel_system, panel_code, panel_display = artifacts.panel_code
    components = [
        ObservationComponentData(
            value_quantity=c.value,
            value_quantity_unit=c.unit,
            name=c.name,
            codings=[CodingData(code=c.code, display=c.display, system=c.system)],
        )
        for c in artifacts.components
    ]
    observation = Observation(
        patient_id=patient_id,
        name=panel_display,
        category="vital-signs",
        effective_datetime=datetime.now(tz=timezone.utc),
        codings=[
            CodingData(code=panel_code, display=panel_display, system=panel_system)
        ],
        components=components,
    )
    return observation.create()


def build_billing_effects(patient_id: str, artifacts: BillingArtifacts) -> list[Effect]:
    """Build the Observation + review/sign ProtocolCard effects.

    Separated from ``compute`` for unit testing without a handler instance.
    """
    effects: list[Effect] = [_observation_effect(patient_id, artifacts)]

    codes = ", ".join(artifacts.eligible_codes)
    card = ProtocolCard(
        patient_id=patient_id,
        key=_CARD_KEY,
        title=f"CGM report ready for review (CPT {codes})",
        narrative=artifacts.interpretation,
        status=ProtocolCard.Status.DUE,
    )
    card.recommendations.append(
        Recommendation(title="Review CGM report and sign", button="Review")
    )
    for code in artifacts.eligible_codes:
        card.recommendations.append(
            Recommendation(title=f"Confirm CPT {code} charge", button="Confirm")
        )
    effects.append(card.apply())

    return effects

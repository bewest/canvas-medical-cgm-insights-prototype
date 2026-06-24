"""Billing-readiness logic (SDK-free).

Computes data-sufficiency for the CGM/RPM billing codes and builds the
structured summary + interpretation text that back the documentation chain.

This module produces *readiness signals and documentation*, not claims. The
clinician reviews and signs; the practice's billing logic decides what is
actually billed. CGM (95249/95250/95251) and RPM (99453/99454/99457) codes
carry bundling rules, so eligible codes are surfaced, never auto-billed.

Terminology codes: ``MEAN_GLUCOSE`` uses a real LOINC code; the remaining CGM
summary metrics use a local code system and MUST be mapped to the practice's
terminology (LOINC/SNOMED) before production use. They are centralized here so
that mapping is a one-line change.
"""


from dataclasses import dataclass, field

from cgm_insights.core.metrics import CGMMetrics, estimated_hours
from cgm_insights.core.nightscout import GlucoseReading

# --- Billing thresholds (Medicare/CPT) ---
CPT_95251_MIN_HOURS = 72.0    # CGM interpretation & report: >= 72 h of data
CPT_99454_MIN_DAYS = 16       # RPM device data: >= 16 days with readings / 30

# --- Terminology codes (system, code, display) ---
# VERIFY all non-LOINC codes against the practice's terminology before production.
LOINC = "http://loinc.org"
LOCAL = "https://github.com/cgm-insights/metrics"  # placeholder; map to LOINC

CODE_MEAN_GLUCOSE = (LOINC, "27353-2", "Glucose mean value")          # real LOINC
CODE_GMI = (LOCAL, "gmi", "Glucose Management Indicator")            # VERIFY -> LOINC
CODE_TIR = (LOCAL, "tir", "Time in range 70-180 mg/dL (%)")          # VERIFY
CODE_TBR = (LOCAL, "tbr", "Time below range <70 mg/dL (%)")          # VERIFY
CODE_TAR = (LOCAL, "tar", "Time above range >180 mg/dL (%)")         # VERIFY
CODE_CV = (LOCAL, "cv", "Coefficient of variation (%)")              # VERIFY

# The summary panel itself.
CODE_CGM_PANEL = (LOINC, "104643-2", "Continuous glucose monitoring report")  # VERIFY


@dataclass
class SufficiencyResult:
    """Whether the CGM window meets billing data-sufficiency thresholds."""

    n_readings: int
    hours: float
    days_with_data: int
    eligible_95251: bool
    eligible_99454: bool

    @property
    def eligible_codes(self) -> list[str]:
        """CPT codes whose data-sufficiency thresholds are met."""
        codes = []
        if self.eligible_95251:
            codes.append("95251")
        if self.eligible_99454:
            codes.append("99454")
        return codes

    @property
    def any_eligible(self) -> bool:
        """True if at least one billing code's data gate is met."""
        return bool(self.eligible_codes)


def count_days_with_data(readings: list[GlucoseReading]) -> int:
    """Count distinct UTC calendar days that contain at least one reading."""
    return len({r.dt.date() for r in readings})


def assess_sufficiency(readings: list[GlucoseReading]) -> SufficiencyResult:
    """Evaluate billing data-sufficiency from a list of glucose readings."""
    n = len(readings)
    hours = estimated_hours(n)
    days = count_days_with_data(readings)
    return SufficiencyResult(
        n_readings=n,
        hours=hours,
        days_with_data=days,
        eligible_95251=hours >= CPT_95251_MIN_HOURS,
        eligible_99454=days >= CPT_99454_MIN_DAYS,
    )


@dataclass
class SummaryComponent:
    """One coded value in the CGM summary panel."""

    name: str
    value: str
    unit: str
    system: str
    code: str
    display: str


@dataclass
class BillingArtifacts:
    """Everything needed to emit the billing-readiness effects."""

    panel_code: tuple[str, str, str]
    components: list[SummaryComponent] = field(default_factory=list)
    interpretation: str = ""
    eligible_codes: list[str] = field(default_factory=list)


def _component(metric_code: tuple[str, str, str], name: str, value: float, unit: str) -> SummaryComponent:
    system, code, display = metric_code
    return SummaryComponent(
        name=name, value=f"{value}", unit=unit, system=system, code=code, display=display
    )


def build_interpretation(metrics: CGMMetrics, suff: SufficiencyResult) -> str:
    """Build the human-readable CGM interpretation narrative (report body)."""
    codes = ", ".join(suff.eligible_codes) if suff.eligible_codes else "none yet"
    return (
        f"Continuous glucose monitoring summary over {suff.days_with_data} day(s) "
        f"({suff.hours:.0f} h of data, {metrics.n} readings). "
        f"Time in range (70-180 mg/dL): {metrics.tir:.0f}%. "
        f"Time below range (<70): {metrics.tbr:.1f}% (<54: {metrics.tbr_l2:.1f}%). "
        f"Time above range (>180): {metrics.tar:.0f}%. "
        f"Mean glucose {metrics.mean:.0f} mg/dL, GMI {metrics.gmi:.1f}%, %CV {metrics.cv:.0f}%. "
        f"Data-sufficient billing code(s): {codes}. "
        f"Clinician review and signature required before billing."
    )


def build_billing_artifacts(
    metrics: CGMMetrics, suff: SufficiencyResult
) -> BillingArtifacts:
    """Assemble the coded summary components + interpretation for documentation."""
    components = [
        _component(CODE_MEAN_GLUCOSE, "Mean glucose", metrics.mean, "mg/dL"),
        _component(CODE_GMI, "GMI", metrics.gmi, "%"),
        _component(CODE_TIR, "Time in range", metrics.tir, "%"),
        _component(CODE_TBR, "Time below range", metrics.tbr, "%"),
        _component(CODE_TAR, "Time above range", metrics.tar, "%"),
        _component(CODE_CV, "Coefficient of variation", metrics.cv, "%"),
    ]
    return BillingArtifacts(
        panel_code=CODE_CGM_PANEL,
        components=components,
        interpretation=build_interpretation(metrics, suff),
        eligible_codes=suff.eligible_codes,
    )

"""Glycemic phenotype triage.

Rule-based classification of a patient's recent CGM window into one of a small
set of actionable phenotypes, plus a hypoglycemia-safety check. Thresholds are
aligned with the ADA/EASD CGM consensus (Battelino 2019).

This is intentionally rule-based and transparent: it is descriptive triage, not
a dosing recommendation. Anything that proposes insulin/parameter changes lives
behind the validated sidecar, not here.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .metrics import (
    CGMMetrics,
    HIGH_CV_THRESHOLD,
    TBR_GOAL,
    TIR_GOAL,
)

# Time-below-range thresholds for the hypo-safety check.
TBR_L2_ALERT = 1.0   # % time < 54 mg/dL that warrants attention
TBR_ALERT = TBR_GOAL  # % time < 70 mg/dL that warrants attention

# Time-above-range threshold separating hyper-prone from at-goal patterns.
TAR_HYPER = 25.0     # % time > 180 mg/dL


class Phenotype(str, Enum):
    """Coarse glycemic phenotype for triage and outreach prioritization."""

    HYPO_PRONE = "hypo_prone"
    HYPER_PRONE = "hyper_prone"
    HIGH_VARIABILITY = "high_variability"
    AT_GOAL = "at_goal"
    INSUFFICIENT_DATA = "insufficient_data"


# Lower number = higher clinical priority (sorts first in a cohort panel).
PHENOTYPE_PRIORITY: dict[Phenotype, int] = {
    Phenotype.HYPO_PRONE: 0,
    Phenotype.HIGH_VARIABILITY: 1,
    Phenotype.HYPER_PRONE: 2,
    Phenotype.AT_GOAL: 3,
    Phenotype.INSUFFICIENT_DATA: 4,
}

PHENOTYPE_LABEL: dict[Phenotype, str] = {
    Phenotype.HYPO_PRONE: "Hypoglycemia-prone",
    Phenotype.HYPER_PRONE: "Hyperglycemia-prone",
    Phenotype.HIGH_VARIABILITY: "High variability",
    Phenotype.AT_GOAL: "At goal",
    Phenotype.INSUFFICIENT_DATA: "Insufficient data",
}


@dataclass
class TriageResult:
    """Outcome of phenotype triage for one patient."""

    phenotype: Phenotype
    reason: str
    priority: int

    @property
    def label(self) -> str:
        """Human-readable phenotype label."""
        return PHENOTYPE_LABEL[self.phenotype]


def classify(metrics: CGMMetrics | None) -> TriageResult:
    """Classify a CGM window into a glycemic phenotype.

    Priority order is intentional and safety-first:
      1. Hypo-prone  (TBR >4% OR any meaningful Level-2 hypo) -- checked first.
      2. High variability (%CV >= 36%).
      3. Hyper-prone (TIR <70% driven by TAR >25%).
      4. At goal (TIR >=70%, TBR <4%, CV <36%).

    A patient can satisfy several rules; the most clinically urgent wins.
    """
    if metrics is None or metrics.n == 0:
        return TriageResult(
            phenotype=Phenotype.INSUFFICIENT_DATA,
            reason="No CGM readings available.",
            priority=PHENOTYPE_PRIORITY[Phenotype.INSUFFICIENT_DATA],
        )

    # 1. Hypoglycemia risk takes precedence over everything else.
    if metrics.tbr > TBR_ALERT or metrics.tbr_l2 >= TBR_L2_ALERT:
        return TriageResult(
            phenotype=Phenotype.HYPO_PRONE,
            reason=(
                f"Time below range {metrics.tbr:.1f}% (goal <{TBR_GOAL:.0f}%), "
                f"time <54 mg/dL {metrics.tbr_l2:.1f}%."
            ),
            priority=PHENOTYPE_PRIORITY[Phenotype.HYPO_PRONE],
        )

    # 2. High variability, regardless of mean.
    if metrics.cv >= HIGH_CV_THRESHOLD:
        return TriageResult(
            phenotype=Phenotype.HIGH_VARIABILITY,
            reason=f"Glucose variability %CV {metrics.cv:.1f}% (goal <{HIGH_CV_THRESHOLD:.0f}%).",
            priority=PHENOTYPE_PRIORITY[Phenotype.HIGH_VARIABILITY],
        )

    # 3. Hyperglycemia-prone: below-target TIR driven by time above range.
    if metrics.tir < TIR_GOAL and metrics.tar > TAR_HYPER:
        return TriageResult(
            phenotype=Phenotype.HYPER_PRONE,
            reason=(
                f"Time in range {metrics.tir:.1f}% (goal >={TIR_GOAL:.0f}%), "
                f"time above range {metrics.tar:.1f}%."
            ),
            priority=PHENOTYPE_PRIORITY[Phenotype.HYPER_PRONE],
        )

    # 4. Default: at goal.
    return TriageResult(
        phenotype=Phenotype.AT_GOAL,
        reason=(
            f"Time in range {metrics.tir:.1f}%, time below range {metrics.tbr:.1f}%, "
            f"%CV {metrics.cv:.1f}%."
        ),
        priority=PHENOTYPE_PRIORITY[Phenotype.AT_GOAL],
    )


@dataclass
class HypoSafetyFlag:
    """Result of the hypoglycemia-safety check."""

    triggered: bool
    narrative: str  # kept <= 90 chars for Canvas AddBannerAlert


def hypo_safety_check(metrics: CGMMetrics | None) -> HypoSafetyFlag:
    """Evaluate whether a hypoglycemia-safety banner should be shown.

    The narrative is capped at 90 characters to satisfy the Canvas
    ``AddBannerAlert.narrative`` constraint.
    """
    if metrics is None:
        return HypoSafetyFlag(triggered=False, narrative="")

    if metrics.tbr > TBR_ALERT or metrics.tbr_l2 >= TBR_L2_ALERT:
        narrative = (
            f"Time below range {metrics.tbr:.1f}% (goal <4%). Review hypo safety plan."
        )
        return HypoSafetyFlag(triggered=True, narrative=narrative[:90])

    return HypoSafetyFlag(triggered=False, narrative="")

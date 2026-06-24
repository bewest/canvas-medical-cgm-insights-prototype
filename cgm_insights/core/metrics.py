"""Descriptive CGM metrics in pure Python.

All standard ambulatory CGM metrics computed with only sandbox-allowed
builtins (``sum``, ``sorted``, ``min``, ``max``, ``len``, ``round`` and the
``**`` operator). No numpy / scipy / statistics / math import is required, so
this runs unchanged inside the Canvas RestrictedPython sandbox.

References:
  * Battelino et al. 2019 (ADA/EASD CGM consensus): TIR/TBR/TAR targets,
    %CV >= 36% as the high-variability threshold.
  * Bergenstal et al. 2018: GMI = 3.31 + 0.02392 * mean_glucose_mgdl.
"""


from dataclasses import dataclass

# Standard glycemic range boundaries (mg/dL).
TIR_LOW = 70.0      # lower bound of time-in-range
TIR_HIGH = 180.0    # upper bound of time-in-range
LEVEL2_LOW = 54.0   # clinically significant hypoglycemia (Level 2)
LEVEL2_HIGH = 250.0  # clinically significant hyperglycemia (Level 2)

# Consensus targets / thresholds.
HIGH_CV_THRESHOLD = 36.0   # %CV >= 36% indicates unstable glucose
TIR_GOAL = 70.0            # >=70% time-in-range is the general goal
TBR_GOAL = 4.0             # <4% time-below-range is the general safety goal

# A 5-minute-cadence CGM yields 288 readings/day; used to convert a reading
# count into an approximate hours-of-data figure for billing sufficiency.
READINGS_PER_DAY = 288
MINUTES_PER_READING = 5


@dataclass
class CGMMetrics:
    """Computed CGM metrics for a window of glucose readings."""

    n: int
    mean: float
    gmi: float
    cv: float
    std: float
    tir: float       # % 70-180
    tbr: float       # % < 70
    tbr_l2: float    # % < 54
    tar: float       # % > 180
    tar_l2: float    # % > 250
    p05: float
    p25: float
    p50: float
    p75: float
    p95: float

    def as_dict(self) -> dict:
        """Plain dict for JSON serialization / templating."""
        return {
            "n": self.n,
            "mean": self.mean,
            "gmi": self.gmi,
            "cv": self.cv,
            "std": self.std,
            "tir": self.tir,
            "tbr": self.tbr,
            "tbr_l2": self.tbr_l2,
            "tar": self.tar,
            "tar_l2": self.tar_l2,
            "p05": self.p05,
            "p25": self.p25,
            "p50": self.p50,
            "p75": self.p75,
            "p95": self.p95,
        }


def _percentile(sorted_vals: list[float], p: float) -> float:
    """Nearest-rank percentile of an already-sorted list.

    ``p`` is a fraction in [0, 1]. Returns 0.0 for an empty list.
    """
    n = len(sorted_vals)
    if n == 0:
        return 0.0
    idx = int(p * (n - 1) + 0.5)  # nearest-rank, rounded
    idx = max(0, min(n - 1, idx))
    return sorted_vals[idx]


def _pct(count: int, total: int) -> float:
    """Percentage of ``count`` out of ``total``, rounded to 1 dp."""
    if total == 0:
        return 0.0
    return round(100.0 * count / total, 1)


def compute_metrics(sgv: list[float]) -> CGMMetrics | None:
    """Compute CGM metrics from a list of glucose values in mg/dL.

    Returns ``None`` when there are no readings. Uses only sandbox-allowed
    builtins; standard deviation is computed via the ``** 0.5`` operator
    rather than ``math.sqrt``.
    """
    n = len(sgv)
    if n == 0:
        return None

    mean = sum(sgv) / n
    variance = sum((x - mean) ** 2 for x in sgv) / n
    std = variance ** 0.5
    cv = (std / mean * 100.0) if mean else 0.0
    gmi = 3.31 + 0.02392 * mean

    in_range = sum(1 for x in sgv if TIR_LOW <= x <= TIR_HIGH)
    below = sum(1 for x in sgv if x < TIR_LOW)
    below_l2 = sum(1 for x in sgv if x < LEVEL2_LOW)
    above = sum(1 for x in sgv if x > TIR_HIGH)
    above_l2 = sum(1 for x in sgv if x > LEVEL2_HIGH)

    ordered = sorted(sgv)

    return CGMMetrics(
        n=n,
        mean=round(mean, 1),
        gmi=round(gmi, 1),
        cv=round(cv, 1),
        std=round(std, 1),
        tir=_pct(in_range, n),
        tbr=_pct(below, n),
        tbr_l2=_pct(below_l2, n),
        tar=_pct(above, n),
        tar_l2=_pct(above_l2, n),
        p05=round(_percentile(ordered, 0.05), 1),
        p25=round(_percentile(ordered, 0.25), 1),
        p50=round(_percentile(ordered, 0.50), 1),
        p75=round(_percentile(ordered, 0.75), 1),
        p95=round(_percentile(ordered, 0.95), 1),
    )


def estimated_hours(n_readings: int) -> float:
    """Approximate hours of CGM data from a reading count (5-min cadence)."""
    return round(n_readings * MINUTES_PER_READING / 60.0, 1)

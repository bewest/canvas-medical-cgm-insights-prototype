"""Tests for cgm_insights.core.billing (data sufficiency + artifacts)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from cgm_insights.core.billing import (
    CPT_95251_MIN_HOURS,
    CPT_99454_MIN_DAYS,
    assess_sufficiency,
    build_billing_artifacts,
    build_interpretation,
    count_days_with_data,
)
from cgm_insights.core.metrics import compute_metrics
from cgm_insights.core.nightscout import GlucoseReading


def _readings(days: int, per_day: int = 288, start=None) -> list[GlucoseReading]:
    """Build evenly-spaced readings spanning `days` calendar days."""
    start = start or datetime(2026, 1, 1, tzinfo=timezone.utc)
    out = []
    step = timedelta(minutes=5)
    t = start
    for _ in range(days):
        day_t = t
        for _ in range(per_day):
            out.append(GlucoseReading(epoch_ms=int(day_t.timestamp() * 1000), sgv=120.0))
            day_t += step
        t += timedelta(days=1)
    return out


def test_count_days_with_data():
    readings = _readings(days=5, per_day=10)
    assert count_days_with_data(readings) == 5


def test_sufficiency_below_thresholds():
    # 2 days of data: < 72h and < 16 days.
    suff = assess_sufficiency(_readings(days=2))
    assert suff.eligible_95251 is False
    assert suff.eligible_99454 is False
    assert suff.eligible_codes == []
    assert suff.any_eligible is False


def test_sufficiency_95251_met_99454_not():
    # 4 full days = 96h >= 72h (95251 yes); 4 days < 16 (99454 no).
    suff = assess_sufficiency(_readings(days=4))
    assert suff.hours >= CPT_95251_MIN_HOURS
    assert suff.eligible_95251 is True
    assert suff.eligible_99454 is False
    assert suff.eligible_codes == ["95251"]


def test_sufficiency_both_met():
    suff = assess_sufficiency(_readings(days=CPT_99454_MIN_DAYS))
    assert suff.eligible_95251 is True
    assert suff.eligible_99454 is True
    assert suff.eligible_codes == ["95251", "99454"]


def test_artifacts_have_six_components():
    readings = _readings(days=4)
    metrics = compute_metrics([r.sgv for r in readings])
    suff = assess_sufficiency(readings)
    art = build_billing_artifacts(metrics, suff)
    names = [c.name for c in art.components]
    assert "Mean glucose" in names
    assert "Time in range" in names
    assert len(art.components) == 6
    assert art.eligible_codes == ["95251"]


def test_interpretation_mentions_signature_requirement():
    readings = _readings(days=4)
    metrics = compute_metrics([r.sgv for r in readings])
    suff = assess_sufficiency(readings)
    text = build_interpretation(metrics, suff)
    assert "signature" in text.lower()
    assert "95251" in text


def test_mean_glucose_uses_loinc():
    from cgm_insights.core.billing import CODE_MEAN_GLUCOSE

    system, code, _ = CODE_MEAN_GLUCOSE
    assert system == "http://loinc.org"
    assert code == "27353-2"

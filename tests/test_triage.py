"""Tests for cgm_insights.core.triage classification and hypo safety."""

from __future__ import annotations

from cgm_insights.core.metrics import compute_metrics
from cgm_insights.core.triage import (
    Phenotype,
    classify,
    hypo_safety_check,
)


def test_insufficient_data():
    result = classify(None)
    assert result.phenotype == Phenotype.INSUFFICIENT_DATA


def test_hypo_takes_priority_over_everything():
    # High variability AND hypo present -> hypo wins (safety first).
    sgv = [40.0] * 20 + [300.0] * 20 + [120.0] * 60
    m = compute_metrics(sgv)
    result = classify(m)
    assert result.phenotype == Phenotype.HYPO_PRONE
    assert result.priority == 0


def test_at_goal():
    m = compute_metrics([110.0] * 100)
    result = classify(m)
    assert result.phenotype == Phenotype.AT_GOAL


def test_hyper_prone():
    # Below-target TIR driven by highs, no lows, low CV (<36%).
    sgv = [170.0] * 50 + [220.0] * 50
    m = compute_metrics(sgv)
    assert m.cv < 36.0  # guard: this pattern is low-variability
    result = classify(m)
    assert result.phenotype == Phenotype.HYPER_PRONE


def test_each_fixture_classifies_to_its_name(phenotype_name):
    from tests.conftest import load_nightscout

    nd = load_nightscout(phenotype_name)
    m = compute_metrics(nd.sgv_values)
    result = classify(m)
    assert result.phenotype.value == phenotype_name


def test_all_scenario_fixtures_match_expected(any_fixture_name):
    from tests.conftest import EXPECTED_CLASSIFICATION, load_nightscout

    nd = load_nightscout(any_fixture_name)
    m = compute_metrics(nd.sgv_values)
    result = classify(m)
    assert result.phenotype.value == EXPECTED_CLASSIFICATION[any_fixture_name]


def test_hypo_banner_narrative_within_90_chars():
    sgv = [40.0] * 30 + [120.0] * 70
    m = compute_metrics(sgv)
    flag = hypo_safety_check(m)
    assert flag.triggered is True
    assert 0 < len(flag.narrative) <= 90


def test_hypo_banner_not_triggered_at_goal():
    m = compute_metrics([110.0] * 100)
    flag = hypo_safety_check(m)
    assert flag.triggered is False
    assert flag.narrative == ""


def test_priority_ordering():
    # Hypo < high-variability < hyper < at-goal numerically.
    hypo = classify(compute_metrics([40.0] * 20 + [120.0] * 80))
    at_goal = classify(compute_metrics([110.0] * 100))
    assert hypo.priority < at_goal.priority

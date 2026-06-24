"""Tests for cgm_insights.core.metrics."""

from __future__ import annotations

import pytest

from cgm_insights.core.metrics import (
    compute_metrics,
    estimated_hours,
    READINGS_PER_DAY,
)


def test_empty_returns_none():
    assert compute_metrics([]) is None


def test_all_in_range():
    m = compute_metrics([100.0] * 100)
    assert m is not None
    assert m.n == 100
    assert m.mean == 100.0
    assert m.tir == 100.0
    assert m.tbr == 0.0
    assert m.tar == 0.0
    assert m.cv == 0.0  # zero variance


def test_std_without_math_module():
    # Values 0 and 100 -> mean 50, population std 50.
    m = compute_metrics([0.0, 100.0])
    assert m is not None
    assert m.std == 50.0


def test_gmi_formula():
    # GMI = 3.31 + 0.02392 * mean. mean=154 -> ~7.0%.
    m = compute_metrics([154.0] * 10)
    assert m is not None
    assert m.gmi == pytest.approx(3.31 + 0.02392 * 154.0, abs=0.05)


def test_tir_tbr_tar_partition():
    # 70 low, 70 in-range, 60 high -> percentages sum to 100.
    sgv = [50.0] * 70 + [120.0] * 70 + [300.0] * 60
    m = compute_metrics(sgv)
    assert m is not None
    assert m.tbr == 35.0
    assert m.tir == 35.0
    assert m.tar == 30.0
    assert round(m.tbr + m.tir + m.tar, 1) == 100.0


def test_level2_thresholds():
    sgv = [50.0] * 10 + [60.0] * 10 + [120.0] * 10 + [260.0] * 10
    m = compute_metrics(sgv)
    assert m is not None
    # tbr (<70) = 20 readings of 40; tbr_l2 (<54) = 10 readings of 50.
    assert m.tbr == 50.0
    assert m.tbr_l2 == 25.0
    assert m.tar_l2 == 25.0  # the 260s


def test_percentiles_ordering():
    m = compute_metrics([float(x) for x in range(1, 101)])
    assert m is not None
    assert m.p05 <= m.p25 <= m.p50 <= m.p75 <= m.p95


def test_estimated_hours():
    assert estimated_hours(READINGS_PER_DAY) == 24.0
    assert estimated_hours(0) == 0.0


def test_metrics_on_fixtures(phenotype_name):
    from tests.conftest import load_nightscout

    nd = load_nightscout(phenotype_name)
    m = compute_metrics(nd.sgv_values)
    assert m is not None
    assert m.n > 0
    # Percentages are well-formed.
    for pct in (m.tir, m.tbr, m.tar, m.tbr_l2, m.tar_l2):
        assert 0.0 <= pct <= 100.0

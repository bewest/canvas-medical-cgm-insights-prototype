"""Tests for cgm_insights.core.demo_data and demo-mode loading."""

from cgm_insights.core.billing import assess_sufficiency
from cgm_insights.core.demo_data import demo_nightscout
from cgm_insights.core.metrics import compute_metrics
from cgm_insights.core.triage import Phenotype, classify, hypo_safety_check


def test_demo_data_is_deterministic():
    a = demo_nightscout().sgv_values
    b = demo_nightscout().sgv_values
    assert a == b
    assert len(a) > 1000


def test_demo_data_is_hypo_prone_with_banner():
    nd = demo_nightscout()
    metrics = compute_metrics(nd.sgv_values)
    assert classify(metrics).phenotype == Phenotype.HYPO_PRONE
    assert hypo_safety_check(metrics).triggered is True


def test_demo_data_meets_both_billing_gates():
    nd = demo_nightscout()
    suff = assess_sufficiency(nd.entries)
    assert suff.eligible_95251 is True
    assert suff.eligible_99454 is True


def test_demo_mode_loader_returns_demo_data():
    # Importing the handler helper requires canvas_sdk (installed in dev env).
    import pytest

    pytest.importorskip("canvas_sdk")
    from cgm_insights.handlers._data import _demo_enabled, load_patient_cgm

    assert _demo_enabled({"DEMO_MODE": "1"}) is True
    assert _demo_enabled({"NIGHTSCOUT_URL": "demo"}) is True
    assert _demo_enabled({"NIGHTSCOUT_URL": "https://real.example"}) is False
    assert _demo_enabled({}) is False

    nd = load_patient_cgm({"DEMO_MODE": "true"})
    assert len(nd.entries) > 1000

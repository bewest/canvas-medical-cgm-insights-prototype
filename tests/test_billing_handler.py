"""Tests for the M2 billing-documentation handler (effect construction)."""

from __future__ import annotations

import json
import os

import pytest

pytest.importorskip("canvas_sdk")

from cgm_insights.core.billing import (  # noqa: E402
    assess_sufficiency,
    build_billing_artifacts,
)
from cgm_insights.core.metrics import compute_metrics  # noqa: E402
from cgm_insights.core.nightscout import parse_entries  # noqa: E402
from cgm_insights.handlers.billing import build_billing_effects  # noqa: E402

FIXTURE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "fixtures", "synthetic"
)


def _entries(name="at_goal"):
    with open(os.path.join(FIXTURE_DIR, f"{name}.json")) as fh:
        bundle = json.load(fh)
    return parse_entries(bundle["entries"])


def _artifacts(name="at_goal"):
    entries = _entries(name)
    metrics = compute_metrics([r.sgv for r in entries])
    suff = assess_sufficiency(entries)
    return build_billing_artifacts(metrics, suff), suff


def test_fixture_is_data_sufficient():
    # 14-day synthetic fixtures clear both thresholds.
    _, suff = _artifacts("at_goal")
    assert suff.eligible_95251 is True
    assert suff.eligible_99454 is True


def test_billing_effects_observation_and_card():
    artifacts, _ = _artifacts("hyper_prone")
    effects = build_billing_effects("patient-123", artifacts)
    # One Observation + one ProtocolCard.
    assert len(effects) == 2
    for eff in effects:
        assert hasattr(eff, "type")
        assert hasattr(eff, "payload")


def test_observation_payload_has_components():
    artifacts, _ = _artifacts("at_goal")
    effects = build_billing_effects("patient-123", artifacts)
    obs_payload = json.loads(effects[0].payload)
    # Effect payload wraps the observation under "data".
    assert "data" in obs_payload


def test_card_lists_eligible_cpt_codes():
    artifacts, _ = _artifacts("at_goal")
    effects = build_billing_effects("patient-123", artifacts)
    card_payload = json.dumps(json.loads(effects[1].payload))
    assert "95251" in card_payload
    assert "99454" in card_payload


def test_billing_handler_imports():
    import cgm_insights.handlers.billing as b

    assert b.CGMBillingDocumentation.RESPONDS_TO

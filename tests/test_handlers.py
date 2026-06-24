"""Tests for the handler layer (effect construction).

These import canvas_sdk (installed in the dev venv) and verify that effects are
built correctly. The SDK-free core is tested separately; here we only check the
glue translates a triage result into well-formed Canvas effects.
"""

from __future__ import annotations

import json
import os

import pytest

# Skip the whole module gracefully if the SDK isn't installed in this env.
pytest.importorskip("canvas_sdk")

from cgm_insights.core.metrics import compute_metrics  # noqa: E402
from cgm_insights.core.triage import classify, hypo_safety_check  # noqa: E402
from cgm_insights.handlers.triage import build_triage_effects  # noqa: E402

FIXTURE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "fixtures", "synthetic"
)


def _metrics(name):
    with open(os.path.join(FIXTURE_DIR, f"{name}.json")) as fh:
        bundle = json.load(fh)
    sgv = [e["sgv"] for e in bundle["entries"]]
    return compute_metrics(sgv)


def _effects_for(name):
    m = _metrics(name)
    r = classify(m)
    return build_triage_effects(
        "patient-123",
        m,
        result_phenotype=r.phenotype,
        result_reason=r.reason,
        result_label=r.label,
        hypo=hypo_safety_check(m),
    )


def test_at_goal_emits_single_card_no_banner():
    effects = _effects_for("at_goal")
    assert len(effects) == 1  # card only, no hypo banner


def test_hypo_emits_card_and_banner():
    effects = _effects_for("hypo_prone")
    assert len(effects) == 2  # card + hypo banner


def test_effects_are_applied_effect_objects():
    effects = _effects_for("hyper_prone")
    # .apply() returns an Effect with a type and payload.
    for eff in effects:
        assert hasattr(eff, "type")
        assert hasattr(eff, "payload")


def test_banner_narrative_within_90_chars():
    m = _metrics("hypo_prone")
    flag = hypo_safety_check(m)
    assert len(flag.narrative) <= 90


def test_handlers_import_cleanly():
    # Importing the handler modules must not raise (validates SDK import paths).
    import cgm_insights.handlers.chart_summary as cs
    import cgm_insights.handlers.triage as tr

    assert cs.CGMSummarySection.SECTION_KEY == "cgm_insights_summary"
    assert tr.CGMTriageProtocol.RESPONDS_TO

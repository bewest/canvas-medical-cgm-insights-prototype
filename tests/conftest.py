"""Shared pytest fixtures for cgm_insights tests."""

from __future__ import annotations

import json
import os

import pytest

from cgm_insights.core.nightscout import NightscoutData, parse_nightscout

FIXTURE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "fixtures", "synthetic"
)

PHENOTYPE_FIXTURES = ["at_goal", "hyper_prone", "hypo_prone", "high_variability"]


def load_bundle(name: str) -> dict:
    """Load a raw synthetic Nightscout bundle by name."""
    with open(os.path.join(FIXTURE_DIR, f"{name}.json")) as fh:
        return json.load(fh)


def load_nightscout(name: str) -> NightscoutData:
    """Load and parse a synthetic Nightscout bundle by name."""
    bundle = load_bundle(name)
    return parse_nightscout(
        bundle["entries"], bundle["devicestatus"], bundle["profile"]
    )


@pytest.fixture(params=PHENOTYPE_FIXTURES)
def phenotype_name(request) -> str:
    """Parametrized phenotype fixture name."""
    return request.param

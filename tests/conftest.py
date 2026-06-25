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

# All committed scenario fixtures and their expected triage classification.
ALL_FIXTURES = [
    "at_goal", "hyper_prone", "hypo_prone", "high_variability",
    "dawn_phenomenon", "post_meal_spiker", "nocturnal_hypo", "aid_well_controlled",
]
EXPECTED_CLASSIFICATION = {
    "at_goal": "at_goal",
    "hyper_prone": "hyper_prone",
    "hypo_prone": "hypo_prone",
    "high_variability": "high_variability",
    "dawn_phenomenon": "at_goal",
    "post_meal_spiker": "hyper_prone",
    "nocturnal_hypo": "hypo_prone",
    "aid_well_controlled": "at_goal",
}


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
    """Parametrized phenotype fixture name (name == triage category)."""
    return request.param


@pytest.fixture(params=ALL_FIXTURES)
def any_fixture_name(request) -> str:
    """Parametrized over all scenario fixtures (incl. pattern scenarios)."""
    return request.param

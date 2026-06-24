"""Generate synthetic, de-identified Nightscout fixtures for tests and demos.

These fixtures contain NO real patient data. They are produced from simple
parametric glucose models so that tests are deterministic and the open-source
repo carries no PHI. Run as a module to (re)write the JSON fixtures:

    python -m fixtures.generate
"""

from __future__ import annotations

import json
import math
import os
import random
from datetime import datetime, timedelta, timezone

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "synthetic")

# Synthetic patient profiles: (name, mean, amplitude, noise, hypo_bias).
# These shape a diurnal glucose curve to exercise each triage phenotype.
PROFILES = {
    "at_goal": dict(base=120, amp=30, noise=12, drift=0.0, seed=1),
    "hyper_prone": dict(base=200, amp=45, noise=20, drift=0.0, seed=2),
    "hypo_prone": dict(base=110, amp=35, noise=18, drift=-0.0, seed=3, hypo=True),
    "high_variability": dict(base=130, amp=35, noise=20, drift=0.0, seed=4,
                             floor=70, spike=185, spike_prob=0.6),
}

CADENCE_MIN = 5
DAYS = 14


def _glucose_series(profile: dict) -> list[tuple[int, float]]:
    """Generate (epoch_ms, sgv) samples for one synthetic profile."""
    rng = random.Random(profile["seed"])
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    n = DAYS * 24 * 60 // CADENCE_MIN
    out: list[tuple[int, float]] = []
    for i in range(n):
        t = start + timedelta(minutes=i * CADENCE_MIN)
        hour = t.hour + t.minute / 60.0
        # Diurnal sinusoid: dawn rise + post-meal bumps approximated by a sine.
        diurnal = profile["amp"] * math.sin((hour - 6) / 24.0 * 2 * math.pi)
        meal_bump = 0.0
        for meal_h in (8, 13, 19):
            dist = abs(hour - meal_h)
            if dist < 2:
                meal_bump += (2 - dist) * profile["amp"] * 0.4
        # Optional large post-meal spikes drive upper-tail variability.
        spike = profile.get("spike", 0)
        if spike:
            spike_prob = profile.get("spike_prob", 0.5)
            for meal_h in (8, 13, 19):
                if 0 <= (hour - meal_h) < 1.5 and rng.random() < spike_prob:
                    meal_bump += rng.uniform(0.4, 1.0) * spike
        value = profile["base"] + diurnal + meal_bump + rng.gauss(0, profile["noise"])
        if profile.get("hypo"):
            # Inject occasional overnight lows.
            if 0 <= hour < 5 and rng.random() < 0.10:
                value -= 45
        # An optional floor models a patient who swings high but rarely low.
        floor = profile.get("floor")
        if floor is not None:
            value = max(floor, value)
        value = max(40, min(400, value))
        out.append((int(t.timestamp() * 1000), round(value)))
    return out


def _entries(series: list[tuple[int, float]]) -> list[dict]:
    """Build Nightscout /entries records from a glucose series."""
    records = []
    for epoch_ms, sgv in series:
        iso = datetime.fromtimestamp(epoch_ms / 1000.0, tz=timezone.utc).isoformat()
        records.append(
            {
                "type": "sgv",
                "sgv": sgv,
                "date": epoch_ms,
                "dateString": iso,
                "direction": "Flat",
                "device": "synthetic://cgm_insights",
            }
        )
    # Nightscout returns newest-first.
    records.reverse()
    return records


def _profile_doc() -> list[dict]:
    """A minimal, generic Nightscout /profile document (no PHI)."""
    return [
        {
            "defaultProfile": "Default",
            "store": {
                "Default": {
                    "dia": 5.0,
                    "timezone": "UTC",
                    "basal": [{"time": "00:00", "value": 0.8, "timeAsSeconds": 0}],
                    "sens": [{"time": "00:00", "value": 40, "timeAsSeconds": 0}],
                    "carbratio": [{"time": "00:00", "value": 10, "timeAsSeconds": 0}],
                }
            },
        }
    ]


def generate() -> None:
    """Write all synthetic fixtures to fixtures/synthetic/."""
    os.makedirs(FIXTURE_DIR, exist_ok=True)
    for name, profile in PROFILES.items():
        series = _glucose_series(profile)
        bundle = {
            "entries": _entries(series),
            "devicestatus": [],  # synthetic T2D-style: no AID device status
            "treatments": [],
            "profile": _profile_doc(),
        }
        path = os.path.join(FIXTURE_DIR, f"{name}.json")
        with open(path, "w") as fh:
            json.dump(bundle, fh, indent=2)
        print(f"wrote {path} ({len(series)} readings)")


if __name__ == "__main__":
    generate()

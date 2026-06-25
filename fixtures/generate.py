"""Generate fully-synthetic, de-identified Nightscout fixtures.

These fixtures contain NO real patient data; they are produced by the
physiological synthetic model in ``fixtures.synth_model`` (dawn phenomenon,
asymmetric meal excursions, autocorrelated noise, sensor gaps, overnight
hypoglycemia). This is the self-contained / no-external-data path; the hybrid
de-identified pipeline is ``fixtures.build_fixtures``.

    python -m fixtures.generate
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from fixtures.synth_model import PRESETS, synth_series

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "synthetic")

DAYS = 20  # >16 days so the RPM 99454 data-sufficiency gate is demonstrable
# Fixed synthetic start (no real calendar date) — keeps fixtures PHI-free and
# inside the documented synthetic window.
START = datetime(2025, 1, 1, tzinfo=timezone.utc)


def _entries(series: list[tuple[int, float]]) -> list[dict]:
    """Build Nightscout /entries records from a glucose series (newest-first)."""
    records = []
    for epoch_ms, sgv in series:
        iso = datetime.fromtimestamp(epoch_ms / 1000.0, tz=timezone.utc).isoformat()
        records.append(
            {
                "type": "sgv",
                "sgv": int(sgv),
                "date": epoch_ms,
                "dateString": iso,
                "direction": "Flat",
                "device": "synthetic://cgm_insights",
            }
        )
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
    """Write all fully-synthetic fixtures to fixtures/synthetic/."""
    os.makedirs(FIXTURE_DIR, exist_ok=True)
    for name, params in PRESETS.items():
        series = synth_series(params, DAYS, START, params.seed)
        bundle = {
            "entries": _entries(series),
            "devicestatus": [],  # glucose-only (T2D-style) unless overridden
            "treatments": [],
            "profile": _profile_doc(),
        }
        path = os.path.join(FIXTURE_DIR, f"{name}.json")
        with open(path, "w") as fh:
            json.dump(bundle, fh, indent=2)
        print(f"wrote {path} ({len(series)} readings)")


if __name__ == "__main__":
    generate()

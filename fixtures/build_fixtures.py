"""Hybrid de-identified fixture builder: fuzz real CGM days + stitch synthetic.

Reads real Nightscout CGM data from EXTERNAL sources (kept outside this repo),
de-identifies it, and stitches it with synthetic days from
``fixtures.synth_model`` to produce the committed fixtures in
``fixtures/synthetic/``.

De-identification (applied to every real day used):
  * Only ``(minute-of-day, glucose)`` is extracted; ALL metadata (``_id``,
    ``device``, ``uploader``, ``dateString``, ``sysTime`` …) is discarded.
  * Date-shift: each real day is remapped onto a fixed synthetic calendar
    (``START``), preserving only time-of-day. Real calendar dates are removed.
  * Value fuzz: each glucose value gets bounded jitter (``FUZZ_MGDL``).
  * Multi-patient blend: every phenotype fixture mixes real days from >= 2
    distinct source patients (k-anonymity) plus synthetic days.

No real values, dates, or identifiers are ever written to the repo. If the
external sources are unavailable, the builder falls back to fully-synthetic
output (identical to ``fixtures.generate``).

    python -m fixtures.build_fixtures
"""

from __future__ import annotations

import json
import os
import random
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fixtures.synth_model import PRESETS, synth_series

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "synthetic")

# External real-data root (NOT part of this repo; never committed).
REAL_ROOT = os.environ.get(
    "CGM_REAL_NS_ROOT",
    "/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/ns-data/patients",
)

DAYS = 20
START = datetime(2025, 1, 1, tzinfo=timezone.utc)  # synthetic calendar anchor
CADENCE_MIN = 5
FUZZ_MGDL = 4          # +/- value jitter applied to real readings
MIN_READINGS_PER_DAY = 200
BUILD_SEED = 20260624

# Per-phenotype: which real patients to draw from, and a day-level selector so
# the borrowed real days actually exhibit the target behavior.
PHENOTYPE_SOURCES = {
    "at_goal": dict(
        patients=["k", "d", "j"],
        day_ok=lambda s: s["tir"] >= 78 and s["tbr"] < 3 and s["cv"] < 32,
        real_days=11,
    ),
    "hyper_prone": dict(
        patients=["a", "b", "e"],
        day_ok=lambda s: s["tar"] >= 30 and s["tbr"] < 3 and s["cv"] < 34 and s["tir"] < 70,
        real_days=11,
    ),
    "hypo_prone": dict(
        patients=["i", "h", "c"],
        day_ok=lambda s: s["tbr"] >= 6,
        real_days=11,
    ),
    "high_variability": dict(
        patients=["f", "i", "a"],
        day_ok=lambda s: s["cv"] >= 38 and s["tbr"] < 4,
        real_days=11,
    ),
}


def _day_metrics(vals: list[float]) -> dict:
    """Quick day-level glycemic metrics used for source-day selection."""
    n = len(vals)
    mean = sum(vals) / n
    std = (sum((v - mean) ** 2 for v in vals) / n) ** 0.5
    return {
        "tir": 100 * sum(1 for v in vals if 70 <= v <= 180) / n,
        "tbr": 100 * sum(1 for v in vals if v < 70) / n,
        "tar": 100 * sum(1 for v in vals if v > 180) / n,
        "cv": std / mean * 100 if mean else 0.0,
        "mean": mean,
    }


def _load_real_days(patient: str) -> dict[object, list[tuple[int, float]]]:
    """Load a real patient's CGM days as {date: [(minute_of_day, sgv), ...]}.

    Only sgv value and minute-of-day are retained; everything else is dropped.
    Returns empty if the patient's data is unavailable.
    """
    days: dict[object, list[tuple[int, float]]] = defaultdict(list)
    for split in ("training", "verification"):
        path = os.path.join(REAL_ROOT, patient, split, "entries.json")
        if not os.path.exists(path):
            continue
        with open(path) as fh:
            data = json.load(fh)
        for x in data:
            if x.get("type") != "sgv":
                continue
            v = x.get("sgv")
            t = x.get("date")
            if not isinstance(v, (int, float)) or not isinstance(t, (int, float)):
                continue
            dt = datetime.fromtimestamp(t / 1000.0, tz=timezone.utc)
            minute_of_day = dt.hour * 60 + dt.minute
            days[dt.date()].append((minute_of_day, float(v)))
    # Keep only days with enough readings; sort each day by time.
    return {
        day: sorted(pairs)
        for day, pairs in days.items()
        if len(pairs) >= MIN_READINGS_PER_DAY
    }


def _select_real_days(spec: dict, rng: random.Random) -> list[tuple[str, list[tuple[int, float]]]]:
    """Select matching real days across >= 2 patients for a phenotype.

    Returns a list of (patient_id, day_pairs). Empty if no real data found.
    """
    want = spec["real_days"]
    day_ok = spec["day_ok"]
    by_patient: dict[str, list[list[tuple[int, float]]]] = {}
    for p in spec["patients"]:
        days = _load_real_days(p)
        matching = [
            pairs for pairs in days.values()
            if day_ok(_day_metrics([v for _, v in pairs]))
        ]
        rng.shuffle(matching)
        if matching:
            by_patient[p] = matching

    if len(by_patient) < 2:
        return []  # need >= 2 sources for k-anonymity; else fall back

    # Round-robin across patients so >= 2 sources are always represented.
    selected: list[tuple[str, list[tuple[int, float]]]] = []
    cursors = {p: 0 for p in by_patient}
    patients = list(by_patient)
    i = 0
    while len(selected) < want:
        p = patients[i % len(patients)]
        c = cursors[p]
        if c < len(by_patient[p]):
            selected.append((p, by_patient[p][c]))
            cursors[p] += 1
        i += 1
        if i > want * 4:  # exhausted
            break
    return selected


def _deidentify_day(day_pairs: list[tuple[int, float]], day_index: int, rng: random.Random) -> list[tuple[int, float]]:
    """Map a real day onto the synthetic calendar with value fuzzing.

    Returns [(epoch_ms, sgv)] anchored at START + day_index, preserving only
    time-of-day. Each glucose value is jittered by +/- FUZZ_MGDL.
    """
    base = START + timedelta(days=day_index)
    out: list[tuple[int, float]] = []
    for minute_of_day, sgv in day_pairs:
        fuzzed = sgv + rng.randint(-FUZZ_MGDL, FUZZ_MGDL)
        fuzzed = max(39.0, min(401.0, fuzzed))
        epoch_ms = int((base + timedelta(minutes=minute_of_day)).timestamp() * 1000)
        out.append((epoch_ms, float(round(fuzzed))))
    return out


def _synthetic_day(name: str, day_index: int, rng: random.Random) -> list[tuple[int, float]]:
    """Generate one synthetic day for a phenotype, anchored at day_index."""
    params = PRESETS[name]
    # Generate a single-day series with a per-day seed for variety.
    series = synth_series(params, 1, START + timedelta(days=day_index), rng.randint(1, 10 ** 9))
    return series


def build_phenotype(name: str, spec: dict, rng: random.Random) -> tuple[list[dict], dict]:
    """Build one phenotype fixture: real de-identified days + synthetic days.

    Returns (entries, provenance). Falls back to fully synthetic if no real
    data is available.
    """
    real_days = _select_real_days(spec, rng)
    provenance = {"real_days": 0, "synthetic_days": 0, "source_patients": []}

    series: list[tuple[int, float]] = []
    day_index = 0
    if real_days:
        sources = sorted({p for p, _ in real_days})
        provenance["source_patients"] = sources
        # Interleave real and synthetic days across the 20-day window.
        n_real = min(len(real_days), spec["real_days"])
        real_iter = iter(real_days[:n_real])
        for day_index in range(DAYS):
            # Roughly alternate: ~half real, half synthetic, real first.
            use_real = (day_index % 2 == 0) and provenance["real_days"] < n_real
            if use_real:
                _, day_pairs = next(real_iter)
                series += _deidentify_day(day_pairs, day_index, rng)
                provenance["real_days"] += 1
            else:
                series += _synthetic_day(name, day_index, rng)
                provenance["synthetic_days"] += 1
    else:
        # No external real data — fully synthetic fallback.
        series = synth_series(PRESETS[name], DAYS, START, PRESETS[name].seed)
        provenance["synthetic_days"] = DAYS
        provenance["fallback"] = "synthetic-only (no external real data)"

    series.sort()
    return _entries(series), provenance


def _entries(series: list[tuple[int, float]]) -> list[dict]:
    """Build de-identified Nightscout /entries records (newest-first)."""
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
                "device": "synthetic://cgm_insights",  # de-identified tag
            }
        )
    records.reverse()
    return records


def _profile_doc() -> list[dict]:
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


def build() -> dict:
    """Build all phenotype fixtures. Returns {name: provenance}."""
    os.makedirs(FIXTURE_DIR, exist_ok=True)
    rng = random.Random(BUILD_SEED)
    manifest = {}
    for name, spec in PHENOTYPE_SOURCES.items():
        entries, provenance = build_phenotype(name, spec, random.Random(rng.randint(1, 10 ** 9)))
        bundle = {
            "entries": entries,
            "devicestatus": [],
            "treatments": [],
            "profile": _profile_doc(),
        }
        path = os.path.join(FIXTURE_DIR, f"{name}.json")
        with open(path, "w") as fh:
            json.dump(bundle, fh, indent=2)
        manifest[name] = provenance
        print(
            f"wrote {path}: {len(entries)} readings | "
            f"real_days={provenance['real_days']} synth_days={provenance['synthetic_days']} "
            f"sources={provenance.get('source_patients') or provenance.get('fallback')}"
        )
    return manifest


if __name__ == "__main__":
    build()

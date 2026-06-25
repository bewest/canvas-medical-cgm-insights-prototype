"""Improved synthetic CGM generator (physiological model).

Pure-synthetic, deterministic, dependency-free. Produces realistic glucose
series by modelling:

  * dawn phenomenon (early-morning baseline rise),
  * asymmetric meal excursions (fast rise to peak, slower exponential decay),
  * autocorrelated (AR(1)) sensor noise rather than white noise,
  * occasional sensor gaps (dropouts),
  * overnight hypoglycemia and transient compression lows.

Used two ways:
  * directly, to generate fully-synthetic fixtures (``fixtures/generate.py``), and
  * as the synthetic "fill" stitched with de-identified real segments by
    ``fixtures/build_fixtures.py``.

This module lives outside the plugin package, so it may use ``math``/``random``
(it never runs inside the Canvas sandbox).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class Meal:
    """A recurring daily meal that produces a glucose excursion."""

    hour: float            # nominal time of day (hours)
    mag: float             # peak rise above baseline (mg/dL)
    tau_rise: float = 45.0   # minutes from meal to peak
    tau_decay: float = 120.0  # exponential decay time constant (minutes)
    prob: float = 1.0        # probability the meal occurs on a given day
    jitter_min: float = 30.0  # +/- timing jitter (minutes)
    mag_jitter: float = 0.3   # +/- fractional magnitude jitter


@dataclass
class SynthParams:
    """Parameters shaping one synthetic phenotype."""

    baseline: float = 110.0
    dawn_amp: float = 0.0          # early-morning rise amplitude (mg/dL)
    meals: list[Meal] = field(default_factory=list)
    ar_phi: float = 0.72           # noise autocorrelation (0..1)
    ar_sigma: float = 8.0          # stationary noise sd (mg/dL)
    gap_rate: float = 0.0015       # per-step probability of starting a sensor gap
    gap_len: int = 12              # gap length in steps (~1h at 5-min cadence)
    comp_low_rate: float = 0.0     # per-night probability of a compression low
    comp_low_depth: float = 35.0
    comp_sd: float = 0.25          # compression-low width (hours)
    hypo_rate: float = 0.0         # per-night probability of an overnight hypo
    hypo_depth: float = 45.0
    hypo_sd: float = 0.5           # overnight-hypo width (hours)
    floor: float | None = None     # optional hard lower clamp (models a non-low patient)
    vmin: float = 39.0
    vmax: float = 401.0
    seed: int = 0                  # default RNG seed for this phenotype
    aid: bool = False              # emit synthetic AID device-status (IOB/COB)


def _dawn(hour: float, amp: float) -> float:
    """Raised-cosine dawn-phenomenon bump between 03:00 and 08:00."""
    if amp <= 0 or not (3.0 <= hour <= 8.0):
        return 0.0
    x = (hour - 3.0) / 5.0  # 0..1 across the window
    return amp * (0.5 - 0.5 * math.cos(2 * math.pi * x))


def _meal_excursion(dt_min: float, mag: float, tau_rise: float, tau_decay: float) -> float:
    """Asymmetric meal response: linear rise to peak, exponential decay."""
    if dt_min < 0:
        return 0.0
    if dt_min < tau_rise:
        return mag * (dt_min / tau_rise)
    return mag * math.exp(-(dt_min - tau_rise) / tau_decay)


def synth_series(
    params: SynthParams,
    days: int,
    start: datetime,
    seed: int,
    cadence_min: int = 5,
) -> list[tuple[int, float]]:
    """Generate a deterministic (epoch_ms, sgv) series for the given params."""
    rng = random.Random(seed)
    n = days * 24 * 60 // cadence_min

    # Pre-roll per-day meal occurrences (absolute minute, magnitude, kinetics).
    meal_events: list[tuple[float, float, float, float]] = []
    for d in range(days):
        for m in params.meals:
            if rng.random() > m.prob:
                continue
            t0 = d * 24 * 60 + m.hour * 60 + rng.uniform(-m.jitter_min, m.jitter_min)
            mag = m.mag * (1.0 + rng.uniform(-m.mag_jitter, m.mag_jitter))
            meal_events.append((t0, mag, m.tau_rise, m.tau_decay))
    meal_events.sort()

    # Overnight events per day.
    hypo_nights = {
        d: rng.uniform(1.0, 4.0)
        for d in range(days)
        if params.hypo_rate and rng.random() < params.hypo_rate
    }
    comp_nights = {
        d: rng.uniform(0.0, 6.0)
        for d in range(days)
        if params.comp_low_rate and rng.random() < params.comp_low_rate
    }

    innov_scale = math.sqrt(max(0.0, 1.0 - params.ar_phi ** 2))
    out: list[tuple[int, float]] = []
    noise = 0.0
    gap_remaining = 0
    mi = 0  # sliding window start into meal_events

    for i in range(n):
        abs_min = i * cadence_min
        d = abs_min // (24 * 60)
        hour = (abs_min % (24 * 60)) / 60.0

        noise = params.ar_phi * noise + innov_scale * rng.gauss(0.0, params.ar_sigma)
        val = params.baseline + _dawn(hour, params.dawn_amp) + noise

        # Advance the sliding window past meals that can no longer contribute.
        while mi < len(meal_events) and meal_events[mi][0] < abs_min - 6 * 240:
            mi += 1
        for j in range(mi, len(meal_events)):
            t0, mag, tr, td = meal_events[j]
            if t0 > abs_min:
                break
            val += _meal_excursion(abs_min - t0, mag, tr, td)

        if d in hypo_nights:
            dd = hour - hypo_nights[d]
            val -= params.hypo_depth * math.exp(-(dd * dd) / (2 * params.hypo_sd ** 2))
        if d in comp_nights:
            dd = hour - comp_nights[d]
            val -= params.comp_low_depth * math.exp(-(dd * dd) / (2 * params.comp_sd ** 2))

        if params.floor is not None:
            val = max(params.floor, val)
        val = max(params.vmin, min(params.vmax, val))

        # Sensor gaps: omit readings during a dropout.
        if gap_remaining > 0:
            gap_remaining -= 1
            continue
        if rng.random() < params.gap_rate:
            gap_remaining = params.gap_len

        epoch_ms = int((start + timedelta(minutes=abs_min)).timestamp() * 1000)
        out.append((epoch_ms, float(round(val))))

    return out


# ── Phenotype presets ────────────────────────────────────────────────────────
# Tuned so each series classifies to its intended glycemic phenotype while
# producing a realistic AGP shape.

PRESETS: dict[str, SynthParams] = {
    "at_goal": SynthParams(
        baseline=102, dawn_amp=18, ar_sigma=12, seed=11,
        meals=[Meal(7.5, 58), Meal(12.5, 66), Meal(18.5, 62)],
        gap_rate=0.0012,
    ),
    "hyper_prone": SynthParams(
        baseline=150, dawn_amp=26, ar_sigma=12, seed=22,
        meals=[
            Meal(7.5, 95, tau_decay=190),
            Meal(12.5, 105, tau_decay=210),
            Meal(18.5, 115, tau_decay=220),
        ],
    ),
    "hypo_prone": SynthParams(
        baseline=98, dawn_amp=12, ar_sigma=10, seed=33,
        meals=[Meal(7.5, 32), Meal(12.5, 36), Meal(18.5, 32)],
        hypo_rate=1.0, hypo_depth=58, hypo_sd=0.8,
        comp_low_rate=0.4, comp_low_depth=38, comp_sd=0.4,
    ),
    "high_variability": SynthParams(
        baseline=100, dawn_amp=22, ar_sigma=20, floor=70, seed=44,
        meals=[
            Meal(7.5, 185, tau_decay=150, mag_jitter=0.7),
            Meal(12.5, 210, tau_decay=170, mag_jitter=0.7),
            Meal(18.5, 190, tau_decay=160, mag_jitter=0.7),
        ],
    ),
    # ── Additional clinically-distinct scenarios (map to triage buckets) ──
    "dawn_phenomenon": SynthParams(  # prominent 03:00-08:00 rise, otherwise at goal
        baseline=92, dawn_amp=55, ar_sigma=9, seed=55,
        meals=[Meal(7.5, 40), Meal(12.5, 45), Meal(18.5, 42)],
    ),
    "post_meal_spiker": SynthParams(  # good fasting, large post-meal excursions -> hyper
        baseline=95, dawn_amp=15, ar_sigma=10, seed=66,
        meals=[
            Meal(7.5, 135, tau_decay=200),
            Meal(12.5, 150, tau_decay=210),
            Meal(18.5, 140, tau_decay=205),
        ],
    ),
    "nocturnal_hypo": SynthParams(  # overnight lows, otherwise controlled -> hypo
        baseline=110, dawn_amp=12, ar_sigma=9, seed=77,
        meals=[Meal(7.5, 40), Meal(12.5, 45), Meal(18.5, 42)],
        hypo_rate=1.0, hypo_depth=58, hypo_sd=0.9,
    ),
    "aid_well_controlled": SynthParams(  # T1D on AID, tight control, with IOB/COB
        baseline=115, dawn_amp=10, ar_sigma=8, seed=88, aid=True,
        meals=[Meal(7.5, 35), Meal(12.5, 40), Meal(18.5, 38)],
    ),
}


# Expected triage classification for each scenario (used to validate fixtures).
EXPECTED_CLASSIFICATION: dict[str, str] = {
    "at_goal": "at_goal",
    "hyper_prone": "hyper_prone",
    "hypo_prone": "hypo_prone",
    "high_variability": "high_variability",
    "dawn_phenomenon": "at_goal",
    "post_meal_spiker": "hyper_prone",
    "nocturnal_hypo": "hypo_prone",
    "aid_well_controlled": "at_goal",
}


def synth_device_status(
    params: SynthParams,
    days: int,
    start: datetime,
    seed: int,
    cadence_min: int = 15,
) -> list[dict]:
    """Generate plausible synthetic AID device-status (IOB/COB) records.

    Values are illustrative, not a physiological simulation: COB rises at meals
    and decays over ~3 h; IOB reflects a basal floor plus meal boluses decaying
    over a ~5 h insulin action window. Shaped like Nightscout Loop records so
    ``has_aid`` is true and the AID data path is exercised.
    """
    if not params.aid:
        return []
    rng = random.Random(seed)
    carb_ratio = 10.0
    cob_absorb_min = 180.0
    dia_min = 300.0

    # Pre-roll meal boluses/carbs.
    events = []  # (abs_min, carbs_g)
    for d in range(days):
        for m in params.meals:
            if rng.random() > m.prob:
                continue
            t0 = d * 24 * 60 + m.hour * 60 + rng.uniform(-m.jitter_min, m.jitter_min)
            carbs = max(5.0, m.mag * 0.45 * (1.0 + rng.uniform(-0.2, 0.2)))
            events.append((t0, carbs))
    events.sort()

    out: list[dict] = []
    n = days * 24 * 60 // cadence_min
    for i in range(n):
        abs_min = i * cadence_min
        cob = 0.0
        iob = 0.8  # basal floor
        for t0, carbs in events:
            dt = abs_min - t0
            if 0 <= dt < cob_absorb_min:
                cob += carbs * (1.0 - dt / cob_absorb_min)
            if 0 <= dt < dia_min:
                bolus = carbs / carb_ratio
                iob += bolus * (1.0 - dt / dia_min)
            if t0 > abs_min:
                break
        ts = (start + timedelta(minutes=abs_min)).isoformat()
        epoch_ms = int((start + timedelta(minutes=abs_min)).timestamp() * 1000)
        out.append(
            {
                "date": epoch_ms,
                "dateString": ts,
                "loop": {
                    "iob": {"iob": round(iob, 2)},
                    "cob": {"cob": round(cob, 1)},
                },
            }
        )
    return out

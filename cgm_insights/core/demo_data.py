"""Embedded synthetic demo data (sandbox-safe, no PHI).

Provides a deterministic, fully synthetic CGM series so the plugin can render
its triage / billing output in a Canvas sandbox without configuring a real
Nightscout instance (and therefore without moving any PHI into Canvas).

Enabled by setting the plugin variable ``DEMO_MODE`` (any truthy value) or
``NIGHTSCOUT_URL=demo``. The series is generated from a 24-hour baseline plus a
deterministic wiggle, using only sandbox-allowed operations (no math/random/file
I/O). It is shaped to be hypoglycemia-prone over ~18 days so it exercises the
triage card, the hypo-safety banner, and the billing-readiness card (CPT 95251
and 99454 thresholds both met).
"""

from cgm_insights.core.nightscout import GlucoseReading, NightscoutData

# Hourly glucose baseline (mg/dL), index = hour of day. Overnight dips below 70
# create time-below-range; daytime meal bumps keep the mean roughly in-range.
_HOURLY_BASELINE = [
    70, 66, 63, 62, 64, 68,        # 00-05 overnight lows
    95, 150, 140, 120, 110, 135,   # 06-11 breakfast / morning
    120, 145, 130, 115, 108, 150,  # 12-17 lunch / afternoon
    135, 120, 150, 140, 110, 90,   # 18-23 dinner / evening
]

_DAYS = 18
_CADENCE_MIN = 15
# Fixed synthetic start (2025-01-01T00:00:00Z) in epoch milliseconds.
_START_EPOCH_MS = 1_735_689_600_000


def demo_nightscout() -> NightscoutData:
    """Return a NightscoutData bundle built from the synthetic demo series."""
    readings: list[GlucoseReading] = []
    n = _DAYS * 24 * 60 // _CADENCE_MIN
    for i in range(n):
        minute = i * _CADENCE_MIN
        hour = (minute // 60) % 24
        base = _HOURLY_BASELINE[hour]
        wiggle = ((i * 37) % 21) - 10  # deterministic, -10..+10
        sgv = max(40, min(360, base + wiggle))
        readings.append(
            GlucoseReading(
                epoch_ms=_START_EPOCH_MS + i * _CADENCE_MIN * 60_000,
                sgv=float(sgv),
                direction="Flat",
                device="synthetic://cgm_insights/demo",
            )
        )
    return NightscoutData(entries=readings)

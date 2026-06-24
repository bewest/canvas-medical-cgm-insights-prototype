"""Nightscout payload parsing.

Pure-Python parsing of Nightscout REST API responses into a normalized,
analysis-ready shape. Uses only sandbox-allowed facilities (list/dict
comprehensions, ``datetime``); no numpy/pandas.

Nightscout endpoints consumed:
  * ``/api/v1/entries``      -> CGM readings (``sgv`` mg/dL, ``date`` epoch ms)
  * ``/api/v1/devicestatus`` -> loop/AID state (IOB, COB) -- optional
  * ``/api/v1/treatments``   -> boluses, carbs -- optional
  * ``/api/v1/profile``      -> basal/ISF/CR schedule -- optional

T2D patients frequently have only ``entries``; everything else degrades
gracefully to empty.
"""


from dataclasses import dataclass, field
from datetime import datetime, timezone

# Nightscout glucose readings can be tagged with several "type" values; only
# sensor glucose values ("sgv") are true CGM readings.
SGV_TYPE = "sgv"


@dataclass
class GlucoseReading:
    """A single CGM sensor glucose value."""

    epoch_ms: int
    sgv: float  # mg/dL
    direction: str = ""
    device: str = ""

    @property
    def dt(self) -> datetime:
        """UTC datetime for this reading."""
        return datetime.fromtimestamp(self.epoch_ms / 1000.0, tz=timezone.utc)


@dataclass
class DeviceStatus:
    """A device/loop status sample (IOB/COB), when an AID system is present."""

    epoch_ms: int
    iob: float | None = None
    cob: float | None = None


@dataclass
class NightscoutData:
    """Normalized bundle of parsed Nightscout data."""

    entries: list[GlucoseReading] = field(default_factory=list)
    device_status: list[DeviceStatus] = field(default_factory=list)
    profile: dict = field(default_factory=dict)

    @property
    def has_aid(self) -> bool:
        """True if AID/loop device-status data (IOB/COB) is present."""
        return any(d.iob is not None or d.cob is not None for d in self.device_status)

    @property
    def sgv_values(self) -> list[float]:
        """Plain list of glucose values in mg/dL (chronological order)."""
        return [r.sgv for r in self.entries]


def _entry_epoch_ms(entry: dict) -> int | None:
    """Extract an epoch-ms timestamp from a Nightscout entry.

    Nightscout stores ``date`` as epoch milliseconds; some exports only carry
    ``dateString``/``sysTime`` ISO timestamps, so fall back to those.
    """
    date = entry.get("date")
    if isinstance(date, (int, float)) and date > 0:
        return int(date)

    iso = entry.get("dateString") or entry.get("sysTime")
    if isinstance(iso, str) and iso:
        try:
            # Normalize a trailing "Z" to an explicit UTC offset.
            cleaned = iso.replace("Z", "+00:00")
            dt = datetime.fromisoformat(cleaned)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp() * 1000)
        except ValueError:
            return None
    return None


def parse_entries(raw: list[dict]) -> list[GlucoseReading]:
    """Parse a Nightscout ``/entries`` payload into sorted GlucoseReadings.

    Only ``sgv``-type readings with a positive glucose value and a resolvable
    timestamp are kept. Results are sorted chronologically (oldest first).
    """
    readings: list[GlucoseReading] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        # Default to "sgv" when type is absent (older Nightscout exports).
        if entry.get("type", SGV_TYPE) != SGV_TYPE:
            continue
        sgv = entry.get("sgv")
        if not isinstance(sgv, (int, float)) or sgv <= 0:
            continue
        epoch_ms = _entry_epoch_ms(entry)
        if epoch_ms is None:
            continue
        readings.append(
            GlucoseReading(
                epoch_ms=epoch_ms,
                sgv=float(sgv),
                direction=str(entry.get("direction", "")),
                device=str(entry.get("device", "")),
            )
        )
    readings.sort(key=lambda r: r.epoch_ms)
    return readings


def parse_device_status(raw: list[dict]) -> list[DeviceStatus]:
    """Parse a Nightscout ``/devicestatus`` payload (IOB/COB).

    Handles both Loop and AAPS/OpenAPS shapes, where IOB/COB live under
    ``loop`` or ``openaps`` keys. Missing values stay ``None``.
    """
    statuses: list[DeviceStatus] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        epoch_ms = _entry_epoch_ms(item)
        if epoch_ms is None:
            continue

        iob = cob = None
        loop = item.get("loop") or {}
        openaps = item.get("openaps") or {}

        iob_obj = loop.get("iob") or openaps.get("iob") or {}
        if isinstance(iob_obj, dict):
            iob = iob_obj.get("iob")
        cob_obj = loop.get("cob") or openaps.get("cob") or {}
        if isinstance(cob_obj, dict):
            cob = cob_obj.get("cob")

        statuses.append(
            DeviceStatus(
                epoch_ms=epoch_ms,
                iob=float(iob) if isinstance(iob, (int, float)) else None,
                cob=float(cob) if isinstance(cob, (int, float)) else None,
            )
        )
    statuses.sort(key=lambda d: d.epoch_ms)
    return statuses


def parse_nightscout(
    entries: list[dict] | None = None,
    device_status: list[dict] | None = None,
    profile: list[dict] | dict | None = None,
) -> NightscoutData:
    """Parse raw Nightscout payloads into a normalized NightscoutData bundle.

    Each argument is optional; absent feeds yield empty collections. The
    ``profile`` endpoint returns a list (most recent first) in Nightscout; the
    first element is used when a list is supplied.
    """
    prof: dict = {}
    if isinstance(profile, list) and profile:
        prof = profile[0] if isinstance(profile[0], dict) else {}
    elif isinstance(profile, dict):
        prof = profile

    return NightscoutData(
        entries=parse_entries(entries or []),
        device_status=parse_device_status(device_status or []),
        profile=prof,
    )

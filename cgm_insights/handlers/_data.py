"""Shared data-loading helper for handlers.

Resolves the Nightscout endpoint for a patient and fetches CGM data using the
Canvas SDK ``Http`` client, then hands raw payloads to the SDK-free core
parser.

POC mapping (single instance): the Nightscout base URL and an optional read
token are supplied via plugin secrets ``NIGHTSCOUT_URL`` and
``NIGHTSCOUT_TOKEN``. The reusability step (see plan) replaces this with a
per-patient base URL stored on the Canvas patient record.

Demo mode: set ``DEMO_MODE`` (any truthy value) or ``NIGHTSCOUT_URL=demo`` to
use bundled synthetic data instead of fetching. This lets the plugin render its
output in a sandbox without a real Nightscout instance and without moving any
PHI into Canvas.
"""


from canvas_sdk.utils.http import Http

from cgm_insights.core.demo_data import demo_nightscout
from cgm_insights.core.ns_client import fetch_nightscout
from cgm_insights.core.nightscout import NightscoutData

_DEMO_SENTINEL = "demo"


def _demo_phenotype(secrets: dict) -> str | None:
    """Return the requested demo phenotype, or None if demo mode is off.

    Demo mode is on when DEMO_MODE is truthy or NIGHTSCOUT_URL == 'demo'. If
    DEMO_MODE names a phenotype (e.g. 'hypo_prone'), that series is used; any
    other truthy value uses the default phenotype.
    """
    from cgm_insights.core.demo_data import DEFAULT_PHENOTYPE, DEMO_SERIES

    s = secrets or {}
    raw = str(s.get("DEMO_MODE", "")).strip()
    low = raw.lower()
    if low in DEMO_SERIES:
        return low
    if low in ("1", "true", "yes", "on"):
        return DEFAULT_PHENOTYPE
    if (s.get("NIGHTSCOUT_URL", "") or "").strip().lower() == _DEMO_SENTINEL:
        return DEFAULT_PHENOTYPE
    return None


def _demo_enabled(secrets: dict) -> bool:
    """True if demo mode is requested via DEMO_MODE or NIGHTSCOUT_URL=demo."""
    return _demo_phenotype(secrets) is not None


def load_patient_cgm(secrets: dict) -> NightscoutData:
    """Fetch and parse Nightscout CGM data for the current patient.

    Returns synthetic demo data when demo mode is enabled, an empty
    NightscoutData when no Nightscout URL is configured (so handlers no-op
    gracefully), else the live Nightscout fetch.
    """
    phenotype = _demo_phenotype(secrets)
    if phenotype is not None:
        return demo_nightscout(phenotype)

    base_url = (secrets or {}).get("NIGHTSCOUT_URL", "").strip()
    if not base_url:
        return NightscoutData()

    token = (secrets or {}).get("NIGHTSCOUT_TOKEN", "").strip() or None
    http = Http(base_url)
    return fetch_nightscout(http.get, token=token)

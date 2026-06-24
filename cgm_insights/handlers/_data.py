"""Shared data-loading helper for handlers.

Resolves the Nightscout endpoint for a patient and fetches CGM data using the
Canvas SDK ``Http`` client, then hands raw payloads to the SDK-free core
parser.

POC mapping (single instance): the Nightscout base URL and an optional read
token are supplied via plugin secrets ``NIGHTSCOUT_URL`` and
``NIGHTSCOUT_TOKEN``. The reusability step (see plan) replaces this with a
per-patient base URL stored on the Canvas patient record.
"""

from __future__ import annotations

from canvas_sdk.utils.http import Http

from cgm_insights.core.ns_client import fetch_nightscout
from cgm_insights.core.nightscout import NightscoutData


def load_patient_cgm(secrets: dict) -> NightscoutData:
    """Fetch and parse Nightscout CGM data for the current patient.

    Returns an empty NightscoutData when no Nightscout URL is configured, so
    handlers can no-op gracefully rather than raise inside ``compute``.
    """
    base_url = (secrets or {}).get("NIGHTSCOUT_URL", "").strip()
    if not base_url:
        return NightscoutData()

    token = (secrets or {}).get("NIGHTSCOUT_TOKEN", "").strip() or None
    http = Http(base_url)
    return fetch_nightscout(http.get, token=token)

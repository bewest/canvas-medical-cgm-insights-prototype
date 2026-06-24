# cgm_insights (plugin package)

This directory is the installable Canvas Medical plugin. It contains only thin
event handlers; all analysis lives in the dependency-free `core/` package
(importable and unit-tested outside Canvas).

## Handlers
- `handlers/chart_summary.py` — `CGMSummarySection`: an AGP-style CGM summary
  rendered as a custom patient-chart section (`PATIENT_CHART_SUMMARY__GET_CUSTOM_SECTION`).
- `handlers/triage.py` — `CGMTriageProtocol`: a glycemic-phenotype ProtocolCard
  plus an optional hypoglycemia-safety banner, emitted on encounter creation
  (`NOTE_STATE_CHANGE_EVENT_CREATED`).

## Configuration (secrets)
- `NIGHTSCOUT_URL` — base URL of the Nightscout instance (POC: single instance).
- `NIGHTSCOUT_TOKEN` — optional Nightscout read token.

## Sandbox notes
The plugin runs under Canvas RestrictedPython. `core/` uses only sandbox-allowed
builtins (no numpy/scipy/pandas/math) so it runs unchanged in-plugin. Outbound
HTTP uses `canvas_sdk.utils.http.Http`.

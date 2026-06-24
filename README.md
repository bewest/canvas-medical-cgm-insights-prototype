# cgm_insights

A [Canvas Medical](https://www.canvasmedical.com/) plugin that turns continuous
glucose monitor (CGM) data from [Nightscout](https://nightscout.github.io/) into
clinical decision support inside the EHR: an AGP-style summary display, glycemic
phenotype triage, and (milestone 2) the documentation needed to drive CGM/RPM
reimbursement.

This is an open-source portfolio piece. It demonstrates platform fluency and
clinical judgment, descriptive analytics and triage, not unvalidated dosing
recommendations. The heavier statistical pipeline (settings extraction and
parameter recommendation) is intentionally deferred to an external service
("Phase 2 / sidecar"); see [`docs/plan.html`](docs/plan.html) for the full
feasibility analysis and architecture.

## What it does (Milestone 1)

- **CGM summary display** — an Ambulatory Glucose Profile (AGP) chart and the
  standard metrics (Time in Range, GMI, %CV, time below/above range) rendered as
  a custom patient-chart section.
- **Glycemic phenotype triage** — classifies each patient as hypoglycemia-prone,
  hyperglycemia-prone, high-variability, or at-goal, surfaced as a Canvas
  `ProtocolCard`, with a hypoglycemia-safety `BannerAlert` when warranted.

## Architecture

```
Nightscout API  ->  cgm_insights.core (pure Python, SDK-free)  ->  Canvas effects
   (entries)          metrics / triage / AGP rendering             ProtocolCard
                                                                    BannerAlert
                                                                    Custom section
```

Two design rules make this work and keep it testable:

1. **All logic lives in `cgm_insights/core/`** and is dependency-free pure Python
   using only the subset of builtins the Canvas RestrictedPython sandbox allows
   (no numpy/scipy/pandas/math). It is unit-tested with plain pytest.
2. **`cgm_insights/handlers/` is thin glue** — it fetches Nightscout data via the
   Canvas SDK `Http` client, calls `core`, and returns Canvas effects.

## Layout

```
cgm_insights/            # installable Canvas plugin
  CANVAS_MANIFEST.json
  core/                  # SDK-free: nightscout, metrics, triage, agp, ns_client
  handlers/              # thin Canvas event handlers
fixtures/                # synthetic, de-identified Nightscout data + generator
tests/                   # pytest suite (core + handler layers)
docs/plan.html           # feasibility analysis & architecture
```

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'        # pytest; the SDK-free core needs no deps
python -m fixtures.generate    # (re)write synthetic fixtures
pytest                         # run the suite
```

Validate / install the plugin (requires the Canvas CLI and a configured
instance):

```bash
pip install canvas
canvas validate-manifest cgm_insights
canvas install cgm_insights \
  --variable NIGHTSCOUT_URL=https://your-ns.example \
  --variable NIGHTSCOUT_TOKEN=your-read-token
```

## Data & privacy

- The repository ships **only synthetic, de-identified** CGM fixtures
  (`fixtures/synthetic/`, produced by `fixtures/generate.py`). No PHI.
- The plugin does **not** mirror the raw 5-minute glucose stream into Canvas.
  Milestone 2 writes only low-cardinality summary `Observation`s and a
  `DocumentReference` report, the artifacts that support CPT 95251 / RPM billing.

## Status

- [x] **M1** — Nightscout fetch, pure-Python metrics, AGP display, phenotype triage
- [x] **M2** — billing-readiness documentation (summary Observations, review/sign card, data-sufficiency gates for CPT 95251 / 99454)
- [ ] **M3** — external sidecar for settings extraction / parameter recommendation

A static render of the in-Canvas output for each synthetic phenotype is in
[`docs/preview.html`](docs/preview.html) (regenerate with `python -m scripts.preview`).

## License

MIT — see [LICENSE](LICENSE).

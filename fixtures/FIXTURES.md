# Demo fixtures: provenance & de-identification

The CGM fixtures in [`synthetic/`](synthetic/) drive the test suite, the static
preview, and the in-sandbox demo mode. They are **de-identified hybrid data**:
fuzzed real CGM days blended with synthetic days, or fully synthetic.

**No raw patient data, real identifiers, or real calendar dates are committed to
this repository.** The real source data lives outside the repo and is never
checked in.

## Producers

| Script | What it does | Needs external data? |
| --- | --- | --- |
| `fixtures/synth_model.py` | Physiological synthetic engine (dawn phenomenon, asymmetric meal excursions, AR(1) sensor noise, gaps, overnight hypos, compression lows, synthetic AID device-status). | No |
| `fixtures/generate.py` | Fully-synthetic fixtures from `synth_model`. Self-contained fallback. | No |
| `fixtures/build_fixtures.py` | **Hybrid** builder: fuzzes real CGM days and stitches synthetic days. Produces the committed fixtures. | Yes (falls back to synthetic) |

Rebuild the committed (hybrid) fixtures:

```bash
# Point at a local Nightscout export tree if not at the default path:
export CGM_REAL_NS_ROOT=/path/to/ns-data/patients
python -m fixtures.build_fixtures
```

Without the external data, `build_fixtures` and `generate` both yield fully
synthetic fixtures.

## De-identification method (applied to every real day used)

1. **Field stripping** — only `(minute-of-day, glucose)` is extracted; every
   other field (`_id`, `device`, `uploader`, `dateString`, `sysTime`, pump/loop
   metadata, …) is discarded. Output records carry only
   `type`/`sgv`/`date`/`dateString`/`direction`/`device`, with a synthetic
   `device` tag.
2. **Date shifting** — each real day is remapped onto a fixed synthetic calendar
   (anchored at 2025-01-01), preserving only time-of-day. Real calendar dates are
   removed.
3. **Value fuzzing** — each glucose value is jittered by ±4 mg/dL.
4. **Multi-patient blending (k-anonymity)** — every hybrid fixture mixes real
   days from **≥ 2 distinct source patients** plus synthetic days, so no fixture
   corresponds to a single individual.

These steps are enforced by `tests/test_fixture_safety.py`, which asserts the
committed fixtures contain no raw fields, only the synthetic `device` tag, and
only dates inside the synthetic window.

## Scenarios

Eight scenario fixtures, each validated to classify into the expected triage
bucket (`fixtures/synth_model.py::EXPECTED_CLASSIFICATION`):

| Fixture | Source | Triage bucket |
| --- | --- | --- |
| `at_goal` | hybrid (≥2 patients + synthetic) | At goal |
| `hyper_prone` | hybrid | Hyperglycemia-prone |
| `hypo_prone` | hybrid | Hypoglycemia-prone |
| `high_variability` | hybrid | High variability |
| `post_meal_spiker` | hybrid | Hyperglycemia-prone |
| `nocturnal_hypo` | hybrid | Hypoglycemia-prone |
| `dawn_phenomenon` | synthetic-only | At goal |
| `aid_well_controlled` | synthetic-only (with AID device-status IOB/COB) | At goal |

The exact real/synthetic day split and source-patient set per fixture are
reported by `build_fixtures` at build time; they are not committed (only the
de-identified output is).

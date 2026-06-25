"""Render a static preview of the cgm_insights CGM display for each synthetic
phenotype fixture. Produces docs/preview.html, a single page showing the
AGP-style chart section plus the triage and billing-readiness summaries that
the plugin would surface in Canvas.

    python -m scripts.preview
"""

from __future__ import annotations

import json
import os

from cgm_insights.core.agp import render_agp
from cgm_insights.core.billing import assess_sufficiency, build_billing_artifacts
from cgm_insights.core.metrics import compute_metrics
from cgm_insights.core.nightscout import parse_nightscout
from cgm_insights.core.triage import classify, hypo_safety_check

FIXTURE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "fixtures", "synthetic")
OUT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "preview.html")

PHENOTYPES = [
    "at_goal", "hyper_prone", "hypo_prone", "high_variability",
    "dawn_phenomenon", "post_meal_spiker", "nocturnal_hypo", "aid_well_controlled",
]


def _section(name: str) -> str:
    with open(os.path.join(FIXTURE_DIR, f"{name}.json")) as fh:
        bundle = json.load(fh)
    nd = parse_nightscout(bundle["entries"], bundle["devicestatus"], bundle["profile"])
    metrics = compute_metrics(nd.sgv_values)
    triage = classify(metrics)
    hypo = hypo_safety_check(metrics)
    suff = assess_sufficiency(nd.entries)
    artifacts = build_billing_artifacts(metrics, suff)

    display = render_agp(metrics, nd.entries)
    banner = (
        f'<div style="background:#fffbeb;border:1px solid #fde68a;padding:8px;'
        f'border-radius:6px;margin:8px 0;font-size:13px">&#9888; {hypo.narrative}</div>'
        if hypo.triggered
        else ""
    )
    return (
        f'<section style="border:1px solid #e5e7eb;border-radius:10px;padding:16px;margin:16px 0">'
        f"<h2 style='margin-top:0'>{name} &mdash; triage: {triage.label}</h2>"
        f"{banner}"
        f"{display}"
        f'<p style="font-size:12px;color:#6b7280;margin-top:10px"><strong>Triage:</strong> {triage.reason}</p>'
        f'<p style="font-size:12px;color:#6b7280"><strong>Billing readiness:</strong> '
        f"{', '.join(suff.eligible_codes) or 'none'} &mdash; {artifacts.interpretation}</p>"
        f"</section>"
    )


def main() -> None:
    sections = "".join(_section(name) for name in PHENOTYPES)
    html = (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<title>cgm_insights preview</title></head>"
        "<body style='font-family:sans-serif;max-width:820px;margin:24px auto;padding:0 16px'>"
        "<h1>cgm_insights &mdash; CGM display & triage preview</h1>"
        "<p style='color:#6b7280'>Rendered from synthetic, de-identified fixtures. "
        "This is what the plugin surfaces inside Canvas (chart section, triage card, "
        "billing-readiness summary).</p>"
        f"{sections}</body></html>"
    )
    with open(OUT, "w") as fh:
        fh.write(html)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()

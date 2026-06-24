"""Manual runner for cgm_insights — exercise the full pipeline outside Canvas.

Runs the exact SDK-free core the plugin uses, against either a synthetic
fixture or a live Nightscout instance, and prints the metrics, triage, and
billing-readiness results. Optionally dumps the Canvas effects the plugin would
emit, and/or an HTML preview.

This reads Nightscout and renders locally only. It does NOT write anything into
Canvas, so it is safe to point at a live instance without moving PHI anywhere.

Examples:
    # Against a bundled synthetic fixture:
    python -m scripts.run --fixture hypo_prone

    # Against a live Nightscout site (local display only, no PHI leaves here):
    python -m scripts.run --url https://your-ns.example --token YOUR_READ_TOKEN

    # Show the Canvas effects the plugin would return, and write a preview:
    python -m scripts.run --fixture at_goal --effects --html /tmp/out.html
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from cgm_insights.core.agp import render_agp
from cgm_insights.core.billing import assess_sufficiency, build_billing_artifacts
from cgm_insights.core.metrics import compute_metrics
from cgm_insights.core.nightscout import NightscoutData, parse_nightscout
from cgm_insights.core.ns_client import fetch_nightscout
from cgm_insights.core.triage import classify, hypo_safety_check

FIXTURE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "fixtures", "synthetic")


def _load_fixture(name: str) -> NightscoutData:
    path = os.path.join(FIXTURE_DIR, f"{name}.json")
    with open(path) as fh:
        bundle = json.load(fh)
    return parse_nightscout(bundle["entries"], bundle["devicestatus"], bundle["profile"])


def _load_live(url: str, token: str | None) -> NightscoutData:
    """Fetch from a live Nightscout instance using plain requests.

    Mirrors what the plugin does via canvas_sdk Http, but standalone so it runs
    without Canvas. The ns_client is dependency-injected with a requests getter.
    """
    import requests

    base = url.rstrip("/")

    def getter(path: str, headers: dict):
        return requests.get(base + path, headers=headers, timeout=30)

    return fetch_nightscout(getter, token=token)


def _print_report(data: NightscoutData) -> dict:
    metrics = compute_metrics(data.sgv_values)
    if metrics is None:
        print("No CGM readings found.")
        return {}

    triage = classify(metrics)
    hypo = hypo_safety_check(metrics)
    suff = assess_sufficiency(data.entries)
    artifacts = build_billing_artifacts(metrics, suff)

    print("=" * 60)
    print(f"  Readings: {metrics.n}   AID device status present: {data.has_aid}")
    print("-" * 60)
    print("  METRICS")
    print(f"    Time in range (70-180):   {metrics.tir:>5.1f} %")
    print(f"    Time below range (<70):   {metrics.tbr:>5.1f} %  (<54: {metrics.tbr_l2:.1f} %)")
    print(f"    Time above range (>180):  {metrics.tar:>5.1f} %")
    print(f"    Mean glucose:             {metrics.mean:>5.0f} mg/dL")
    print(f"    GMI:                      {metrics.gmi:>5.1f} %")
    print(f"    %CV:                      {metrics.cv:>5.1f} %")
    print("-" * 60)
    print("  TRIAGE")
    print(f"    Phenotype: {triage.label}  (priority {triage.priority})")
    print(f"    Reason:    {triage.reason}")
    if hypo.triggered:
        print(f"    \u26a0  HYPO BANNER: {hypo.narrative}")
    print("-" * 60)
    print("  BILLING READINESS")
    print(f"    Hours of data: {suff.hours:.0f}   Days with data: {suff.days_with_data}")
    print(f"    Eligible CPT code(s): {', '.join(suff.eligible_codes) or 'none yet'}")
    print("=" * 60)

    return {
        "metrics": metrics.as_dict(),
        "phenotype": triage.phenotype.value,
        "hypo_banner": hypo.narrative if hypo.triggered else None,
        "eligible_codes": suff.eligible_codes,
        "interpretation": artifacts.interpretation,
        "_data": data,
        "_metrics": metrics,
    }


def _dump_effects(result: dict) -> None:
    """Show the Canvas effects the plugin would emit (requires canvas_sdk)."""
    try:
        from cgm_insights.core.triage import classify, hypo_safety_check
        from cgm_insights.handlers.triage import build_triage_effects
        from cgm_insights.handlers.billing import build_billing_effects
    except Exception as exc:  # SDK not installed
        print(f"\n[effects] canvas_sdk not available ({exc}); skipping effect dump.")
        return

    metrics = result["_metrics"]
    data = result["_data"]
    tri = classify(metrics)
    hypo = hypo_safety_check(metrics)
    suff = assess_sufficiency(data.entries)

    print("\n--- Canvas effects (triage) ---")
    for eff in build_triage_effects(
        "demo-patient", metrics,
        result_phenotype=tri.phenotype, result_reason=tri.reason,
        result_label=tri.label, hypo=hypo,
    ):
        print(f"  {eff.type}: {eff.payload[:120]}...")

    if suff.any_eligible:
        artifacts = build_billing_artifacts(metrics, suff)
        print("\n--- Canvas effects (billing) ---")
        for eff in build_billing_effects("demo-patient", artifacts):
            print(f"  {eff.type}: {eff.payload[:120]}...")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run cgm_insights against a fixture or live Nightscout.")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--fixture", help="synthetic fixture name (e.g. at_goal, hypo_prone)")
    src.add_argument("--url", help="live Nightscout base URL")
    parser.add_argument("--token", help="Nightscout read token (with --url)")
    parser.add_argument("--effects", action="store_true", help="also print Canvas effects the plugin would emit")
    parser.add_argument("--html", help="write an AGP HTML preview to this path")
    args = parser.parse_args(argv)

    if args.fixture:
        data = _load_fixture(args.fixture)
    else:
        data = _load_live(args.url, args.token)

    result = _print_report(data)
    if not result:
        return 1

    if args.effects:
        _dump_effects(result)

    if args.html:
        html = render_agp(result["_metrics"], result["_data"].entries)
        with open(args.html, "w") as fh:
            fh.write(f"<!DOCTYPE html><meta charset='utf-8'><body>{html}</body>")
        print(f"\nwrote HTML preview: {args.html}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

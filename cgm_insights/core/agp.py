"""AGP-style CGM display rendered as an inline SVG/HTML string.

The Canvas ``PatientChartSummaryCustomSection`` effect accepts an inline HTML
``content`` string. Since the sandbox forbids charting libraries, the display
is built directly as SVG via string formatting. This is deliberately a small,
dependency-free renderer.

It draws a simplified Ambulatory Glucose Profile (AGP): the median glucose and
inter-quartile band by hour of day, with the 70-180 mg/dL target range shaded,
plus a metrics header.
"""

from __future__ import annotations

from .metrics import CGMMetrics, TIR_HIGH, TIR_LOW
from .nightscout import GlucoseReading

# SVG geometry.
_W = 720
_H = 240
_PAD_L = 44
_PAD_R = 12
_PAD_T = 12
_PAD_B = 24
_PLOT_W = _W - _PAD_L - _PAD_R
_PLOT_H = _H - _PAD_T - _PAD_B

# Glucose axis range (mg/dL) for the plot.
_Y_MIN = 40.0
_Y_MAX = 350.0


def _esc(text: str) -> str:
    """Minimal XML/HTML escape for text rendered into SVG/HTML."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _y(value: float) -> float:
    """Map a glucose value (mg/dL) to an SVG y-coordinate."""
    value = max(_Y_MIN, min(_Y_MAX, value))
    frac = (value - _Y_MIN) / (_Y_MAX - _Y_MIN)
    return _PAD_T + (1.0 - frac) * _PLOT_H


def _x(hour: float) -> float:
    """Map an hour of day [0, 24] to an SVG x-coordinate."""
    return _PAD_L + (hour / 24.0) * _PLOT_W


def hourly_percentiles(
    readings: list[GlucoseReading],
) -> dict[int, tuple[float, float, float]]:
    """Compute (p25, p50, p75) glucose by hour of day from readings.

    Returns a dict mapping hour -> (p25, median, p75). Hours with no data are
    omitted. Pure Python; uses local hour-of-day from each reading's UTC time.
    """
    buckets: dict[int, list[float]] = {}
    for r in readings:
        buckets.setdefault(r.dt.hour, []).append(r.sgv)

    result: dict[int, tuple[float, float, float]] = {}
    for hour, vals in buckets.items():
        vals.sort()
        n = len(vals)

        def pct(p: float) -> float:
            idx = int(p * (n - 1) + 0.5)
            return vals[max(0, min(n - 1, idx))]

        result[hour] = (pct(0.25), pct(0.50), pct(0.75))
    return result


def _band_paths(pcts: dict[int, tuple[float, float, float]]) -> tuple[str, str]:
    """Build the IQR band polygon and the median polyline from hourly pcts."""
    hours = sorted(pcts)
    if not hours:
        return "", ""

    # IQR band: p75 across hours (left-to-right) then p25 (right-to-left).
    top = [f"{_x(h):.1f},{_y(pcts[h][2]):.1f}" for h in hours]
    bottom = [f"{_x(h):.1f},{_y(pcts[h][0]):.1f}" for h in reversed(hours)]
    band = " ".join(top + bottom)

    median = " ".join(f"{_x(h):.1f},{_y(pcts[h][1]):.1f}" for h in hours)
    return band, median


def _metrics_header(m: CGMMetrics) -> str:
    """Render the headline metrics as an HTML row above the chart."""
    chips = [
        ("Time in range", f"{m.tir:.0f}%"),
        ("GMI", f"{m.gmi:.1f}%"),
        ("Mean", f"{m.mean:.0f} mg/dL"),
        ("CV", f"{m.cv:.0f}%"),
        ("Time below 70", f"{m.tbr:.1f}%"),
        ("Time above 180", f"{m.tar:.0f}%"),
    ]
    cells = "".join(
        f'<div style="flex:1;min-width:90px">'
        f'<div style="font-size:11px;color:#6b7280">{_esc(label)}</div>'
        f'<div style="font-size:18px;font-weight:600;color:#111827">{_esc(value)}</div>'
        f"</div>"
        for label, value in chips
    )
    return (
        f'<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px">{cells}</div>'
    )


def _y_axis_labels() -> str:
    """Glucose y-axis gridlines and labels at clinically relevant values."""
    parts = []
    for val in (54, 70, 180, 250):
        y = _y(val)
        parts.append(
            f'<line x1="{_PAD_L}" y1="{y:.1f}" x2="{_W - _PAD_R}" y2="{y:.1f}" '
            f'stroke="#e5e7eb" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{_PAD_L - 6}" y="{y + 3:.1f}" text-anchor="end" '
            f'font-size="10" fill="#9ca3af">{val}</text>'
        )
    return "".join(parts)


def render_agp(metrics: CGMMetrics, readings: list[GlucoseReading]) -> str:
    """Render the full CGM summary section as an inline HTML/SVG string.

    Combines a metrics header with a simplified AGP chart (target range shaded,
    IQR band, median line). Safe to pass to PatientChartSummaryCustomSection
    ``content``.
    """
    pcts = hourly_percentiles(readings)
    band, median = _band_paths(pcts)

    target_top = _y(TIR_HIGH)
    target_bottom = _y(TIR_LOW)

    band_svg = (
        f'<polygon points="{band}" fill="#93c5fd" fill-opacity="0.45" stroke="none"/>'
        if band
        else ""
    )
    median_svg = (
        f'<polyline points="{median}" fill="none" stroke="#1d4ed8" stroke-width="2"/>'
        if median
        else ""
    )

    # Hour axis ticks every 6 hours.
    hour_ticks = "".join(
        f'<text x="{_x(h):.1f}" y="{_H - 8}" text-anchor="middle" '
        f'font-size="10" fill="#9ca3af">{h:02d}</text>'
        for h in (0, 6, 12, 18, 24)
    )

    svg = (
        f'<svg viewBox="0 0 {_W} {_H}" width="100%" '
        f'style="max-width:{_W}px;font-family:sans-serif" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" aria-label="AGP chart">'
        # target range shading
        f'<rect x="{_PAD_L}" y="{target_top:.1f}" width="{_PLOT_W}" '
        f'height="{(target_bottom - target_top):.1f}" fill="#bbf7d0" fill-opacity="0.5"/>'
        f"{_y_axis_labels()}"
        f"{band_svg}{median_svg}{hour_ticks}"
        f"</svg>"
    )

    return (
        f'<div style="font-family:sans-serif">'
        f"{_metrics_header(metrics)}"
        f"{svg}"
        f'<div style="font-size:11px;color:#9ca3af;margin-top:4px">'
        f"Median (line) and IQR (band) by hour of day over {metrics.n} readings. "
        f"Green = 70-180 mg/dL target range.</div>"
        f"</div>"
    )

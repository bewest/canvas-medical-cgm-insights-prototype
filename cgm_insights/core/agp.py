"""AGP-style CGM display rendered as an inline SVG/HTML string.

The Canvas application/section effects accept an inline HTML ``content`` string.
Since the sandbox forbids charting libraries, the display is built directly as
SVG via string formatting (no JavaScript, no external dependencies) so it
renders reliably inside Canvas without CSP/CDN concerns.

It renders two standard CGM-report visuals:
  * a **Time-in-Range** stacked bar (5 glycemic zones, consensus colors), and
  * an **Ambulatory Glucose Profile** (median with p25-p75 and p5-p95 bands by
    hour of day, target range shaded).
"""


from cgm_insights.core.metrics import CGMMetrics, TIR_HIGH, TIR_LOW
from cgm_insights.core.nightscout import GlucoseReading

# SVG geometry for the AGP chart.
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

# Consensus glycemic-zone colors (low -> high).
_ZONE_VERY_LOW = "#7e1416"   # < 54
_ZONE_LOW = "#d64545"        # 54-69
_ZONE_TARGET = "#1a9850"     # 70-180
_ZONE_HIGH = "#f4c430"       # 181-250
_ZONE_VERY_HIGH = "#e8893c"  # > 250


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
) -> dict[int, tuple[float, float, float, float, float]]:
    """Compute (p5, p25, p50, p75, p95) glucose by hour of day.

    Returns a dict mapping hour -> 5 percentiles. Hours with no data are
    omitted. Pure Python; uses local hour-of-day from each reading's UTC time.
    """
    buckets: dict[int, list[float]] = {}
    for r in readings:
        buckets.setdefault(r.dt.hour, []).append(r.sgv)

    result: dict[int, tuple[float, float, float, float, float]] = {}
    for hour, vals in buckets.items():
        vals.sort()
        n = len(vals)

        def pct(p: float) -> float:
            idx = int(p * (n - 1) + 0.5)
            return vals[max(0, min(n - 1, idx))]

        result[hour] = (pct(0.05), pct(0.25), pct(0.50), pct(0.75), pct(0.95))
    return result


def _band_polygon(pcts: dict, lo_idx: int, hi_idx: int) -> str:
    """SVG polygon points for the band between two percentile indices."""
    hours = sorted(pcts)
    if not hours:
        return ""
    top = [f"{_x(h):.1f},{_y(pcts[h][hi_idx]):.1f}" for h in hours]
    bottom = [f"{_x(h):.1f},{_y(pcts[h][lo_idx]):.1f}" for h in reversed(hours)]
    return " ".join(top + bottom)


def _median_polyline(pcts: dict) -> str:
    hours = sorted(pcts)
    return " ".join(f"{_x(h):.1f},{_y(pcts[h][2]):.1f}" for h in hours)


def _zone_breakdown(m: CGMMetrics) -> list[tuple[str, str, float]]:
    """(label, color, percent) for each glycemic zone, low -> high."""
    very_low = m.tbr_l2
    low = max(0.0, m.tbr - m.tbr_l2)
    target = m.tir
    high = max(0.0, m.tar - m.tar_l2)
    very_high = m.tar_l2
    return [
        ("Very low (<54)", _ZONE_VERY_LOW, very_low),
        ("Low (54-69)", _ZONE_LOW, low),
        ("In range (70-180)", _ZONE_TARGET, target),
        ("High (181-250)", _ZONE_HIGH, high),
        ("Very high (>250)", _ZONE_VERY_HIGH, very_high),
    ]


def render_tir_bar(m: CGMMetrics) -> str:
    """Render a Time-in-Range stacked horizontal bar with a legend (inline SVG)."""
    zones = _zone_breakdown(m)
    total = sum(p for _, _, p in zones) or 1.0
    bar_w = 680
    bar_h = 26
    x = 0.0
    segments = []
    for label, color, pct in zones:
        w = bar_w * pct / total
        if w <= 0:
            continue
        seg = f'<rect x="{x:.1f}" y="0" width="{w:.1f}" height="{bar_h}" fill="{color}"/>'
        if w > 34:  # label the segment inline if wide enough
            seg += (
                f'<text x="{x + w / 2:.1f}" y="{bar_h / 2 + 4:.1f}" text-anchor="middle" '
                f'font-size="11" fill="#ffffff" font-weight="600">{pct:.0f}%</text>'
            )
        segments.append(seg)
        x += w
    legend = "".join(
        f'<span style="display:inline-flex;align-items:center;gap:4px;margin-right:10px">'
        f'<span style="width:10px;height:10px;border-radius:2px;background:{color};'
        f'display:inline-block"></span>{_esc(label)} {pct:.1f}%</span>'
        for label, color, pct in zones
    )
    return (
        '<div style="margin-bottom:10px">'
        '<div style="font-size:11px;color:#6b7280;margin-bottom:3px">Time in ranges</div>'
        f'<svg viewBox="0 0 {bar_w} {bar_h}" width="100%" style="max-width:{bar_w}px" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Time in range bar">'
        f'{"".join(segments)}</svg>'
        f'<div style="font-size:10px;color:#6b7280;margin-top:4px">{legend}</div>'
        "</div>"
    )


def _metrics_header(m: CGMMetrics) -> str:
    """Render the headline metrics as an HTML row."""
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
        f'<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px">{cells}</div>'
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


def render_agp_chart(readings: list[GlucoseReading]) -> str:
    """Render just the AGP chart SVG (median + p25-p75 + p5-p95 bands)."""
    pcts = hourly_percentiles(readings)
    outer = _band_polygon(pcts, 0, 4)   # p5-p95
    inner = _band_polygon(pcts, 1, 3)   # p25-p75
    median = _median_polyline(pcts)

    target_top = _y(TIR_HIGH)
    target_bottom = _y(TIR_LOW)

    outer_svg = (
        f'<polygon points="{outer}" fill="#bfdbfe" fill-opacity="0.5" stroke="none"/>'
        if outer else ""
    )
    inner_svg = (
        f'<polygon points="{inner}" fill="#60a5fa" fill-opacity="0.55" stroke="none"/>'
        if inner else ""
    )
    median_svg = (
        f'<polyline points="{median}" fill="none" stroke="#1d4ed8" stroke-width="2.5"/>'
        if median else ""
    )
    hour_ticks = "".join(
        f'<text x="{_x(h):.1f}" y="{_H - 8}" text-anchor="middle" '
        f'font-size="10" fill="#9ca3af">{h:02d}</text>'
        for h in (0, 6, 12, 18, 24)
    )
    return (
        f'<svg viewBox="0 0 {_W} {_H}" width="100%" '
        f'style="max-width:{_W}px;font-family:sans-serif" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" aria-label="AGP chart">'
        f'<rect x="{_PAD_L}" y="{target_top:.1f}" width="{_PLOT_W}" '
        f'height="{(target_bottom - target_top):.1f}" fill="#bbf7d0" fill-opacity="0.5"/>'
        f"{_y_axis_labels()}"
        f"{outer_svg}{inner_svg}{median_svg}{hour_ticks}"
        f"</svg>"
    )


def render_agp(metrics: CGMMetrics, readings: list[GlucoseReading]) -> str:
    """Render the full CGM summary: metrics header, TIR bar, and AGP chart."""
    return (
        f'<div style="font-family:sans-serif">'
        f"{_metrics_header(metrics)}"
        f"{render_tir_bar(metrics)}"
        f"{render_agp_chart(readings)}"
        f'<div style="font-size:11px;color:#9ca3af;margin-top:4px">'
        f"AGP: median (line), p25-p75 (dark band) and p5-p95 (light band) by hour "
        f"of day over {metrics.n} readings. Green = 70-180 mg/dL target range.</div>"
        f"</div>"
    )

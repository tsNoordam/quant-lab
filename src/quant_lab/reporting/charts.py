"""Inline SVG charts for the lab's HTML reports.

Pure Python, no JavaScript library, so a report is one self-contained file that
also prints. Colors are CSS custom properties defined by the page (light and
dark themes, print), never hex in the SVG. Every data mark carries a
``data-tip`` (the page's tooltip layer) and a ``<title>`` (fallback and screen
readers). Mark specs follow the lab's chart conventions: bars at most 24 px
thick with a 4 px rounded data end, 2 px lines, dots r >= 4 with a 2 px
surface ring, hairline recessive grids, text in ink tokens, never series color.

Series roles: ``ours`` (slot 1, blue), ``paper`` (slot 2, orange), ``third``
(slot 3, aqua). Validated with the data-viz palette validator in light and dark.
"""

import html
import math
from collections.abc import Sequence

WIDTH = 720
FONT = 12


def esc(text: object) -> str:
    return html.escape(str(text), quote=True)


def nice_ticks(lo: float, hi: float, count: int = 5) -> list[float]:
    """Round tick values covering [lo, hi]."""
    if hi <= lo:
        hi = lo + 1
    raw = (hi - lo) / max(count - 1, 1)
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
    start = math.floor(lo / step + 1e-9) * step
    end = math.ceil(hi / step - 1e-9) * step  # the last tick is at or beyond hi
    n = round((end - start) / step)
    return [round(start + i * step, 10) for i in range(n + 1)]


def fmt_tick(v: float) -> str:
    if abs(v) >= 1000:
        return f"{v / 1000:g}K"
    return f"{v:g}"


def svg(width: int, height: int, body: Sequence[str], label: str) -> str:
    """Scales down on narrow screens, never up past its design width (text stays 12 px)."""
    return (
        f'<svg class="chart" viewBox="0 0 {width} {height}" width="100%" style="max-width:{width}px" '
        f'role="img" aria-label="{esc(label)}" preserveAspectRatio="xMidYMid meet">'
        + "".join(body)
        + "</svg>"
    )


def text(x, y, s, *, anchor="start", cls="t-muted", size=FONT, weight=None) -> str:
    w = f' font-weight="{weight}"' if weight else ""
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" class="{cls}" '
        f'font-size="{size}"{w}>{esc(s)}</text>'
    )


def tip_attrs(tip: str) -> str:
    return f'data-tip="{esc(tip)}" tabindex="0"'


def hbar_path(x0: float, x1: float, y: float, h: float, r: float = 4) -> str:
    """Horizontal bar from baseline x0 to data end x1: square at the baseline, rounded at the end."""
    if abs(x1 - x0) < 2 * r:
        r = abs(x1 - x0) / 2
    top, bot = y, y + h
    if x1 >= x0:
        return (
            f"M{x0:.1f},{top:.1f} H{x1 - r:.1f} Q{x1:.1f},{top:.1f} {x1:.1f},{top + r:.1f} "
            f"V{bot - r:.1f} Q{x1:.1f},{bot:.1f} {x1 - r:.1f},{bot:.1f} H{x0:.1f} Z"
        )
    return (
        f"M{x0:.1f},{top:.1f} H{x1 + r:.1f} Q{x1:.1f},{top:.1f} {x1:.1f},{top + r:.1f} "
        f"V{bot - r:.1f} Q{x1:.1f},{bot:.1f} {x1 + r:.1f},{bot:.1f} H{x0:.1f} Z"
    )


def vbar_path(x: float, w: float, y0: float, y1: float, r: float = 4) -> str:
    """Vertical column from baseline y0 to data end y1 (SVG y grows down)."""
    if abs(y1 - y0) < 2 * r:
        r = abs(y1 - y0) / 2
    left, right = x, x + w
    if y1 <= y0:  # positive value: column goes up
        return (
            f"M{left:.1f},{y0:.1f} V{y1 + r:.1f} Q{left:.1f},{y1:.1f} {left + r:.1f},{y1:.1f} "
            f"H{right - r:.1f} Q{right:.1f},{y1:.1f} {right:.1f},{y1 + r:.1f} V{y0:.1f} Z"
        )
    return (
        f"M{left:.1f},{y0:.1f} V{y1 - r:.1f} Q{left:.1f},{y1:.1f} {left + r:.1f},{y1:.1f} "
        f"H{right - r:.1f} Q{right:.1f},{y1:.1f} {right:.1f},{y1 - r:.1f} V{y0:.1f} Z"
    )


def x_axis(scale, ticks, y_top: float, y_bottom: float, *, unit: str = "") -> list[str]:
    out = []
    for t in ticks:
        x = scale(t)
        cls = "baseline" if t == 0 else "grid"
        out.append(
            f'<line x1="{x:.1f}" y1="{y_top:.1f}" x2="{x:.1f}" y2="{y_bottom:.1f}" class="{cls}"/>'
        )
        out.append(text(x, y_bottom + 16, fmt_tick(t) + unit, anchor="middle"))
    return out


def linear(lo: float, hi: float, a: float, b: float):
    return lambda v: a + (v - lo) / (hi - lo) * (b - a)


def dumbbell(
    rows: Sequence[tuple[str, float, float]],
    *,
    label: str,
    unit: str = "",
    digits: int = 2,
    names: tuple[str, str] = ("Ours", "Paper"),
    roles: tuple[str, str] = ("ours", "paper"),
    left: int = 200,
) -> str:
    """One row per category: the paper's value and ours, joined by a connector."""
    row_h, top, right = 28, 12, 28
    height = top + row_h * len(rows) + 30
    values = [v for _, a, b in rows for v in (a, b)] + [0.0]
    lo, hi = min(values), max(values)
    pad = (hi - lo) * 0.06 or 1
    ticks = nice_ticks(lo - pad, hi + pad)
    scale = linear(ticks[0], ticks[-1], left, WIDTH - right)
    body = x_axis(scale, ticks, top - 4, top + row_h * len(rows), unit=unit)
    for i, (name, a, b) in enumerate(rows):
        y = top + row_h * i + row_h / 2
        body.append(text(left - 12, y + 4, name, anchor="end", cls="t-secondary"))
        xa, xb = scale(a), scale(b)
        body.append(
            f'<line x1="{xa:.1f}" y1="{y:.1f}" x2="{xb:.1f}" y2="{y:.1f}" class="connector"/>'
        )
        tip = f"{name}: {names[0].lower()} {a:.{digits}f}{unit}, {names[1].lower()} {b:.{digits}f}{unit}"
        for x, role, nm, v in ((xb, roles[1], names[1], b), (xa, roles[0], names[0], a)):
            body.append(
                f'<g class="mark" {tip_attrs(tip)}><title>{esc(f"{name}, {nm}: {v:.{digits}f}{unit}")}</title>'
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="11" class="hit"/>'
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" class="dot {role}"/></g>'
            )
    return svg(WIDTH, height, body, label)


def hbars(
    rows: Sequence[tuple[str, float, str, str]],
    *,
    label: str,
    unit: str = "",
    domain: tuple[float, float] | None = None,
    track: bool = False,
    left: int = 230,
    value_labels: bool = True,
) -> str:
    """Horizontal bars, one per row: (label, value, role, tooltip)."""
    row_h, top, right, thick = 30, 10, 70, 16
    height = top + row_h * len(rows) + 30
    vals = [v for _, v, _, _ in rows] + [0.0]
    lo, hi = domain or (min(vals), max(vals))
    ticks = nice_ticks(lo, hi) if domain is None else nice_ticks(*domain)
    scale = linear(ticks[0], ticks[-1], left, WIDTH - right)
    body = x_axis(scale, ticks, top - 4, top + row_h * len(rows), unit=unit)
    x0 = scale(0)
    for i, (name, v, role, tip) in enumerate(rows):
        y = top + row_h * i + (row_h - thick) / 2
        body.append(text(left - 12, y + thick / 2 + 4, name, anchor="end", cls="t-secondary"))
        if track:
            body.append(f'<path d="{hbar_path(x0, scale(ticks[-1]), y, thick)}" class="track"/>')
        body.append(
            f'<g class="mark" {tip_attrs(tip)}><title>{esc(tip)}</title>'
            f'<path d="{hbar_path(x0, scale(v), y, thick)}" class="bar {role}"/></g>'
        )
        if value_labels:
            xv = scale(v)
            anchor = "start" if v >= 0 else "end"
            body.append(
                text(
                    xv + (6 if v >= 0 else -6),
                    y + thick / 2 + 4,
                    f"{v:g}{unit}",
                    anchor=anchor,
                    cls="t-primary",
                )  # fmt: skip
            )
    return svg(WIDTH, height, body, label)


def grouped_hbars(
    rows: Sequence[tuple[str, Sequence[float]]],
    *,
    roles: Sequence[str],
    names: Sequence[str],
    label: str,
    digits: int = 2,
    left: int = 230,
) -> str:
    """Two (or more) thin bars per row, sharing a zero baseline, value at each tip."""
    thick, gap = 11, 2
    row_h = len(roles) * (thick + gap) + 16
    top, right = 10, 60
    height = top + row_h * len(rows) + 30
    vals = [v for _, vs in rows for v in vs] + [0.0]
    ticks = nice_ticks(min(vals), max(vals))
    scale = linear(ticks[0], ticks[-1], left, WIDTH - right)
    body = x_axis(scale, ticks, top - 4, top + row_h * len(rows))
    x0 = scale(0)
    for i, (name, vs) in enumerate(rows):
        y_row = top + row_h * i + 8
        body.append(text(left - 12, y_row + len(roles) * (thick + gap) / 2 + 3, name, anchor="end",
                         cls="t-secondary"))  # fmt: skip
        for j, (v, role, nm) in enumerate(zip(vs, roles, names, strict=True)):
            y = y_row + j * (thick + gap)
            tip = f"{name}, {nm}: {v:.{digits}f}"
            body.append(
                f'<g class="mark" {tip_attrs(tip)}><title>{esc(tip)}</title>'
                f'<path d="{hbar_path(x0, scale(v), y, thick)}" class="bar {role}"/></g>'
            )
            xv = scale(v)
            body.append(
                text(
                    xv + (5 if v >= 0 else -5),
                    y + thick - 1,
                    f"{v:.{digits}f}",
                    anchor="start" if v >= 0 else "end",
                    cls="t-primary",
                    size=11,
                )  # fmt: skip
            )
    return svg(WIDTH, height, body, label)


def columns(
    cats: Sequence[str],
    values: Sequence[float],
    *,
    label: str,
    unit: str = "",
    digits: int = 2,
    width: int = WIDTH,
    height: int = 260,
    domain: tuple[float, float] | None = None,
    role: str = "ours",
    highlight: int | None = None,
    wrap: int = 16,
    title: str | None = None,
) -> str:
    """Vertical columns, value on each cap; ``highlight`` gets the second role."""
    top = 26 if title else 14
    bottom, left, right = 52, 44, 12
    lo, hi = domain or (min([*values, 0.0]), max([*values, 0.0]))
    ticks = nice_ticks(lo, hi, 4)
    yscale = linear(ticks[0], ticks[-1], height - bottom, top)
    body = []
    if title:
        body.append(text(left, 16, title, cls="t-primary", weight=600))
    for t in ticks:
        y = yscale(t)
        cls = "baseline" if t == 0 else "grid"
        body.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{width - right}" y2="{y:.1f}" class="{cls}"/>'
        )
        body.append(text(left - 6, y + 4, fmt_tick(t) + unit, anchor="end"))
    band = (width - left - right) / len(cats)
    thick = min(24, band * 0.5)
    for i, (c, v) in enumerate(zip(cats, values, strict=True)):
        cx = left + band * i + band / 2
        r = "paper" if highlight is not None and i == highlight else role
        tip = f"{c}: {v:.{digits}f}{unit}"
        body.append(
            f'<g class="mark" {tip_attrs(tip)}><title>{esc(tip)}</title>'
            f'<path d="{vbar_path(cx - thick / 2, thick, yscale(0), yscale(v))}" class="bar {r}"/></g>'
        )
        ylab = yscale(v) - 6 if v >= 0 else yscale(v) + 14
        body.append(text(cx, ylab, f"{v:.{digits}f}", anchor="middle", cls="t-primary", size=11))
        for k, line in enumerate(wrap_words(c, wrap)):
            body.append(text(cx, height - bottom + 16 + 13 * k, line, anchor="middle", size=11))
    return svg(width, height, body, label)


def wrap_words(s: str, width: int) -> list[str]:
    lines, cur = [], ""
    for w in s.split():
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    return [*lines, cur][:3]


def scatter_identity(
    points: Sequence[tuple[float, float, str]], *, label: str, flag: float, size: int = 460
) -> str:
    """Ours (y) against the paper (x) with the 45-degree line; points off it by more
    than ``flag`` are labelled."""
    pad_l, pad_b, pad_t, pad_r = 48, 40, 28, 16
    vals = [v for x, y, _ in points for v in (x, y)]
    ticks = nice_ticks(min(vals), max(vals), 5)
    lo, hi = ticks[0], ticks[-1]
    sx = linear(lo, hi, pad_l, size - pad_r)
    sy = linear(lo, hi, size - pad_b, pad_t)
    body = []
    for t in ticks:
        cls = "baseline" if t == 0 else "grid"
        body.append(
            f'<line x1="{sx(t):.1f}" y1="{pad_t}" x2="{sx(t):.1f}" y2="{size - pad_b}" class="{cls}"/>'
        )
        body.append(
            f'<line x1="{pad_l}" y1="{sy(t):.1f}" x2="{size - pad_r}" y2="{sy(t):.1f}" class="{cls}"/>'
        )
        body.append(text(sx(t), size - pad_b + 16, fmt_tick(t), anchor="middle"))
        body.append(text(pad_l - 6, sy(t) + 4, fmt_tick(t), anchor="end"))
    body.append(
        f'<line x1="{sx(lo):.1f}" y1="{sy(lo):.1f}" x2="{sx(hi):.1f}" y2="{sy(hi):.1f}" class="identity"/>'
    )
    body.append(text(size - pad_r, size - 6, "paper →", anchor="end"))
    body.append(text(pad_l - 6, 12, "ours ↑", anchor="end"))
    for x, y, name in points:
        tip = f"{name}: ours {y:.3f}, paper {x:.3f}"
        body.append(
            f'<g class="mark" {tip_attrs(tip)}><title>{esc(tip)}</title>'
            f'<circle cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="10" class="hit"/>'
            f'<circle cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="4.5" class="dot ours"/></g>'
        )
        if abs(x - y) > flag:
            body.append(text(sx(x) + 9, sy(y) + 4, name, cls="t-secondary", size=11))
    return svg(size, size, body, label)


def timeline(
    rows: Sequence[tuple[str, float, float, str]],
    *,
    label: str,
    start: int,
    end: int,
    left: int = 210,
) -> str:
    """One bar per row from a start to an end year (fractional years)."""
    row_h, top, right, thick = 24, 10, 20, 12
    height = top + row_h * len(rows) + 30
    ticks = list(range(start, end + 1, 2))
    scale = linear(start, end, left, WIDTH - right)
    body = []
    for t in ticks:
        x = scale(t)
        body.append(
            f'<line x1="{x:.1f}" y1="{top - 4}" x2="{x:.1f}" y2="{top + row_h * len(rows)}" class="grid"/>'
        )
        body.append(text(x, top + row_h * len(rows) + 16, str(t), anchor="middle"))
    for i, (name, a, b, tip) in enumerate(rows):
        y = top + row_h * i + (row_h - thick) / 2
        body.append(text(left - 12, y + thick / 2 + 4, name, anchor="end", cls="t-secondary"))
        body.append(
            f'<g class="mark" {tip_attrs(tip)}><title>{esc(tip)}</title>'
            f'<path d="{hbar_path(scale(a), scale(b), y, thick, r=4)}" class="bar ours"/></g>'
        )
    return svg(WIDTH, height, body, label)

"""Paper-2 final report (ROADMAP step 19) as a standalone HTML page and a PDF.

    uv run python -m quant_lab.reporting.dejong_final

Inputs (committed):

- ``research/reports/dejong_final_report.md``: the narrative, the single
  source of the report's text. Lines ``<!-- chart:NAME -->`` mark where a
  chart goes; they are invisible in the Markdown.
- ``research/reports/dejong_final/report_data.yaml``: every number the charts
  show, copied with its source from a committed report or a named MLflow run.

Outputs: ``research/reports/dejong_final_report.html``, one self-contained file
(inline CSS, SVG and a small script; no network) with a table of contents,
headline tiles, verdict cards, charts with hover tooltips and a table view under
each, and a light/dark theme. ``dejong_final_report.pdf`` is the same page
printed by headless Chromium (light theme, every table view open); it is
skipped with a message if no Chromium is found (set ``QUANT_LAB_CHROMIUM``).

Nothing is computed here beyond layout: the numbers are the data file's.
"""

import argparse
import glob
import html
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import markdown
import yaml

from quant_lab.reporting import charts as c

REPORT_MD = "research/reports/dejong_final_report.md"
DATA = "research/reports/dejong_final/report_data.yaml"
OUT_HTML = "research/reports/dejong_final_report.html"
OUT_PDF = "research/reports/dejong_final_report.pdf"
MARKER = re.compile(r"<!--\s*chart:([a-z0-9_]+)\s*-->")

# charts whose numbers the report's Markdown already tabulates (no table view in the PDF)
TEXT_TABLES = {"scorecard", "waterfall", "groups", "strategies", "lab"}


def esc(s: object) -> str:
    return html.escape(str(s), quote=True)


def load_data(root: Path) -> dict:
    return yaml.safe_load((root / DATA).read_text(encoding="utf-8"))


# ---------------------------------------------------------------- figures


def table_html(header: list[str], rows: list[list[object]]) -> str:
    head = "".join(f"<th>{esc(h)}</th>" for h in header)
    body = "".join("<tr>" + "".join(f"<td>{esc(v)}</td>" for v in r) + "</tr>" for r in rows)
    return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def figure(
    fid: str,
    title: str,
    subtitle: str,
    chart: str,
    legend: list[tuple[str, str]],
    table: str,
    source: str,
) -> str:
    keys = "".join(
        f'<span class="key"><span class="swatch {role}"></span>{esc(name)}</span>'
        for role, name in legend
    )
    legend_html = f'<div class="legend">{keys}</div>' if keys else ""
    # in the PDF the table view is printed unless the narrative already has that table
    cls = "table-view" if fid in TEXT_TABLES else "table-view print-open"
    return (
        f'<figure class="viz" id="fig-{fid}">'
        f'<figcaption><span class="fig-title">{esc(title)}</span>'
        f'<span class="fig-sub">{esc(subtitle)}</span></figcaption>'
        f"{legend_html}{chart}"
        f'<details class="{cls}"><summary>Table view</summary>{table}</details>'
        f'<p class="source">Source: {esc(source)}</p></figure>'
    )


def year_fraction(date: str) -> float:
    y, m, d = (int(x) for x in date.split("-"))
    return y + (m - 1) / 12 + (d - 1) / 365


def build_figures(d: dict) -> dict[str, str]:
    figs: dict[str, str] = {}
    ours_paper = [("ours", "Ours"), ("paper", "Paper")]

    # windows
    rows = []
    for t in d["twins"]:
        a, b = t["window"].split("..")
        tip = f"{t['name']} ({t['countries']}, {t['gap_h']} h): {a} to {b}"
        rows.append((f"{t['name']} · {t['gap_h']} h", year_fraction(a), year_fraction(b), tip))
    figs["windows"] = figure(
        "windows",
        "Twelve DLCs, twelve sample windows",
        "Each bar is a twin's Table II window; the label gives the closing-time gap between its markets",
        c.timeline(rows, label="Sample windows of the 12 twins", start=1980, end=2004),
        [],
        table_html(
            ["Twin", "Countries", "Gap (h)", "Window", "Unified in sample"],
            [
                [
                    t["name"],
                    t["countries"],
                    t["gap_h"],
                    t["window"],
                    "yes" if t["unified_in_sample"] else "no",
                ]
                for t in d["twins"]
            ],
        ),  # fmt: skip
        "conf/dlc/*.yaml; research/reports/data_decisions.md",
    )

    # scorecard
    sc = d["scorecard"]["rows"]
    rows = [
        (r["table"], round(100 * r["within"] / r["total"], 1), "ours",
         f"{r['table']}: {r['within']} of {r['total']} within rounding ({100 * r['within'] / r['total']:.0f}%)")
        for r in sc
    ]  # fmt: skip
    figs["scorecard"] = figure(
        "scorecard",
        "How much of each table reproduces",
        "Share of the paper's printed statistics our replication matches within rounding",
        c.hbars(
            rows,
            label="Share within rounding per table",
            unit="%",
            domain=(0, 100),
            track=True,
            left=260,
        ),  # fmt: skip
        [],
        table_html(
            ["Table", "Within rounding", "Total", "Notes"],
            [[r["table"], r["within"], r["total"], r["note"]] for r in sc],
        ),  # fmt: skip
        d["scorecard"]["source"],
    )

    # Table II
    t2 = d["table2"]["rows"]
    figs["table2"] = figure(
        "table2",
        "Table II: mean deviation from parity",
        "Mean log deviation in %, ours and the paper's, per twin. Rio Tinto differs only in sign; Dexia and Fortis "
        "in data version",
        c.dumbbell(
            [(r["twin"], r["mean"][0], r["mean"][1]) for r in t2],
            label="Table II mean deviation",
            unit="%",
        ),  # fmt: skip
        ours_paper,
        table_html(
            ["Twin", "Mean (ours / paper)", "Mean abs.", "St. dev."],
            [
                [
                    r["twin"],
                    f"{r['mean'][0]:.2f} / {r['mean'][1]:.2f}",
                    f"{r['mean_abs'][0]:.2f} / {r['mean_abs'][1]:.2f}",
                    f"{r['stdev'][0]:.2f} / {r['stdev'][1]:.2f}",
                ]
                for r in t2
            ],
        ),  # fmt: skip
        d["table2"]["source"],
    )

    # Table III
    t3 = d["table3"]["rows"]
    pts = []
    names = {"index1": "index 1", "index2": "index 2", "fx": "exchange rate", "lag": "lagged dep."}
    for r in t3:
        for k, nm in names.items():
            pts.append((r[k][1], r[k][0], f"{r['twin']}, {nm}"))
    figs["table3"] = figure(
        "table3",
        "Table III: 48 coefficient sums on the 45-degree line",
        "Each dot is one sum of coefficients (index 1, index 2, exchange rate, lagged dependent) for one twin, "
        "ours against the paper's; labelled where they differ",
        c.scatter_identity(pts, label="Table III coefficient sums, ours vs paper", flag=0.01),
        [],
        table_html(
            ["Twin", "R²", "Index 1", "Index 2", "Exchange rate", "Lagged dep."],
            [
                [r["twin"]]
                + [
                    f"{r[k][0]:.3f} / {r[k][1]:.3f}"
                    for k in ("r2", "index1", "index2", "fx", "lag")
                ]
                for r in t3
            ],
        ),  # fmt: skip
        d["table3"]["source"],
    )

    # Table IV
    t4 = d["table4"]["rows"]
    figs["table4"] = figure(
        "table4",
        "Table IV: benchmark return per twin",
        "Days-weighted mean return of the 10%/5%/12-month strategy, % per month, under the paper's conventions",
        c.dumbbell(
            [(r["twin"], r["wmean"][0], r["wmean"][1]) for r in t4],
            label="Table IV weighted mean",
            unit="%",
            digits=3,
        ),  # fmt: skip
        ours_paper,
        table_html(
            ["Twin", "Positions", "Mean days", "Weighted mean % p.m.", "Median % p.m."],
            [
                [
                    r["twin"],
                    f"{r['positions'][0]} / {r['positions'][1]}",
                    f"{r['mean_days'][0]} / {r['mean_days'][1]}",
                    f"{r['wmean'][0]:.3f} / {r['wmean'][1]:.3f}",
                    f"{r['median'][0]:.3f} / {r['median'][1]:.3f}",
                ]
                for r in t4
            ],
        ),  # fmt: skip
        d["table4"]["source"],
    )

    # Table V
    t5 = d["table5"]["rows"]
    figs["table5"] = figure(
        "table5",
        "Table V: eight strategies",
        "Days-weighted mean return, % per month, all twins, buy/sell threshold and maximum horizon",
        c.dumbbell(
            [(r["strategy"], r["wmean"][0], r["wmean"][1]) for r in t5],
            label="Table V weighted mean",
            unit="%",
            digits=3,
        ),  # fmt: skip
        ours_paper,
        table_html(
            ["Strategy", "Positions", "Weighted mean % p.m."],
            [
                [
                    r["strategy"],
                    f"{r['positions'][0]} / {r['positions'][1]}",
                    f"{r['wmean'][0]:.3f} / {r['wmean'][1]:.3f}",
                ]
                for r in t5
            ],
        ),  # fmt: skip
        d["table5"]["source"],
    )

    # Table VI
    t6 = d["table6"]["rows"]
    figs["table6"] = figure(
        "table6",
        "Table VI: Fama-French alpha",
        "FF3 alpha of the pooled position-days, % per month; significance in the table view (a 1%, b 5%, c 10%)",
        c.dumbbell(
            [(r["strategy"], r["alpha"][0], r["alpha"][1]) for r in t6],
            label="Table VI alpha",
            unit="%",
            digits=3,
        ),  # fmt: skip
        ours_paper,
        table_html(
            [
                "Strategy",
                "Alpha % p.m.",
                "Sig.",
                "Position-days",
                "σ",
                "σ S&P 500",
                "Kurtosis",
                "1% VaR",
            ],
            [
                [
                    r["strategy"],
                    f"{r['alpha'][0]:.3f} / {r['alpha'][1]:.3f}",
                    f"{r['sig'][0] or '–'} / {r['sig'][1] or '–'}",
                    f"{r['position_days'][0]} / {r['position_days'][1]}",
                    f"{r['sigma'][0]} / {r['sigma'][1]}",
                    f"{r['sigma_sp500'][0]} / {r['sigma_sp500'][1]}",
                    f"{r['kurtosis'][0]} / {r['kurtosis'][1]}",
                    f"{r['var'][0]} / {r['var'][1]}",
                ]
                for r in t6
            ],
        ),  # fmt: skip
        d["table6"]["source"],
    )

    # sensitivities (change against each side's own benchmark)
    sens = d["table6"]["sensitivities"]
    base_o, base_p = sens[0]["ours"], sens[0]["paper"]
    rows = [(s["case"], s["ours"] - base_o, s["paper"] - base_p) for s in sens[1:]]
    figs["sensitivities"] = figure(
        "sensitivities",
        "p. 515 sensitivities: change in the benchmark alpha",
        "Each case minus its own benchmark, % per month. Costs and rebate match; the one-day delay hurts ours twice "
        "as much",
        c.dumbbell(rows, label="Sensitivity of the benchmark alpha", unit="%", digits=3),
        ours_paper,
        table_html(
            ["Case", "Ours", "Paper", "Ours − benchmark", "Paper − benchmark"],
            [
                [
                    s["case"],
                    f"{s['ours']:.3f}",
                    f"{s['paper']:.3f}",
                    f"{s['ours'] - base_o:+.3f}",
                    f"{s['paper'] - base_p:+.3f}",
                ]
                for s in sens
            ],
        ),  # fmt: skip
        d["table6"]["source"],
    )

    # waterfall
    wf = d["waterfall"]
    steps = [s["label"] for s in wf["steps"]]
    allg = next(g for g in wf["groups"] if g["id"] == "all")
    figs["waterfall"] = figure(
        "waterfall",
        "From the paper's conventions to ours",
        "Benchmark 10%/5%/12 months, all twins, % per month; each step includes the ones before it. The third step "
        "trades one close after the signal",
        c.columns(
            steps,
            allg["wmean"],
            label="Convention waterfall",
            unit="%",
            digits=3,
            height=280,
            highlight=2,
        ),
        [("ours", "Cumulative step"), ("paper", "Largest single change")],
        table_html(
            ["Step", "% per month", "Excess % p.a.", "Sharpe", "Positions"],
            [
                [s, f"{w:.3f}", f"{e:.2f}", f"{sh:.3f}", p]
                for s, w, e, sh, p in zip(
                    steps,
                    allg["wmean"],
                    allg["excess_pa"],
                    allg["sharpe"],
                    allg["positions"],
                    strict=True,
                )
            ],
        ),  # fmt: skip
        wf["source"],
    )

    # small multiples by time-zone gap
    groups = [g for g in wf["groups"] if g["id"] != "all"]
    top = max(max(g["wmean"]) for g in groups)
    panels = "".join(
        '<div class="panel">'
        + c.columns(
            [str(i + 1) for i in range(len(steps))],
            g["wmean"],
            label=g["label"],
            digits=2,
            width=340,
            height=210,
            domain=(0, top),
            highlight=2,
            wrap=4,
            title=g["label"],
        )  # fmt: skip
        + "</div>"
        for g in groups
    )
    key = "".join(f"<li>{i + 1}. {esc(s)}</li>" for i, s in enumerate(steps))
    figs["groups"] = figure(
        "groups",
        "Where the return goes: by closing-time gap",
        "Same waterfall per group of twins, % per month, one shared scale. Steps: see the list",
        f'<div class="multiples">{panels}</div><ol class="step-key">{key}</ol>',
        [("ours", "Cumulative step"), ("paper", "Trade one close later")],
        table_html(
            ["Group"] + steps, [[g["label"]] + [f"{v:.3f}" for v in g["wmean"]] for g in groups]
        ),  # fmt: skip
        wf["source"],
    )

    # strategies: Sharpe paper conventions -> our standard
    st = wf["strategies"]
    figs["strategies"] = figure(
        "strategies",
        "Calendar-time Sharpe ratio of all eight strategies",
        "One daily portfolio over all twins, excess over the T-bill: under the paper's conventions and under ours",
        c.dumbbell(
            [(r["strategy"], r["sharpe"][1], r["sharpe"][0]) for r in st],
            label="Sharpe by strategy",
            digits=2,
            names=("Our standard", "Paper's conventions"),
        ),  # fmt: skip
        [("ours", "Our standard"), ("paper", "Paper's conventions")],
        table_html(
            [
                "Strategy",
                "% p.m. paper's conv.",
                "% p.m. ours",
                "Sharpe paper's conv.",
                "Sharpe ours",
            ],
            [
                [
                    r["strategy"],
                    f"{r['wmean'][0]:.3f}",
                    f"{r['wmean'][1]:.3f}",
                    f"{r['sharpe'][0]:.3f}",
                    f"{r['sharpe'][1]:.3f}",
                ]
                for r in st
            ],
        ),  # fmt: skip
        wf["source"],
    )

    # lab engine
    lab = d["lab_engine"]["rows"]
    figs["lab"] = figure(
        "lab",
        "The lab's engine: Sharpe ratio after and without costs",
        "Strategy dejong_threshold on the lab pairs' development periods, liquidity-scaled costs; 3-5 positions per run",
        c.grouped_hbars(
            [(f"{r['pair']}, {r['period']}", [r["sharpe"], r["sharpe_zero_cost"]]) for r in lab],
            roles=("ours", "third"),
            names=("after costs", "without costs"),
            label="Lab engine Sharpe ratios",
        ),  # fmt: skip
        [("ours", "After costs"), ("third", "Without costs")],
        table_html(
            [
                "Pair, period",
                "Positions",
                "Sharpe after costs",
                "Sharpe without costs",
                "Median order cost (bps)",
                "MLflow runs",
            ],
            [
                [
                    f"{r['pair']}, {r['period']}",
                    r["positions"],
                    f"{r['sharpe']:.3f}",
                    f"{r['sharpe_zero_cost']:.3f}",
                    r["median_order_cost_bps"],
                    f"{r['run']}, {r['run_zero_cost']}",
                ]
                for r in lab
            ],
        ),  # fmt: skip
        d["lab_engine"]["source"],
    )

    # Dexia spike
    dx = d["table6"]["dexia_spike"]
    rows = [(lab_, k, "paper" if lab_ == "paper" else "ours", f"Kurtosis, {lab_}: {k}")
            for lab_, k in zip(dx["labels"], dx["kurtosis"], strict=True)]  # fmt: skip
    figs["dexia"] = figure(
        "dexia",
        "One data error, most of the excess kurtosis",
        "Kurtosis of the pooled daily returns, 10%/5%/12 months, with the 1997-12-19 Dexia spike and without it",
        c.hbars(rows, label="Kurtosis with and without the Dexia spike", left=180),
        ours_paper,
        table_html(
            ["Case", "Kurtosis", "Alpha % p.m."],
            [
                [lab_, k, a]
                for lab_, k, a in zip(dx["labels"], dx["kurtosis"], dx["alpha"], strict=True)
            ],
        ),  # fmt: skip
        d["table6"]["source"],
    )
    return figs


# ---------------------------------------------------------------- page parts


# verdict keyword -> (status color, icon, short label); first match wins
VERDICT_STATUS = [
    ("not robust", "warning", "!", "Partly"),
    ("challenged", "serious", "✕", "Challenged"),
    ("not tested", "neutral", "–", "Not tested"),
    ("reproduced", "good", "✓", "Reproduced"),
]


def claims_cards(d: dict) -> str:
    cards = []
    for cl in d["claims"]:
        status, icon, short = next(
            ((s, i, lbl) for key, s, i, lbl in VERDICT_STATUS if key in cl["verdict"]),
            ("neutral", "–", "Open"),
        )
        detail = cl["verdict"] if cl["verdict"].lower() != short.lower() else ""
        cards.append(
            f'<div class="claim {status}"><div class="claim-head"><span class="claim-id">{esc(cl["id"])}</span>'
            f'<span class="chip {status}"><span aria-hidden="true">{icon}</span> {esc(short)}</span></div>'
            f'<p class="claim-text">{esc(cl["claim"])}</p>'
            + (f'<p class="claim-verdict">{esc(detail)}</p>' if detail else "")
            + (f'<p class="claim-evidence">{esc(cl["evidence"])}</p>' if cl["evidence"] else "")
            + "</div>"
        )
    return f'<div class="claims">{"".join(cards)}</div>'


def tiles(d: dict) -> str:
    t4 = d["table4"]["total"]
    bench = next(r for r in d["table6"]["rows"] if r["strategy"] == "10%/5%/12 months")
    allg = next(g for g in d["waterfall"]["groups"] if g["id"] == "all")
    drop = 1 - allg["wmean"][2] / allg["wmean"][1]
    items = [
        (
            "Benchmark return, % per month",
            f"{t4['wmean'][0]:.3f}",
            f"paper {t4['wmean'][1]:.3f}",
            "good",
        ),
        (
            "Fama-French alpha, % per month",
            f"{bench['alpha'][0]:.3f}",
            f"paper {bench['alpha'][1]:.3f}, both at 1%",
            "good",
        ),  # fmt: skip
        (
            "Return lost trading one close later",
            f"{100 * drop:.0f}%",
            "85% for the Australian twins",
            "serious",
        ),
        (
            "Sharpe ratio under our standard",
            f"{allg['sharpe'][-1]:.2f}",
            f"paper's conventions {allg['sharpe'][0]:.2f}",
            "warning",
        ),  # fmt: skip
    ]
    return (
        '<div class="tiles">'
        + "".join(
            f'<div class="tile"><div class="tile-label">{esc(lbl)}</div><div class="tile-value">{esc(v)}</div>'
            f'<div class="tile-delta {s}">{esc(sub)}</div></div>'
            for lbl, v, sub, s in items
        )
        + "</div>"
    )


def render_markdown(md_text: str) -> tuple[str, str, list[dict]]:
    """(title, body html, toc tokens) of the report Markdown."""
    lines = md_text.splitlines()
    title = lines[0].lstrip("# ").strip()
    md = markdown.Markdown(extensions=["tables", "fenced_code", "toc", "sane_lists"])
    body = md.convert("\n".join(lines[1:]))
    return title, body, md.toc_tokens


def insert_figures(body: str, figs: dict[str, str]) -> str:
    missing = set(MARKER.findall(body)) - set(figs)
    if missing:
        raise KeyError(f"chart markers without a chart: {sorted(missing)}")
    return MARKER.sub(lambda m: figs[m.group(1)], body)


def toc_html(tokens: list[dict]) -> str:
    items = []
    for t in tokens:
        for h2 in t.get("children", []) if t["level"] == 1 else [t]:
            items.append(f'<li><a href="#{esc(h2["id"])}">{esc(h2["name"])}</a></li>')
    return f'<nav class="toc" aria-label="Contents"><p class="toc-title">Contents</p><ol>{"".join(items)}</ol></nav>'


def page(root: Path, *, print_version: bool = False) -> str:
    d = load_data(root)
    title, body, toc = render_markdown((root / REPORT_MD).read_text(encoding="utf-8"))
    body = insert_figures(body, build_figures(d))
    body = body.replace("<table>", '<div class="table-wrap"><table>').replace(
        "</table>", "</table></div>"
    )
    if print_version:
        body = body.replace(
            '<details class="table-view print-open">',
            '<details class="table-view print-open" open>',
        )
    meta = d["meta"]
    header = (
        f'<header class="hero"><p class="eyebrow">Quant research lab · paper 2 · steps {esc(meta["steps"])}</p>'
        f"<h1>{esc(title)}</h1>"
        f'<p class="byline">{esc(meta["paper"])} · final report, {esc(meta["date"])}</p>'
        f'{tiles(d)}<h2 class="claims-title">The paper\'s claims, checked</h2>{claims_cards(d)}</header>'
    )
    return TEMPLATE.format(
        title=esc(title),
        css=CSS,
        script=SCRIPT,
        toc=toc_html(toc),
        header=header,
        body=body,
        theme=' data-theme="light"' if print_version else "",
    )


def find_chromium() -> str | None:
    env = os.environ.get("QUANT_LAB_CHROMIUM")
    if env:
        return env
    for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable"):
        found = shutil.which(name)
        if found:
            return found
    hits = sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))
    return hits[-1] if hits else None


def write_pdf(html_text: str, out: Path) -> bool:
    chrome = find_chromium()
    if chrome is None:
        print("no Chromium found (set QUANT_LAB_CHROMIUM): PDF skipped")
        return False
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "print.html"
        src.write_text(html_text, encoding="utf-8")
        subprocess.run(
            [chrome, "--headless", "--no-sandbox", "--disable-gpu", "--no-pdf-header-footer",
             f"--print-to-pdf={out}", "--virtual-time-budget=2000", src.as_uri()],
            check=True, capture_output=True,
        )  # fmt: skip
    return True


def build(root: Path, *, pdf: bool = True) -> dict:
    out_html = root / OUT_HTML
    out_html.write_text(page(root), encoding="utf-8")
    made_pdf = write_pdf(page(root, print_version=True), root / OUT_PDF) if pdf else False
    return {"html": out_html, "pdf": (root / OUT_PDF) if made_pdf else None}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--no-pdf", action="store_true", help="write the HTML only")
    args = parser.parse_args(argv)
    out = build(Path.cwd(), pdf=not args.no_pdf)
    print("html:", out["html"])
    print("pdf:", out["pdf"] or "skipped")


# ---------------------------------------------------------------- page template

CSS = """
:root{color-scheme:light;
--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink-2:#52514e;--muted:#6f6d68;--grid:#e1e0d9;--axis:#c3c2b7;
--border:rgba(11,11,11,.10);--ours:#2a78d6;--paper:#eb6834;--third:#1baf7a;--track:#eceae4;
--good:#0ca30c;--good-ink:#006300;--warning:#fab219;--serious:#ec835a;--critical:#d03b3b;--accent:#2a78d6;
--code:#f0efec}
@media (prefers-color-scheme:dark){:root:where(:not([data-theme="light"])){color-scheme:dark;
--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink-2:#c3c2b7;--muted:#9a988f;--grid:#2c2c2a;--axis:#383835;
--border:rgba(255,255,255,.10);--ours:#3987e5;--paper:#d95926;--third:#199e70;--track:#262624;
--good-ink:#0ca30c;--accent:#5598e7;--code:#232321}}
:root[data-theme="dark"]{color-scheme:dark;
--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink-2:#c3c2b7;--muted:#9a988f;--grid:#2c2c2a;--axis:#383835;
--border:rgba(255,255,255,.10);--ours:#3987e5;--paper:#d95926;--third:#199e70;--track:#262624;
--good-ink:#0ca30c;--accent:#5598e7;--code:#232321}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--page);color:var(--ink);font:16px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif}
.layout{display:grid;grid-template-columns:260px minmax(0,1fr);max-width:1240px;margin:0 auto;gap:32px;padding:0 24px}
.toc{position:sticky;top:0;align-self:start;max-height:100vh;overflow:auto;padding:28px 0}
.toc-title{font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin:0 0 8px}
.toc ol{list-style:none;margin:0;padding:0}
.toc a{display:block;padding:5px 10px;border-radius:6px;color:var(--ink-2);text-decoration:none;font-size:14px}
.toc a:hover{background:var(--surface);color:var(--ink)}
.toc a.active{color:var(--ink);background:var(--surface);box-shadow:inset 3px 0 0 var(--accent)}
main{min-width:0;padding:28px 0 80px}
.topbar{display:flex;justify-content:flex-end;gap:8px}
button.theme{font:inherit;font-size:13px;color:var(--ink-2);background:var(--surface);border:1px solid var(--border);
border-radius:999px;padding:4px 12px;cursor:pointer}
.hero h1{font-size:34px;line-height:1.2;margin:8px 0 6px;letter-spacing:-.01em}
.eyebrow{margin:0;color:var(--muted);font-size:13px;letter-spacing:.04em;text-transform:uppercase}
.byline{margin:0 0 24px;color:var(--ink-2)}
.tiles{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:0 0 28px}
.tile{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:14px 16px}
.tile-label{font-size:13px;color:var(--ink-2)}
.tile-value{font-size:30px;font-weight:600;margin:4px 0 2px}
.tile-delta{font-size:13px;color:var(--ink-2)}
.tile-delta::before{content:"";display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px;
vertical-align:1px;background:var(--muted)}
.tile-delta.good::before{background:var(--good)}.tile-delta.warning::before{background:var(--warning)}
.tile-delta.serious::before{background:var(--serious)}
.claims-title{font-size:20px;margin:0 0 12px;border:0;padding:0}
.claims{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:12px;margin-bottom:12px}
.claim{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:12px 14px}
.claim-head{display:flex;align-items:center;justify-content:space-between;gap:8px}
.claim-id{font-weight:600;color:var(--ink-2)}
.chip{font-size:12px;border-radius:999px;padding:2px 8px;border:1px solid var(--border);color:var(--ink);
background:var(--page);white-space:normal;text-align:right}
.chip span{font-weight:700}
.chip.good span{color:var(--good)}.chip.warning span{color:#b07800}.chip.serious span{color:var(--serious)}
.chip.neutral span{color:var(--muted)}
.claim-text{margin:8px 0 4px;font-size:14px}
.claim-verdict{margin:0 0 4px;font-size:13px;font-weight:600;color:var(--ink)}
.claim-evidence{margin:0;font-size:13px;color:var(--ink-2)}
main h2{font-size:24px;margin:48px 0 12px;padding-top:12px;border-top:1px solid var(--border)}
main h3{font-size:18px;margin:28px 0 8px}
main p,main li{max-width:78ch}
a{color:var(--accent)}
code{background:var(--code);padding:1px 5px;border-radius:4px;font-size:.88em}
pre{background:var(--code);padding:14px;border-radius:10px;overflow:auto;font-size:13px}
pre code{background:none;padding:0}
.table-wrap{overflow-x:auto;margin:12px 0;border:1px solid var(--border);border-radius:10px;background:var(--surface)}
table{border-collapse:collapse;width:100%;font-size:14px;font-variant-numeric:tabular-nums}
th,td{text-align:left;padding:7px 10px;border-bottom:1px solid var(--grid);vertical-align:top}
th{color:var(--ink-2);font-weight:600;background:var(--page)}
tr:last-child td{border-bottom:0}
.viz{margin:20px 0 28px;background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:16px 18px}
.viz figcaption{display:flex;flex-direction:column;gap:2px;margin-bottom:8px}
.fig-title{font-weight:600;font-size:16px}
.fig-sub{font-size:13px;color:var(--ink-2)}
.legend{display:flex;flex-wrap:wrap;gap:14px;font-size:13px;color:var(--ink-2);margin:4px 0 6px}
.key{display:inline-flex;align-items:center;gap:6px}
.swatch{width:10px;height:10px;border-radius:50%;display:inline-block}
.swatch.ours{background:var(--ours)}.swatch.paper{background:var(--paper)}.swatch.third{background:var(--third)}
.source{font-size:12px;color:var(--muted);margin:8px 0 0}
details.table-view summary{cursor:pointer;font-size:13px;color:var(--accent);margin-top:6px}
details.table-view .table-wrap{margin-top:8px}
.multiples{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
.step-key{font-size:13px;color:var(--ink-2);columns:2;margin:8px 0 0;padding-left:0;list-style:none}
svg.chart{display:block;height:auto;overflow:visible}
svg .grid{stroke:var(--grid);stroke-width:1}
svg .baseline{stroke:var(--axis);stroke-width:1}
svg .identity{stroke:var(--axis);stroke-width:1.5}
svg .connector{stroke:var(--axis);stroke-width:2;stroke-linecap:round}
svg .dot{stroke:var(--surface);stroke-width:2}
svg .dot.ours,svg .bar.ours{fill:var(--ours)}
svg .dot.paper,svg .bar.paper{fill:var(--paper)}
svg .bar.third{fill:var(--third)}
svg .track{fill:var(--track)}
svg .hit{fill:transparent}
svg .t-muted{fill:var(--muted)}svg .t-secondary{fill:var(--ink-2)}svg .t-primary{fill:var(--ink)}
svg .mark{cursor:default;outline:none}
svg .mark:hover .dot,svg .mark:focus .dot{stroke:var(--ink)}
svg .mark:hover .bar,svg .mark:focus .bar{opacity:.85}
.tooltip{position:fixed;pointer-events:none;z-index:10;background:var(--ink);color:var(--surface);font-size:13px;
padding:6px 9px;border-radius:8px;max-width:320px;opacity:0;transition:opacity .08s}
.tooltip.on{opacity:1}
footer{color:var(--muted);font-size:13px;margin-top:48px}
@media (max-width:900px){.layout{grid-template-columns:1fr;padding:0 16px}.toc{position:static;max-height:none;padding:16px 0 0}
.toc ol{columns:2}.tiles{grid-template-columns:repeat(2,minmax(0,1fr))}.multiples{grid-template-columns:1fr}
.hero h1{font-size:26px}}
@media print{
:root,:root[data-theme="dark"]{color-scheme:light;--page:#fff;--surface:#fff;--ink:#0b0b0b;--ink-2:#52514e;--muted:#6f6d68;
--grid:#e1e0d9;--axis:#c3c2b7;--border:rgba(11,11,11,.14);--ours:#2a78d6;--paper:#eb6834;--third:#1baf7a;--track:#eceae4;
--accent:#1c5cab;--code:#f3f2ee}
@page{size:A4;margin:16mm 14mm}
body{font-size:11pt}
.layout{display:block;padding:0;max-width:none}
.toc,.topbar,.tooltip{display:none}
main{padding:0}
.hero h1{font-size:22pt}
.tiles{grid-template-columns:repeat(4,1fr)}
.multiples{grid-template-columns:repeat(2,minmax(0,1fr))}
.viz{break-inside:auto;padding:10px 12px}
.viz svg,.viz figcaption,.legend,.panel,.tile,.claim,tr{break-inside:avoid}
.viz figcaption,.legend{break-after:avoid}
.table-wrap{break-inside:auto}
main h2{break-after:avoid;margin-top:28px}
main h3{break-after:avoid}
details.table-view summary{display:none}
details.table-view:not([open]){display:none}
a{color:inherit;text-decoration:none}
}
"""

SCRIPT = """
(function(){
  var root=document.documentElement, btn=document.querySelector('button.theme');
  function current(){return root.dataset.theme||(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light')}
  try{var saved=localStorage.getItem('dejong-report-theme'); if(saved && !root.dataset.theme) root.dataset.theme=saved;}catch(e){}
  function label(){if(btn) btn.textContent=current()==='dark'?'Light theme':'Dark theme'}
  if(btn){btn.addEventListener('click',function(){var t=current()==='dark'?'light':'dark';root.dataset.theme=t;
    try{localStorage.setItem('dejong-report-theme',t)}catch(e){} label();}); label();}
  var tip=document.createElement('div'); tip.className='tooltip'; tip.setAttribute('role','status'); document.body.appendChild(tip);
  function show(el,x,y){tip.textContent=el.getAttribute('data-tip'); tip.classList.add('on');
    var w=tip.offsetWidth,h=tip.offsetHeight; var left=Math.min(x+14,innerWidth-w-8), top=y-h-12<8?y+16:y-h-12;
    tip.style.left=left+'px'; tip.style.top=top+'px';}
  document.addEventListener('pointermove',function(e){var el=e.target.closest&&e.target.closest('[data-tip]');
    if(el) show(el,e.clientX,e.clientY); else tip.classList.remove('on');});
  document.addEventListener('focusin',function(e){var el=e.target.closest&&e.target.closest('[data-tip]');
    if(el){var r=el.getBoundingClientRect(); show(el,r.left+r.width/2,r.top);} });
  document.addEventListener('focusout',function(){tip.classList.remove('on')});
  window.addEventListener('beforeprint',function(){document.querySelectorAll('details.print-open').forEach(function(d){d.open=true})});
  var links=[].slice.call(document.querySelectorAll('.toc a')), heads=links.map(function(a){return document.getElementById(a.getAttribute('href').slice(1))});
  if('IntersectionObserver' in window){var io=new IntersectionObserver(function(es){es.forEach(function(en){if(en.isIntersecting){
    links.forEach(function(a){a.classList.toggle('active',a.getAttribute('href')==='#'+en.target.id)})}})},{rootMargin:'0px 0px -70% 0px'});
    heads.forEach(function(h){if(h) io.observe(h)});}
})();
"""

TEMPLATE = """<!doctype html>
<html lang="en"{theme}>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{css}</style>
</head>
<body>
<div class="layout">
{toc}
<main>
<div class="topbar"><button class="theme" type="button">Dark theme</button></div>
{header}
<article>{body}</article>
<footer>Rendered from research/reports/dejong_final_report.md and research/reports/dejong_final/report_data.yaml
by quant_lab.reporting.dejong_final. Aggregates only; the underlying Datastream data is licensed.</footer>
</main>
</div>
<script>{script}</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()

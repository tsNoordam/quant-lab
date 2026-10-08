# de Jong et al. (2009), Tables IV-V replication: the arbitrage strategies (step 16)

Date: 2026-10-08.

- **Code:**
  - `quant_lab.backtest.dejong` is the paper-convention engine: positions,
    Regulation T account, tables (MLflow experiment `dejong.replication`, run
    `tables45`).
  - Configuration is in `conf/dejong/default.yaml`.
  - Trading panels: `data/interim/dlc/<twin>.trading.parquet` (DVC stage
    `dlc_ingest`).
- **Data:**
  - the 12 DLC workbooks over the user-approved 1980-2002 windows;
  - the 3-month T-bill (FRED DTB3, `data/raw/fred_tbill/`, to be added by the
    user).
- **Aggregates only** (licensed data).

Reproduce:

    uv run dvc repro dlc_ingest
    uv run python -m quant_lab.backtest.dejong

> **Status: return statistics are provisional.** FRED is not reachable from the
> cloud session, so the return figures below were computed with a stand-in
> T-bill: statsmodels' quarterly FRED average (`macrodata.tbilrate`).
>
> The T-bill only pads positions shorter than a month. Holding statistics
> (positions, days, cut-offs) do not depend on it and are final.
>
> The return figures are replaced by the user's run on DTB3 before this step
> closes.

## 1. What the paper specifies and what we had to identify

The paper fixes the parameters (thresholds, horizons, costs, margins, rates)
but not every mechanic. The workbooks contain no simulation sheets.

Each convention below was identified from the paper's own Table IV-V numbers,
in sequence, with a scratch prototype. About 30 combinations were examined.
They are replication conventions, not strategy parameters: the whole sample is
the paper's in-sample period, so nothing out-of-sample was used.

| # | Convention | Evidence (prototype, before the next convention was added) |
|---|---|---|
| D6 | **Entry on a crossing:** \|d\| >= b on the signal day and < b the day before | Closer to the paper's counts than entry at any \|d\| >= b for RD/Shell (4/12 vs 6/14; paper 3/12), Unilever, Reed and Smithkline; further for ABB (5/4 vs 5/5; paper 5/5); equal for the rest |
| D4 | **Exit signal on the first close with \|d\| <= s** | Gives the paper's maximum holding periods: Fortis 99, Merita 148 |
| D5 | **No new position within 22 trading days of the previous entry.** The proceeds of a short position stay in the T-bill until the month is over | Positions 138 → 124 (paper 127). BHP (0/5, mean 23.0, max 27), Brambles (1/4, 30.6, 65), Fortis (14/4, 32.8, 99) and Unilever (10/21, 88.6) become exact |
| D20 | **Unified twins:** a position still open at the window end is held, and closed on the first trading day after the unification announcement (21 rows later) | ABB 5/5, Dexia 4/0, Merita 4/0, Zürich 0/3 become exact, with means 96.7, 124.5, 55.3, 133.0 and Zürich's max 254. Text: "open positions at the end of the sample period are not taken into account" holds only for twins not unified in the sample |
| D4 | **Trades at the close on which the signal is observed** (delay 0). Positions and days are the same either way; only returns tell them apart | With a one-day delay, BHP, Rio and Zürich have losing positions; the paper has none. The paper's own one-day-delay case cuts alpha from 0.718 to 0.382 (factor 0.53); ours cuts the benchmark return from 1.158 to 0.489 (factor 0.42) |
| D19 | **Leg returns in one currency** (A converted to B's), so a position's P&L follows the deviation | With local-currency (hedged) returns, BHP, Rio, Brambles and Merita have losing 22-day positions (BHP min −2.98 vs paper +2.93); in one currency none do |
| D3 | **Half spread paid at exit as well** | BHP min 3.32 → 2.99 (paper 2.93); Fortis weighted mean 4.09 → 3.82 (3.76) |
| D21 | **The short sale's 50% margin deposit is collateral and earns nothing**; "cash balances" are free cash | Total weighted mean 1.47 → 1.27 (paper 1.18), median 3.87 → 3.695 (3.703); negative positions exact for RD/Shell, Unilever and Smithkline |

**Fixed by the text, not by fit:**

- **Total-return P&L (D2):** price-only is reported as a variant.
- **Arithmetic monthly return:** total return × 22 / days, days at least 22.
- **Interest per trading day:** rate / 260.
- **T-bill at the exit date (D11).**
- **Per-leg margin rule (D10):** "25% for long positions and 30% for short
  positions"; pooled is reported as a variant.

The secondary choices (dividends, monthly compounding, median convention)
moved the fit only marginally. Choosing them by fit, with a stand-in T-bill,
would have been overfitting.

## 2. Holding statistics (final)

### Table IV (10%/5%/12 months)

**78 of 91 statistics agree within rounding**, among positions, mean, median,
min and max days, and cut-offs. **Position counts by direction match for 11 of
12 twins.**

The differences:

| Twin | Statistic | Ours | Paper | Reading |
|---|---|---|---|---|
| Elsevier/Reed | positions long A | 7 | 6 | one extra position; mean days 109.4 vs 116.2 follow from it |
| RD/Shell | cut-offs | 4 | 5 | one position that converges exactly at day 260 is a cut-off in the paper? |
| Smithkline | mean days | 166.8 | 167.7 | the authors converted Smithkline to Datastream dates for "the arbitrage simulations" (workbook note); we trade the Bloomberg dates of the step-14 panel |
| Rio Tinto | mean days | 24.77 | 24.6 | one day over 13 positions |
| ABB, Smithkline | median days | 51.5, 193.5 | 77, 260 | even number of positions: the paper reports the upper middle value |
| Dexia, Merita | median days | 108, 25.5 | 46, 22 | even number: the paper reports the lower middle value |

The median convention is inconsistent, so it was not adjusted.

### Table V (eight strategies)

Positions and cut-offs are within 4 of the paper in every strategy, for
example 10%/5%/1 month: 109/181 vs 107/181 positions, 214 vs 215 cut-offs.

## 3. Returns (provisional: stand-in T-bill)

### Table IV, ours / paper (% per month)

| Twin | Weighted mean | Median | Min | Max | # < 0 | # margin calls |
|---|---|---|---|---|---|---|
| Royal Dutch/Shell | 0.403 / 0.492 | 1.372 / 1.460 | -0.593 / -0.728 | 5.542 / 5.393 | 3 / 2 | 3 / 3 |
| Unilever | 1.188 / 1.134 | 4.499 / 4.346 | -1.445 / -1.374 | 14.280 / 13.044 | 4 / 4 | 9 / 6 |
| ABB | 0.739 / 0.920 | 2.403 / 3.607 | -0.416 / -0.393 | 7.073 / 6.960 | 2 / 1 | 3 / 1 |
| Smithkline Beecham | 0.321 / 0.147 | 0.417 / 0.680 | -0.090 / -0.464 | 4.106 / 3.976 | 1 / 2 | 2 / 2 |
| Fortis | 3.577 / 3.760 | 4.518 / 4.677 | 0.748 / 0.805 | 9.705 / 9.589 | 0 / 0 | 2 / 0 |
| Elsevier/Reed | 0.817 / 0.694 | 1.577 / 1.095 | -0.295 / -0.573 | 10.230 / 9.552 | 2 / 1 | 4 / 1 |
| Rio Tinto | 5.392 / 5.054 | 4.846 / 5.140 | 3.383 / 2.539 | 8.763 / 8.250 | 0 / 0 | 0 / 0 |
| Dexia | 0.336 / 0.917 | 3.296 / 1.179 | -1.734 / -0.318 | 5.720 / 5.385 | 1 / 1 | 1 / 1 |
| Merita/Nordbanken | 1.880 / 2.150 | 4.546 / 2.885 | -0.065 / 0.513 | 9.298 / 8.627 | 1 / 0 | 1 / 0 |
| Zürich Allied | 0.691 / 1.062 | 0.715 / 1.249 | 0.373 / 0.712 | 4.221 / 4.058 | 0 / 0 | 2 / 0 |
| BHP Billiton | 4.190 / 4.238 | 3.717 / 3.703 | 2.782 / 2.930 | 7.098 / 6.705 | 0 / 0 | 0 / 0 |
| Brambles | 3.813 / 3.106 | 4.733 / 3.830 | 1.538 / 0.764 | 8.437 / 6.056 | 0 / 0 | 0 / 0 |
| **Total** | **1.158 / 1.180** | **3.696 / 3.703** | -1.734 / -1.374 | 14.280 / 13.044 | 14 / 11 | 27 / 14 |

**The benchmark total is reproduced:**

- weighted mean 1.158 vs 1.180% per month;
- median 3.696 vs 3.703.

Per twin, the returns are close but rarely within rounding (7 of 65
statistics).

### Table V, weighted mean % per month, ours / paper

| Strategy | Primary | Dexia spike removed | Pooled margin | Price only | One-day delay |
|---|---|---|---|---|---|
| 5%/1%/1 month | -0.140 / -0.009 | -0.140 | -0.108 | -0.131 | -0.743 |
| 5%/1%/3 months | 0.497 / 0.558 | 0.497 | 0.575 | 0.467 | 0.096 |
| 5%/1%/12 months | 0.689 / 0.892 | 0.717 | 0.803 | 0.671 | 0.390 |
| 5%/1%/unlimited | 0.639 / 0.780 | 0.663 | 0.801 | 0.625 | 0.402 |
| 10%/5%/1 month | 0.483 / 0.432 | 0.535 | 0.527 | 0.480 | -0.625 |
| 10%/5%/3 months | 1.042 / 1.064 | 1.082 | 1.094 | 1.057 | 0.195 |
| 10%/5%/12 months | 1.158 / 1.180 | 1.201 | 1.271 | 1.135 | 0.489 |
| 10%/5%/unlimited | 1.131 / 1.238 | 1.174 | 1.369 | 1.110 | 0.510 |

The paper's pattern is reproduced:

- 5%/1%/1 month is about zero;
- the 10%/5% strategies earn about 1% per month from 3 months on;
- returns rise with the horizon.

The 5%/1% strategies run 0.06-0.2 below the paper. The paper's 5%/1% maximum
of 11.704 (the same position in all four horizons) is not reached: ours is
7.3-10.5.

## 4. Open points

1. **Margin calls (D10).**
   - In the benchmark, 27 positions have margin calls under the per-leg rule,
     against 14 in the paper; the pooled rule gives 1.
   - The same holds in every strategy (1 month: 12 per-leg, 0 pooled, 3-4 in
     the paper).
   - The paper's rule lies in between and is not identified.
   - The returns of the two rules bracket the paper's in most strategies.
2. **5%/1% returns** are lower than the paper's (above).
3. **Per-twin returns:**
   - Brambles is too high (3.81 vs 3.11).
   - Zürich, Dexia and ABB are too low.
   - Brambles and BHP fall in the low-rate period 2001-02, where the stand-in
     T-bill is coarsest; rerun with DTB3.
4. **Smithkline** is traded on the step-14 panel (Bloomberg dates). The authors
   converted it to Datastream dates for the simulations.

## 5. Findings for the research

- **The paper's trading convention is same-close execution.**
  - The signal and the trade use the same closing prices.
  - With one day of delay, the benchmark falls from 1.16 to 0.49% per month,
    and the 1-month strategies turn negative.
  - For twins whose markets close hours apart (Australia/UK: 10 hours), a
    same-close trade on both legs is not executable.
  - Step 18 (our standard: one bar later, liquidity costs) addresses this.
- **Positions in unified twins are held into the unification announcement.**
  The sample "ends 20 trading days before the announcement", but open
  positions run until the first trading day after it. They collect the
  announcement jump (e.g. Dexia -9.22% → -0.14%, p. 516). Affected:
  - one benchmark position each in ABB, Dexia, Merita and Zürich;
  - more under the unlimited horizons.
- **The Dexia spike (1997-12-19) matters only through one position.** The
  260-day position opened in July 1997:
  - with the spike, 17 margin-call days and -1.73% per month;
  - without it, -0.01% per month;
  - the paper's Dexia minimum, -0.318, lies in between.

  Both are reported; the total moves by 0.04.

## 6. Pinned by tests

- `tests/unit/test_dejong_engine.py`: the rules, the account, margin calls,
  padding, evidence parsing, the T-bill loader and the panel extension.
- `tests/integration/test_dejong_engine_real.py`, real data:
  - the 13 holding-statistic differences above;
  - position counts for 11 twins;
  - Table V counts within 4;
  - every forced close on the first trading day after the announcement;
  - with DTB3 present, a provisional bound on the benchmark returns.

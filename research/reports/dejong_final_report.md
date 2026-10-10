# The risk and return of arbitrage in dual-listed companies: replication and a test under realistic execution

Final report of the quant research lab on paper 2, steps 13-19. Date:
2026-10-10.

- **Paper:** de Jong, Rosenthal & van Dijk (2009), *The Risk and Return of
  Arbitrage in Dual-Listed Companies*, Review of Finance 13: 495-520.
- **Data:** the authors' own Datastream workbooks for 12 dual-listed companies
  (DLCs), licensed: aggregates only in this report. Public: FRED 3-month
  T-bill (DTB3) and Kenneth French's daily factors.
- **Every number below is taken from a committed report or a named MLflow
  run.**
  - The numbers are collected with their sources in
    `research/reports/dejong_final/report_data.yaml`.
  - The HTML and PDF versions of this report are rendered from that file
    (`quant_lab.reporting.dejong_final`).

## Summary

| | |
|---|---|
| **Is the paper reproducible?** | **Yes.** From the authors' own data, the deviations (Table II), the comovement regressions (Table III), the arbitrage strategies (Tables IV-V) and their abnormal returns (Table VI) reproduce closely. The benchmark strategy earns 1.158% per month (paper 1.180) with a Fama-French alpha of 0.794% (paper 0.718), significant at 1%. |
| **Is its result robust?** | **No.** The paper trades at the close on which its signal appears. Trading one close later, as any real desk must, removes 56% of the benchmark return (1.20 → 0.53% per month, Dexia spike cleaned), and 85% for the Australian twins, whose markets close 10 hours apart. |
| **What survives under the lab's standard?** | A calendar-time Sharpe ratio of about 0.16 before realistic costs, concentrated in twins that trade in one time zone. On the two pairs with the lab's full cost model, Sharpe ratios of -0.07 to 0.10 after costs, on 3-5 positions per run. |
| **Agreement with paper 1** | The same conclusion as the Maymin replication (steps 1-12): the mispricing is real and persistent, and execution and costs absorb the gain from trading it. |

## 1. Question

Why do the prices of twin shares, claims on the same cash flows, deviate from
parity for years in large and liquid companies? The paper measures the risk
and return of simple arbitrage strategies after realistic costs and margin
requirements, and concludes that the risk deters arbitrage.

This lab asked two questions:

1. Can the paper's results be reproduced from the authors' own data?
2. What is left of the arbitrage return under the lab's standard of
   execution: no look-ahead, trades after the signal, realistic costs?

## 2. The paper and its claims

`research/extraction/dejong_dlc.md`

| # | Claim | Verdict here |
|---|---|---|
| C1 | Every DLC shows large, persistent deviations from parity | **Reproduced** (Table II) |
| C2 | Relative returns co-move with local indices and exchange rates | **Reproduced** (Table III) |
| C3 | Threshold strategies earn abnormal returns of up to ~10% p.a. after costs and margin requirements | **Reproduced under the paper's conventions; not robust to execution** (Tables IV-VI, step 18) |
| C4 | The risk is idiosyncratic and fat-tailed, ~30% volatility | **Reproduced** (Table VI) |
| C5 | Time zones and currencies do not explain the mispricing (an unreported ADR test) | **Challenged.** Not tested with ADRs here, but the non-synchronous Australian twins lose 85% of their return under next-close execution |
| C6 | Taxes, governance and short-sale constraints explain little | Not tested |
| C7 | Prices converge within days of a unification announcement | Not tested directly. The strategies turn out to hold positions into the announcement (D20) |

The paper is in-sample by design: thresholds and horizons are chosen and
reported on the same 1980-2002 data.

## 3. Data and sample design

`research/reports/data_decisions.md` (2026-10-07), `data/metadata/`

**Twins and windows.** All 12 DLCs, each over the paper's Table II window:
from the merger (1980 for RD/Shell and Unilever) to 20 trading days before the
unification announcement, or to 2002-10-03.

| Closing-time gap | Twins |
|---|---|
| 0 hours | ABB, Dexia, Fortis |
| 1 hour | Royal Dutch/Shell, Unilever, Elsevier/Reed, Merita/Nordbanken, Zürich Allied |
| 5 hours | Smithkline Beecham |
| 10 hours | Rio Tinto, BHP Billiton, Brambles |

<!-- chart:windows -->

**The windows reach 2002-10-03.** The user approved these windows for this
replication. The 2000-02 period was the out-of-sample period of paper 1 (used
once, in step 11). So paper 2 has no out-of-sample period in this dataset, and
every run that reads 2000-02 rows is tagged `unlock_oos=true`.

**Inputs are checked against the authors' own columns.**

- The deviation from parity, d = ln(P_A/P_B) - ln(R), rebuilt from prices, FX
  and the workbook's theoretical ratio, equals the authors' column on every
  row of all 12 twins. The largest error is 4.4e-16.
- The regression returns equal our panels' total-return returns: 48,978
  checked, largest error 2.2e-15.

**Public data.**

- FRED DTB3, md5 `7edbf761…`.
- French daily factors, md5 `95ef09e3…`.

Both were downloaded by the user and versioned with DVC.

## 4. Methods and rule classifications

`research/assumptions/dejong_dlc.md` (D1-D25), `conf/dlc/`, `conf/dejong/default.yaml`

The paper fixes its parameters, such as thresholds, costs, margins and rates,
but not every mechanic, and the workbooks contain no simulation sheets. Each
open convention was identified from the paper's own numbers, one at a time,
and tagged:

| Area | Convention | How it was settled |
|---|---|---|
| Table III | e.r. is B's currency per unit of A's; R² unadjusted; leads and lags across the window edge; RD/Shell index without Royal Dutch; Dexia without the spike days; Smithkline on Datastream dates (D13-D17) | each reproduces every value of its table; the literal reading is kept as variant `as_stated` (59/84) |
| Table III | Newey-West: EViews default, fixed lag, no prewhitening (D18) | [IMPLEMENTATION-ASSUMPTION], chosen before comparing; 48/48 significance marks |
| Tables IV-V | entry on a crossing of the buy threshold (D6); exit at the sell threshold (D4); no new position within 22 days, the month the proceeds sit in the T-bill (D5) | position counts and holding periods |
| Tables IV-V | trades at the close on which the signal appears (D4) | only this timing gives the paper's all-positive returns for the Australian twins; its own one-day-delay case halves alpha |
| Tables IV-V | P&L in one currency (D19); half spread at exit too (D3); the short-sale margin deposit earns nothing (D21) | per-twin minima and totals |
| Tables IV-V | unified twins: open positions held until the first trading day after the announcement (D20) | holding periods of ABB, Dexia, Merita, Zürich |
| Tables IV-V | margin calls per leg (D10) | [IMPLEMENTATION-ASSUMPTION]; **not identified**: per leg gives 27 positions with calls, pooled 1, the paper 14 |
| Table VI | stacked position-days (D11); every day kept, factors 0 on US holidays (D22); sigma = daily sd × 22, the paper's "% per month" units (D23) | the paper's "# Days" and S&P 500 sigma |
| Table VI | IAPM (D25) | **not replicable**: Datastream's World index is not in the data |

**About 30 combinations of conventions were examined** to identify Tables
IV-V. These are replication conventions, not strategy parameters: no
threshold, horizon or cost was chosen on the data.

**Our standard (step 18)** keeps the paper's rule and changes its conventions
one at a time:

1. clean the Dexia spike;
2. trade on the close after the signal;
3. no position held into an announcement, positions open at the end marked;
4. no T-bill padding or lockout.

It also runs the rule as lab strategy `dejong_threshold`
(`research/specs/replication/dejong_threshold.md`) through the lab's engine,
with liquidity-scaled costs.

## 5. Results

### 5.1 Reproduction of the paper's tables

| Table | Within rounding | Notes |
|---|---|---|
| II, deviations from parity | **58 / 72** | Rio Tinto mean sign (-1.90 vs +1.90, a slip in the paper); ABB st. dev.; Dexia and Fortis differ throughout (data versions) |
| III, comovement | **77 / 84**, 48/48 significance marks | ABB one observation fewer; Brambles df 292 vs 293; Merita -0.317 vs -0.371 (transposed digits); Smithkline DW |
| IV, holding statistics | **78 / 91** | position counts exact for 11 of 12 twins (Reed one extra) |
| IV, all statistics | 91 / 169 | no single return value within rounding |
| V, eight strategies | 29 / 104 | positions and cut-offs within 4 of the paper everywhere |
| VI, FF3 | every alpha within 0.15% p.m. | significance marks agree for 5 of 8 strategies |

<!-- chart:scorecard -->

<!-- chart:table2 -->

<!-- chart:table3 -->

**Benchmark strategy (10%/5%/12 months), ours / paper:**

| Statistic | Ours | Paper |
|---|---|---|
| Positions | 128 | 127 |
| Weighted mean, % per month | 1.158 | 1.180 |
| Median, % per month | 3.697 | 3.703 |
| FF3 alpha, % per month | 0.794 (1%) | 0.718 (1%) |
| Sigma, "% per month" units | 29.7 | 30.7 |

Sources: `dejong_tables45.md`, run `1d9f0b53`; `dejong_table6.md`, run
`4d73e5e3`.

<!-- chart:table4 -->

<!-- chart:table5 -->

<!-- chart:table6 -->

**Cost sensitivities reproduce, the delay sensitivity does not.** On p. 515
the paper changes one assumption at a time. Our alpha changes by -0.267
(commission 50 bps), -0.203 (spread 80 bps) and -0.138 (rebate 1%), against
the paper's -0.265, -0.212 and -0.156. One extra day of delay costs us 0.633
and the paper 0.336.

<!-- chart:sensitivities -->

**Not reproduced.**

- **The margin-call counts:** 27 vs 14 positions.
- **The 5%/1% strategies:** they earn 0.06-0.2% per month less than the
  paper's. Their best position, 11.7% per month in the paper, does not
  appear.
- **Brambles, Zürich, Dexia and ABB:** per-twin returns are off by 0.2-0.7%
  per month.

### 5.2 The convention waterfall (step 18)

Run `8b36f314`, `dejong_standard.md`. Benchmark 10%/5%/12 months, all twins.
Each step includes the ones before it.

| Step | % per month (paper metric) | Excess return % p.a. (calendar time) | Sharpe (calendar time) | Positions |
|---|---|---|---|---|
| Paper's conventions | 1.158 | 5.8 | 0.38 | 128 |
| Dexia spike cleaned | 1.201 | 6.0 | 0.40 | 128 |
| **Trade one close later** | **0.530** | **0.5** | **0.03** | 128 |
| No announcement hold, ends marked | 0.471 | 0.1 | 0.01 | 130 |
| No T-bill padding or lockout | 0.662 | 2.7 | 0.16 | 144 |

<!-- chart:waterfall -->

By closing-time gap (% per month, paper's conventions → our standard):

| Gap | Paper's conventions | One close later | Our standard |
|---|---|---|---|
| 0 hours | 1.458 | 1.075 | 1.225 |
| 1 hour | 0.879 | 0.404 | 0.433 |
| 5 hours | 0.320 | 0.172 | 0.171 |
| 10 hours | 4.750 | 0.698 | 2.433 |

<!-- chart:groups -->

**Trading one close after the signal is the single largest change in every
group.** The Australian twins lose 85% of their return at that step. Their
deviations, measured on closes 10 hours apart, are partly noise that reverses
by the next close. The paper's strategy books that reversal by trading at the
same close on which it observes it, which no one can do.

Under our standard, no strategy keeps more than 0.16 of calendar-time Sharpe
ratio:

| Strategy | Sharpe, paper's conventions → our standard |
|---|---|
| 5%/1%/1 month | -0.21 → -0.33 |
| 5%/1%/3 months | 0.20 → 0.01 |
| 5%/1%/12 months | 0.35 → 0.15 |
| 5%/1%/unlimited | 0.28 → 0.13 |
| 10%/5%/1 month | 0.00 → -0.30 |
| 10%/5%/3 months | 0.33 → 0.10 |
| 10%/5%/12 months | 0.38 → 0.16 |
| 10%/5%/unlimited | 0.46 → 0.15 |

<!-- chart:strategies -->

### 5.3 The lab's engine with liquidity costs

Strategy `dejong_threshold`: the user's eight runs, git clean.

| Pair, period | Positions | Sharpe after costs | Sharpe without costs | Median order cost |
|---|---|---|---|---|
| RD/Shell, train 1987-96 | 5 | -0.07 | 0.09 | 22 bps |
| RD/Shell, validation 1997-99 | 3 | 0.10 | 0.25 | 29 bps |
| Elsevier/Reed, train 1993-97 | 3 | 0.03 | 0.24 | 41 bps |
| Elsevier/Reed, validation 1998-99 | 5 | 0.10 | 0.38 | 51 bps |

<!-- chart:lab -->

- **Costs are not the main difference.** The lab's costs per order are about
  the paper's 45 bps per leg; the main difference is timing.
- **After timing, costs remove most of what is left.**
- **No figure here is distinguishable from zero.**

## 6. Robustness and multiple testing

- **Variants of the paper engine,** each run on all eight strategies
  (`dejong_tables45.md`):
  - Dexia spike removed;
  - pooled margin rule;
  - price-only P&L;
  - one-day delay.

  The benchmark weighted mean moves between 1.135 and 1.271 under the first
  three. Under the one-day delay it falls to 0.489.
- **The Dexia spike:**
  - It decides one position (-1.73% vs -0.01% per month).
  - It drives most of the excess kurtosis in Table VI (21.9 → 12.9; paper
    9.6).
  - Together with Table III, this is strong evidence that the authors cleaned
    it.

<!-- chart:dexia -->
- **Multiple testing:**
  - The identification examined about 30 convention combinations against the
    paper's own numbers. Nothing was tuned for performance.
  - The step-18 lab runs add 4 trials per pair to the MLflow trial count of
    `rd_shell` and `reed_elsevier`.
  - No deflated Sharpe ratio was computed for paper 2, because no strategy is
    proposed: the result is a decomposition, not a candidate for trading.

## 7. Audits

**No `/audit-backtest` was run on the paper-2 engine.** It reproduces the
paper's conventions, including its same-close execution, which an audit would
flag as look-ahead in a strategy of ours. The waterfall measures exactly that.

The lab's own engine and `dejong_threshold` inherit the paper-1 audits
(`research/reports/audits/2026-10-07-freeze.md`).

The new strategy passes the structural look-ahead test
(`tests/structural/test_strategy_causality.py`).

## 8. Pre-registration and out-of-sample result

**Not applicable.** Paper 2 is a replication of a published in-sample result
on the authors' own data. The sample design decision (§3) states that no
out-of-sample period is left in this dataset for paper 2. Nothing in this
report is a pre-registered test.

A real test of the step-18 strategy needs data after 2002-10-03.

## 9. Errata and failed expectations

- **Corrected reading of the paper.** Our extraction (step 13) said the
  strategy samples exclude the unification announcement jumps. Step 16 showed
  the opposite (D20): open positions in unified twins are held until the first
  trading day after the announcement, and they collect the jump.
- **The review's suspicion was confirmed, not refuted.** Before any run, the
  review (`research/methodology/dejong_dlc.md` §2) flagged non-synchronous
  closes and same-day reversal as a possible source of the return. Step 18
  confirms it.
- **Unresolved:**
  - the paper's margin-call rule;
  - its median convention (inconsistent between twins);
  - its ABB, Dexia and Fortis data versions;
  - the 5%/1% maximum return.

## 10. Limitations

- **In-sample only.** The whole sample is the paper's own period. No
  out-of-sample claim is possible on this data.
- **Identified conventions are inferences.** They are inferred from matching
  numbers, not documented by the authors. Where two readings fit, both are
  reported.
- **The IAPM is not replicated.** The World index is missing; the paper's
  IAPM alphas lie within 0.05 of its FF3 alphas.
- **The lab's cost model covers two pairs only.** The other ten twins have no
  validated lab panels (volume and quotes). Their "our standard" figures keep
  the paper's flat costs.
- **Power.** The lab-engine runs have 3-5 positions each. The pooled waterfall
  is the informative result.
- **Time-zone groups are small.** 3, 5, 1 and 3 twins; the 5-hour group is a
  single twin.

## 11. Reproducibility

```bash
git clone https://github.com/tsNoordam/quant-lab.git && cd quant-lab
uv sync --locked
uv run dvc pull && uv run dvc repro dlc_ingest   # licensed data: needs access to the DVC remote
uv run pytest                                    # real-data pins: tests/integration/test_dejong_*.py
uv run python -m quant_lab.models.dejong          # Tables II-III
uv run python -m quant_lab.backtest.dejong        # Tables IV-V
uv run python -m quant_lab.models.dejong_risk     # Table VI
uv run python -m quant_lab.models.dejong_standard # step 18 waterfall
uv run python -m quant_lab.reporting.dejong_final # this report as HTML and PDF
```

**Pins.** Paper-2 headline numbers are pinned in
`tests/integration/test_dejong_real.py` and `test_dejong_engine_real.py`:

- Table II/III differences;
- holding statistics;
- the eight weighted means;
- the eight alphas;
- the waterfall.

**Paper 1 versus paper 2.** `uv run python -m quant_lab.reproduce` covers
paper 1's headline numbers only.

**There are no freeze tags for paper 2:** nothing was pre-registered.

## 12. Conclusion

The paper is reproducible from its authors' data to a degree that is rare.
Most entries of Tables II and III, and most holding statistics of Table IV,
match to the printed decimals. The strategy returns and alphas come within
about 0.15% per month without matching exactly. Where they differ, the cause
is identified or narrowed to a data version or an unidentified convention.

The result it reports, about 9% a year of abnormal return from arbitraging
twin shares, depends on trading at the closing price on which the opportunity
is observed. One close later, and with the Dexia data error cleaned, about
half of it disappears. For the twins whose markets close hours apart, most of
it disappears.

What remains is a calendar-time Sharpe ratio of about 0.16 before realistic
costs, and around zero after them on the pairs where those costs can be
measured.

The mispricing is real and persistent, as both papers say. Like paper 1, this
lab finds no tradable edge in it.

# Self-imposed limits to arbitrage in dual-listed shares: replication and out-of-sample test

Final report of the quant research lab, steps 1-12. Date: 2026-10-07.

- **Paper:** Maymin, *Self-Imposed Limits to Arbitrage* (SILTA).
- **Data:** Datastream dual-listed company (DLC) workbooks, licensed; aggregates
  only in this report.
- **Every number below is taken from a committed report or a named MLflow run.**

## 1. Question

Maymin argues that twin-share price gaps persist because arbitrageurs limit
themselves. They cap positions in days of trading volume and pace their
trading, so transaction costs and the rarity of convergence keep capital out.
The paper predicts:

- **H1:** a negative relation between the standardized relative price and the
  standardized relative volume of the two share classes, provided the expensive
  class trades more (chi > 0);
- **H2:** a roughly constant implied position limit of about 100 days of volume.

This lab asked two questions:

1. Does H1 hold in our data?
2. Can a trading strategy built on the paper's mechanism earn a net return,
   tested without look-ahead and with realistic costs?

The paper itself proposes no trading rule
(`research/specs/replication/maymin_silta.md`).

## 2. Data and sample design

`research/reports/data_decisions.md`

**Pairs.**

- Royal Dutch/Shell (`rd_shell`): the development pair.
- Reed/Elsevier (`reed_elsevier`): the validation pair.
- Rio Tinto Ltd/plc (`rio_tinto`): out-of-sample only, a pair the paper did not
  study.
- Unilever was dropped. Its NV volume is about 300 times too low to be primary
  market volume.

**Locked splits.**

| Pair | Train | Validation | Out-of-sample |
|---|---|---|---|
| RD/Shell | 1987-1996 | 1997-1999 | 2000-01-01 .. 2002-10-03 |
| Reed/Elsevier | 1993-1997 | 1998-1999 | 2000-01-01 .. 2002-10-03 |
| Rio Tinto | none | none | 1996-2002, all of it |

**Mismatch with the paper.** The paper's twin sample is 2002-2007 and our data
ends in October 2002. So Table VI cannot be replicated numerically: H1 was
tested on an earlier, disjoint period instead.

**Data pipeline:**

- dates repaired;
- units converted;
- prices in GBP;
- a total-return series used for dividends;
- validation by deterministic code in `quant_lab.data.validation`.

## 3. Methods

- **Econometrics** (`quant_lab.models.silta`, step 7). The paper's four
  regression specifications plus a version that uses only past data. t-stats
  use Newey-West errors as in R `sandwich::NeweyWest`, checked against
  statsmodels. Lag sensitivity and the chi > 0 check (in shares and in value)
  are reported too.
- **Strategies.** Every rule is tagged by its source; specs are in
  `research/specs/`.
  - `parity_zscore` (baseline): trades a trailing 60-day z-score of
    ln(Pa/Pb). Enters beyond 2.0, exits inside 0.5.
  - `silta_parity` (step 8): the trade the paper's arbitrageur makes. It goes
    short the expensive leg when the deviation from theoretical parity exceeds
    the paper's 180 bps cost bound, and exits at parity.
  - Relative volume (H1) is deliberately not used as a signal. It describes the
    same day, not what happens next, and it was absent in our data.
- **Execution and costs.**
  - Fills at the next close.
  - Order costs: half the quoted spread (10 bps when no quote is available),
    plus square-root market impact on volatility and average daily volume
    lagged to the decision day, plus commission and FX conversion.
  - Borrow on the short leg; a 15% cap on participation in daily volume.
  - Total-return dividends: withholding tax on long positions, full payment on
    short positions.
  - VectorBT is reconciled against an independent reference implementation.
- **Look-ahead control.**
  - Structural tests check causality, each with a mutation check.
  - The out-of-sample period is locked (`+unlock_oos`, logged).
  - Split boundaries cannot be overridden from the command line.
  - The walk-forward has an embargo, and parameters are selected by the
    average over grid neighbours, not the single best point.

## 4. Development results

**H1 is not supported on 1987-1999 data** (`silta_replication.md`).

| Pair | Slope b | t | Paper (2002-07) |
|---|---|---|---|
| RD/Shell | +0.016 | 0.44 | -0.25 (t -3.4) |
| Reed Elsevier | +0.075 | 1.92 | -0.09 (t -2.2) |

- Reed Elsevier's sign is unstable across sub-periods.
- The chi > 0 condition holds in value traded for both pairs, so the null is
  not explained by it.

**Strategies on RD/Shell, after the freeze-audit corrections**
(`robustness_step9.md` errata, `audits/2026-10-07-freeze.md`):

| | Train 1987-96 | Validation 1997-99 | Walk-forward 1991-99 | Walk-forward at zero cost |
|---|---|---|---|---|
| parity_zscore | -0.38 | -0.98 | -0.34 (-11.5%) | +0.75 |
| silta_parity | -0.08 | +0.14 (one trade) | +0.02 (-0.7%) | +0.28 |

**Robustness** (step 9, 19 cases × 2 strategies).

- No positive net Sharpe in any realistic case, across costs, capital,
  leverage, selection rule and walk-forward design.
- Losses grow with capital.
- The walk-forward always picks the grid corner that trades least, because
  the objective is dominated by costs.
- The deflated Sharpe ratio is about 0 for both strategies.
- Reed Elsevier at the frozen values agrees.

## 5. Audits and what they changed

| Audit | Verdict | Findings and fixes |
|---|---|---|
| Step 5a | FAIL | Dividends were missing from P&L |
| Step 5b | WARNING | A1: total-return dividends fixed. A2: locked quotes fixed. A5: FX cost fixed |
| Freeze audit, step 10 | FAIL, then PASS with warnings | A1: the RD/Shell parity constant (6.863) matched only out-of-sample share counts; replaced by 6.9558 from pre-2000 share counts. A2: at the start of the data, positions could be held at zero size and orders could fill at zero cost; fixed |

Both freeze-audit defects were confirmed by tests that failed before the fix.
The documented warnings that remain:

- the fallback spread on unquoted legs;
- market impact sized on initial capital;
- grid-corner selection;
- entries just after ex-dividend dates on raw closes;
- the B6 wide quotes, kept as quoted, which is conservative.

## 6. Pre-registration and out-of-sample result

`research/specs/freeze/preregistration.md`, `oos_evaluation.md`

The freeze fixed in advance:

- the code, under tags `freeze-parity_zscore` and `freeze-silta_parity`;
- 6 primary runs and 3 secondary cost cases;
- n_trials = 600;
- the decision rule: deflated Sharpe above 0.95, at least 10 entries, no trade
  above 50% of P&L, and a Holm correction across the 6 runs;
- the power statement: about 1.5-1.8 annualized Sharpe is needed to count as
  evidence;
- the predictions;
- the Rio Tinto execution protocol.

The evaluation was run once by the user on the frozen tag (MLflow
`c5a6c503f45a4d5e818a5b96c27b3ddb`).

| Pair | parity_zscore net (gross) | silta_parity net (gross) |
|---|---|---|
| RD/Shell | -0.12 (+0.67) | +0.13 (+0.35), not evaluable, declared in advance |
| Reed Elsevier | -0.54 (+0.98) | -0.04 (+0.06), not evaluable (2 entries) |
| Rio Tinto | -0.27 (+0.76) | -0.28 (+0.84), -41% |

- **No run shows evidence of edge.** Every deflated Sharpe is below 0.3.
- **All pre-registered predictions held except one.** `silta_parity` made 9
  trades on RD/Shell, not the predicted 1-3.
- **The "edge before costs, loss after costs" pattern held** on RD/Shell and
  Reed Elsevier, as predicted. It also appears on Rio Tinto, as an exploratory
  observation.
- **Rio Tinto's loss also occurs in 2000-02**, the part that is new in time. It
  is consistent with noise from non-synchronous closes, which `silta_parity`
  pays costs to trade.

## 7. Limitations

- **Different period from the paper.** Our data uses the pre-2002 Datastream
  volume that Maymin chose to avoid. The paper's 2002-2007 sample was not
  available to us.
- **Low power.** About 690 out-of-sample days per twin pair gives a standard
  error of about 0.6 on an annualized Sharpe. Only a large edge is ruled out.
- **Costs are modelled, not observed.**
  - Royal Dutch had no quotes before 1997; the fallback spread was used.
  - Market impact is sized on initial capital.
  - Stamp duty is 0 in the base case; 50 bps is tested as a sensitivity.
  - The negative net result depends on the cost model. Halving market impact
    does not change it.
- **Rio Tinto is economically simplified.** Its closes are non-synchronous, and
  unfranked dividends and franking credits owed by short sellers are not
  modelled.
- **H2 was not calibrated.** Too few development days fall inside the 180 bps
  bound.
- **The 2000-02 period has been used.** It cannot be reused for these
  strategies.

## 8. Reproducibility

```bash
git clone https://github.com/tsNoordam/quant-lab.git && cd quant-lab
uv sync --locked
uv run dvc pull && uv run dvc repro     # licensed data: needs access to the DVC remote
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run python -m quant_lab.reproduce    # 10/10 headline development numbers
```

- **Headline numbers.** `research/reports/headlines.yaml` holds the Step 7
  slopes and the frozen-value and walk-forward Sharpe ratios. They are
  recomputed without logging and checked to 1e-4.
- **Out-of-sample run.** It is recorded in MLflow (`c5a6c503`), was produced
  from the freeze tags, and is not repeated.
- **CI** (`.github/workflows/ci.yml`) runs ruff and pytest on synthetic data
  only. Real-data tests skip themselves, and a check fails the build if any
  data file is tracked by git.
- **Fresh-clone check.** A clone with no data was verified locally: 268
  passed, 11 real-data tests skipped.

## 9. Conclusion

The paper's mechanism describes these pairs well. Deviations from parity are
persistent, and a mean-reversion trade on them is profitable before costs.
Realistic costs absorb that gain in development (1987-1999) and out of sample
(2000-2002, and Rio Tinto 1996-2002) alike.

Neither the relative-volume relation (H1, not found in our data) nor a trade
on the deviation from parity itself gave a tradable edge. This is a negative
result, reached with pre-registration and without look-ahead. It supports the
paper's explanation of why such discrepancies persist, not a strategy to
exploit them.

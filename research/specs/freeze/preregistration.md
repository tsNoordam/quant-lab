# Pre-registration: one-shot out-of-sample evaluation (steps 10-11)

Written 2026-10-07, before any backtest, return or price statistic of the OOS
period was computed. Frozen with the git tags `freeze-parity_zscore` and
`freeze-silta_parity` on the commit that adds this file.

**Executable form:** `conf/oos/default.yaml`, run by `quant_lab.backtest.oos`.
That module refuses to run:

- without `+unlock_oos=true`;
- on a dirty tree;
- when HEAD has no `freeze-*` tag.

**Audit behind the freeze:** `research/reports/audits/2026-10-07-freeze.md`.

## What is frozen

| | Value | Spec |
|---|---|---|
| `parity_zscore` | window 60, entry_z 2.0, exit_z 0.5, leg_weight 0.5 | `research/specs/baseline/parity_zscore.md` |
| `silta_parity` | entry_bound 0.018, exit_bound 0.0, leg_weight 0.5 | `research/specs/extensions/silta_parity.md` |
| Costs | `liquidity` defaults: impact k 1.0, fallback half-spread 10 bps, commission 5 bps, FX 3 bps, borrow 50 bps a year, stamp duty 0, 15% participation cap | `conf/costs/liquidity.yaml` |
| Execution | decision on close t, fill on close t+1 (`next_close`), init_cash 1,000,000 GBP | `conf/backtest/default.yaml` |
| Parity | RD/Shell 6.9558 (pre-2000 share counts), Reed/Elsevier 1.538, Rio Tinto 1.0 | `conf/data/*.yaml` |

The frozen values are the configured defaults, not the walk-forward's choices.
The development comparators are therefore the frozen-value runs below, not the
walk-forward figures.

## Runs (nothing else is ever run on the OOS period)

**Primary:** 2 strategies × 3 pairs = 6 runs.

| Pair | OOS window | Note |
|---|---|---|
| `rd_shell` | 2000-01-01 .. 2002-10-03 | warm-up uses pre-2000 history |
| `reed_elsevier` | 2000-01-01 .. 2002-10-03 | warm-up uses pre-2000 history |
| `rio_tinto` | 1996-01-01 .. 2002-10-03 | never used in development; starts at the first data row |

A `silta_parity` position open at the end of 1999 is entered on the second OOS
bar. Every period starts flat.

**Secondary,** all reported: `zero_cost` (gross of trading costs),
`stamp_duty_50` and `impact_k_0.5`, for each primary run.

**Diagnostics,** all reported:

- traded orders and entries;
- yearly net and gross returns, and the cost drag;
- sub-periods: split at 2002-07-01 for RD/Shell and Reed Elsevier (Royal Dutch
  left the S&P 500 in July 2002), and at 2000-01-01 for Rio Tinto;
- largest-trade share of absolute P&L;
- share of entries within 5 trading days after an ex-date (the raw-close
  artefact, finding B5);
- deflated and probabilistic Sharpe ratios.

## Development comparators (frozen values, clean rerun at the freeze commit)

Net Sharpe, with gross (zero cost) in brackets:

| | RD/Shell train 1987-96 | RD/Shell validation 1997-99 | Reed train 1993-97 | Reed validation 1998-99 |
|---|---|---|---|---|
| parity_zscore | -0.38 (+0.60) | -0.98 (+0.79) | -1.36 (-0.03) | -1.09 (+0.47) |
| silta_parity | -0.08 (+0.40) | +0.14 (+0.19) | +0.02 (+0.20) | +0.05 (+0.22) |

Walk-forward on RD/Shell, 1991-99:

- `parity_zscore`: -0.34;
- `silta_parity`: +0.02 (-0.7%).

## Deflation inputs (n_trials, var_sr_per_period, sr0_per_period)

**`n_trials` = 600.** These are distinct strategy configurations evaluated on
RD/Shell, counted in both MLflow stores:

- the scratch store of steps 4c-9;
- the clean freeze rerun.

Parity is ignored for `parity_zscore`, because a constant parity drops out of
the z-score. Cost, capital and withholding variants count as trials (auditor
A5: conservative).

**`var_sr_per_period`.** The variance of the walk-forward grid's training
Sharpe ratios in the clean rerun, in daily units:

- `parity_zscore`: 0.000288;
- `silta_parity`: 0.000097.

These come from nested windows, so they understate the dispersion (auditor A5).

**`sr0_per_period`** is the expected maximum daily Sharpe of 600 null trials:

| | sr0 per day | annualized |
|---|---|---|
| `parity_zscore` | 0.0527 | 0.84 |
| `silta_parity` | 0.0306 | 0.49 |

**Power, stated in advance.**

- About 690 OOS days on RD/Shell and Reed: standard error of an annualized
  Sharpe about 0.60. DSR > 0.95 needs an annualized net Sharpe of about 1.8
  (`parity_zscore`) or 1.5 (`silta_parity`).
- About 1,640 days on Rio Tinto: standard error about 0.39; DSR > 0.95 needs
  about 1.5 and 1.1.
- This evaluation can detect only a large edge. A null result does not show
  that there is no edge; it shows that there is no large one.

## decision_rule

For each (pair, strategy), the verdict is exactly one of:

- **"evidence of edge"**, only if ALL of these hold:
  - DSR > 0.95 at the frozen `n_trials` and `var_sr_per_period`;
  - at least 10 entries;
  - largest trade < 50% of absolute P&L;
  - rejected by Holm's step-down over the 6 primary runs at family level 0.05,
    with p = 1 - PSR(SR > 0).
- **"not evaluable (too few entries)"** when there are fewer than 5 entries.
- **"not evaluable (pre-declared)"** for `silta_parity` on RD/Shell. It is about
  one trade on a premium path shaped by known events, which the researchers
  and the agents know from the literature, so it is reported but never read as
  evidence, whatever its sign.
- **"no evidence of edge"** otherwise.

**Secondary hypothesis (limits to arbitrage).** On RD/Shell and Reed Elsevier,
`parity_zscore` has gross total return >= 0 and net total return < 0. It is
reported as holds or does not hold for each pair.

## predictions

Recorded before the run. Probabilities are subjective.

| Prediction | P |
|---|---|
| No "evidence of edge" verdict in any of the 6 runs | 0.95 |
| `parity_zscore` net Sharpe < 0 on RD/Shell | 0.75 |
| `parity_zscore` net Sharpe < 0 on Reed Elsevier | 0.75 |
| `parity_zscore` net Sharpe < 0 on Rio Tinto | 0.85 |
| Limits-to-arbitrage pattern holds on RD/Shell | 0.6 |
| Limits-to-arbitrage pattern holds on Reed Elsevier | 0.6 |

The Rio Tinto prediction is more confident because non-synchronous closes add
reverting noise, which the strategy pays costs to trade.

Expected trade counts:

- `silta_parity` RD/Shell: 1-3 entries;
- `silta_parity` Reed Elsevier: few trades, |Sharpe| < 0.5 (it starts near the
  bound: D was about +230 bps at the end of 1999).

**What would surprise us:**

- a net `parity_zscore` Sharpe above about 0.8 on RD/Shell or Reed Elsevier;
- any Rio Tinto Sharpe above about 0.5 with 10 or more entries.

**Alternative explanations to rule out before reading a positive result as
skill:**

- lower 2000-02 spreads and impact (a cost regime, not a signal);
- 2000-02 volatility;
- a single convergence or index event: the S&P removal in July 2002, or
  free-float reweightings;
- a dividend below the 50 bps `min_yield` going unbooked.

## rio_tinto_execution

- **Prices and timing.**
  - Same-date closes from the panel, on dates both legs traded.
  - D and the z-score are computed on them as they are: no re-alignment, no
    ADR or futures proxy.
  - The decision is taken after the later (London) close of day t.
  - Each leg fills at its own close on the next joint trading date: Sydney
    close t+1 (about 06:00 London), London close t+1. This is causal.
  - Marks are non-synchronous: about 10 hours apart, AUD converted at
    Datastream's fixing. This adds negative autocorrelation and noise. It is
    known and accepted, and not corrected after the fact.
- **Warm-up.**
  - The OOS period starts on the first data row.
  - No position before both legs' sigma, ADV and price exist (rule 5b, at
    least 61 rows), and before z exists (60 rows) for `parity_zscore`.
- **Parity 1.0** (equal dividend and voting rights per share in the DLC).
- **Withholding 0% on Ltd** (fully franked dividends). Unfranked parts, and
  the franking credits a short seller of Ltd may owe, are not modelled. These
  are known upward biases.
- **Costs.** The `liquidity` defaults. The Ltd leg pays the 3 bps FX
  conversion. Quotes are costed as quoted.
- **Overlap with development.** 1996-99 is the same calendar period as the
  development data, though never used for Rio. Only 2000-02 is new in time;
  the sub-period split shows both parts.

## Data policy

- OOS quotes are costed as quoted, whatever the B6 or wide-quote flags say.
- The parity constants are not changed.
- `min_yield` stays at 50 bps.
- The data pipeline is not changed after the freeze.

## if a run errors

1. Record the failure: command, commit, traceback.
2. Fix only a bug that a test reproduces on non-OOS data, in a new commit with
   new tags (`freeze-*-r1`).
3. Repeat ALL runs.
4. Report both attempts.
5. Never repeat a run because its result is bad.

## OOS data touches before this note (disclosure)

- **Step 6:** the RD/Shell parity check compared the workbook constant with
  2000-02 share counts. These were share counts, not prices or returns. This
  is the reason the constant was replaced (audit A1).
- **The rd_shell and reed_elsevier panels contain 2000-02 rows.** No backtest,
  regression or price statistic used them:
  - the code truncates at the period end;
  - the MLflow stores contain no run with `period=oos` or `unlock_oos=true`.
- **The red-team review** computed D only up to 1999-12-31. It cited, from
  memory, published accounts of the RD premium in 2000-02. That knowledge is
  why `silta_parity` on RD/Shell is pre-declared not evaluable.

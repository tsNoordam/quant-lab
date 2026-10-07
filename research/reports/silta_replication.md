# SILTA price-volume regressions on our twin data (Step 7)

Date: 2026-10-07. Code: `quant_lab.models.silta`, config `conf/silta/default.yaml`.
MLflow experiments `rd_shell.silta` and `reed_elsevier.silta` (tag
`kind=silta_regressions`). Reproduce with:

    uv run python -m quant_lab.models.silta data=rd_shell
    uv run python -m quant_lab.models.silta data=reed_elsevier

Only aggregate statistics are reported here (Datastream data is licensed).

## What this is, and what it is not

The paper's Table VI uses the twins from 2002-04-25 to 2007-04-24 (footnote 11).
Our data ends 2002-10-03 and everything from 2000 on is locked OOS. So this is
**not a replication of the Table VI numbers**. It is an **out-of-period test of
H1** on earlier, disjoint data. The windows are the locked development ranges,
chosen in `research/reports/data_decisions.md` and in the Step 6 methodology
note before any regression was run:

- RD/Shell 1987-1999;
- Reed Elsevier 1993-1999.

The OOS period was never loaded. A test (`tests/integration/test_silta_run.py`)
checks that data after `validation.end` cannot change any result.

H1 [PAPER-DERIVED]: the slope b of Z[ln(P1/P2)] on Z[ln(V1/V2)] is negative,
provided the leg that is expensive relative to parity also has more "standard"
volume (chi > 0). Here Z = demean, descale and remove a linear trend (spec
`std_detrended`). The headline window is `development`.

## Method checks (synthetic and unit tests)

- **Newey-West implementation.** With a fixed lag and no prewhitening it matches
  statsmodels HAC (with small-sample correction) to rtol 1e-10. The automatic
  lag follows R `sandwich::NeweyWest` (Bartlett kernel, Newey-West 1994
  bandwidth, AR(1) prewhitening).
- **Positive control.** A planted slope of -0.3 is recovered.
- **Negative control.** On the synthetic pair, volume is independent of prices
  by construction. There every slope is insignificant: |t| < 1 for every
  spec in every window.
- **Causality.** The full-sample Z[.] changes past values when the future
  changes (tested, labelled explanatory only). The causal spec uses trailing
  250-day z-scores and does not.

## Results: H1 slope, `std_detrended`, auto NW lag

| Pair | Window | n | b | t (NW) | Paper, Table VI (2002-07) |
|---|---|---|---|---|---|
| RD/Shell | development 1987-99 | 3204 | **+0.016** | **0.44** | -0.25 (t -3.4) |
| RD/Shell | train 1987-96 | 2457 | +0.026 | 0.61 | |
| RD/Shell | validation 1997-99 | 747 | +0.049 | 0.96 | |
| Reed Elsevier | development 1993-99 | 1745 | **+0.075** | **1.92** | -0.09 (t -2.2) |
| Reed Elsevier | train 1993-97 | 1247 | -0.091 | -2.24 | |
| Reed Elsevier | validation 1998-99 | 498 | -0.063 | -0.78 | |

**Lag sensitivity** (t of the development slope, fixed lag, no prewhitening):

| Lag | 0 | 5 | 10 | 20 | 40 | 80 |
|---|---|---|---|---|---|---|
| RD/Shell | 0.91 | 0.63 | 0.55 | 0.48 | 0.42 | 0.38 |
| Reed Elsevier | 3.25 | 2.41 | 2.12 | 1.84 | 1.53 | 1.29 |

**Other specifications** (development window; slope and t):

| Spec | RD/Shell | Reed Elsevier |
|---|---|---|
| `raw_shares` (y on x) | +0.016 (3.81) | +0.005 (0.91) |
| `std` (demeaned and descaled, not detrended) | +0.161 (3.77) | +0.035 (0.91) |
| `causal` (trailing z-scores) | -0.035 (-0.80) | -0.088 (-1.28) |

`raw_notional` regresses y on y + x. Its positive slope is mechanical, so it is
not evidence for or against H1.

## The chi > 0 precondition

Leg a (Royal Dutch, Elsevier) is above parity on average in every window:

- RD/Shell: +7.1% on average, above parity on 84% of days;
- Reed Elsevier: +6.0% on average, above parity on 77% of days.

| Pair (development) | chi in shares | chi in value traded |
|---|---|---|
| RD/Shell | -1.41 (fails) | +0.59 (holds) |
| Reed Elsevier | +0.25 (holds) | +0.75 (holds) |

Both are the mean log ratio, expensive leg over cheap leg.

The paper proxies chi by the shares volume ratio. That is exact for HSBC (1:1
shares) but not for RD/Shell, where one Royal Dutch share is worth about 6.9
Shell shares. In value terms the expensive leg trades more in both pairs, so
the precondition holds. The absent slope is therefore not explained by chi < 0.
This is A6 in `research/assumptions/maymin_silta.md`.

**Table VII statistics.** The paper fits a lognormal to the log volume ratio on
days inside the 180 bps cost bound.

- RD/Shell: inside the bound on 13% of development days (none in validation);
  mu = -1.44, sigma = 0.62 in shares.
- Reed Elsevier: inside the bound on only about 1% of days (fewer than 20
  days); mu = 0.31, sigma = 0.46.

So for this period the bound-based calibration of H2 has almost no data. That is
one more reason H2 stays deferred.

## Conclusion

**H1 is not supported on our 1987-1999 data.**

- **RD/Shell.** No relation at all: b = +0.016 against the paper's -0.25. The
  sign is wrong in every window, and |t| < 1 at every lag.
- **Reed Elsevier.** The sign is unstable across windows:
  - train: -0.09, t -2.2, numerically close to the paper's figure;
  - validation: -0.06, insignificant;
  - full development range: +0.075.

  A slope that flips sign when two sub-periods are pooled says the detrended
  relation is not stable. The train-window match with Table VI is a
  coincidence of one sub-period. It is not a replication, and it was not the
  pre-declared headline.
- **Causal spec.** It is negative for both pairs but insignificant. It is a
  trailing-z relation, not the paper's specification.

Under the golden rule, this is a research result, not a reason to change the
specification.

## Caveats (why this does not refute the paper)

1. **Different period, different volume data.** The author restricted the twins
   to 2002+ because earlier Datastream and Bloomberg volumes disagreed. Our data
   is exactly that earlier Datastream volume. We cannot cross-check it.
2. **Pre-unification regime.** RD/Shell's equalization structure and market
   (fewer hedge funds, the 1990s) differ from 2002-07. SILTA's arbitrageurs may
   not have been the marginal traders then.
3. **Persistence.** Both series are highly persistent. Our NW lags of 16-27
   are automatic, and the lag table shows how t moves with the lag. A linear
   detrend does not remove stochastic trends. A block bootstrap and a
   differenced specification were not run (noted for step 9).
4. **One specification choice.** The linear trend form is our reading
   (assumption A1); the paper does not state it.

## Consequences for the roadmap

- Step 8 must not treat the price-volume relation as an established fact on our
  data. Any SILTA-derived rule enters as [PAPER-DERIVED], with this null result
  recorded as the prior. It is evaluated against the parity z-score baseline
  in walk-forward, not tuned until it "works".
- H2 calibration (eq. 1, Tables VII-VIII) stays deferred: the cost-bound sample
  is too small in our period.

## Erratum 2026-10-07 (freeze audit A1)

The RD/Shell parity used above (6.863, the workbook constant) carried
post-1999 share-count information; it is now 6.9558 (pre-2000 share counts,
`research/reports/data_decisions.md`). Recomputed on the development window:
the regressions are unchanged (they do not use parity; `std_detrended`
b = +0.016, t 0.44); the chi check is unchanged in every conclusion. Leg a's
mean deviation from parity becomes +5.7% (was +7.1%), above parity on 79% of
days (was 84%); chi in shares -1.41, in value +0.59; inside the cost bound on
13% of days. The numbers above are left as originally reported.

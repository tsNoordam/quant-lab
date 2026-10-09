# de Jong et al. (2009), Table VI replication: abnormal returns and risk (step 17)

Date: 2026-10-09.

- **Code:** `quant_lab.models.dejong_risk` (MLflow experiment
  `dejong.replication`, run `table6`). Settings are in the `table6` section of
  `conf/dejong/default.yaml`. The engine is step 16's
  (`quant_lab.backtest.dejong`).
- **Data:**
  - the daily position returns of the step-16 engine;
  - the S&P 500 from the RD/Shell workbook's regression sheet;
  - SMB and HML from Kenneth French's daily file (`data/raw/french_ff/`, DVC);
  - FRED DTB3 as the risk-free rate.

Reproduce:

    uv run python -m quant_lab.models.dejong_risk

> **Status: alphas and idiosyncratic volatilities are provisional.** French's
> site is not reachable from the cloud session. The figures below were
> computed with a stand-in factor file: US business days, SMB and HML as tiny
> noise. That makes them effectively one-factor (S&P 500) alphas.
>
> Already final, because they do not depend on SMB and HML:
>
> - position counts and position-days;
> - sigma and the S&P 500's sigma;
> - skewness, kurtosis and VaR.
>
> The alphas are replaced by the user's run on the real factors before this
> step closes.

## 1. How the paper pools the positions (identified)

**Stacked position-days (D11).**

- The "# Days" column equals the number of position-days, with the padding
  days of positions shorter than a month included.
- Example: 6,798 = 309 × 22 for 5%/1%/1 month.
- So the regression has one row per position and day. It is not a daily
  portfolio average.

**Every position-day is kept (D22).**

- On US holidays SMB and HML are set to 0; the Datastream S&P 500 return is 0
  on those days anyway.
- Dropping the US holidays instead would leave 10,065 rows for the benchmark,
  against the paper's 10,422; keeping them gives 10,437.

**Sigma is the daily standard deviation × 22 (D23).**

- The paper's S&P 500 sigma is our daily standard deviation times 21.65-21.90
  in every strategy. That is 22, the paper's days per month: its returns are
  "expressed in % per month".
- With the usual √260 our S&P 500 sigma would be 17.3% against the paper's
  22.9%. The text calls the figures "annualized"; they are not.
- The paper's main risk statement survives either way: arbitrage returns are
  about 1.3 times as volatile as the S&P 500 over the same days.

## 2. Table VI, primary configuration, ours / paper

| Strategy | Positions | Position-days | Alpha % p.m. (provisional) | Sig. | σ | σ S&P 500 | Skewness | Kurtosis | 1% VaR |
|---|---|---|---|---|---|---|---|---|---|
| 5%/1%/1 month | 313 / 309 | 6,871 / 6,798 | -0.393 / -0.415 | – / – | 36.3 / 34.6 | 23.8 / 23.6 | 0.69 / 0.46 | 13.4 / 12.4 | -4.5 / -4.6 |
| 5%/1%/3 months | 203 / 205 | 9,136 / 9,148 | 0.228 / 0.159 | – / – | 35.1 / 34.5 | 23.9 / 23.8 | 0.77 / 0.40 | 13.2 / 11.6 | -4.2 / -4.5 |
| 5%/1%/12 months | 151 / 156 | 12,931 / 13,019 | 0.414 / 0.457 | – / b | 31.9 / 33.5 | 22.8 / 22.6 | 0.54 / 0.34 | 17.3 / 11.0 | -3.7 / -4.2 |
| 5%/1%/unlimited | 134 / 138 | 17,409 / 17,505 | 0.294 / 0.310 | – / b | 25.5 / 31.6 | 22.2 / 22.1 | 0.74 / 0.29 | 29.3 / 10.8 | -3.1 / -4.0 |
| 10%/5%/1 month | 290 / 288 | 6,380 / 6,339 | 0.181 / 0.011 | – / – | 32.7 / 31.0 | 24.3 / 24.0 | -0.24 / 0.23 | 25.6 / 8.9 | -3.6 / -3.8 |
| 10%/5%/3 months | 185 / 184 | 8,480 / 8,462 | 0.726 / 0.610 | b / a | 31.4 / 30.7 | 23.5 / 23.2 | 0.06 / 0.23 | 13.7 / 8.3 | -3.6 / -3.8 |
| 10%/5%/12 months | 128 / 127 | 10,437 / 10,422 | 0.823 / 0.718 | a / a | 29.7 / 30.7 | 23.2 / 22.9 | 0.12 / 0.35 | 21.9 / 9.6 | -3.4 / -3.7 |
| 10%/5%/unlimited | 113 / 112 | 11,199 / 11,210 | 0.739 / 0.745 | a / a | 26.5 / 30.9 | 22.6 / 22.2 | 0.24 / 0.41 | 30.8 / 10.2 | -3.2 / -3.8 |

σ: daily sd × 22 (D23). Significance: OLS (D24). Clustering by date gives the
same marks here.

**Results:**

- **Position-days are within 1.1% of the paper's in every strategy.**
- **The S&P 500's sigma is within 1.6%** (0.3-1.6% high).
- **The ranking of the alphas is the paper's:**
  - the 10%/5% strategies from 3 months on earn 0.7-0.8% per month,
    significant;
  - 5%/1%/1 month is negative;
  - 5%/1%/12 months and unlimited earn 0.29-0.41% (paper 0.31-0.46%).
- **Kurtosis is too high for the long horizons.** This is the Dexia spike; see
  §3.

## 3. The Dexia spike, again

On 1997-12-19 the Dexia position open since July 1997 loses 24% of equity in
one day (a margin call under the per-leg rule locks the loss in).

| 10%/5%/12 months | Kurtosis | Skewness | Alpha (provisional) |
|---|---|---|---|
| As delivered | 21.9 | 0.12 | 0.823 |
| Spike removed (variant `dexia_spike_removed`) | 12.9 | 0.69 | 0.866 |
| Paper | 9.6 | 0.35 | 0.718 |

Without that one day, kurtosis falls from 21.9 to 12.9 (paper 9.6). The
10%/5% 1-month and 3-month strategies come within a point of the paper's
kurtosis (9.3 vs 8.9, 8.9 vs 8.3).

Together with Table III, where the two spike observations are the only thing
separating us from the paper, this is strong evidence that the authors cleaned
the spike. The next largest daily moves are Unilever's in 1980-87, when the NV
price is stale on most days (`data/metadata/datastream_dlc.json`).

## 4. The p. 515 sensitivities (benchmark FF3 alpha, % per month)

| Case | Ours (provisional) | Paper | Ours − our benchmark | Paper − paper benchmark |
|---|---|---|---|---|
| Benchmark | 0.823 | 0.718 | | |
| Commission 50 bps | 0.555 | 0.453 | -0.268 | -0.265 |
| Spread 80 bps | 0.619 | 0.506 | -0.204 | -0.212 |
| Short rebate 1% | 0.684 | 0.562 | -0.139 | -0.156 |
| One extra day of delay | 0.186 | 0.382 | -0.637 | -0.336 |

**The cost and rebate effects are reproduced to within 0.02% per month.**

**The delay effect is not:** our engine loses three quarters of the alpha, the
paper about half. One day of delay changes which closes are traded, so
everything that differs between our positions and the paper's is amplified.

## 5. IAPM: not replicated

The IAPM alphas need Datastream's World Market Index (p. 501). It is not in
the archives and not public. The paper's IAPM alphas lie within 0.05 of its
FF3 alphas in every strategy, so FF3 carries the result. This stays open
(D25).

## 6. Pinned by tests

- `tests/unit/test_dejong_risk.py`: the factor loader, pooling (holidays
  kept), units (alpha × 22, sigma × 22, raw kurtosis) and evidence parsing.
- `tests/integration/test_dejong_engine_real.py`:
  - position-days within 1.5% of the paper for all strategies;
  - with the factor file present, the S&P 500 sigma within 2.5%.

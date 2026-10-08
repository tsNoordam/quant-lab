# de Jong et al. (2009), Table III replication: comovement with local markets (step 15)

Date: 2026-10-08.

- **Code:**
  - `quant_lab.data.dlc` writes the regression inputs per twin,
    `data/interim/dlc/<twin>.regression.parquet` (DVC stage `dlc_ingest`).
  - `quant_lab.models.dejong` runs the regressions (MLflow experiment
    `dejong.replication`, run `table3`).
- **Data:** each workbook's own regression sheet ("Regression data"; for
  Smithkline "Regression data DS dates"), over the Table II windows that the
  user approved for this replication (`research/reports/data_decisions.md`).
- **Aggregates only** (licensed data).
- **Descriptive, not a trading rule.** The regression uses the next day's index
  and exchange-rate returns, so it cannot be traded.

Reproduce:

    uv run dvc repro dlc_ingest
    uv run python -m quant_lab.models.dejong --table 3

## 1. The regression (E2, `research/equations/dejong_dlc.md`)

    r_A,t - r_B,t = a + b (r_A,t-1 - r_B,t-1)
                    + g1_0 Index1_t + g1_1 Index1_t+1
                    + g2_-1 Index2_t-1 + g2_0 Index2_t
                    + d_-1 e.r._t-1 + d_0 e.r._t + d_1 e.r._t+1 + e_t

- r are daily local-currency total-return log returns.
- For the three twins whose markets share a time zone (ABB, Dexia, Fortis) only
  Index1_t and Index2_t enter [PAPER-DERIVED].
- Table III reports, per twin:
  - R², Durbin-Watson and degrees of freedom;
  - the sum of each regressor group's coefficients, with a Wald test that the
    sum is zero, using Newey-West standard errors.

**The inputs are checked.** In every workbook, the regression sheet's two return
columns equal the total-return log differences of our step-14 panel on every
panel date: 48,978 returns checked, largest error 2.2e-15. Table III and
Table II therefore rest on the same data.

**Paper's indices (p. 501) [PAPER-DERIVED]:**

| Country | Index |
|---|---|
| Australia | ASX All Ordinaries |
| Belgium | Brussels Allshare |
| France | SBF 250 |
| Finland | HEX |
| Netherlands | CBS Allshare |
| Sweden | Stockholmsbörsen Allshare |
| Switzerland | Swiss Performance Index |
| United Kingdom | FTSE Allshare |
| United States | S&P 500 |

Each workbook has these columns, plus some alternatives (FTSE 100, SMI, CAC 40,
BEL 20, CBS ex. Royal Dutch).

## 2. Conventions the paper's numbers identify

The paper leaves some details open. Each convention below was identified by the
paper's own numbers, not by a better fit. The data is never altered; only the
workbook column or the sample is chosen.

| # | Question | Answer | Evidence |
|---|---|---|---|
| D13 | Direction of e.r. | B's currency per unit of A's: the negative of the workbook column (which is A per B, equal to Δln of our panel's FX to 1e-16) | Every exchange-rate sum then matches in magnitude *and* sign; with the workbook's direction all 12 have the opposite sign |
| D17 | Which R² and which sample | Unadjusted R² (the caption says "adjusted"); every window row with complete data, with leads and lags read from the workbook rows just outside the window | Unadjusted R² matches for 11 of 12 twins, adjusted R² for 1 (e.g. BHP 0.397 unadjusted, 0.382 adjusted, paper 0.397); df matches for 10 of 12 (Fortis 2506, not 2505 as it would be if leads stopped at the window end) |
| D18 | Newey-West variant | Bartlett kernel, fixed lag floor(4 (n/100)^(2/9)), no prewhitening, n/(n-k) correction (the EViews default) [IMPLEMENTATION-ASSUMPTION, chosen before comparing] | All 48 significance marks equal the paper's. The lab's R-sandwich default (automatic lag, prewhitened) gets 47 of 48: Zürich index 2 has p = 0.008 (a) vs the paper's b, against EViews-style p = 0.014 (b) |

Three twins need a twin-specific choice. For each, the paper's text taken
literally (variant `as_stated`, also computed and logged) does not reproduce
the table, and the identified choice reproduces every value:

| # | Twin | As stated | Identified | Effect |
|---|---|---|---|---|
| D14 | Royal Dutch/Shell | CBS Allshare | **CBS Allshare ex. Royal Dutch** (a workbook column; Royal Dutch was a large part of the Dutch index) | R² 0.317 → 0.242, index 1 sum 0.457 → 0.346: all 7 values match |
| D15 | Dexia | all rows | **without the return observations of 1997-12-19 and 1997-12-22**, the spike and its reversal from Table II's report | df 710 → 708, R² 0.194 → 0.100: all 7 values match |
| D16 | Smithkline Beecham | the Bloomberg FTSE (FTSE 100, p. 501) | **the Datastream FTSE Allshare on Datastream dates** ("Regression data DS dates") | index 1 sum 0.065 → 0.086: 6 of 7 values match |

## 3. Table III, ours vs the paper

Each cell is ours / the paper's; bold marks a difference beyond rounding.
Significance marks (a 1%, b 5%, c 10%) are identical in all 48 cells.

| Twin | R² | DW | df | Lagged dep. | Index country 1 | Index country 2 | Exchange rate |
|---|---|---|---|---|---|---|---|
| Royal Dutch/Shell | 0.242 / 0.242 | 2.03 / 2.03 | 5927 / 5927 | -0.231ᵃ / -0.231ᵃ | 0.346ᵃ / 0.346ᵃ | -0.501ᵃ / -0.501ᵃ | -0.806ᵃ / -0.806ᵃ |
| Unilever | 0.146 / 0.146 | 2.06 / 2.06 | 5927 / 5927 | -0.216ᵃ / -0.216ᵃ | 0.170ᵃ / 0.170ᵃ | -0.560ᵃ / -0.560ᵃ | -0.595ᵃ / -0.595ᵃ |
| ABB | **0.156 / 0.155** | 2.04 / 2.03 | **1951 / 1952** | -0.119ᵃ / -0.119ᵃ | **0.436ᵃ / 0.433ᵃ** | -0.400ᵃ / -0.399ᵃ | **-0.506ᵃ / -0.509ᵃ** |
| Smithkline Beecham | 0.132 / 0.132 | **2.12 / 2.14** | 1527 / 1527 | -0.299ᵃ / -0.299ᵃ | 0.086ᶜ / 0.086ᶜ | -0.248ᵃ / -0.248ᵃ | 0.031 / 0.031 |
| Fortis | 0.104 / 0.104 | 1.99 / 1.99 | 2506 / 2506 | -0.163ᵃ / -0.163ᵃ | 0.476ᵃ / 0.476ᵃ | -0.537ᵃ / -0.537ᵃ | -0.580ᵇ / -0.580ᵇ |
| Elsevier/Reed | 0.197 / 0.197 | 2.14 / 2.14 | 2534 / 2534 | -0.319ᵃ / -0.319ᵃ | 0.331ᵃ / 0.331ᵃ | -0.417ᵃ / -0.417ᵃ | -0.772ᵃ / -0.772ᵃ |
| Rio Tinto | 0.272 / 0.272 | 2.15 / 2.15 | 1760 / 1760 | -0.296ᵃ / -0.296ᵃ | 0.431ᵃ / 0.431ᵃ | -0.741ᵃ / -0.741ᵃ | -0.524ᵃ / -0.524ᵃ |
| Dexia | 0.100 / 0.100 | 2.19 / 2.18 | 708 / 708 | -0.216ᵃ / -0.216ᵃ | 0.290ᵃ / 0.290ᵃ | -0.324ᵃ / -0.324ᵃ | -0.319 / -0.319 |
| Merita/Nordbanken | 0.246 / 0.246 | 2.09 / 2.09 | 431 / 431 | **-0.317ᵃ / -0.371ᵃ** | 0.463ᵃ / 0.463ᵃ | -0.445ᵃ / -0.445ᵃ | -0.139 / -0.139 |
| Zürich Allied/Allied Zürich | 0.091 / 0.091 | 2.03 / 2.03 | 390 / 390 | -0.153ᵃ / -0.153ᵃ | 0.155 / 0.155 | -0.354ᵇ / -0.354ᵇ | -0.928ᵃ / -0.928ᵃ |
| BHP Billiton | 0.397 / 0.397 | 2.21 / 2.21 | 319 / 319 | -0.280ᵃ / -0.280ᵃ | 0.459ᵇ / 0.459ᵇ | -0.709ᵃ / -0.709ᵃ | -0.647ᵇ / -0.647ᵇ |
| Brambles Industries | 0.288 / 0.288 | 2.00 / 2.00 | **292 / 293** | -0.005 / -0.005 | 0.343 / 0.343 | -0.866ᵃ / -0.866ᵃ | -0.567 / -0.567 |

**Result: 77 of 84 statistics agree within rounding, and all 48 significance
marks agree.** Eight twins match on every value; Merita, Brambles and
Smithkline differ in one value each; ABB differs in four (small).

The paper's claims hold in our replication:

- **Signs:** every index-1 sum is positive and every index-2 sum is negative,
  for all 12 twins (the comovement prediction).
- **Significance:** 22 of the 24 index sums are significant; the two that are
  not are Zürich index 1 and Brambles index 1.
- **R²:** the paper says 10% to 40%. Our R² runs from 0.091 (Zürich) to 0.397
  (BHP), so Zürich is just below 10%, as in the paper's own table.

## 4. The differences

1. **Merita/Nordbanken lagged dependent: -0.317 vs -0.371.**
   - Every other Merita value matches, and the lagged dependent variable
     enters every other statistic.
   - Reading: transposed digits in the paper. [our reading]
2. **Brambles df: 292 vs 293.**
   - R², DW and all four sums match to the printed decimals.
   - 303 window rows, minus the first (no lag) and the last (no lead), leave
     301 observations and 9 coefficients: df = 292.
   - Reading: a slip in the df column. [our reading]
3. **Smithkline Durbin-Watson: 2.12 vs 2.14.**
   - Everything else matches, including df.
   - The sample has 158 gaps (the Datastream-dates sheet has no returns on the
     Bloomberg holidays). Neither DW convention for gaps (2.117 contiguous,
     2.064 consecutive pairs only) gives 2.14.
   - Unexplained; small.
4. **ABB: one observation fewer (df 1951 vs 1952).**
   - Index 1 sum 0.436 vs 0.433, exchange rate -0.506 vs -0.509, R² 0.156 vs
     0.155. All marks match.
   - Our sample is every complete window row. The first row has no lagged
     return in the workbook, so the paper's 1959 observations are not
     reachable from this sheet. Extending the window by one day gives df 1952
     but sums 0.434 and -0.500, which is no closer.
   - Together with Table II's ABB standard deviation (10.02 vs 10.17), the
     paper probably had a slightly different ABB series.

## 5. What this adds to step 14

- **Fortis:** Table III matches exactly, although every Table II statistic
  differs. The returns are therefore the authors' returns. The Table II
  difference lies in the level of the deviation (the parity ratio or prices
  around the 1998 equalization), not in the daily data.
- **Dexia:** the authors had the 1997-12-19 spike in their regression data and
  left those two observations out of Table III. Table II still differs without
  the spike (step 14), so its level difference has another source.
- **Royal Dutch/Shell and Smithkline:** the authors' data choices are finer
  than the text says. Step 16 should not assume the text is complete.

## 6. Consequences for the next steps

- **The comovement result is reproduced.** For every DLC, relative twin
  returns move with the local markets, in the predicted direction, with index
  sums between 0.09 and 0.87 in absolute value. This is the noise-trader risk an
  arbitrageur bears, not a signal: the next day's index return enters the
  regression.
- **Step 16 (Tables IV-V):**
  - The Dexia spike treatment is still open for the strategy tables. Table III
    shows the authors excluded it from the regression; that is evidence, not
    proof, of what they did in the simulations. Report both.
  - Fortis can be compared on returns; its deviation levels differ (step 14).
- Pinned by `tests/integration/test_dejong_real.py`: the 7 differences above,
  48/48 marks, the as-stated variant departing only for RD/Shell, Dexia and
  Smithkline, and the Merita transposition.

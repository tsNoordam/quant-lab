# Extraction: de Jong, Rosenthal & van Dijk (2009), "The Risk and Return of Arbitrage in Dual-Listed Companies"

## Source and conventions

**Source.** *Review of Finance* 13: 495-520, doi:10.1093/rof/rfn031. Read in
full (26 pp.) from the PDF uploaded on 2026-10-07. It is to be added to
`papers/raw/` under DVC by the user (immutable raw sources).

**Page numbers** are the journal's (495-520).

**Tags:**

- [PAPER-DERIVED] stated in the paper;
- [MATHEMATICALLY-DERIVED] follows from it;
- [IMPLEMENTATION-ASSUMPTION] our reading where the paper is silent.

**Companion files:**

- equations: `research/equations/dejong_dlc.md`;
- method and review: `research/methodology/dejong_dlc.md`;
- assumptions and ambiguities: `research/assumptions/dejong_dlc.md`;
- numbers: `research/evidence/dejong_dlc_evidence.csv`.

**Relation to this lab.**

- The authors built the Datastream workbooks this lab already uses (van Dijk's
  site; `data/metadata/datastream_dlc.json`).
- Unlike Maymin (SILTA), this paper does specify trading rules, with
  per-twin results.

## Research question

Why does mispricing between twin shares persist? The paper asks this for
large, liquid dual-listed companies (DLCs), where fundamental risk, transaction
costs and short-sale constraints should not bind.

It answers by measuring the risk and return of simple arbitrage strategies,
after realistic transaction costs and margin requirements.
[PAPER-DERIVED, pp. 495-497]

## Hypotheses and claims

| # | Claim | Pages |
|---|---|---|
| C1 | Every DLC shows large, time-varying deviations from theoretical parity (mean absolute 4-12%; every twin exceeds 15% at some point, up to 40%). | 496, 500-502 |
| C2 | Relative twin returns co-move with the local market indices and exchange rates (Froot-Dabora comovement). | 502-504 |
| C3 | Simple threshold strategies (open at a buy threshold, close at a sell threshold, optional maximum horizon) earn abnormal returns of up to about 10% p.a. after costs and margin requirements. | 495, 497, 505-510 |
| C4 | DLC arbitrage risk is mostly idiosyncratic, about 30-35% annual volatility, with fat tails and a daily 1% VaR of about -4%. Uncertainty about when prices converge deters arbitrage (limits to arbitrage: Shleifer-Vishny, Pontiff). | 497, 509-511 |
| C5 | Time zones and currencies do not explain the mispricing: ADR-based deviations give similar arbitrage results. | 497, 512 |
| C6 | Taxation, governance and short-sale constraints explain at most a minor part. | 512-514 |
| C7 | Once horizon uncertainty disappears (unification announced), prices converge to parity within one or two days. | 497, 514-518 |

## Data

All [PAPER-DERIVED], pp. 498-500.

**Sample.** All 12 DLCs that existed for at least 12 months during 1980-2002
(Table I):

- Royal Dutch/Shell;
- Unilever;
- ABB;
- Smithkline Beecham;
- Fortis;
- Elsevier/Reed International;
- Rio Tinto;
- Dexia;
- Merita/Nordbanken;
- Zürich Allied/Allied Zürich;
- BHP Billiton;
- Brambles Industries.

Six of them unified during the sample.

**Sample windows:**

- RD/Shell and Unilever: 1980-01-01 to 2002-10-03;
- other twins: from the merger date to either 20 trading days before the
  unification announcement, or 2002-10-03.

**Datastream:** daily prices, total returns in local currency, bid and ask,
volume, shares outstanding and exchange rates. Bid, ask and volume are mostly
missing in the early years.

**Bloomberg exceptions:**

- ABB AB: bid-ask and volume;
- Smithkline Beecham: E and H shares.

**Theoretical price ratio:**

- from annual reports and merger or unification prospectuses;
- 1:1 for 6 of the 12 twins;
- for the other six, Rosenthal & Young's (1990) procedure using shares
  outstanding, "fixed at a specified ratio".

**Indices and factors:**

- local indices: ASX All Ordinaries, Brussels Allshare, SBF 250, Helsinki HEX,
  CBS Allshare, Stockholm Allshare, Swiss Performance Index, FTSE Allshare,
  S&P 500;
- Datastream World index as the global market;
- 3-month T-bill from FRED;
- Fama-French SMB and HML from Ken French's website.

**Availability in this lab** [IMPLEMENTATION-ASSUMPTION]:

- The workbooks' `Ratio` sheet carries the authors' theoretical ratio and
  "LOG DEVIATIONS FROM PARITY". Our ingest already reproduces that column to
  machine precision for RD/Shell, Reed/Elsevier and Rio Tinto
  (`tests/integration/test_datastream_real.py`).
- The `Regression data` sheet holds the Table III inputs: total returns, FX,
  S&P 500, FTSE 100 and the CBS index for RD/Shell.
- The Fama-French factors and the T-bill rate are not in the workbooks.
- The other 9 DLCs have been obtained by the user; they are not yet ingested.

## Variables

| Variable | Definition | Tag |
|---|---|---|
| Log deviation from parity | ln(P_A / P_B) - ln(theoretical ratio), common currency; A is the twin in the earlier time zone | [PAPER-DERIVED] (Table I note, Figure 1, Table II); price type: see assumptions D1 |
| r_A,t, r_B,t | daily log returns of each twin in local currency | [PAPER-DERIVED] (Table III) |
| Index1, Index2, e.r. | log returns of the two domestic indices and the exchange rate | [PAPER-DERIVED] (Table III) |
| Buy threshold, sell threshold, maximum horizon | strategy parameters (Section 3.3) | [PAPER-DERIVED] |
| Arbitrage return | return on the arbitrageur's equity (margin account), daily marked to market, reported in % per month | [PAPER-DERIVED] (pp. 503-506) |

## Methods (summary; details in the methodology file)

1. **Descriptive statistics** of the deviations (Table II): mean, mean absolute,
   standard deviation, min, max, % of days positive; correlations across twins.
2. **Comovement regressions** (Table III): OLS of the relative return on its lag,
   leads and lags of the two local indices, and the FX return; Newey-West
   standard errors.
3. **Threshold arbitrage strategies** (Tables IV-V):
   - equal-dollar long the cheap twin, short the expensive one;
   - US Regulation T margins and maintenance margin calls;
   - commission plus half spread;
   - at most one position per twin;
   - signals from the previous day's prices.
4. **Risk-adjusted performance** (Table VI): alpha against Fama-French 3-factor
   and an IAPM (global plus two local markets) on pooled daily excess returns;
   volatility, idiosyncratic volatility, skewness, kurtosis and 1% VaR.
5. **Robustness** (Section 5):
   - ADR-based deviations;
   - taxation and governance events;
   - a threshold surface (Figure 2);
   - cost and delay sensitivity;
   - unification event windows (Figure 3).

## Main empirical results

All [PAPER-DERIVED]; full numbers are in the evidence CSV.

- **Deviations** (Table II):
  - mean absolute deviation from 4.11% (Rio Tinto) to 11.93% (Zürich);
  - RD/Shell: mean 0.86%, standard deviation 12.71%, range -36.22% to +19.83%;
  - Elsevier/Reed: mean 2.15%, absolute 8.88%;
  - Rio Tinto: mean 1.90%, absolute 4.11%.
- **Correlations of deviations:**
  - RD/Shell with Unilever: 0.86;
  - RD/Shell with Elsevier/Reed: 0.71;
  - Rio Tinto with BHP Billiton: 0.57.
- **Comovement** (Table III): 22 of 24 index coefficient sums are significant,
  with the predicted signs; R² 10-40%.
- **Benchmark strategy 10%/5%/1 year** (Table IV):
  - 127 positions (the text says 136), average 82 days;
  - weighted-average return 1.18% per month (14.2% p.a.);
  - 18 positions cut off at the horizon, 11 negative, 14 with margin calls.
  - Per twin (weighted % per month):
    - RD/Shell 0.492 (15 positions);
    - Elsevier/Reed 0.694 (13);
    - Rio Tinto 5.054 (13, all one month or less).
- **Eight strategies** (Table V): buy/sell thresholds 5%/1% and 10%/5% × horizon
  1 month, 3 months, 12 months, unlimited.
  - Weighted returns -0.009 to 1.238% per month.
  - Unlimited horizons last up to 2,321 days.
- **Abnormal returns** (Table VI):
  - five of eight Fama-French alphas are significant at 5%;
  - 10%/5%/12 months: 0.718% per month (8.6% p.a.);
  - 10%/5%/unlimited: 0.745% (8.9% p.a.);
  - 1-month horizons give no alpha;
  - volatility 30.7-34.6% p.a. (S&P 500: 22-24%);
  - skewness 0.23-0.46, kurtosis 8.3-12.4, 1% VaR -3.7% to -4.6%.
- **Sensitivity** (Section 5.3; benchmark alpha 0.718% per month):

  | Change | Alpha (% per month) |
  |---|---|
  | Commission 50 bps | 0.453 |
  | Spread 80 bps | 0.506 |
  | Short rebate 1% | 0.562 |
  | One extra day of delay | 0.382 |

  - Thresholds 10/6 and 9/5 do better than the benchmark.
  - 18/10 earns about 15% p.a. on only 24 positions.
- **Unifications** (Section 5.4): deviations collapse within 1-2 days of the
  announcement, e.g. Dexia -9.22% to -0.14%. After announcement the strategies
  open only 1 (10/5) or 4 (5/1) positions.

## Authors' conclusions

Large, well-traded securities stay mispriced for long periods. Simple
arbitrage earns up to about 10% p.a. abnormal, but with large idiosyncratic,
fat-tailed risk and an uncertain horizon, and that deters arbitrage.
[PAPER-DERIVED, pp. 511, 518]

## Limitations (stated or evident)

- **Everything is in-sample.** Thresholds and horizons are chosen and evaluated
  on the same 1980-2002 data, and the threshold surface (Figure 2) is shown in
  full. [MATHEMATICALLY-DERIVED from the design]
- **Several conventions are not fully specified:**
  - price type for the deviation;
  - exit costs;
  - fixed interest rates;
  - re-entry after a horizon cut-off;
  - the 136 vs 127 count.

  See the assumptions file.
- **Open positions at the sample end are discarded** (p. 505), a possible
  upward bias. [PAPER-DERIVED fact; our reading of the bias]
- **The ADR robustness test is unreported** ("available from the authors").
  [PAPER-DERIVED]
- **Unification announcement jumps are excluded** from the strategy samples,
  which end 20 trading days before the announcement. [PAPER-DERIVED, p. 500]

## Trading rules: yes, unlike Maymin

The paper defines explicit trading rules (Section 3.3). This extraction records
them; it designs no strategy. Turning them into code is step 14
(`/build-strategy`), with every deviation from the paper tagged.

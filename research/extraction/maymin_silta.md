# Extraction: Maymin, "Self-Imposed Limits to Arbitrage" (SILTA)

Source: `papers/raw/ssrn_id1807341_code938524.pdf` (50 pp., "In Press with Journal
of Applied Finance", SSRN 1088553; DVC md5 177d90ea). Page numbers below are the
printed page numbers. This file reconstructs what the author did; it designs no
strategy. Every item is tagged:

- [PAPER-DERIVED] stated in the paper
- [MATHEMATICALLY-DERIVED] follows from the paper's equations
- [IMPLEMENTATION-ASSUMPTION] our reading where the paper is silent or ambiguous

Equations: `research/equations/maymin_silta.md`. Method details and our review:
`research/methodology/maymin_silta.md`. Assumptions and ambiguities:
`research/assumptions/maymin_silta.md`. Numbers: `research/evidence/maymin_silta_evidence.csv`.

## Research question

Why did a multi-billion-pound, multi-year price discrepancy persist between two
identical, non-fungible HSBC share classes (1992-1999), when the usual external
limits to arbitrage (transaction costs, short-sale constraints, home bias, capital
withdrawal) did not bind? [PAPER-DERIVED, pp. 1, 4-5, 10-13]

## Hypotheses

- **H1 (relative volume).** Self-imposed limits to arbitrage (caps on total position
  as a multiple of average daily volume, and on daily trading as a share of volume)
  imply a **negative relation between the standardized relative price
  Z[ln(P1/P2)] and the standardized relative shares volume Z[ln(V1/V2)]**, *provided
  the more expensive class also has the higher "standard" volume (chi > 0)*.
  [PAPER-DERIVED, pp. 5, 18-20]
- **H2 (constancy).** The overall position limit N implied by market data is roughly
  constant across pairs, periods and countries (about 100 days of trading volume).
  [PAPER-DERIVED, pp. 5-6, 28-30]
- **Small pairs.** Pairs too small to attract arbitrageurs show no relation.
  [PAPER-DERIVED, pp. 26-27]

## Data

| Pair | Type | Period | Source | Notes |
|---|---|---|---|---|
| HSBC New / Old | twin, same exchange (LSE), GBP | 1992-07-10 .. 1999 (merged July 1999) | not stated explicitly for HSBC; Bloomberg cited for market value | New = 75p par, Old = HK$10 par [PAPER-DERIVED, pp. 2-4, 7] |
| 3Com / Palm | stub | 2000-03-02 .. 2000-07-27 | CRSP | 1 3Com share = 1.5 Palm [PAPER-DERIVED, p. 24] |
| RD-Shell, Unilever, Reed-Elsevier | twins, London / Netherlands | **2002-04-25 .. 2007-04-24** (5 years, daily) | Datastream and Bloomberg | local listings only; prices converted to a common currency at end-of-day mid FX; "volume data prior to this time does not always agree between Datastream and Bloomberg" [PAPER-DERIVED, p. 26 fn 11] |
| Creative/Ubid, HNC/Retek, DaisyTek/PFSWeb, Metamor/Xpedior, Methode/Stratos | small stubs | per Lamont & Thaler (2003) | CRSP | $150-600m market cap [PAPER-DERIVED, p. 26] |

## Variables

- Relative price: y = ln(P1/P2), natural log of the ratio of the two classes' prices. [PAPER-DERIVED, pp. 5, 34]
- Relative (shares) volume: x = ln(V1/V2), natural log of the ratio of daily share volumes. [PAPER-DERIVED, pp. 5, 34]
- Relative notional volume: ln(P1V1/(P2V2)) = y + x. [PAPER-DERIVED, p. 9]
- Turnover = annual shares traded / shares outstanding (only for HSBC description). [PAPER-DERIVED, p. 33]
- Z[.]: standardization that "demeans, descales, and detrends". [PAPER-DERIVED, p. 20]
- Model quantities N, D, p, f(N,t), theta, k, chi, S_i: see equations file.

## Empirical results (main numbers; full list in the evidence CSV)

- HSBC, unstandardized (Table II): alpha = 3.3% [t 12.0], beta = -1.7% [t -7.6],
  rho = -51%, R^2 = 26%. Standardized and detrended: beta = rho = -22% [t -4.2],
  R^2 = 5%. [PAPER-DERIVED, p. 34]
- Table VI (standardized, detrended, Newey-West): RD-Shell 2002-07 -25% (SE 7%,
  t -3.4); Unilever 2002-07 -23% (SE 6%, t -3.8); Reed-Elsevier 2002-07 -9% (SE 4%,
  t -2.2); 3Com/Palm -43% (t -2.9); the five small stubs insignificant
  (t between -1.6 and +1.8). [PAPER-DERIVED, p. 38]
- Implied daily convergence probability at N = 100 (Table VII): HSBC 70 bps,
  3Com/Palm 340 bps, RD-Shell 120 bps, Unilever 60 bps, Reed-Elsevier 0 bps.
  [PAPER-DERIVED, p. 39]
- Implied maximum position N (Table VIII), e.g. p = 0.95%: HSBC 77, RD-Shell 127,
  Unilever 69 days of volume. [PAPER-DERIVED, p. 40]
- Model-implied arbitrage activity in HSBC averages ~20% of daily volume.
  [PAPER-DERIVED, p. 24]
- HSBC round-turn transaction costs 180 bps (Table III); |log price ratio| exceeded
  180 bps more than 70% of the time. [PAPER-DERIVED, pp. 12-13, 35]

## Conclusions (author)

SILTA explains both the persistence of the HSBC discrepancy and the negative
relative-volume/relative-price relation; the relation holds for large pairs and is
absent for small ones; implied position limits are roughly constant at ~100 days of
volume. [PAPER-DERIVED, pp. 30-31]

## Limitations (stated or evident)

- The volume prediction needs chi > 0 (expensive class trades more). [PAPER-DERIVED, p. 20]
- Standard volumes S1, S2 are unobservable; proxied by the volume ratio when the
  price ratio is within transaction-cost bounds, with HSBC's 180 bps bound reused
  for all pairs "for simplicity". [PAPER-DERIVED, pp. 21, 27]
- The model is calibrated by simulation and cubic interpolation (Figures 6, 10);
  the exact simulation code and seeds are not given. [MATHEMATICALLY-DERIVED from the description]
- Correlation, not causation; full-sample standardization is an explanatory
  device, not a tradable signal. [IMPLEMENTATION-ASSUMPTION: our reading]
- The author traded HSBC (LTCM) and Reed-Elsevier himself (pp. 4, 28).
  [PAPER-DERIVED]

## No trading rule

The paper proposes no trading strategy, entry/exit rule or parameters. Any rule
built on it is a [PROPOSED-EXTENSION] (CLAUDE.md research rules). [PAPER-DERIVED by absence]

# Equations: Maymin (SILTA)

Transcribed from the rendered PDF (the text layer drops most symbols). Printed
page numbers. Notation as in the paper.

## Empirical definitions [PAPER-DERIVED]

| # | Equation | Page |
|---|---|---|
| E1 | y_t = ln(P1_t / P2_t)  (relative price; HSBC: P_New / P_Old) | 5, 34 |
| E2 | x_t = ln(V1_t / V2_t)  (relative shares volume) | 5, 34 |
| E3 | ln(P1V1 / (P2V2)) = ln(P1/P2) + ln(V1/V2)  (relative notional volume) | 9 |
| E4 | y_t = alpha + beta x_t + eps_t  (OLS; Newey-West t-statistics) | 34 |
| E5 | Z[ln(P1/P2)] = a + b Z[ln(V1/V2)],  Z[.] demeans, descales and detrends | 20 |

Footnote 3 (p. 9) [MATHEMATICALLY-DERIVED in the paper]: if y = alpha + beta x, then
y = alpha/(1+beta) + beta/(1+beta) * ln(P1/P2 * V1/V2); with 1 + beta = 0.983 the
shares- and notional-volume regressions hardly differ.

With Z applied to both sides, the intercept is 0 and b equals the correlation
rho(Z[y], Z[x]) (Table VI caption, p. 38). [PAPER-DERIVED]

## SILTA model

Arbitrageur's problem, equation (1), p. 16 [PAPER-DERIVED]:

    max_t  sum_{s=1}^{t-1} (s/t) N p (1-p)^{s-1} ( E0(D_t) - f((s/t) N, s) )
           + N (1-p)^t ( E0(D_t) - f(N, t) )                                   (1)

- N: overall position limit in days of average trading volume
- D0: current discrepancy; E0(D_t): expected discrepancy over the next t days absent convergence
- f(N, t): average market impact of trading N days of volume over t days
- p: constant daily probability of convergence; t*: chosen trading horizon

Special cases (pp. 16-17) [PAPER-DERIVED]:
- p = 0, constant E0(D): t* minimizes f(N, t).
- p = 1: max_t (N/t)(D0 - f(N/t, 1)); with f(x, 1) = 1{x > x*} D0, t* = N / x*.

Volume decomposition (pp. 18-19) [PAPER-DERIVED]:

    V_i = S_i + k_i,   k = k1 = k2 = theta * min(S1, S2),   theta = N / t*
    lim_{k->inf} (V1 + k)/(V2 + k) = 1
    S1 = S2 (1 + chi), chi > 0  (expensive class has more standard volume; P1 > P2)
    V1/V2 = (S1 + theta S2)/(S2 + theta S2) = 1 + chi/(1 + theta)
    ln(V1/V2) = ln(1 + chi/(1+theta)) ~= chi/(1+theta)

Calibration link (p. 21) [PAPER-DERIVED]:

    D = Z[ln(P1/P2)] = a + b Z[ln(V1/V2)] = a + b Z[ln(1 + chi/(1+theta))]
      ~= a + b Z[ln(1 + 1/(1+theta))]

- Market impact used in Figures 5-7: f = sqrt(theta) ("square-root"), p. 19.
- Figure 5 / 6 grids (p. 21): p from 0.00005 to 0.00250 step 0.00005 (50 values) and
  0.00500 to 0.25000 step 0.0025 (99 values); D from 0.025 to 5 step 0.025 (200 values).
- Noisy model (p. 22): 1 + chi ~ lognormal(mu = 1.01, sigma = 0.81) for HSBC;
  N in {5, 100, 500}.
- Convergence probability from a horizon (p. 22): (1 - p)^126 = 0.50 => p = 0.55%.

## Return on capital example (p. 13) [PAPER-DERIVED]

    (100 / 20) x (5.0% - 1.8%) = 16%

## Parity of the twins (not in the paper; from the equalization agreements in
`data/raw/datastream_dlc/`)

- Royal Dutch / Shell: combined dividends split 60% / 40% ("sixty per cent. ... forty
  per cent", RD-Shell agreement). Per-share parity = 1.5 x N_Shell / N_RD on a common
  split basis. With the workbook's end-of-sample share counts this gives
  6.87-6.96 (1997-2002), versus the workbook constant 6.863. [MATHEMATICALLY-DERIVED]
  **Freeze audit 2026-10-07 (A1):** that check used 2000-02 share counts (an OOS
  data touch, no returns). Split-adjusted, the development-period share counts give
  6.956 in every year 1987-1999; 6.863 matches only 2000-02. `parity_ratio` is now
  6.9558 (median 1997-07-01..1999-12-31); 6.863 is kept as `workbook_parity_ratio`
  for the ingest check only.
- Reed / Elsevier: "Equalisation Ratio means the ratio of 1.538:1" (gross dividend of
  one Elsevier share to one Reed share). Workbook constant 1.538. [PAPER-DERIVED
  from the agreement]
- Rio Tinto: agreement PDF has no text layer; workbook ratio 1.0 not verified.
  [IMPLEMENTATION-ASSUMPTION]
- Under Z[.] (demeaning, detrending) a constant or slowly drifting parity does not
  affect E5. [MATHEMATICALLY-DERIVED]

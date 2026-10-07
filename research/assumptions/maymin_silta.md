# Assumptions and ambiguities: Maymin (SILTA)

## Assumptions made by the paper [PAPER-DERIVED]

| # | Assumption | Page |
|---|---|---|
| P1 | Arbitrageurs cap total position at N days of average volume and choose how fast to trade (eq. 1). | 13-16 |
| P2 | Constant daily convergence probability p. | 16 |
| P3 | Market impact f(N, t) = sqrt(theta) (square-root) for Figures 5-7. | 19 |
| P4 | Arbitrageurs trade equal numbers of shares in both classes: k1 = k2 = theta min(S1, S2). | 18 |
| P5 | Discrepancy D > 0 with P1 > P2, and the expensive class has more standard volume (chi > 0). | 18-20 |
| P6 | Standard volume ratio is proxied by the observed ratio when |relative price| < 180 bps; the 180 bps HSBC bound is used for all pairs. | 21, 27 |
| P7 | Twins: local listings, common currency at end-of-day mid FX, 2002-2007 because earlier Datastream/Bloomberg volumes disagree. | 26 |
| P8 | 20 arbitrageurs solve for the total position jointly (market impact on N, not N/20). | 23 |
| P9 | Top-tier arbitrageur costs (HSBC): commissions 10 bps/side, spread 40 bps per class, financing 50 bps/yr (GC borrow 30 + funding 20), stamp duty avoided via swaps, leverage 10x. | 11-13 |

## Ambiguities in the paper

| # | Ambiguity | Our reading | Tag |
|---|---|---|---|
| A1 | Form of "detrending" in Z[.] | Linear time trend, removed by OLS on a time index, then demean/descale | [IMPLEMENTATION-ASSUMPTION] |
| A2 | Order of operations in Z[.] | Detrend (with intercept) -> divide by the residual standard deviation | [IMPLEMENTATION-ASSUMPTION] |
| A3 | Newey-West settings | R sandwich `NeweyWest` defaults: automatic NW(1994) Bartlett lag, AR(1) prewhitening, n/(n-k) adjustment. Reported with a fixed-lag sensitivity. | [IMPLEMENTATION-ASSUMPTION] |
| A4 | Text says the New price "increases by another 1.7%" per unit of log volume ratio, Table II says beta = -1.7% | Table is right (the stated relation is negative); the text has a typo | [PAPER-DERIVED table; our reading] |
| A5 | "RD-Shell 2002-2007" runs past the July 2005 unification of Royal Dutch and Shell Transport | After 2005 presumably Royal Dutch Shell A vs B shares; not stated | [IMPLEMENTATION-ASSUMPTION] (unresolved) |
| A6 | Which twin leg is "1" (more expensive) and whether chi > 0 was checked for the twins | Check both against parity in our data and report. Step 7: leg a is the expensive one in both pairs; chi is reported in shares (the paper's proxy) and in value traded, because RD and Shell shares differ in size ~6.9x (RD/Shell chi < 0 in shares, > 0 in value) | [IMPLEMENTATION-ASSUMPTION] |
| A7 | Raw prices vs total-return prices in ln(P1/P2) | Raw prices ("prices of the two share classes"); ex-dividend jumps are not removed in the paper | [PAPER-DERIVED reading] |
| A8 | Treatment of days when one market is closed (twins) | Not stated; we use dates on which both legs traded | [IMPLEMENTATION-ASSUMPTION] |
| A9 | HSBC data source | Not stated (Bloomberg used for market value) | unresolved |

## Our implementation decisions that depend on this paper

| Decision | Tag | Where |
|---|---|---|
| Relative price on raw closes ln(close_a / close_b) | [PAPER-DERIVED] (A7) | `quant_lab.strategies.parity_zscore`, `quant_lab.models.silta` |
| Prices in GBP via the workbook's own daily FX (paper: end-of-day mid FX) | [IMPLEMENTATION-ASSUMPTION], close to P7 | `quant_lab.data.datastream` |
| Explanatory Z[.] uses the full sample of the analysed window; any trading use needs a trailing Z | [MATHEMATICALLY-DERIVED] (look-ahead) | `quant_lab.models.silta` |
| Analysis windows limited to the locked development periods (RD-Shell 1987-1999, Reed-Elsevier 1993-1999) | [IMPLEMENTATION-ASSUMPTION] (sample design, `research/reports/data_decisions.md`) | `conf/split/` |
| 15% participation cap in the cost model | [PAPER-DERIVED example, p. 13] -> sizing rule [PROPOSED-EXTENSION] | `conf/costs/liquidity.yaml` |

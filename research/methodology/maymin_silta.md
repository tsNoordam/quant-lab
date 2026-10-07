# Methodology: Maymin (SILTA), with review

## 1. Price-volume regressions (the testable core)

What the paper does [PAPER-DERIVED, pp. 9, 34, 37-38]:

1. Daily data per pair; y = ln(P1/P2), x = ln(V1/V2) (shares volume).
2. Four specifications (Table II, Table V):
   - (a) OLS of y on x (raw);
   - (b) OLS of y on ln(P1V1/(P2V2)) (notional volume);
   - (c) y and x demeaned and descaled, then OLS;
   - (d) y and x demeaned, descaled and **detrended**, then OLS.
   Table VI reports only (d) for all pairs; for the twins "regressions are done on
   standardized variables only" (p. 26 fn 11).
3. Reported: coefficient, Newey-West corrected standard error and t-statistic,
   correlation rho, R^2. In (c)/(d) the intercept is 0 and beta = rho.
4. Standard errors: "Newey & West (1994) as implemented and described by Zeileis
   (2004)", i.e. R `sandwich::NeweyWest`: automatic lag selection (Newey-West 1994,
   Bartlett kernel), and, as we understand the package defaults, AR(1)
   prewhitening and a finite-sample adjustment n/(n-k).
   [PAPER-DERIVED for the citation; IMPLEMENTATION-ASSUMPTION for the defaults]

Twin specifics [PAPER-DERIVED, p. 26 fn 11]: local listings only (London and
Amsterdam), prices in a common currency using end-of-day mid FX, 2002-04-25 to
2007-04-24.

## 2. Model calibration (H2)

[PAPER-DERIVED, pp. 20-24, 27-29]

1. Proxy the standard-volume ratio S1/S2 = 1 + chi by the observed volume ratio on
   days when |ln(P1/P2)| is inside the transaction-cost bound (180 bps, HSBC's,
   reused for every pair; whole history for 3Com/Palm). Fit lognormal (mu, sigma)
   of the log volume ratio (Table VII).
2. For grids of p and D, solve equation (1) for theta (f = sqrt(theta)), simulate
   chi from the fitted lognormal, regress D on Z[ln(1 + chi/(1+theta))] and record
   the slope b (Figure 6). Fit a cubic of b in p.
3. Invert the cubic at the market slope (Table VI) to get the implied p (Table VII,
   N = 100); repeat over N to get N as a function of p (Figure 10, Table VIII).

Not specified: simulation sample sizes, seeds, the optimizer for (1), how theta
enters when D is below the cost bound (Figure 7 sets activity to zero below 1.8%).

## 3. Review (quant-researcher role)

Written for this lab before any regression was run on our data.

**Standardization.** Full-sample demeaning, descaling and detrending use the whole
sample, so Z[.] at time t depends on future observations. That is legitimate for an
explanatory regression but not for any trading signal. Our implementation must
offer a causal (trailing) variant for anything used in a strategy. The paper does
not state the trend form; a linear time trend fitted by OLS is the natural reading.

**Inference.** Both y and x are highly persistent (near unit-root in levels for
twins over short samples). Spurious-regression risk is real: detrending helps only
against deterministic trends. HAC standard errors with an automatically chosen lag
are fragile for highly persistent series; reporting a range of lags and a
block-bootstrap check is prudent. A significant contemporaneous correlation does not
identify direction (volume -> price or price -> volume).

**Sign convention.** Swapping legs flips both y and x, so the sign of b is
orientation-invariant. But the prediction is conditional on chi > 0: the class that
is more expensive *relative to parity* must also have more standard volume. For
twins with parity != 1, "more expensive" must be measured against parity, and the
paper does not say how it checked this for RD-Shell, Unilever or Reed-Elsevier.

**Volume quality.** The author restricted the twins to 2002+ because earlier
Datastream and Bloomberg volumes disagreed. Our Datastream data is exactly the
pre-2002 kind. Results on it carry that caveat; we cannot cross-check against
Bloomberg.

**Multiple testing.** Table VI reports 10 pairs with 5 significant; the selection
of the five "large" pairs is by size (motivated ex ante by the model), which is
reasonable but post-hoc within the paper.

**What our data allows (Step 7).**
- Exact replication of Table VI numbers: **not possible** (our twin data ends
  2002-10-03; the paper starts 2002-04-25; overlap is ~5 months, inside our locked OOS).
- Methodology replication: possible and testable on synthetic data with a known
  slope.
- A test of H1 on an **earlier, disjoint period** (RD-Shell 1987-1999, Reed-Elsevier
  1993-1999): possible, within the development periods, and an out-of-period test of
  the paper's claim rather than a replication.
- H2 calibration: possible in principle; deferred (needs the simulation of eq. 1).

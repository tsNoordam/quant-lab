# Methodology: de Jong, Rosenthal & van Dijk (2009), with review

## 1. What the paper does

### Deviations

[PAPER-DERIVED, pp. 500-502]

- Compute d_t for each twin over its sample window (E1).
- Report the Table II statistics, the cross-twin correlations, and Figure 1
  (RD/Shell and Brambles).

### Comovement

[PAPER-DERIVED, pp. 502-504]

- Run regression E2 with Newey-West standard errors.
- Report the coefficient sums with Wald tests, R² and Durbin-Watson.

### Arbitrage strategies

[PAPER-DERIVED, pp. 503-509]

The perspective is a US arbitrageur.

**Signal and positions.**

- The signal comes from the previous day's closing prices; trades happen at
  daily closes.
- Equal-dollar long/short positions, at most one position per twin.
- Thresholds b/s ∈ {10%/5%, 5%/1%}.
- Horizon ∈ {1 month, 3 months, 12 months, unlimited}.

**Costs, margins and interest.**

- Commission: 25 bps per transaction.
- Spread: half of a 40 bps spread on both twins at set-up. A per-DLC average
  spread gives "similar findings" (not reported).
- Regulation T: 50% initial margin, maintenance 25% long / 30% short, partial
  liquidation on a margin call.
- Fixed interest: cash 5%, margin loan 5.5%, short rebate 3%.
- Currency hedging costs are ignored.

**Reporting.**

- Tables IV and V show positions by direction, days held, weighted, median,
  min and max monthly returns, cut-offs, negative returns and margin calls.

### Risk-adjusted performance

[PAPER-DERIVED, pp. 509-511]

- Pooled daily returns, excess over the T-bill rate.
- Fama-French 3-factor (S&P 500, SMB, HML) and IAPM (World index plus two
  local indices) alphas.
- Volatility, idiosyncratic volatility, skewness, kurtosis and 1% VaR.

### Robustness

[PAPER-DERIVED, pp. 512-518]

- ADR deviations for 7 twins (results not reported).
- Ex-dividend event study (34 events) and an Advance Corporation Tax (ACT)
  abolition event study (both not reported).
- Blockholdings.
- Short-sale constraints (Belgium, Sweden, Finland).
- Threshold surface (Figure 2).
- Cost, rebate and one-day-delay sensitivity.
- Unification event windows (Figure 3) and post-announcement strategies.

## 2. Review (quant-researcher role)

Written before any replication run.

### In-sample design and multiple testing

- Thresholds and horizons are chosen and evaluated on the same 1980-2002
  sample.
- Eight strategies are reported in tables, plus a full b/s surface; the
  best-looking point (18%/10%, about 15% p.a.) rests on 24 positions.
- There is no hold-out and no correction for the number of configurations.
- The benchmark 10/5/12 months is described as "not exceptional", which is
  fair, but its significance is a single-test p-value.

### Size of the edge relative to its risk

- The benchmark's abnormal return is 8.6% p.a., against about 30.6%
  idiosyncratic volatility. That is a Sharpe of about 0.28 on equity at about
  2x gross leverage.
- Over about 10,000 position-days pooled across 12 twins this can be
  significant, but per twin it is not detectable.
- In this lab's one-shot OOS test (about 690 days per pair) the standard error
  of an annual Sharpe was about 0.6.
- So the paper's result and our step 11 null result are not in conflict.

### Return accounting choices that can inflate monthly figures

1. **Short positions are padded with the T-bill** to a full month, so a 2-day
   convergence counts as a 22-day position.
   - Weighting by days limits the effect on the weighted mean, but the median
     and maximum "% per month" figures are not comparable with an equity-curve
     return.
2. **Open positions at the sample end are discarded.** These are positions
   that have not converged, so the bias is likely upward.
3. **Fixed interest rates.** Cash at 5% and loans at 5.5% across 1980-2002,
   while 3-month T-bills ran from about 15% (1981) to about 1.7% (2002).
   Alphas are measured over the actual T-bill rate, so the fixed 5% cash
   credit creates a period-dependent bias:
   - negative in the 1980s;
   - positive in 2001-02.

### Execution and asynchrony

- The signal is taken from day t-1 prices and the position is taken at day-t
  prices, which is causal.
- One extra day of delay cuts alpha from 0.718 to 0.382% per month. Half of
  the profit therefore comes from reversal within about a day of the
  threshold crossing.
- That is the profile of non-synchronous noise. The best monthly returns come
  from the 10-hour-gap Australian twins:
  - Rio Tinto 5.05%;
  - BHP Billiton 4.24%;
  - Brambles 3.11%;

  all with positions of about one month.
- The paper says ADR prices remove this explanation (C5), but those results
  are not reported.
- Our step 11 found Rio Tinto profitable gross and strongly unprofitable net
  under liquidity-scaled costs, which is consistent with asynchrony.
- This is testable on our data: with the same rules, split the results by
  time-zone gap.

### Costs

- 25 bps commission plus 20 bps half-spread is similar in size to our median
  order cost (about 20-36 bps per order).
- Volume and market impact are not modelled. For the large twins this is
  probably minor at moderate size.
- Exit spread: see D3.

### Survivorship and sample construction

- The paper uses all 12 DLCs that existed for 12 months or more in 1980-2002.
- The unified twins are cut 20 trading days before the announcement.
- This avoids the announcement jump (which would favour arbitrage), but the
  set of twins is known with hindsight (12 months of existence).

## 3. What our data and lab allow (step 13 assessment)

### Table II (deviations)

- Directly replicable: the workbooks contain the authors' own deviation
  series, and our ingest reproduces it.
- It can be done for all 12 twins once ingested.
- This is a data-level replication, not a test.

### Table III (comovement)

- Replicable from the `Regression data` sheets (indices and FX), with
  Newey-West errors (`quant_lab.models` already has a sandwich-compatible
  implementation).

### Tables IV and V (strategies)

- Replicable per twin with the paper's rules and its cost, margin and interest
  conventions.
- This needs new code:
  - a margin-account simulator (Reg T, maintenance calls with partial
    liquidation);
  - fixed interest;
  - the T-bill padding convention for reporting.
- Ambiguities D1-D9 have to be resolved by declared assumptions, and each
  checked against the per-twin table values.

### Table VI (abnormal returns)

- Needs the Fama-French factors and the 3-month T-bill (public), the S&P 500
  (in the workbooks) and the Datastream World index (to be checked in the new
  workbooks).

### Our standard (second layer)

The same rules run through our engine:

- liquidity-scaled costs;
- next-close fills;
- total-return P&L;
- no padding;
- open positions marked at the period end.

The gap between the paper's convention and ours is itself a result.

### OOS status

- **The paper is in-sample over 1980-2002.** Replicating it needs data from
  2000 onward, which our sample design locks. That window was used once in
  step 11, for the frozen strategies only.
- **A replication run over 2000-02 does not reopen that test**, but it does
  touch the OOS window and needs `+unlock_oos=true`. CLAUDE.md allows that
  only when the user explicitly asks. **This decision belongs to the user at
  step 14 (sample design).**
- **Consequence:** any new strategy developed from this paper on 1980-2002 has
  no unused OOS period left in this dataset. A real test would need post-2002
  data (option B).

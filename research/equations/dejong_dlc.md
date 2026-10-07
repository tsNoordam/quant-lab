# Equations: de Jong, Rosenthal & van Dijk (2009)

Journal page numbers. A is the first part of the twin, in the earlier time zone
(Table I note), e.g. Royal Dutch, Elsevier, Rio Tinto Ltd.

## E1 Deviation from parity [PAPER-DERIVED, pp. 500-502, Table II]

    d_t = ln(P_A,t / P_B,t) - ln(R)

- P are the two twins' prices in a common currency (FX from Datastream).
- R is the theoretical price ratio:
  - 1:1 for six of the twins (which six is not stated; assumption D12);
  - otherwise the Rosenthal-Young ratio, fixed over the sample.
- Table II reports d_t in percent.
- In the workbooks, "LOG DEVIATIONS FROM PARITY" in the `Ratio` sheet is d_t,
  and "THEORETICAL RATIO" is R. [IMPLEMENTATION-ASSUMPTION, matched for 3 pairs
  by our ingest test]

## E2 Comovement regression [PAPER-DERIVED, Table III, p. 504]

    r_A,t - r_B,t = alpha + beta (r_A,t-1 - r_B,t-1)
                    + sum_{i=0}^{1}  gamma1_i Index1_{t+i}
                    + sum_{j=-1}^{0} gamma2_j Index2_{t+j}
                    + sum_{k=-1}^{1} delta_k  er_{t+k}  + eps_t

- r: daily log returns in local currency.
- Index1, Index2: log returns of the two domestic indices.
- er: log change of the exchange rate.
- For twins with no time difference, only contemporaneous index returns enter.
- Reported: R², Durbin-Watson, degrees of freedom, and the coefficient sums
  (lagged dependent variable; index 1; index 2; exchange rate), with Wald tests
  that each sum is zero, using Newey-West standard errors.

## E3 Arbitrage position [PAPER-DERIVED, pp. 503-506]

**Entry** on day t, when the previous day's deviation crosses the buy
threshold:

- |d_{t-1}| >= b: go long the cheap twin and short the expensive twin, in
  equal dollar amounts X.
  - d > 0: short A, long B.
  - d < 0: long A, short B.

**Exit** at the first of:

- |d| <= s (the sell threshold, s < b);
- the maximum horizon H (1 month = 22, 3 months, 12 months = 260 trading days,
  or unlimited);
- the end of the sample (open positions are discarded).

**Margins** (Regulation T):

- initial equity E_0 = 0.5 X (long) + 0.5 X (short) = X;
- maintenance margin 25% of long market value and 30% of short market value.
- When equity falls below maintenance, the smallest fraction of both legs is
  unwound that restores it (a margin call).

**Interest** (fixed nominal rates, per year):

- cash +5%;
- margin loans -5.5%;
- short rebate +3% (equivalent to a 200 bps borrowing fee).

**Costs:**

- commission c = 25 bps per transaction;
- half the bid-ask spread on both twins at set-up, with spread = 40 bps (the
  median of the 24 twin stocks).

## E4 Reported returns [PAPER-DERIVED, pp. 505-507]

- **Daily return** on the arbitrageur's equity, from daily equity values marked
  to market.
- **Position return:** expressed in % per month.
- **Short positions:** if a position lasts less than one month (22 trading
  days), the proceeds earn the 3-month T-bill for the rest of the month, so
  every position counts at least 22 days.
- **Strategy return:** the average of position returns, weighted by days
  invested ("w.% p.m."), plus median, min and max.

## E5 Abnormal returns [PAPER-DERIVED, Table VI, pp. 509-510]

The daily portfolio return pools all open positions:

    FF 3-F:  R_p,t - Rf_t = alpha + b (R_S&P,t - Rf_t) + s SMB_t + h HML_t + eps_t
    IAPM:    R_p,t - Rf_t = alpha + b_W (R_World,t - Rf_t) + b_1 Local1_t + b_2 Local2_t + eps_t

- alpha is in % per month; the annualized abnormal return is reported next to
  it.
- Also reported: sigma, sigma of the S&P 500 over the same period, sigma_eps
  for each model, skewness, kurtosis and the 1% VaR of the daily return
  distribution.

## Numerical cross-checks [MATHEMATICALLY-DERIVED]

- **The monthly figures are consistent with the annual ones:**
  - 1.18% per month × 12 = 14.2% p.a. (text);
  - alpha 0.718% per month × 12 = 8.6% p.a. (Table VI).
- **Implied annual Sharpe of the benchmark strategy's abnormal return:** about
  8.6% / 30.6% = 0.28, using the Fama-French idiosyncratic volatility. This is
  not reported by the paper.
- **Round-trip cost per twin at set-up and exit:** 2 legs × (2 × 25 + 20) bps
  = 1.4% of one leg's notional if half the spread is paid only at set-up, or
  1.8% if it is also paid at exit (assumption D3).

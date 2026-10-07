# SILTA arbitrageur (`silta_parity`) on RD/Shell, development data (Step 8)

Date: 2026-10-07. Spec: `research/specs/extensions/silta_parity.md`. The spec,
including its pre-registered expectation, was committed in b555c5e before
these runs. Code at that commit. Costs `liquidity`, execution `next_close`,
init_cash 1,000,000 GBP, leg_weight 0.5 (gross 1x). Train and validation only;
the OOS period was not touched. Aggregates only (licensed data).

Reproduce:

    uv run python -m quant_lab.backtest.run data=rd_shell strategy=silta_parity
    uv run python -m quant_lab.backtest.run data=rd_shell strategy=silta_parity backtest.period=validation
    uv run python -m quant_lab.backtest.walkforward data=rd_shell strategy=silta_parity
    uv run python -m quant_lab.backtest.walkforward data=rd_shell      # baseline, for comparison

These numbers come from a scratch copy of the data outside git, so their run
tags say `git_dirty=unknown`. Rerun them on a clean checkout of this commit to
get citable MLflow runs.

## Results

| Run | Sharpe | Total return | Max DD | Entries | Exposure |
|---|---|---|---|---|---|
| silta_parity, paper values (0.018 / 0), train 1987-96 | -0.12 | -12.4% | -24.6% | 34 | 90% |
| silta_parity, paper values, validation 1997-99 | +0.14 | +2.7% | -7.5% | 1 | 100% |
| silta_parity walk-forward 1991-99 (9 folds) | -0.02 | -3.5% | -11.7% | 10 | |
| baseline `parity_zscore` walk-forward 1991-99 | -0.34 | -11.5% | -11.6% | | |

The baseline line reproduces audit 5b exactly. That cross-checks the refactor
that moved the walk-forward grid into the strategy config.

**Walk-forward selection.**

- Every fold chose the grid corner `entry_bound = 0.054`,
  `exit_bound = 0.009`. That is the widest entry and the earliest exit, so
  the fewest trades.
- 54 training backtests (6 per fold) lie behind the selection.
- 3 of 9 test years were positive.
- The corner choice fits audit A3 (`neighbourhood_mean` favours corners)
  and also cost avoidance. The grid does not bracket the chosen point.

## Where the train-period money went

Train run at the paper's values. GBP on a 1,000,000 book over 10 years.

| Component | GBP |
|---|---|
| Price P&L before costs (residual) | about +281,000 |
| Dividends (short RD pays in full; long Shell receives) | -47,000 |
| Spread + impact | -296,000 |
| Commission | -34,000 |
| Borrow | -28,000 |
| Net | -124,000 |

Notes on the cost line:

- 122 orders, with a median cost of 36 bps per order.
- Only half the orders had a usable quoted spread; the rest used the 10 bps
  fallback.

The trade earns before costs: about 2.5% a year on gross 1x exposure. The
discrepancy did narrow more often than it widened in 1987-96. But D crossed
the 180 bps bound often enough to make 34 round trips, and the costs were
about the same size as the gain.

In validation D never came back to parity: above parity on 100% of days. The
single trade was held for three years and closed by force at the period end.

## Reading

- As pre-registered, P&L comes from slow changes in the RD premium and from
  carry, not from many small convergences.
- The paper's 180 bps bound is roughly a round trip at our cost model's median
  (four orders of about 36 bps). In 1987-96 RD/Shell, the discrepancy rarely
  paid much more than that. That is the paper's mechanism: costs and the rarity
  of convergence keep arbitrage capital out.
- **Neither strategy shows a positive edge after costs** on the development
  data. `silta_parity` loses less than the baseline in walk-forward
  (-3.5% vs -11.5%). With 10 entries in 9 years, that difference is not
  statistically meaningful.
- **No rule or parameter is changed because of these results** (CLAUDE.md
  golden rules).

## Open for step 9 (robustness)

- **Cost sensitivity.** Impact k, the fallback spread and stamp duty: the
  result is cost-dominated, so this matters most.
- **Leverage and capital.** The paper's 5x example scales the costs as well.
- **The `reed_elsevier` validation pair**, at the frozen paper values.
- **Sub-periods.** Before and after the 1997 UK tax-credit change.
- **Corner selection.** A wider grid would bracket the chosen point. This is a
  research decision, since widening the grid after seeing the corner is itself
  a choice informed by the results.
- **Deflated Sharpe.** Use the MLflow trial count, which includes these 54
  training backtests.

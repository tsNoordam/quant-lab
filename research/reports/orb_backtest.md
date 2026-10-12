# Track A: the course's session rules as trades on ES (step 23)

Date: 2026-10-12. Project 3, track A.

**Sources.**

- The user's run `8c5e84e4e8974b64b6166b83aa3af568` (MLflow
  `es.orb_backtest/track_a`) of `quant_lab.backtest.orb` at the audited
  engine (commit 21b2762).
- Rules, costs and the kill criterion are in `conf/orb/backtest.yaml`,
  fixed before the first run.
- Audit: `research/reports/audits/2026-10-12-orb-track-a.md`. The first run
  (`17635fdf…`, before the audit fixes) gave the same verdicts; differences
  are in §6.

**Scope.**

- ES front month, RTH, development period only:
  - train: 2010-06 to 2017;
  - validation: 2018-2020.
- One contract per trade, intraday.
- 2021 onward is out-of-sample and was not read.

## 1. What was tested

70 configurations; this is the trial count of the deflated Sharpe ratio.

| Rule | Content | Configurations |
|---|---|---|
| R1 | Opening-range breakout: range of the first 15/30/60 minutes, the first 5-minute close beyond it decides, stop at the range midpoint (course) or the opposite side, target none / 1-3R / 50% or 100% range extension | 36 |
| R1c | R1 plus one re-entry in the other direction after a stop-out (course: "double breakout") | 12 |
| R2 | RTH gap fade toward the previous close, stop 0.5 or 1 gap beyond the open, exit after 60 minutes or at the close | 4 |
| R3 | R1 only toward a gap still unfilled at entry, target the previous close | 6 |
| R4 | IVB proxy: target at the excursion reached by 70% / 50% of train breakouts | 12 |

**Execution:**

- Market entry at the open of the minute after the decision bar closes.
- Stop and time exits at market.
- Targets are limits that fill on a one-tick trade-through.
- A bar touching both stop and target counts as a stop.
- Stops and targets are on the tick grid, rounded away from the entry.

**Base costs.** Standard retail values, by the user's decision:

- ES commission $2.50 per side;
- 1 tick of slippage per market order;
- square-root impact over lagged volume, which is negligible for one
  contract.

## 2. The kill criterion

The pre-registered rule: a family survives only if, in the development period
on usable sessions after base costs, the mean net P&L per trade is positive
AND the deflated Sharpe ratio is above 0.5 in every window.

**Result: none of the 26 families survives.**

- No configuration has a positive mean.
- The DSR clause never had to decide anything. Its hurdle is SR0 = 0.065 per
  day (var_sr 7.3e-4, 70 trials).

| | Base costs (development, usable) |
|---|---|
| Configurations with a positive mean | **0 of 70** |
| Median mean net per trade | −$33.20 |
| Best configuration | R1c, midpoint stop, no target, 60-minute window: **−$18.90** per trade, 95% interval [−$38.3, +$0.5], 2967 trades |

No configuration's 95% interval reaches above +$0.5 per trade. That is per
configuration, without a multiple-testing correction, which would only
widen the intervals.

## 3. Costs and execution: how much each assumption matters

Development, usable, all 70 configurations:

| Scenario | Positive | Median $/trade | Best $/trade |
|---|---|---|---|
| base | 0 | −33.20 | −18.90 |
| slippage 2 ticks | 0 | −54.91 | −40.71 |
| commission $1.25 / side | 0 | −30.70 | −16.40 |
| commission $4.00 / side | 0 | −36.20 | −21.90 |
| MES (per MES contract) | 0 | −4.06 | −2.63 |
| no slippage (base fill conventions) | 6 | −12.04 | +6.10 |
| optimistic bracket ¹ | 2 | −14.46 | +0.28 |
| no fees, slippage or impact ("gross") ² | 15 | −5.16 | +12.94 |

¹ Optimistic bracket: half a tick of slippage, touch fills on targets,
target first on a shared bar, no slippage at the close, $1.90 per side. It
is a sensitivity, not a trial.

² "Gross" keeps the base fill conventions.

**The rules have no gross edge either.**

- On driftless random walks (8 seeds, `tests/integration/test_orb_audit.py`),
  the base fill conventions give about −$3 per trade before costs (seed
  standard deviation $7.5).
- The optimistic conventions give about +$1, which is neutral.
- The real-data gross median of −$5.16 is indistinguishable from that null.
- The 15 positive gross configurations, best +$12.94, are what the best of 70
  correlated trials on noise looks like.
- Even the optimistic bracket leaves 68 of 70 configurations negative.

**MES is worse, not better.** Per contract it loses $4.06, which is −$40.6
per ES-equivalent: commission is a larger share of a smaller contract.

## 4. Stability over time and between the periods

Median over configurations of the mean $/trade per year:

| Year | Base | Gross | Optimistic |
|---|---|---|---|
| 2010 | −13.3 | +11.8 | +5.0 |
| 2011 | −26.2 | −0.1 | −8.4 |
| 2012 | −23.9 | +4.4 | −5.7 |
| 2013 | −32.8 | −4.5 | −14.4 |
| 2014 | −48.1 | −19.5 | −30.4 |
| 2015 | −45.1 | −17.0 | −26.3 |
| 2016 | −36.2 | −8.8 | −17.9 |
| 2017 | −31.3 | −4.5 | −11.5 |
| 2018 | −11.8 | +13.0 | +6.9 |
| 2019 | −44.5 | −15.2 | −22.8 |
| 2020 | −39.1 | −7.1 | −14.4 |

- After base costs, every year is negative.
- Gross is positive in three of eleven years (2010, 2012, 2018) and negative
  in the other eight.
- There is no trend toward the recent years. 2019 and 2020 are among the
  worst.

**Train against validation:**

- Train is negative in every cell.
- In validation a few cells are positive: R1c midpoint none 60 at +$12.9
  (876 trades), R1 midpoint none/3R 60 at +$2.1/+$2.2, R1c opposite 2R 60 at
  +$7.7.
- With a per-trade standard deviation of about $540, +$12.9 over 876 trades
  is t ≈ 0.7, and several such cells are expected among 70.
- They are not consistent with train, so they are noise, not a regime.
- R4 is negative on validation alone too (−$21.4 to −$71.1). Its targets were
  fitted on train (audit A5).

## 5. Both ways (data_decisions.md)

- Including the 16 unusable sessions (the March 2020 halts and
  vendor-flagged days):
  - no configuration turns positive;
  - 0 of 26 families is positive in every window
    (`test_unusable_sessions_do_not_change_any_verdict`, run on the user's
    data).
- The largest change is −$30.11 per trade for R3 opposite 30. A few halt-day
  trades lose thousands of dollars each.
- Excluding those days flatters the rules, it does not hurt them. A
  breakout rule without a hard loss cap can lose thousands per contract on a
  single crash day.

## 6. What the audit changed

The full report is `research/reports/audits/2026-10-12-orb-track-a.md`.
Four defects were confirmed and fixed:

- RT-1: a target already passed at entry was filled behind the entry.
- RT-8: a session without bars silently removed the next 20 sessions.
- A1: whether a trade existed depended on the entry bar's open.
- A3: off-grid stop and target prices.

Their net effect on the headline:

| | First run 17635fdf | Audited run 8c5e84e4 |
|---|---|---|
| Configurations positive (base) | 0 | 0 |
| Median $/trade | −33.08 | −33.20 |
| Best $/trade | −18.52 | −18.90 |
| R1 trades, window 15, development | 2552 | 2612 (sessions restored by RT-8) |
| R1 midpoint ext50, window 15 | −38.5 | −35.3 (RT-1) |

## 7. Conclusion of track A

**The verdict.**

- On ES 2010-2020, the course's mechanical session rules (opening-range
  breakout with the course's windows, stops and re-entry; gap fade;
  breakout toward the gap; IVB-like targets) do not make money after
  realistic retail costs. None of 70 configurations does.
- Their gross P&L is indistinguishable from this engine's result on a
  random walk.
- This agrees with step 22: target-before-stop shares are at or below a
  driftless walk.

**What this rules out and what it does not.**

- Per configuration, net edges above about +$0.5 per trade are excluded at
  95%. A small edge hidden by the conservative fill conventions is bounded
  by the optimistic bracket: at most +$0.28 for the best configuration.
- Not tested:
  - the course's POC/VAL stops (they need volume at price);
  - the move of the stop to breakeven;
  - the 5-minute window;
  - the proprietary IVB levels;
  - the order-flow confirmations;
  - NQ;
  - the 2021+ period of the course's own evidence.
- Stops and targets alone cannot create an expectancy where the entry has no
  drift (optional stopping). So these variants could only help through a
  better entry, and the order-flow confirmations are the course's only
  candidate for that.

**Consequence.**

- No family passes the kill criterion, so step 24 (freeze and one-shot OOS)
  is not run, as pre-registered.
- The 2021+ period stays unspent for track A and remains locked.

## Reproduce

    uv run dvc repro es_ingest
    uv run python -m quant_lab.backtest.orb
    uv run pytest tests/integration/test_orb_audit.py   # incl. the real-data check

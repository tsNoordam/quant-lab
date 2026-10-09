# de Jong et al. (2009) under the lab's standard (step 18)

Date: 2026-10-10.

- **Part 1, the convention waterfall:** `quant_lab.models.dejong_standard`
  (MLflow `dejong.replication/standard`), on all 12 twins. Steps are in the
  `standard` section of `conf/dejong/default.yaml`.
- **Part 2, the lab's engine:** strategy `dejong_threshold`
  (`research/specs/replication/dejong_threshold.md`) through
  `quant_lab.backtest.run`, on the lab pairs' development periods.
- **No parameter is chosen in this step.** The rule is the paper's benchmark
  throughout.

Reproduce:

    uv run python -m quant_lab.models.dejong_standard
    uv run python -m quant_lab.backtest.run data=rd_shell strategy=dejong_threshold backtest.period=train run_label=step18

The same command runs `backtest.period=validation`, `data=reed_elsevier`, and
the zero-cost case `costs=flat_bps costs.fee_bps=0 costs.slippage_bps=0
run_label=step18_zero_cost`.

> **Status:** the waterfall figures below were computed in the cloud session
> with a stand-in T-bill (FRED unreachable). The T-bill only pads short
> positions and sets the excess-return benchmark. They are replaced by the
> user's run on DTB3 before this step closes; the "paper" column already
> equals step 16's DTB3 value (1.158).
>
> The lab-engine figures are final. The panels are byte-identical to the
> user's `dvc.lock`, and the lab engine uses no T-bill.

## 1. The waterfall (benchmark 10%/5%/12 months)

Each step adds one change to the step before it:

| Step | Change |
|---|---|
| paper | the paper's conventions as identified in steps 16-17 |
| dexia_cleaned | without the 1997-12-19 Dexia spike (the authors cleaned it, D15) |
| next_close | decide on close t, trade on close t+1, the lab's execution |
| marked_at_end | no position held into a unification announcement; positions open at the end marked at the last close, not discarded |
| no_padding | no T-bill padding of short positions, no 22-day lockout after them |

Costs, margins and rates stay the paper's in every step: part 2 handles costs.

### Paper metric: days-weighted mean, % per month

| Time-zone gap | paper | dexia_cleaned | next_close | marked_at_end | no_padding |
|---|---|---|---|---|---|
| All 12 twins | 1.158 | 1.201 | 0.530 | 0.470 | **0.662** |
| 0 h (ABB, Dexia, Fortis) | 1.457 | 1.675 | 1.074 | 0.913 | 1.225 |
| 1 h (RD/Shell, Unilever, Reed, Merita, Zürich) | 0.879 | 0.879 | 0.404 | 0.376 | 0.433 |
| 5 h (Smithkline) | 0.321 | 0.321 | 0.172 | 0.172 | 0.171 |
| 10 h (Rio Tinto, BHP, Brambles) | 4.748 | 4.748 | 0.696 | 0.544 | 2.433 |

### Calendar time: one daily portfolio

Excess return over the T-bill in % per year, Sharpe ratio in brackets:

| Time-zone gap | paper | dexia_cleaned | next_close | marked_at_end | no_padding |
|---|---|---|---|---|---|
| All 12 twins | 5.8 (0.38) | 6.0 (0.40) | 0.5 (0.03) | 0.1 (0.01) | **2.8 (0.16)** |
| 0 h | 8.2 (0.48) | 10.5 (0.69) | 7.0 (0.45) | 5.3 (0.35) | 7.2 (0.45) |
| 1 h | 3.0 (0.20) | 3.0 (0.20) | -0.7 (-0.04) | -0.8 (-0.05) | 0.4 (0.03) |
| 5 h | -0.1 (-0.01) | -0.1 (-0.01) | -1.1 (-0.10) | -1.1 (-0.10) | -1.1 (-0.10) |
| 10 h | 15.2 (0.93) | 15.2 (0.93) | 2.3 (0.13) | 2.0 (0.11) | 7.0 (0.29) |

Positions (all twins): 128, 128, 128, 130 and 144.

### Reading

1. **Trading one close later is the single largest change.**
   - The benchmark falls from 1.20 to 0.53% per month, and the calendar-time
     Sharpe ratio from 0.40 to 0.03.
   - Most of the paper's return is earned between the close on which the
     signal appears and the next close.
2. **The time-zone gap explains where that return comes from.**
   - The Australian twins (Sydney and London close 10 hours apart) lose 85% of
     their return (4.75 → 0.70).
   - The twins in one time zone keep two thirds (1.68 → 1.07).
   - A deviation measured on non-synchronous closes is partly noise that
     reverses the next day; trading it at the same close captures that
     reversal, and no one can trade it at the same close.
   - This confirms the review's suspicion
     (`research/methodology/dejong_dlc.md`, §2) and is consistent with step
     11's Rio Tinto result.
3. **Holding into unification announcements and discarding open positions
   add a little** (0.53 → 0.47 when both are removed).
4. **The lockout costs return.**
   - Without padding and lockout, more positions are taken (130 → 144) and
     the return recovers to 0.66% per month (Sharpe 0.16).
   - The paper's one-month lockout is not conservative for the twins whose
     positions are short: it skips some of the best trades.
5. **What survives under our execution is a calendar-time Sharpe ratio of
   0.16 before realistic costs.**
   - It is concentrated in the same-time-zone twins (0.45).
   - The 1-hour twins, the paper's largest group by positions and the only
     ones in the lab's data, earn 0.4% per year over the T-bill (Sharpe
     0.03).

### All eight strategies, all twins

| Strategy | Weighted mean % p.m., paper → ours | Calendar-time Sharpe ratio, paper → ours |
|---|---|---|
| 5%/1%/1 month | -0.140 → -0.746 | -0.21 → -0.32 |
| 5%/1%/3 months | 0.497 → 0.110 | 0.20 → 0.01 |
| 5%/1%/12 months | 0.689 → 0.399 | 0.36 → 0.15 |
| 5%/1%/unlimited | 0.639 → 0.401 | 0.28 → 0.14 |
| 10%/5%/1 month | 0.483 → -0.569 | 0.00 → -0.30 |
| 10%/5%/3 months | 1.042 → 0.389 | 0.33 → 0.10 |
| 10%/5%/12 months | 1.158 → 0.662 | 0.38 → 0.16 |
| 10%/5%/unlimited | 1.131 → 0.642 | 0.46 → 0.15 |

No strategy keeps more than about 0.16 of calendar-time Sharpe ratio.

## 2. The lab's engine on the lab pairs (development periods)

The engine trades on close t+1, uses liquidity-scaled costs (quoted spread,
square-root impact, borrow) and total-return P&L with withholding tax, at
gross 1x and capital 1m.

| Pair, period | Positions | Sharpe after costs | Sharpe without costs | Return % p.a. after / without costs | Median order cost (bps) |
|---|---|---|---|---|---|
| RD/Shell, train 1987-96 | 5 | -0.07 | 0.09 | -0.20 / 0.20 | 22 |
| RD/Shell, validation 1997-99 | 3 | 0.10 | 0.25 | 0.45 / 1.71 | 29 |
| Reed/Elsevier, train 1993-97 | 3 (4 without costs) | 0.03 | 0.24 | 0.02 / 1.27 | 41 |
| Reed/Elsevier, validation 1998-99 | 5 | 0.10 | 0.38 | 0.48 / 4.19 | 51 |

**Costs.** The lab's median cost per order is 22-51 bps, about the paper's 45
bps per leg (25 commission + 20 half-spread). Costs are not what separates the
paper from us; execution timing is. They remove most of what is left after
it: the Sharpe ratio drops from 0.09-0.38 to -0.07-0.10.

**Positions.** Reed/Elsevier's train period has one entry fewer with costs:
it falls in the cost model's 60-day warm-up, when no position is allowed
before the cost statistics exist.

**Power.** These are 3-5 positions per pair and period. No figure in this
table is distinguishable from zero; it is a consistency check, not evidence.
The pooled answer is the waterfall's.

The out-of-sample periods (2000-02) and Rio Tinto are not run: they stay
locked unless the user unlocks them explicitly.

The DSR trial count of `rd_shell` and `reed_elsevier` rises by these runs once
they are in the user's MLflow store: 4 per pair (2 periods × 2 cost cases), as
the lab's trial counting requires. The cloud session's own store also holds two
superseded zero-cost runs per pair, with 5 bps slippage.

## 3. Conclusion for paper 2

| Question | Answer |
|---|---|
| Is the paper reproducible? | Yes. Tables II, III and the holding statistics of IV-V reproduce closely; returns and alphas within about 0.15% per month; every difference documented (steps 14-17) |
| Is its return robust to its own conventions? | No. About 55% of the benchmark return disappears when trades happen one close after the signal, and 85% for the non-synchronous Australian twins |
| What survives under our standard? | A calendar-time Sharpe ratio of about 0.16 before realistic costs, concentrated in same-time-zone twins; on the lab pairs, Sharpe ratios of -0.07 to 0.10 after costs |
| Agreement with paper 1 (Maymin, steps 1-12)? | Yes: in both, the gross edge in RD/Shell-type pairs is small and costs or execution remove it |

## 4. Pinned by tests

- `tests/unit/test_dejong_threshold.py`: the lab strategy enters and exits on
  the same closes as the paper engine (synthetic series).
- `tests/structural/test_strategy_causality.py`: no future data.
- `tests/unit/test_dejong_standard.py`: cumulative steps, groups, the
  calendar-time metric.
- `tests/integration/test_dejong_engine_real.py`, with DTB3: the waterfall's
  first step equals step 16, and next_close is its largest drop.

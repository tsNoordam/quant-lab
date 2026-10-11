# Methodology: the course's session edges (ORB/IB, IVB, RTH gap fill), with review and test plan

Track A of the order-flow project (ROADMAP step 20). The source is a
commercial course; its claims are hypotheses for this lab, not evidence.
Extraction: `research/extraction/deepcharts_orb.md`. Ambiguities:
`research/assumptions/deepcharts_orb.md`. Claims:
`research/evidence/deepcharts_orb_evidence.csv`.

## 1. What the course does

The course builds on mechanical session "edges" and adds discretionary
order-flow confirmation on top. In its own words, these are "very mechanical
edges" on which one builds a "discretionary narrative"
(`Learn/Auction Session Dynamics/5.RTH Gap Fill`, [00:52]).

| Layer | Content | Testable in track A? |
|---|---|---|
| L1 mechanical | ORB/IB breakout of the first 15/30/60 min of the RTH session; RTH gap fill; their combination | yes, from 1-minute bars |
| L2 statistical | Deep-M IVB: "protection" and extension targets from a proprietary model ("neural network, machine learning", lesson 6 [08:23]) | only by proxy: the algorithm is not published |
| L3 location | IB volume profile: POC to value-area edge as re-entry zone, VAL/VAH close as invalidation | partly: needs volume at price (trades data) |
| L4 order flow | absorption, aggression, exhaustion, imbalance, big trades | no: no thresholds are given; track B |

## 2. Review

1. **Probability is not edge.** The course's numbers are hit rates: about 70%
   of opening-range breakouts give "some level of excursion" (lesson 4
   [02:41]); gaps fill 68% of the time (lesson 5 [00:33]); IVB targets are
   reached with 65-70% probability (lesson 6 [08:54]). None defines the
   excursion size, the stop, or the time window, and a hit rate says nothing
   about expectancy without the loss side. The lab tests both the statistic
   (can it be reproduced?) and the trade (is the net expectancy positive?).
2. **The performance evidence is a screenshot.** ORB "risking 2% per trade"
   beat buy-and-hold S&P 500 "from 2021 till more or less today", with a
   better Sharpe ratio (lesson 4 [01:51]). No costs, rule details or
   out-of-sample period are shown, and the presenter adds that whole years
   can be flat (lesson 4 [02:22]).
3. **The external evidence is gross-positive, net-doubtful.**
   [EXTERNAL-RESEARCH]
   - Crabel (1990) introduced the opening range breakout; Holmberg, Lönnbark
     & Lundström (2013, *Finance Research Letters* 10(1): 27-33) test it
     intraday on futures. Their results could not be retrieved in this step.
   - Tsai et al. (2019, *IEEE Access* 7, doi:10.1109/ACCESS.2019.2899177):
     one-minute data on DJIA, S&P 500, NASDAQ, HSI and TAIEX index futures,
     2003-2013; a secondary summary reports that the traditional ORB showed no
     significant profitability and a "timely" variant did. Unverified.
   - Zarattini & Aziz (2023, SSRN 4416622): a 5-minute ORB on QQQ, 2016-2023,
     reports 33% annual alpha net of commissions. An independent replication
     reproduces the gross result on NQ but finds no index distinguishable
     from zero after spread and slippage, which the paper does not charge,
     and notes that the paper has no out-of-sample period.
   - The RTH gap-fill statistics in circulation (e.g. fill rates falling with
     gap size) come from trading-community studies without published method.
4. **Same-bar ambiguity.** With 1-minute bars a breakout bar can touch both
   the stop and the target. The lab resolves this conservatively (stop first)
   and reports how often it happens; if it is frequent, the test needs trades
   data.
5. **What track A cannot show.** A negative L1 result says the mechanical
   base has no net edge. It does not say that L3/L4 confirmation adds
   nothing: a filter can in principle select profitable trades from an
   unprofitable base. That is track B's question. A positive L1 result is the
   base that track B's measured decisions are compared against.

## 3. Test plan [IMPLEMENTATION-ASSUMPTION unless tagged]

### Data

- **Instrument.** ES continuous front month (CME Globex), 1-minute OHLCV
  bars, from Databento (`GLBX.MDP3`, schema `ohlcv-1m`, coverage from 2010).
  OHLCV is Databento's smallest schema; the exact cost is to be read from
  their cost endpoint before download (the account's free credit is expected
  to cover it).
- **MES.** Listed only since May 2019. Prices are ES prices; MES enters only
  through contract size and costs, so a retail-sized account can be modelled
  without a shorter history.
- **Roll.** Volume-based roll, with the roll date logged; no back-adjustment
  of intraday levels across a roll (the range, entry and exit are always on
  one contract).
- **Sessions.** RTH 09:30-16:00 America/New_York, from the exchange calendar,
  including early closes; the ETH session is used only for the gap
  definition. Days with missing minutes in the opening window are dropped and
  counted.
- **Validation** is deterministic code in `src/quant_lab/data/` with tests in
  `tests/data/` (timestamps, session boundaries, gaps, duplicates, roll
  jumps), as for the DLC data.

### Sample design (fixed before any result is seen)

| Period | Use |
|---|---|
| 2010-2017 | development (train) |
| 2018-2020 | validation |
| 2021 onward | out-of-sample, locked |

The course's own evidence covers "2021 till today". The locked period is
therefore exactly the period in which the course claims its edge, and it is
tested once, with rules frozen on 2010-2020.

### Rules to test

| ID | Rule | Origin |
|---|---|---|
| R1 | ORB: range = high/low of the first N minutes of RTH, N ∈ {15, 30, 60}. Enter on the first 5-minute close beyond the range, at the next bar's open; stop at the opposite side of the range; exit at the RTH close. One trade per day | [PAPER-DERIVED] from lessons 4 and 6, with the stop and exit [IMPLEMENTATION-ASSUMPTION] (A-ambiguities) |
| R1b | R1 with a target at 1R, 2R, and the range-height extensions of 50% and 100% (Session Imbalance indicator) | [PAPER-DERIVED] levels, their use as targets [IMPLEMENTATION-ASSUMPTION] |
| R2 | RTH gap fill: gap = RTH open vs. previous RTH close. Measure the fill probability by gap size, and test a fade with a fixed stop | [PAPER-DERIVED] statistic; the trade [IMPLEMENTATION-ASSUMPTION] |
| R3 | R1 restricted to days where the breakout points toward an unfilled gap | [PAPER-DERIVED] combination (lesson 5 [04:23]) |
| R4 | IVB proxy: targets at percentiles of the post-breakout excursion, estimated on the training window only | [PROPOSED-EXTENSION]: the proprietary model is not available |

N, the target and the gap-size buckets form a small grid. Only
neighbourhoods are reported, the trial count goes into the deflated Sharpe
ratio as in step 9, and the frozen choice is pre-registered before 2021 is
opened.

### Statistics the course states, reproduced first

- P(price exceeds the range by at least x ticks after the first breakout),
  for x as a grid; the course's "70%" without x is compared with the whole
  curve.
- P(gap fill within the RTH session), by gap size; compared with 68%.

### Costs and execution

- Entry on the next bar's open after the signal bar (no same-bar entry),
  stop and target fills at the level plus slippage; same-bar conflicts
  resolved stop-first.
- Commission and exchange fees per contract from a broker schedule chosen by
  the user, plus slippage in ticks (1 tick per side as the base case,
  0 and 2 as sensitivities). ES tick: 0.25 points = $12.50; MES: $1.25.
- No volume-based costs: one or a few contracts are far below ES liquidity.

### Kill criteria (pre-registered)

Track A stops for a rule if, on 2010-2020 after base-case costs, its
expectancy per trade is not positive with a deflated Sharpe ratio above 0.5
across a neighbourhood of N (not a single best cell). Then:

- the hit-rate claims are still reported (they may hold while the trade
  loses);
- track B starts from the course's order-flow confirmation, not from R1.

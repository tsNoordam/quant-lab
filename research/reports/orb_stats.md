# The course's range and gap statistics on ES (step 22)

Date: 2026-10-12. Project 3, track A.

**Source.**

- The user's run `c71da63105a143ba843de70409695eb7` (MLflow
  `es.orb_stats/course_statistics`) of `quant_lab.models.orb_stats`.
- Definitions are fixed in `conf/orb/default.yaml` before the run.
- Claims are from `research/extraction/deepcharts_orb.md`.

**Scope.**

- ES front month, RTH, development period only:
  - train: 2010-06 to 2017, 1898 usable sessions;
  - validation: 2018-2020, 743;
  - together: 2641.
- The out-of-sample period (2021 on) is not read.
- These are probabilities, not trades: no costs, no position, no
  expectancy. Step 23 tests the trades.

**Both ways** (`data_decisions.md`).

- The run printed the usable sessions. All sessions with bars differ by 16
  of 2657 in the development period (13 in validation, 3 in train).
- So no proportion below can move by more than 0.6 percentage points (1.7
  in validation) between the two universes.
- No development-period verdict can change by that much. The one verdict
  that could is C5 in validation, where "consistent" rests on a lower bound
  0.6 points from the claim.
- The code now prints both universes; the next run shows them directly.

## 1. The claims

Development period, usable sessions, 95% Wilson interval:

| Claim | Course | Ours | Verdict |
|---|---|---|---|
| C4: price stays inside the 15-minute range all session | about 15% | **0.2%** (0.1-0.5) | not reproduced |
| C5: single breakout of the 15-minute range | 48-49% | 54.4% (52.5-56.3) | higher; validation alone 52.2% (48.6-55.8) is consistent |
| C10: at least one side of the 60-minute IB is taken out | about 98% | 97.5% (96.8-98.0) | reproduced (half a point lower) |
| G1/G2: RTH gap fully filled | 68-71% | **59.5%** (57.6-61.4) | lower in both periods (train 61.1%, validation 55.6%) |
| G2: gap filled to its midline | about 80% | 76.0% (74.3-77.6) | lower |

**C4 is not a matter of definition.**

- Inside by 5-minute closes: 0.2%. Inside by touches: 0.1%.
- Even the 60-minute range holds all session on only 4.8% (closes) or 2.5%
  (touches) of days.
- No window the course uses gives 15%.

**C10** belongs to the same picture: the opening range, of any length, is
left on almost every day.

## 2. Breakouts

Share of sessions by type of 5-minute-close breakout:

| Window | No close outside | Single side | Both sides |
|---|---|---|---|
| 15 min | 0.2% | 54.4% | 45.4% |
| 30 min | 1.3% | 64.1% | 34.5% |
| 60 min | 4.8% | 76.2% | 19.0% |

With the course's live 15-minute window, almost half of all days also
close beyond the other side later (a "double breakout"). The course allows
re-entry in that case (O9), but its claims do not mention how often it
happens.

## 3. How far a breakout runs

Measured from the trigger close, in the breakout direction, until the RTH
close; share of breakouts.

| Excursion of at least | 15 min | 30 min | 60 min |
|---|---|---|---|
| 0.25 range heights | 89.1% | 83.8% | 75.3% |
| 0.5 | 77.8% | 68.6% | 54.6% |
| 1.0 | 57.5% | 44.4% | 28.0% |
| 2.0 | 28.8% | 16.2% | 7.6% |
| 3.0 | 13.5% | 6.3% | 2.4% |

**What "70% of breakouts" reach** (30% quantile, ticks of 0.25 points):

| | 15 min | 30 min | 60 min |
|---|---|---|---|
| Median range height | 20 | 26 | 34 |
| Excursion until the close | 13 | 12 | 10 |
| Excursion before the midpoint stop | 6 | 7 | 8 |
| Excursion before the opposite-side stop | 9 | 10 | 10 |

**C1** ("about 70% of breakouts give some excursion") is true but carries
little information. The excursion 70% of breakouts reach before the
midpoint stop is 6-8 ticks (1.5-2 points), against a round-trip cost of
about 2-3 ticks for one contract (O16; set in step 23).

## 4. Targets before the stop

Share of breakouts reaching k × risk before the stop (a bar touching both
counts as stopped):

| Stop | k | 15 min | 30 min | 60 min | Driftless random walk, no time limit |
|---|---|---|---|---|---|
| range midpoint | 1 | 47.7% | 46.1% | 41.1% | 50.0% |
| range midpoint | 2 | 29.0% | 24.0% | 17.3% | 33.3% |
| range midpoint | 3 | 17.8% | 12.1% | 7.0% | 25.0% |
| opposite side | 1 | 42.6% | 34.2% | 22.7% | 50.0% |
| opposite side | 2 | 17.8% | 10.6% | 5.2% | 33.3% |
| opposite side | 3 | 7.2% | 3.8% | 1.3% | 25.0% |

**Reading the benchmark.** The last column, 1/(1+k), is a reference, not a
test.

- The session close cuts trades off before either level is reached, which
  lowers both the target and the stop share.
- The farther the levels, the more it does so: the opposite-side stop and
  the 60-minute window are the most affected.
- Even so, no cell is above the driftless benchmark.
- A breakout that carried a directional edge strong enough to pay for
  costs would be expected to beat it, at least at 1R with the near
  (midpoint) stop.

**C2** ("protection level reached in 60-75% of breakouts") cannot be tested
directly, because the level is proprietary. A target that is reached 60-75%
of the time before the midpoint stop lies below 1R here, where the risk is
larger than the reward.

## 5. RTH gaps

Development, usable sessions, gaps of at least one tick (2604 sessions):

| Gap size (\|gap\| / previous close) | Sessions | Full fill | Full fill, first hour | Midline fill |
|---|---|---|---|---|
| all | 2604 | 59.5% | 40.6% | 76.0% |
| up to 0.1% | 497 | 90.7% | 85.9% | 95.0% |
| 0.1-0.25% | 716 | 75.0% | 53.9% | 86.9% |
| 0.25-0.5% | 667 | 54.0% | 26.8% | 74.7% |
| 0.5-1% | 487 | 32.4% | 11.1% | 57.1% |
| over 1% | 237 | 18.6% | 4.2% | 45.6% |
| gap up | 1456 | 57.6% | 40.0% | 72.7% |
| gap down | 1148 | 62.0% | 41.3% | 80.1% |

**Fill depends on gap size above all.**

- A gap of under 0.1% fills nine times in ten.
- A gap of over 1% fills in fewer than one in five.
- The course's single "68-71%" fits a sample of mostly small gaps, not
  ES 2010-2020.
- The fill also takes time: about 40% fill in the first hour.
- A fill of a tiny gap is a move of a few ticks: the probability is high
  where the distance is small.

## 6. What this changes

**The trigger and the windows hold as defined.**

- The course's mechanical statistics are partly reproduced (C10, roughly
  C5).
- One is far off (C4).
- One is overstated (gap fill: 60% against 69-71%, and strongly
  size-dependent).

**The breakout itself shows no continuation beyond a driftless random walk**
in the target shares (section 4).

- Taken alone, that predicts a negative expectancy after costs for R1/R1b.
- Step 23 measures the expectancy directly, as planned. Nothing in the
  rules, windows or stops changes because of these numbers.

**Not tested here:**

- the order-flow confirmations (track B);
- the proprietary IVB levels (C2, C3);
- the 5-minute window (C9);
- NQ;
- 2021 onward, which is the period of the course's own evidence.

## Reproduce

    uv run dvc repro es_ingest
    uv run python -m quant_lab.models.orb_stats

Pinned by tests:

- `tests/unit/test_orb_stats.py`: hand-built sessions with known answers,
  OOS refusal, verdicts;
- `tests/structural/test_orb_causality.py`: the range and the breakout
  ignore later bars;
- `tests/integration/test_orb_stats_run.py`: the MLflow run on synthetic
  files.

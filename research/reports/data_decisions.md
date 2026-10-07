# Data and research-design decisions

Decisions that shape what the lab can conclude, with the evidence behind them.
Newest first. Each entry is fixed once a result depends on it.

## 2026-10-07: RD/Shell parity from pre-2000 share counts (freeze audit A1)

The workbook's constant parity 6.863 cannot be derived from information before
2000: split-adjusted, 1.5 x N_Shell / N_RD is 6.956 in every year 1987-1999,
and values near 6.863 occur only in 2000-02 (the OOS period). The step 6 check
that compared them used 2000-02 share counts (a data touch, no returns); it is
recorded here as such.

Decision, on causality grounds: `parity_ratio = 6.9558` (median over
1997-07-01..1999-12-31, after the 1997 splits). The workbook value stays as
`workbook_parity_ratio`, used only to verify the ingest against the workbook's
own deviation column. The development effect was seen before this decision
(auditor's read-only check: silta_parity train -12.4% -> about -5%, validation
unchanged); the choice is fixed by the causality argument, not by that number.
`parity_zscore` is unaffected (a constant parity drops out of the z-score).

## 2026-10-07: Sample design for real pairs (Step 4c), committed before any real-data backtest

No backtest had been run on Datastream data when this design was committed.

| Pair | Role | Train | Validation | OOS (locked) |
|---|---|---|---|---|
| `rd_shell` | development | 1987-01-01 .. 1996-12-31 | 1997-01-01 .. 1999-12-31 | 2000-01-01 .. 2002-10-03 |
| `reed_elsevier` | validation pair | 1993-01-01 .. 1997-12-31 | 1998-01-01 .. 1999-12-31 | 2000-01-01 .. 2002-10-03 |
| `rio_tinto` | out-of-sample pair | none | none | 1996-01-01 .. 2002-10-03 |

- Strategy development (including walk-forward parameter selection) uses
  `rd_shell` train + validation only.
- `reed_elsevier` validation results are compared only for variants frozen on
  `rd_shell`; its train period is for checks, not for tuning.
- 2000-01-01 onward is held out for every pair, and `rio_tinto` is held out
  entirely (a pair the paper did not study). Each OOS evaluation needs
  `+unlock_oos=true`, is logged, and happens once per frozen strategy.
- `rio_tinto` is non-synchronous (Sydney closes before London opens); any OOS
  test on it must state how this is handled.

## 2026-10-07: Unilever dropped from the analysis

Unilever NV's "TURNOVER BY VOLUME" in the Datastream workbook is about 0.0007%
of NV shares outstanding per day, roughly 300x below every other leg in the
dataset (0.2-0.7%/day), so it is not NV's primary-market volume. The NV quotes
are also unusable (median spread 165-420 bps, close outside the quotes on 10%
of days), and the NV price is stale on most days before ~1993.

SILTA is a prediction about relative volume, and the cost model needs ADV, so
the pair cannot contribute. `conf/data/unilever.yaml` and its pipeline stages
were removed. The original archive stays in `data/raw/datastream_dlc/`
(immutable raw data); the evidence is reproducible with the turnover check in
`quant_lab.data.validation` (`min_median_turnover`).

Consequence: of the paper's sample, only Royal Dutch/Shell and Reed Elsevier
remain (HSBC and 3Com/Palm were never available).

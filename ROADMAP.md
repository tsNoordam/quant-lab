# Roadmap

Work proceeds in numbered steps. A step is done when its code, tests, docs and
commit are pushed and the user has confirmed it on their machine. Only then is
the next step started (see "Working in steps" in CLAUDE.md).

## Done

| Step | What | Commit |
|---|---|---|
| 1 | uv project, single `quant_lab` package, locked dependencies | 267df81 |
| 2 | v3 scaffolding, DVC-safe `.gitignore`, `CLAUDE.md`, Bash guard hook | 9dfc488 |
| 3 | DVC pipeline, validated preprocessing, synthetic twin pair | e7cbddf |
| 4 | Hydra + VectorBT + MLflow backtest, provenance tags, OOS lock | 0be0676 |
| 4a | Datastream DLC ingest (date repair, units, holidays) | ad06c25 |
| 4b | Liquidity-scaled costs, borrow, participation cap, VectorBT reconciliation | 0f891be |
| 4c | Locked sample design, walk-forward, Unilever dropped | bfe79e7 |
| 5 | `backtest-auditor` agent + audit workflow | ea1827b |
| 5a | First audit: rd_shell walk-forward. Verdict FAIL (A1 dividends); A4 logging fixed | ffcf775 |
| 5b | Fixes A1 (total-return dividends), A2 (locked quotes), A5 (FX cost); re-audit verdict WARNING. Walk-forward Sharpe -0.34, total -11.5% | befb58f |
| 6 | Paper extraction: `research/{extraction,equations,methodology,assumptions,evidence}/maymin_silta.*`; parity checked against the equalization agreements | d063320 |
| 7 | SILTA regressions (`quant_lab.models.silta`), Newey-West as in R sandwich, causal variant, chi check. H1 not supported on 1987-99 data (RD/Shell b=+0.02, t 0.4; Reed Elsevier b=+0.08, t 1.9, sign unstable); `research/reports/silta_replication.md` | 5079cb1 |
| 8 | Strategy registry; `silta_parity` (the SILTA arbitrageur: deviation from parity, 180 bps entry, exit at parity) with replication/extension specs and `run-backtest` skill. RD/Shell: train Sharpe -0.12, validation +0.14, walk-forward -0.02 (-3.5%) vs baseline -0.34 (-11.5%); cost-dominated, no edge after costs. `research/reports/silta_parity_rd_shell.md` | b555c5e, 21b18c9 |
| 9 | Robustness runner (`quant_lab.backtest.robustness`), deflated Sharpe and MLflow trial count. 19 cases x 2 strategies: no positive net Sharpe in any realistic cost/capital/leverage/selection case; baseline gross WF Sharpe +0.75 consumed by costs; DSR 0.001 / 0.027 at 502 trials; Reed Elsevier at frozen values agrees. `research/reports/robustness_step9.md` | 895df80, 0d96ef1 |
| 10 | Freeze audit (auditor + red-team): FAIL fixed. A1 RD/Shell parity carried OOS share counts -> 6.9558; A2 warm-up zero-size positions and zero-cost orders -> fixed. OOS evaluation code and pre-registration frozen (`conf/oos/`, `research/specs/freeze/preregistration.md`); n_trials 600. Tags `freeze-parity_zscore`, `freeze-silta_parity`. `research/reports/audits/2026-10-07-freeze.md` | ff1e9eb |
| 11 | One-shot OOS evaluation on the frozen tag (run once by the user, MLflow c5a6c503): no evidence of edge in any run; parity_zscore net -0.12 / -0.54 / -0.27 vs gross +0.67 / +0.98 / +0.76 (limits-to-arbitrage pattern holds); silta_parity RD/Shell not evaluable (pre-declared), Reed too few entries, Rio -41%. `research/reports/oos_evaluation.md` | bc3a8e8, 4131fc9 |
| 12 | Final report (`research/reports/final_report.md`, `research-report` skill); `quant_lab.reproduce` checks 10 headline development numbers (10/10); CI on synthetic data (`.github/workflows/ci.yml`); fresh clone without data: 268 passed, 11 real-data skips | a84c952 + (this step) |

## Notes from the steps

Open from the audits (decisions, not fixes): B6 treatment of RD/Elsevier
1996-98 wide quotes (needs a source); A3 corner-biased selection (documented
in step 9 as cost-driven). Rio Tinto Ltd withholding: settled at the freeze
(fully franked dividends, 0%).

Settled in step 6: the paper's relative price uses raw prices (A7 in
`research/assumptions/maymin_silta.md`), so the signal stays on raw closes.
Found in step 6: the paper's twin sample is 2002-04-25..2007-04-24, which our
data does not cover, so step 7 tests H1 on an earlier, disjoint period instead
of replicating Table VI numbers. Also: `shares_outstanding` (NOSH) is not
split-adjusted while volume is, so the turnover check overstates pre-split
turnover (less sensitive, never a false failure); fix before relying on it.

Found in step 7: chi is measured in value traded as well as shares (RD and
Shell shares differ in size ~6.9x); H2 calibration (eq. 1) deferred, since only
~1-13% of development days lie inside the 180 bps bound. Block bootstrap and a
differenced specification of the step 7 regression were not run (open).

Decided in step 8: the paper has no trading rule, so there is no replication
strategy (`research/specs/replication/maymin_silta.md`); relative volume (H1)
is not used as a signal (contemporaneous, and absent in our data); the
walk-forward grid now lives in each strategy's config (`strategy.grid`).

Found in step 9: with the raw-close signal, the baseline buys Royal Dutch just
after its ex-dividend drop, so it is never long RD over an RD ex-date in the
walk-forward (withholding has no effect there). The paper's 5x leverage is
outside the useful range of the metrics (equity near zero).

All numbered steps are done. Open items for any follow-up study (not started):
B6 sourced RD/Elsevier spreads 1996-98; impact sized on running equity (A7);
H2 calibration (needs the paper's 2002-07 sample); the 2000-02 OOS period is
spent for these strategies.

# Paper 2: de Jong, Rosenthal & van Dijk (2009), DLC arbitrage

Same data source (the authors built the Datastream DLC workbooks). The paper is
in-sample over 1980-2002 and specifies trading rules with per-twin results, so
a numerical replication is possible. Branch: work on `claude/sharp-bohr-snz350`
(restarted from main), merged by the user into `Dijk-paper`.

| Step | What | Commit |
|---|---|---|
| 13 | Paper extraction: `research/{extraction,equations,methodology,assumptions}/dejong_dlc.md`, evidence CSV (539 rows: Tables II-VI, sensitivity, unifications); ambiguities D1-D12; review | 947f8a9 |
| 14 | All 12 DLCs: paper-convention panels (`quant_lab.data.dlc`, `conf/dlc/`, DVC stage `dlc_ingest`) reproducing the authors' deviation column on every row; Table II replicated (`quant_lab.models.dejong`): 58/72 statistics within rounding, differences documented (Rio sign, ABB st. dev., Dexia and Fortis data versions); user approved the full 1980-2002 windows. `research/reports/dejong_table2.md` | a847032 |
| 15 | Table III comovement regressions (E2, EViews-style Newey-West) from each workbook's regression sheet (`<twin>.regression.parquet`, checked against the step-14 panels): 77/84 statistics within rounding, 48/48 significance marks; conventions D13-D18 identified from the paper's numbers, the literal reading kept as variant `as_stated`. `research/reports/dejong_table3.md` | 2268cd7 |
| 16 | Paper-convention arbitrage engine (`quant_lab.backtest.dejong`, `conf/dejong/`, trading panels with the post-window rows of unified twins): Reg T account, per-leg margin calls, fixed interest, flat costs, T-bill padding; conventions D3-D7, D19-D21 identified from the paper's numbers. Holding statistics final (Table IV 78/91 within rounding, counts exact for 11 of 12 twins); benchmark return 1.158 vs 1.180% p.m., median 3.697 vs 3.703 (FRED DTB3, added by the user); margin-call counts (D10) open; Dexia spike reported both ways. `research/reports/dejong_tables45.md` | ab4f09f, 36ecff6 |
| 17 | Table VI (`quant_lab.models.dejong_risk`): stacked position-days (D11), S&P 500 + French SMB/HML, sigma in "% per month" units (D23); position-days within 1.1% and S&P sigma within 1.6% of the paper; alpha ranking reproduced, p. 515 cost/rebate sensitivities within 0.02% p.m.; the Dexia spike explains the excess kurtosis; IAPM not replicable (no World index, D25). FF3 alphas within 0.15% p.m. of the paper's (benchmark 0.794 vs 0.718, significant at 1%). `research/reports/dejong_table6.md` | d35722d, e100030 |
| 18 | Our standard: convention waterfall over all 12 twins (`quant_lab.models.dejong_standard`) and the paper's rule as lab strategy `dejong_threshold` through the lab engine on RD/Shell and Reed/Elsevier development periods. Trading one close after the signal removes 56% of the benchmark return (Australian twins 85%); calendar-time Sharpe 0.38 → 0.16 before realistic costs; lab engine Sharpe -0.07 to 0.10 after liquidity costs (3-5 positions per run). User's runs 8b36f314 (waterfall) and the eight `step18` lab runs. `research/reports/dejong_standard.md` | 87c9484 + (step 19) |
| 19 | Final report of paper 2 (`research-report` skill): `research/reports/dejong_final_report.md`, every number from a committed report or named MLflow run, collected with sources in `research/reports/dejong_final/report_data.yaml`; claims C1-C7 with verdicts (C1, C2, C4 reproduced; C3 reproduced under the paper's conventions, not robust to execution; C5 challenged; C6, C7 not tested); errata and limitations. Rendered by `quant_lab.reporting.dejong_final` as a standalone HTML page (13 inline SVG charts with tooltips and table views, light/dark) and a PDF | (this step) |

All numbered steps of paper 2 are done. Open items for any follow-up study
(not started): margin-call counts (D10, 27 per-leg vs the paper's 14); the
IAPM column of Table VI (needs a World index, D25); the paper's one-day-delay
sensitivity (alpha falls 0.633 for us, 0.336 in the paper); `/audit-backtest` was not run on the
paper-convention engine; the 2000+ periods and Rio Tinto stay locked.

# Project 3: order flow (DeepCharts course), tracks A and B

Source: the user's course material (`tsNoordam/order-data`, commit `ee2c839`;
copyrighted, kept out of this repository). Market: CME index futures (ES,
MES). Paper 2 is preserved on the user's branch `Paper2`.

- **Track A** tests the course's mechanical session edges in the lab.
- **Track B** then measures whether the user's own discretionary order-flow
  decisions add to that base: a replay journal that records each decision
  with the market state at that moment, no look-ahead, scored by the lab.

| Step | What | Commit |
|---|---|---|
| 20 | Extraction and test plan (track A): `research/{extraction,assumptions,methodology}/deepcharts_orb.md`, claims in `research/evidence/deepcharts_orb_evidence.csv`. The mechanical core is consistent (5-minute close beyond the RTH opening range); window, stop (eight versions) and targets (proprietary IVB levels) vary by session; no claim states a sample, period or costs. Ambiguities O1-O18 fixed before any data; sample 2010-17 / 2018-20 / 2021+ locked (the period of the course's evidence) | cb7e9b9 |
| 21 | ES 1-minute data pipeline: `quant_lab.data.databento_fetch` (cost quote first, `--download` writes the unmodified DBN files and `data/metadata/databento_es.json`; key from `.env`, never written) and DVC stage `es_ingest` (`quant_lab.data.es_futures`): NYSE-RTH sessions with early closes, volume-ranked front month (`ES.v.0`) plus `ES.v.1` for the same-contract previous close on roll days, usable-session rule (98% minute coverage, no gap over 5 minutes), point-in-time roll check, bad-print and OHLC checks. Split locked in `conf/split/es.yaml` (`data_decisions.md`). Unit tests on synthetic bars and synthetic DBN files; real-data checks in `tests/data/test_es_sessions.py`. User's run (Databento quote $28.01, within the free credit): 7.67m bars, 4105 sessions, 4077 usable, 66 rolls (4 per full year), 34 early closes; the first run's missed 2014 roll fixed (rolls after bar-less sessions), vendor-degraded days excluded, unusable reasons recorded, results to be reported both ways | 2249b4e, f0a7bf0 + (this step) |

| 22 | The course's statistics on ES 2010-2020 (`quant_lab.models.orb_stats`, `conf/orb/default.yaml`; user's run c71da631): C10 reproduced (97.5% vs 98%); C5 single breakout 54% vs 48-49%; C4 not reproduced (0.2% of days stay inside the 15-minute range, not 15%); gap fill 59.5% vs 69-71% (midline 76% vs 80%), from 91% for gaps under 0.1% to 19% over 1%. Target-before-stop shares at or below a driftless random walk's 1/(1+k) in every cell. `research/reports/orb_stats.md` | 8006745, 9f3684e |
| 23 | Track-A backtest (`quant_lab.backtest.orb`, `conf/orb/backtest.yaml`): 70 configurations of R1/R1c/R2/R3/R4 on ES 2010-2020, one contract, standard retail costs (ES $2.50/side, 1 tick). User's audited run 8c5e84e4: **0 of 70 positive, 0 of 26 families survive the kill criterion**; median -$33.2/trade, best -$18.9 (95% CI up to +$0.5); gross indistinguishable from the engine's random-walk null; optimistic execution bracket 2/70 positive, best +$0.28; negative after costs in every year; unusable sessions change no verdict. Audit (auditor + red team): RT-1, RT-8, A1, A3 confirmed and fixed, the rest rejected or documented; PASS with WARNINGs. `research/reports/orb_backtest.md`, `research/reports/audits/2026-10-12-orb-track-a.md` | 7a65518, 07026cd-21b2762 + (this step) |

Planned, in order:

24. **Freeze and one-shot OOS: not run.** No family passed step 23's
    pre-registered kill criterion, so nothing is frozen; 2021+ stays unspent
    and locked.
25. **Track B design**: the decision journal (what is recorded, how it is
    scored against the track-A base), on trades data.


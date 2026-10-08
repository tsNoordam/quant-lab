# Assumptions and ambiguities: de Jong, Rosenthal & van Dijk (2009)

## Assumptions made by the paper [PAPER-DERIVED]

| # | Assumption | Page |
|---|---|---|
| P1 | The theoretical price ratio is fixed per twin: 1:1 for six twins, Rosenthal-Young for the others | 500 |
| P2 | US arbitrageur under Regulation T: 50% initial margin on each leg; maintenance 25% long, 30% short; partial liquidation on margin calls | 503-506 |
| P3 | Fixed interest rates: cash +5% p.a., margin loans -5.5% p.a., short rebate +3% p.a. (a 200 bps borrowing fee) | 503 |
| P4 | Commission 25 bps per transaction; half of a 40 bps bid-ask spread on both twins at set-up; currency translation costs ignored | 505 |
| P5 | Currency risk disregarded (hedging assumed cheap and immaterial) | 503 |
| P6 | Equal dollar amounts long and short; at most one position per twin | 503, 505 |
| P7 | A position is set up on the basis of the previous day's prices; daily closing prices are used | 505 |
| P8 | A position that ends within a month earns the 3-month T-bill for the rest of the month | 505 |
| P9 | Positions still open at the sample end are discarded | 505 |
| P10 | Sample windows: merger date (1980 for RD/Shell and Unilever) to 20 trading days before the unification announcement, or to 2002-10-03 | 500 |
| P11 | Benchmark parameters: buy 10%, sell 5%, maximum horizon one year (260 trading days) | 506 |

## Ambiguities (to resolve before step 14; each is a declared [IMPLEMENTATION-ASSUMPTION])

| # | Question | Candidate reading | How to settle it |
|---|---|---|---|
| D1 | Which prices define d_t: raw closes, or total-return indices? | Raw prices in a common currency, as in the workbook's "LOG DEVIATIONS FROM PARITY" column | Our ingest reproduces that column from raw closes (`test_datastream_real.py`) |
| D2 | Do position returns include dividends (total return) or only price changes? | Total return: the paper collects total-return indices, and the twins' dividends are equalized | Compare both against Table IV per twin |
| D3 | Is half the spread paid only at set-up, or at exit too? Is "25 bps per transaction" per leg and per side? | Commission on every leg on entry and exit; half-spread at set-up only, as written | Sensitivity: half-spread on exit too |
| D4 | Entry timing: decision on close t-1, filled at close t? Exit too? | Both entry and exit decided on close t-1 and executed at close t | The paper's one-day-delay sensitivity (alpha 0.382) brackets it |
| D5 | Monthly return of a position: from equity, compounded to a monthly rate? How are positions shorter than 22 days converted? | Position return on initial equity, padded with the T-bill to 22 days, then converted to a monthly rate | Reproduce Table IV medians and min/max |
| D6 | Re-entry after a horizon cut-off while \|d\| is still above the buy threshold: immediately, or only after a new crossing? | Only after \|d\| falls below b and crosses it again ("crosses") | Count positions per twin against Table IV |
| D7 | A deviation already beyond b at the start of the sample: entry on the first day? | Yes, on the first available signal | Count positions |
| D8 | 136 positions in the text vs 127 in Table IV | The table is right; 136 may include the discarded open positions | Our count |
| D9 | Table II Brambles: Abs = StDev = 11.32 | Likely a typo in one column | Recompute from the workbook |
| D10 | Margin call mechanics: which prices, and is the liquidation charged costs? | Close-to-close equity check; liquidation pays the same costs | Margin-call counts in Table IV |
| D11 | Which T-bill rate pads short positions, and how are the daily excess returns in Table VI pooled across overlapping positions? | FRED 3-month T-bill at the exit date; equal-weight average of open positions' daily returns | Table VI, after Tables IV and V match |
| D12 | Which six twins have a 1:1 ratio? | The workbooks' THEORETICAL RATIO column says it | Read from the workbooks |

## Table III conventions (settled in step 15, `research/reports/dejong_table3.md`)

Each was identified by the paper's own Table III numbers. The data is never
altered; only a workbook column or the sample is chosen. The paper's text taken
literally is kept as the `as_stated` variant.

| # | Question | Answer | Tag |
|---|---|---|---|
| D13 | Direction of e.r. | B's currency per unit of A's: the negative of the workbook's log-return column | PAPER-DERIVED (identified) |
| D14 | Royal Dutch/Shell's Dutch index | CBS Allshare ex. Royal Dutch (the text says CBS Allshare) | PAPER-DERIVED (identified) |
| D15 | Dexia's regression sample | Without the return observations of 1997-12-19 and 1997-12-22 (the spike) | PAPER-DERIVED (identified) |
| D16 | Smithkline's data | "Regression data DS dates" with the Datastream FTSE Allshare (the text says a Bloomberg FTSE) | PAPER-DERIVED (identified) |
| D17 | R² and sample | Unadjusted R² (the caption says adjusted); every complete window row, leads and lags read across the window edges | PAPER-DERIVED (identified) |
| D18 | Newey-West variant | Bartlett, fixed lag floor(4 (n/100)^(2/9)), no prewhitening, n/(n-k): the EViews default. Chosen before comparing; all 48 significance marks match | IMPLEMENTATION-ASSUMPTION |

## Arbitrage conventions (step 16, `research/reports/dejong_tables45.md`)

Settings live in `conf/dejong/default.yaml`; the evidence for each is in the
report. "Identified" means the paper's Table IV-V numbers single it out.

| # | Question | Answer | Tag |
|---|---|---|---|
| D2 | Total return or price only | Total return; price only is a variant (small effect) | IMPLEMENTATION-ASSUMPTION |
| D3 | Half spread at exit too? | Yes, on both legs | PAPER-DERIVED (identified) |
| D4 | Timing | Exit signal on the first close with \|d\| <= s; both trades at the close on which the signal is observed (delay 0); delay 1 is the paper's own sensitivity case | PAPER-DERIVED (identified) |
| D5 | Short positions and the month | % per month = total return × 22 / days (days at least 22; shorter positions earn the T-bill for the rest of the month); no new position within 22 trading days of the last entry | PAPER-DERIVED (identified) |
| D6 | Re-entry | Only on a fresh crossing of b | PAPER-DERIVED (identified) |
| D7 | Deviation beyond b at the start | No entry until it crosses b (follows from D6) | PAPER-DERIVED (identified) |
| D8 | 136 vs 127 positions | Our count is 128 with Table IV's rules; 127 is the table's figure | open |
| D10 | Margin rule | Per leg (each leg against its own maintenance); pooled as a variant. Neither reproduces the margin-call counts (27 and 1 vs 14) | IMPLEMENTATION-ASSUMPTION, open |
| D11 | T-bill | FRED DTB3, the rate at the exit date | IMPLEMENTATION-ASSUMPTION |
| D19 | Currency of the leg returns | One currency (A converted into B's) | PAPER-DERIVED (identified) |
| D20 | Open positions in unified twins | Closed on the first trading day after the unification announcement, not discarded | PAPER-DERIVED (identified) |
| D21 | Interest on the short sale's margin deposit | None: it is collateral; only free cash earns 5% | PAPER-DERIVED (identified) |

## Lab rules that conflict with the paper's design (flag, do not silently change)

| Lab rule (CLAUDE.md) | Paper | Resolution proposed for step 14 |
|---|---|---|
| Costs scale with size and liquidity; a flat bps fee only as a labelled sensitivity | Flat 25 + 20 bps | Replication layer uses the paper's flat costs, labelled as the paper's convention; our layer uses the liquidity model |
| 2000+ and Rio Tinto are locked OOS | Full sample 1980-2002 in-sample | User decision: a replication that touches 2000-02 needs `+unlock_oos=true` |
| Rolling statistics are lagged; no look-ahead | Thresholds chosen in-sample; fixed parity ratios possibly from later data (cf. our audit A1 for RD/Shell 6.863) | Replication reproduces the paper as published; look-ahead is documented, not fixed, in that layer |
| Total-return P&L, next-close fills | Closing prices, previous-day signal | Same timing; D2 decides the dividend treatment |

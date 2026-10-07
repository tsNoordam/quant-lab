# Replication spec: Maymin (SILTA)

## There is no trading strategy to replicate

The paper explains why twin-share discrepancies persist. It proposes **no
trading strategy, entry/exit rule or parameters** (`research/extraction/maymin_silta.md`,
"No trading rule"). A strategy labelled "replication" would therefore contain
only invented rules, which CLAUDE.md forbids.

What the paper does contain, and what this lab replicates, is empirical:

| Paper element | Replicated in | Status |
|---|---|---|
| Price-volume regressions E4, E5 (Tables II, V, VI), Newey-West t-statistics | `quant_lab.models.silta` (Step 7) | Done on an earlier, disjoint period. H1 is not supported on our 1987-99 data: `research/reports/silta_replication.md` |
| chi > 0 condition and Table VII statistics | `quant_lab.models.silta.chi_condition` | Done; chi > 0 in value traded for both pairs |
| Calibration of eq. (1): implied p and N (Tables VII, VIII; Figures 5-10) | not implemented | Deferred: under 13% of development days lie inside the 180 bps bound (1% for Reed Elsevier) |

## What a strategy may take from the paper

These elements can be carried into a strategy as [PAPER-DERIVED] rules. Each
use is documented in the spec that uses it.

| # | Element | Page |
|---|---|---|
| R1 | The discrepancy D = ln(P1/P2) relative to theoretical parity is the arbitrageur's opportunity; he shorts the expensive class and buys the cheap one | 4-5, 13, 16 |
| R2 | The trade is worth taking when D exceeds round-turn transaction costs; 180 bps for HSBC, reused for all pairs | 12-13, 27 |
| R3 | The arbitrageur is paid when the discrepancy disappears (convergence), an event with a small daily probability p, not by mean reversion within a few weeks | 16, 22 |
| R4 | Self-imposed limits: total position at most N days of ADV (N ~ 100) and daily trading a limited share of volume (~15-20%) | 13-16, 24, 28-30 |
| R5 | Top-tier cost and financing assumptions (P9 in `research/assumptions/maymin_silta.md`) | 11-13 |

H1 (relative volume) is a contemporaneous equilibrium relation. It says which
volume pattern goes with a given discrepancy. It does not say what the
discrepancy will do next. It is not in this list. See
`research/specs/extensions/silta_parity.md`, "Relative volume".

Strategies built from R1-R5: `research/specs/extensions/silta_parity.md`.

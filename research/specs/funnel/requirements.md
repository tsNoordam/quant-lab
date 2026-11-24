# Idea funnel: requirements (project 4)

Goal: collect trading ideas from many sources and kill the bad ones fast and honestly. The
funnel is not a profit predictor. It turns an idea into a testable hypothesis, applies hard
stops in code, and records **every** idea and test, including the ones that fail, so the lab
does not build its own survivorship bias.

## Lessons this is built on (projects 1-3 and the Gotobi, London and Treasury repos)

- The bottleneck is killing ideas, not finding them. Of ten ideas tested so far, one survives
  weakly (Treasury multi-day pre-auction short). The rest failed on costs, on an effect that
  sits on a single print (FX fix, closing auction), on decay after publication, or on
  tradability.
- Rule of thumb: the gross move per trade must be at least 3x the round-trip cost. London
  would have died in an hour instead of a day.
- Testing many ideas and keeping only the winners is data mining. Everything is logged, and
  the significance bar rises with the number of tests.

## Two speeds in one repository

| Part | Purpose | Weight |
|---|---|---|
| Funnel (`quant_lab.funnel`) | intake, idea cards, hard stops, register, test budget | light: plain Python + YAML + SQLite, no DVC/MLflow/Hydra |
| Event test (`quant_lab.events`, step F3) | quick screen of effects around scheduled events | light, minutes to hours |
| Lab (existing) | full replication/backtest, audits, freeze, OOS | heavy, only for survivors |

## Register

- **Source of truth is text in git:** one Markdown idea card per idea
  (`research/funnel/ideas/<ID>.md`, YAML front matter) and one append-only event log
  (`research/funnel/log.jsonl`). Text diffs, no binary merge conflicts, full history in git.
- **SQLite is a derived index** (`.cache/funnel_index.sqlite`, git-ignored), rebuilt from the
  cards and the log for queries.
- **The card says what the idea is; the log says what happened to it.** Status and stage live
  only in the log; the current state is the last valid event.
- The log is append-only: entries are never edited or deleted. A mistake is corrected by a new
  entry.

### Card fields

Every field is `{value, label, quote, where}`. Labels:

| Label | Meaning | Requirements |
|---|---|---|
| `SOURCE` | stated in the source | `quote` (verbatim) and `where` (page/section/url) |
| `OWN-TEST` | measured by one of our own tests | `where` = report file |
| `ASSUMPTION` | our explicit assumption | `quote` = the reasoning |
| `NOT-IN-SOURCE` | the source was checked and does not give it | value empty |
| `MISSING` | not filled in yet | value empty |

Nothing is invented: a value without a label and its evidence is invalid.

### Statuses and transitions

```
inbox -> needs_info | rejected_screen | hypothesis | duplicate | parked
needs_info -> rejected_screen | hypothesis | parked | duplicate
hypothesis -> quick_test | full_research | parked | rejected_screen
quick_test -> full_research | rejected_quick | parked
full_research -> candidate | rejected_full | parked
candidate -> demo | rejected_full | parked
demo -> live | rejected_live | parked
live -> rejected_live | parked
parked -> inbox | needs_info | hypothesis
```

Stages (evidence ladder, separate from status): `phenomenon -> hypothesis ->
historical_anomaly -> robust_anomaly -> executable_edge -> live_validated`.

### Who may do what

| Actor | May |
|---|---|
| `code` (screen) | inbox/needs_info -> needs_info, rejected_screen, hypothesis |
| `judge` (AI, step F2) | fill card fields and add flags; **never change a status or stage** |
| `human` | every allowed transition; promotions past `hypothesis` need a recorded test |

Promotion guards: `-> full_research` from `quick_test` needs a `quick` test with verdict `pass`;
`-> candidate` needs a `full` pass; `-> live` needs a `demo` pass. `-> hypothesis` needs a
screen without FAIL or UNKNOWN.

**Human override.** A human may move an idea to `hypothesis` despite a failed or unknown
screen, with an explicit `override` reason in the log entry (e.g. ideas researched before the
funnel existed, or a ratio just below 3x that the user accepts knowingly). An override never
skips a required test, and every override is listed by `funnel status` and in reports.

## Hard stops (deterministic code, `quant_lab.funnel.kill`)

Each rule returns PASS, FAIL or UNKNOWN. Any FAIL rejects the idea. Any UNKNOWN keeps it in
`needs_info`. Settings live in `conf/funnel/profile.yaml`.

| Rule | PASS when | FAIL when |
|---|---|---|
| K1 rules | entry, exit and instrument are given | the source has no trading rule (`NOT-IN-SOURCE`) |
| K2 data | a data source is named and its cost is within the budget (default $50) | no data can be had, or it costs more |
| K3 tradable | the market class is one the user trades | it is not |
| K4 cost ratio | gross effect per trade >= 3x the round-trip cost | ratio below 3, or the source gives no effect size |
| K5 events | at least 10 events or trades per year (configurable) | fewer |
| K6 print | the edge does not need a fill at a benchmark print, or the user has access to that print | it needs a print the user cannot get (e.g. the WM/Reuters fix) |

If the card gives no cost, the profile's default round-trip cost for the market class is used
and reported as an assumption.

Soft flags (shown, never a stop): no evidence after publication for an idea older than 5 years;
a sample shorter than 5 years; flags from the Judge.

## Test budget (multiple testing)

- Every statistical test (`quick`, `full`, `demo`) counts; screens do not, because they do not
  look at returns.
- The t-stat a new result must beat: `max(3.0, t_bonferroni(n))`, with
  `t_bonferroni(n) = Phi^-1(1 - 0.025 / n)` for the n tests run so far.
- Full-research results also report the deflated Sharpe ratio (`quant_lab.backtest.stats`).

## User profile (answers of 2026-11-24)

- Markets: FX/CFDs via MT5, CME futures incl. micros, stocks and ETFs, crypto, Polymarket.
- Runs on Windows with uv (Python 3.12); the funnel and event test avoid heavy parts.
- The Judge runs inside Claude Code (skill/agent), no API key; an API version may follow once
  the Judge is reliable on the golden set.

## Requirements

**Must (F1-F3)**

- M1 Register: cards + append-only log + SQLite index, fixed statuses, stages and reject reasons.
- M2 Seed the register with the ideas already judged (projects 1-3, Gotobi, London, Treasury,
  the papers of the first comparison).
- M3 Card schema with labelled evidence per field; a validator that rejects invented values.
- M4 Hard stops K1-K6 in code, with tests.
- M5 Judge in two passes (neutral extraction, then adversarial review); never a profit score.
- M6 Golden set: the seeded ideas with known outcomes as a regression test for the Judge.
- M7 Manual intake: url, pdf or a loose tip.
- M8 Generic event test: calendar, windows, bid/ask costs, control days, all-days benchmark,
  permutation test, periods, cost sensitivity; adapters for Dukascopy M1 bid/ask and Databento
  bbo-1m; validated with a planted synthetic effect and a null test.
- M9 Every quick test has a written spec before it runs and is counted in the budget.
- M10 Lives next to the existing lab; the existing tests stay green.

**Should (F4)**

- S1 Paper intake (arXiv q-fin, SSRN, NBER, Fed/ECB working papers), deduplicated.
- S2 Permitted RSS/blog/Substack/GitHub feeds.
- S3 Weekly shortlist digest.
- S4 Near-duplicate clustering.
- S5 Hand-over template from a passed quick test to a lab spec.

**Could (later)**

- C1 X/Twitter with targeted queries and a small account list, within an API budget.
- C2 Vector search when the register reaches thousands of items.
- C3 Register dashboard.

**Won't**

- Reddit or unofficial scrapers.
- An LLM that predicts profit or promotes an idea.
- Automatic trading.
- Multi-agent frameworks for the funnel.

## Constraints

- No API keys, credentials or licensed data in git. Every paid download shows its cost first.
- Only permitted sources; respect rate limits and terms.
- `CLAUDE.md` rules apply: rule labels, locked OOS periods, one step at a time with the user's
  confirmation.
- Speed: an idea through the screen in minutes; a quick event test in hours, not days.

## Steps

| Step | What |
|---|---|
| F1 | Register, card schema and validator, hard stops, test budget, CLI, seeded register (this document) |
| F2 | Judge skill/agent (extraction + adversarial review) and the golden-set test |
| F3 | Generic event test, ported from the London and Treasury repositories |
| F4 | Paper intake and the weekly digest |

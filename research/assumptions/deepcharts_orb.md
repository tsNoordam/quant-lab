# Assumptions and ambiguities: the DeepCharts course's session edges

Each choice the course leaves open, and how track A fixes it. Citations as in
`research/extraction/deepcharts_orb.md`. Every resolution is an
[IMPLEMENTATION-ASSUMPTION] unless tagged otherwise, and is fixed before any
ES data is loaded.

| ID | Open point | Course | Resolution |
|---|---|---|---|
| O1 | Range window | 15 (live default), 30 (recommended), 60 min ("validation"); 5 and 10 min as aggressive variants | Grid {15, 30, 60}, all [PAPER-DERIVED]; the neighbourhood is reported, not the best cell. 5 and 10 min not tested |
| O2 | Session and clock | 09:30-16:00 ET | Exchange calendar in America/New_York, DST-aware; early closes end at the published time |
| O3 | Trigger | 5-minute candle close beyond the range | [PAPER-DERIVED]. 5-minute bars built from 1-minute bars, aligned to 09:30 |
| O4 | Entry price | at market on the close, or on a retest | At the open of the next 1-minute bar after the trigger close, plus slippage. Retest entries are not tested: whether a limit order fills cannot be known from bars |
| O5 | Volume and big-trade confirmation | rising volume, a ≥150-contract trade in the body | Not in track A (needs trades data and has no fixed threshold); track B |
| O6 | Stop | eight versions | Two: the range midpoint (F3L [23:04], [PAPER-DERIVED], needs no volume) and the opposite side of the range (conventional ORB, [EXTERNAL-RESEARCH]). POC/VAL stops need volume at price: deferred to trades data |
| O7 | Targets | proprietary IVB levels; 1:2-1:3 R; prior value area; the gap | Fixed R multiples {1, 2, 3} and none (exit at the RTH close). IVB levels by proxy only (R4, [PROPOSED-EXTENSION]) |
| O8 | Time exit | none stated | Exit at the last RTH minute's close; no overnight positions (the course trades intraday) |
| O9 | Trades per day | at most two; the opposite breakout is valid after a failure | Base case: one trade (first breakout). Variant: one re-entry in the opposite direction after a stop-out |
| O10 | Same-bar stop and target | not addressed | Stop first (conservative); count and report such bars |
| O11 | Gap reference close | last RTH trade or settlement: not said | Last RTH 1-minute close (16:00 bar; 15:59-16:00 minute); settlement as a sensitivity if available |
| O12 | Gap "fill" | full fill and midline fill | Full fill: RTH trades at or through the prior close the same session. Midline: through the midpoint. Both reported, by gap size in % of the prior close |
| O13 | "Fundamental" gaps excluded | not defined | Not applied (no news data); reported as a limitation |
| O14 | Instrument | ES, NQ; MES/MNQ for execution; levels calibrated on NQ | ES prices first; NQ as a second market only after ES is frozen (it would otherwise be a second trial on the same idea) |
| O15 | "Excursion" in C1 | not defined | The probability curve P(max favourable excursion ≥ x ticks before the RTH close) over a grid of x |
| O16 | Costs | never mentioned | Commission and fees per contract from a broker schedule chosen by the user, plus 1 tick of slippage per side (0 and 2 as sensitivities) |
| O17 | Position size | "risking 2% per trade" (C6); 0.25% (J2P [31:22]); one contract live | Results in points and R per trade, independent of size; equity curves at 1 contract MES and at fixed 1% risk as illustrations |
| O18 | Data period of the claims | "2021 till today", "decades", "20 years" | Develop on 2010-2020; 2021 onward is out-of-sample and locked (it is the period of C6) |

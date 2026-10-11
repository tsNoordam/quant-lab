# Extraction: the DeepCharts course's session edges (ORB/IB, IVB, RTH gap fill)

## Source and conventions

**Source.** The DeepCharts "Order Flow Mastery" course and its weekly live
sessions, as 177 PDFs (transcripts of the videos with screenshot markers,
plus indicator manuals) in the user's repository `tsNoordam/order-data`,
commit `ee2c839`. The material is copyrighted: it stays in that repository,
and this note paraphrases it, with at most a short phrase quoted.

**Citations** are `path [mm:ss]` in that repository, shortened as:

| Code | Path |
|---|---|
| L4, L5, L6 | `Learn/Auction Session Dynamics/4.Initial Balance Breakout`, `5.RTH Gap Fill`, `6.Orderflow Trading Model` |
| IVB | `Deep Indicators/Deep-M IVB` (manual) |
| SI | `Indicators/Session Imbalance` (manual) |
| D2L, J2L, ... | `December/Week_2/Live Charting & Q&A`, `January/Week_2/...`; L = Live Charting, P = Profile Framing, T = Deep Templates, D = Deep Live International |

**How it was read.**

- The core lessons and manuals were read in full.
- The 41 weekly sessions (about 160,000 words) were searched and read by two
  read-only `paper-reader` agents.
- Five of their citations were checked against the text and matched:
  A2L [08:22], D2L [28:06], D2L [01:26:52], A1L [45:14], A4D [01:46:01].
- `December/Week_1/Deep Template Features` was not checked.

**Tags:**

- [STATED]: said explicitly;
- [VAGUE]: said, but without a number or a definition;
- [CLAIM]: a performance or probability statement.

None of the claims comes with a sample, period, cost assumption or method.

## 1. Opening range / initial balance breakout (the "IVB" setup)

**What the course calls it.**

- The setup is the opening range breakout (ORB), credited to Toby Crabel
  (1990) (L6 [00:10]).
- DeepCharts' indicator for it is Deep-M IVB. It is called "initial volume
  breakout" (D2L [16:37]), "initial volume balance" (F3L [13:37]) and
  "initial balance" (file summaries); all mean the same.
- The breakout is presented as the only statistical part of the method;
  everything else is discretionary (D2L [01:10:07]).

**Session.** The NY cash session (RTH), 09:30-16:00 ET (D2L [18:59];
F3L [07:17]; A3L [06:06]). [STATED]

**Range window.** This is not consistent:

| Window | Where |
|---|---|
| 15 min, the live default | D2L [14:08]; F2L [19:16]; L6 [00:04] |
| 30 min, "recommended by the team"; said to have a higher win rate | IVB manual; M3L [17:37]; A2L [39:18] |
| 60 min, "the validation we've done" | A1L [45:14]; "only working on a 60 minutes timeframe" F2L [14:40]; J3L [48:03] |
| 60 min, the IB of the Deep Templates / Deep Live hosts and the Session Imbalance default | J2T [01:13:35]; A3D [01:27:49]; SI |
| 5 min, the "aggressive" variant; 10 min "early" | J2L [07:19], [05:35]; M1L [06:07]; M1L [10:26] |

The ORB anchored at 08:00 is said not to work (F3L [43:43]).

**Trigger.**

- A 5-minute candle closes beyond the range high (long) or low (short).
  [STATED] (L4 [00:53]; M1L [16:14]; A1L [06:09]; F3L [19:46])
- IVB is meant for a 5-minute close, not for 1-hour candles (A4L [43:03]).
  [STATED]
- Confirmations: rising volume [VAGUE, no threshold]; a big trade (Deep
  Trades bubble) in the candle body, not the wick [STATED]; delta in the
  direction of the break [VAGUE]. The number of confirmations required
  varies: any one of three (A5L [05:57]), two (A4L [05:06]), three to four
  (A2L [03:48]).

**Entry.** Three versions, all [STATED]:

- (a) at market on the trigger candle's close, the "mechanical" version:
  "blindly buy" a volume-confirmed break (M3L [17:37]; F3L [22:55]-[26:38]);
- (b) on the retest of the range edge only (M1L [49:47]; F1L [34:27]);
- (c) (a) plus an add on the retest (A2L [20:47]; A5L [03:17]).

Do not enter if the trigger candle closed far beyond the range (R:R too
small; M1L [01:21:17]). [VAGUE: no distance]

**Stop.** At least eight definitions:

- the range POC;
- the range midpoint;
- the session VPOC;
- VWAP;
- the value-area high or low of the range's volume profile;
- a high-volume node;
- beyond the last big trade;
- "below the fair value".

(L6 [06:09]; M1L [49:57], [50:36]; M2L [14:02]; M3L [18:18]; A1L [17:28];
A2L [21:07]; A3L [53:05]; F3L [23:04]; J3L [07:22]; A4L [05:31].)

The opposite side of the range, the conventional ORB stop, is not among
them; L6 [06:20] calls waiting for it unnecessary.

**Targets and management.**

- The IVB indicator plots a "protection level" (the highest-probability
  target of the day), an "exit average" (the second target) and an
  "extension standard deviation" (the third) (IVB manual).
- The protection level is used as the first target, a breakeven point or a
  partial exit: the sessions disagree (D2L [01:27:10]; F1L [34:47];
  J4P [33:47]).
- Other targets: 1:2-1:3 R (M1L [50:06]; A1L [07:53]); the other side of the
  prior value area (F2L [03:48]); the prior RTH close, i.e. the gap
  (F2L [21:30]).
- The level formulas are proprietary (J4P [33:20]). They are described as
  built from "years of historical data" with "neural network, machine
  learning" (L6 [08:23]; IVB manual) and also as the average favourable
  excursion of "the last few sessions" (F3L [30:17]). The levels are said to
  be calibrated on NQ even when shown on ES (D2L [26:12]). [VAGUE]

**Time exit and size.** None stated. Trade at most two breakouts a day
(D2L [52:13]). If the first breakout fails, the opposite breakout is a valid
entry (M2L [20:32]; F4L [38:25]; A5L [38:07]). One contract, or MES/MNQ, in
the live demos (F3L [22:55]; A3L [24:19]).

**Filters.** Officially none: a range/trend filter would have to be
"quantified and backtested" to be mechanical (A5L [41:34]). Discretionary
context: avoid balanced days (F4L [49:37]); prefer breaks that also leave a
multi-day balance (F3L [18:19]).

## 2. Claims about the breakout [CLAIM]

| ID | Claim | Source |
|---|---|---|
| C1 | About 70% of opening-range breakouts give "some level of excursion" | L4 [02:41]; "70 of the time" D2L [14:39] |
| C2 | After a breakout the protection level is reached 65-70% / 68-75% / "at least 60 to 70%" of the time | L6 [08:54]; J4P [33:25]; A2L [21:21]; A3L [44:39] |
| C3 | The exit average is reached in "50%, 60% of sessions" (from memory) | D2L [01:27:19] |
| C4 | Price stays inside the 15-minute range all session in about 15% of sessions | D2L [28:06] |
| C5 | A single breakout (one side only) happens in 48-49% of sessions (indicator readout) | D2L [01:26:52]; A1L [17:53]; A3L [52:22] |
| C6 | ORB "risking 2% per trade" beat buy-and-hold S&P 500 since 2021 with a better Sharpe ratio; whole flat years possible | L4 [01:51]-[02:22] |
| C7 | Outperformed the S&P 500 "over the last decades"; tested with Python, ML and genetic algorithms (screenshot only) | F3L [42:24]; A3L [06:41]; A4L [15:01] |
| C8 | The 30-minute range has a higher win rate than the 15-minute | M3L [17:37]; A2L [39:18]; "similar" F4L [40:28] |
| C9 | Breaking the 5-minute range reaches its target "maybe 60%" of the time | F4L [25:49] |
| C10 | At least one side of the 60-minute IB is taken out in about 98% of sessions | A4D [01:46:01] |
| C11 | Recent results are reported both as poor ("first breakout quite unprofitable", "failing consistently") and as excellent ("absolute fire") | M2L [14:22]; M3L [15:21]; M4L [13:17]; A3L [02:32] |
| C12 | Counterpoint from a presenter: an 80-90% win rate at 1:2-1:3 R "doesn't exist" | F2P [43:03] |

## 3. RTH gap fill

**Definition.** The gap between the previous RTH close (the last cash-session
candle) and the new RTH open; no gap if they are equal (L5 [00:08]; D2L
[12:57]; A2L [07:24]; M2L [06:27]). [STATED] Whether "close" is the last
trade or the settlement price is not said (M4L [14:43]).

**Use.**

- Mainly as an ORB target or "edge booster": the ORB "works even better"
  with a gap, and an ORB toward an unfilled gap is "the best setup"
  (A2L [08:43]; M4L [15:00]; D2L [53:00]; L5 [03:51]-[04:49]).
- As a standalone first trade of the day, a momentum scalp toward the fill
  with a quick breakeven (D2L [01:46]-[02:21]). Entry trigger, stop and
  time cut-off are not stated; no minimum gap size.
- "Fundamental" (news or weekend) gaps fill less often and are not traded
  (A2L [50:39]; J3L [02:36]). [VAGUE]

**Claims.** [CLAIM]

| ID | Claim | Source |
|---|---|---|
| G1 | Gaps are refilled 68% / "70% of the time" | L5 [00:33]; D2L [12:37] |
| G2 | Full fill 69-71% of the time; fill of the gap's midline about 80% | A2L [08:22]-[08:39] |
| G3 | About 70% on ES and NQ "over the last 20 years" (in-house research) | A2L [09:49] |

## 4. Other rules close to codeable (not tested in step 20)

- **IB extensions.** IB = 09:30-10:30; after an IB break price "tends to"
  reach the 50% projection of the IB range, then 100% (J2T [01:13:35];
  J3T [24:16]; SI). No probabilities.
- **Value-area rules.**
  - 70% of volume is inside the value area.
  - A move back inside value goes to the other side about 70% of the time
    (D2L [15:36]); "80, 70%" reversion to balance (A3L [14:41]).
  - In tension with: opening outside the prior value area means
    continuation (A3L [21:36]).
- **Day type.** First 30-60 minutes' volume 50-60% below average means a
  mean-reverting day (J4P [43:07]). A "choppy" session is under about 0.5%
  range at the open (A1L [41:52]).
- **Order-flow thresholds**, the track-B input; they vary between sessions:
  - big trade ≥150 contracts on ES (150/180/250/300 in different sessions),
    ≥60-80 on NQ;
  - stacked imbalances ≥200-400% ratio, 3-4 in a row;
  - delta above 10% of volume as "strong";
  - absorption = high effort without result, clustered within 3-5 ticks;
  - CVD not used by the ES presenter (J3L [23:54]).

## 5. What this means for track A

- The mechanical core is consistent: a 5-minute close beyond the RTH opening
  range, in its direction.
- Everything around it varies by session: the window (15/30/60), the stop
  (eight versions), the targets (proprietary) and the confirmations.
- The test therefore fixes one conventional version and a small grid around
  it (`research/methodology/deepcharts_orb.md`), and lists each choice in
  `research/assumptions/deepcharts_orb.md`.
- The probability claims C1-C5, C8-C10 and G1-G3 are reproduced as
  statistics before any trade is simulated.

# de Jong et al. (2009), Table II replication: deviations from parity (step 14)

Date: 2026-10-07.

- **Code:** `quant_lab.data.dlc` (paper-convention twin panels, DVC stage
  `dlc_ingest`) and `quant_lab.models.dejong` (MLflow experiment
  `dejong.replication`, run `table2`).
- **Data:** the 12 DLC workbooks in `data/raw/datastream_dlc/`. The paper's
  windows, 1980-2002, were approved by the user
  (`research/reports/data_decisions.md`).
- **Aggregates only** (licensed data).

Reproduce:

    uv run dvc repro dlc_ingest
    uv run python -m quant_lab.models.dejong

## 1. The panels reproduce the authors' deviation series

For each twin, the import recomputes d_t = ln(P_A / P_B) - ln(R) from the leg
prices, the workbook's FX and the theoretical ratio. It then compares the result
with the authors' "LOG DEVIATIONS FROM PARITY" column.

- **All 12 twins match on every row of the paper's window.** The largest error
  is 4.4e-16; no row was dropped.
- **Settled along the way:**
  - which legs are in pence: Shell, Unilever PLC, Reed, Allied Zurich,
    BHP Billiton PLC and Brambles PLC;
  - the common currency: leg A converted into leg B's currency;
  - the theoretical ratios, which are constant over each window (ambiguity D12):

    | Ratio | Twins |
    |---|---|
    | 1:1 | BHP Billiton, Dexia, Fortis, Merita/Nordbanken, Rio Tinto, Smithkline |
    | Other | RD/Shell 6.863, Unilever 6.67, ABB 1.563, Reed/Elsevier 1.538, Brambles 1.068, Zürich 42.928 |

## 2. Table II, ours vs the paper

All values are log deviations from parity, in percent.

| Twin (window) | Days | Mean | Mean abs | St. dev. | Min | Max | % positive |
|---|---|---|---|---|---|---|---|
| Royal Dutch/Shell (1980-01-01..2002-10-03) | 5938 | 0.86 / 0.86 | 10.04 / 10.04 | 12.71 / 12.71 | -36.22 / -36.22 | 19.83 / 19.83 | 68.5 / 68.5 |
| Unilever (1980-01-01..2002-10-03) | 5938 | 1.16 / 1.16 | 8.99 / 8.99 | 11.41 / 11.41 | -39.07 / -39.07 | 29.10 / 29.10 | 62.2 / 62.2 |
| ABB (1991-07-08..1999-01-07) | 1959 | 2.26 / 2.26 | 8.91 / 8.91 | **10.02 / 10.17** | -20.48 / -20.47 | 17.77 / 17.77 | 64.4 / 64.4 |
| Smithkline Beecham (1989-07-26..1996-01-22) | 1642 | 7.94 / 7.94 | 8.10 / 8.10 | 4.09 / 4.09 | -2.23 / -2.22 | 15.97 / 15.97 | 92.8 / 92.8 |
| Fortis (1990-12-12..2000-07-31) | 2514 | **-2.38 / -2.64** | **4.52 / 4.56** | **5.02 / 4.90** | **-17.03 / -17.10** | **13.64 / 13.79** | **31.7 / 30.5** |
| Elsevier/Reed (1993-01-01..2002-10-03) | 2545 | 2.15 / 2.15 | 8.88 / 8.88 | 9.20 / 9.20 | -14.73 / -14.73 | 17.58 / 17.58 | 55.6 / 55.6 |
| Rio Tinto (1995-12-21..2002-10-03) | 1771 | **-1.90 / 1.90** | 4.11 / 4.11 | 4.76 / 4.76 | -16.42 / -16.42 | 11.31 / 11.31 | 37.4 / 37.5 |
| Dexia (1996-11-19..1999-08-20) | 719 | **-9.40 / -9.22** | **9.47 / 9.33** | **3.56 / 3.67** | **-32.37 / -17.66** | **4.31 / 5.15** | **1.4 / 1.8** |
| Merita/Nordbanken (1997-12-15..1999-08-23) | 441 | -7.01 / -7.01 | 7.07 / 7.07 | 3.19 / 3.19 | -15.11 / -15.11 | 2.03 / 2.03 | 3.2 / 3.2 |
| Zürich Allied/Allied Zürich (1998-09-07..2000-03-20) | 401 | 11.93 / 11.93 | 11.93 / 11.93 | 3.47 / 3.47 | 1.36 / 1.36 | 21.00 / 21.00 | 100 / 100 |
| BHP Billiton (2001-06-29..2002-10-03) | 330 | 7.09 / 7.09 | 7.09 / 7.09 | 2.26 / 2.26 | 1.14 / 1.14 | 18.45 / 18.45 | 100 / 100 |
| Brambles (2001-08-07..2002-10-03) | 303 | 8.45 / 8.45 | 11.32 / 11.32 | 11.32 / 11.32 | -18.62 / -18.62 | 29.15 / 29.15 | 74.3 / 74.3 |

Each cell is ours / the paper's. Bold marks a difference beyond rounding.

**Result: 58 of 72 statistics agree** within rounding or truncation to the
printed decimals (one day either way for % positive). Nine twins match on every
statistic, apart from Rio Tinto's sign and ABB's standard deviation.

## 3. The differences

1. **Rio Tinto mean: -1.90 vs +1.90.**
   - Every other Rio statistic matches exactly.
   - Only 37.5% of days are positive, which is consistent with a negative
     mean.
   - Reading: a sign slip in the paper's table. [our reading]
2. **ABB standard deviation: 10.02 vs 10.17.**
   - Mean, mean absolute, min, max and % positive match.
   - No window change or degrees-of-freedom choice gives 10.17.
   - Reading: a reporting slip. [our reading]
3. **Dexia: every statistic differs.**
   - The workbook series has a one-day spike to -32.4% on 1997-12-19 that
     reverses the next day. The archive contains
     "Dexia outlier causes 19 December 1997".
   - The paper's minimum (-17.66%) does not contain that spike.
   - Removing the spike alone does not reproduce the paper (mean -9.37 vs
     -9.22), so the paper most likely used a cleaned or different data version.
4. **Fortis: every statistic differs, by small amounts** (mean -2.38 vs -2.64,
   % positive 31.7 vs 30.5).
   - No window choice reproduces the paper.
   - The archive mentions a 1998 equalization and share split ("Fortis
     equalization & split various media 1998").
   - Reading: the paper probably used a different data version.
5. **Truncation, not rounding:** ABB min -20.477 is printed as -20.47, and
   Smithkline min -2.226 as -2.22. Some of the paper's numbers are truncated.

The data was not adjusted to match the paper. The workbooks are immutable
inputs, and each difference is pinned by
`tests/integration/test_dejong_real.py`. Any new difference fails that test,
and so does one of these disappearing.

## 4. Consequences for the next steps

- **The replication base is solid** for 10 of 12 twins, including both of our
  original pairs.
- **Dexia and Fortis:** strategy results (Tables IV-V) can be compared with the
  paper only qualitatively.
- **The Dexia spike is a known data error** that would trigger a trade under a
  10% threshold. How the replication treats it is decided in step 16, before
  any strategy result, and reported both ways.
- **Ambiguities settled here:**
  - D1: raw prices define d_t; confirmed, since our raw-price deviation equals
    the authors' column.
  - D9: Brambles' mean absolute = standard deviation = 11.32 is real, not a
    typo.
  - D12: ratios read from the workbooks.
- **Table III** (comovement) needs the `Regression data` sheets. That is step
  15.
- **Update from step 15** (`dejong_table3.md`):
  - Fortis and Dexia reproduce Table III exactly; for Dexia this holds once the
    two spike observations are left out.
  - So their daily returns are the authors' returns, and the Table II
    differences lie in the deviation levels.

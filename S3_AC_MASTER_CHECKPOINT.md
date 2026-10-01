# SYSTEM 3 — A+C ONLY — REPRODUCIBLE MASTER CHECKPOINT

Status: ACTIVE RESEARCH MASTER after removal of Setup B.
Setup B is **REMOVED / NOT ACTIVE / SUPERSEDED** and must not be silently restored.
This checkpoint is the reconstruction source for the active System-3 research base before developing the next setup.

## 1. Required raw sources
Only these market-data sources are required by the rebuild script:
- `/mnt/data/CL-3.txt` — CL M1, New-York-local timestamps, columns `MM/DD/YYYY,HH:MM,O,H,L,C,V`.
- `/mnt/data/CL-4(6).txt` — CL M5, same timestamp convention/columns.

Run: `python /mnt/data/rebuild_s3_ac_master.py`
It rebuilds completed PW/PM 70% TPO Value Areas, daily context, causal session features, A and C, fills, fees and Golden logs.

## 2. Global execution assumptions
- Instrument: CL; price tick = 0.01; $10 per tick for one contract.
- Round-trip fee: **$7.20 per executed trade**, deducted from every trade PnL.
- Source timestamps: America/New_York. Europe/Berlin conversion is timezone/DST aware.
- Signal uses a completed M1 bar; entry is the **next M1 open**.
- No overlapping trades inside each setup: a new signal is ignored while that setup has an open position.
- No entry if the next M1 bar is at/after 20:00 Europe/Berlin.
- Open positions are force-closed at the first 20:00-Europe/Berlin bar open (or date boundary).
- Intrabar ambiguity is conservative **stop-first** if SL and TP are both touched.
- Net PnL = direction × (exit-entry) × 1000 − 7.20.

## 3. Causal NON-TREND context
Completed M5 data from 09:00–15:00 ET is aggregated into 30-minute TPO buckets. 70% TPO Value Areas are built for completed weeks/months only.
For each day, the reference open is the first M5 open in the 09:00 ET hour. Classification:
1. open > PW_VAH and PM_VAH => TB
2. open < PW_VAL and PM_VAL => TS
3. open > PM_VAH => MB
4. open < PM_VAL => MS
5. open > PW_VAH => WB
6. open < PW_VAL => WS
7. else => R

Active System-3 context = **NON-TREND only: MB, MS, WB, WS, R**. TB/TS excluded.
Because the 09:00 ET reference open must already be known, the context mask is only tradable from the 09:00 ET hour onward. No pre-09:00 use of this context is allowed.

## 4. Causal regime features
Futures session id rolls at 18:00 ET.
- ATR5 = mean range in ticks of the **five previous completed futures sessions**; current session excluded.
- Previous-session momentum = `(previous session close - previous session open) * 100`; shifted one completed session.
No year, future day outcome, later bar, or retrospective regime label is an input.

## 5. ACTIVE SETUP A — LV CONTINUATION
Session permission: **both sides of 09:30 ET** (no 09:30 filter).
- NON-TREND context.
- `100 < ATR5 <= 150` ticks.
- Berlin signal time: `10:00 <= hour < 20:00` (next-open entry must still be before 20:00).
- Lookback = previous 6 completed M1 bars.
- Candle body/range >= 0.80.
- LONG: current close > maximum high of previous 6 bars, bullish candle.
- SHORT: current close < minimum low of previous 6 bars, bearish candle.
- SL = 140 ticks; TP = 60 ticks.

Golden expectation from current raw sources:
- Trades: **619**
- Net: **+$31,683.20**
- PF: **1.2823351607**
- WR: **56.0582%**
- Trade-sequence DD: **-$7,330.40**
- Golden log SHA256: `3b5d55c7404d0e0eefa32d86cd5e773ed5187a8d9eca438c7cbb4718eceb11d6`

## 6. ACTIVE SETUP C — EXTREME-HV FAILED BREAK / FADE
Session permission: **both sides of 09:30 ET** (no 09:30 filter).
- NON-TREND context.
- `ATR5 > 200` ticks.
- Berlin signal time: `10:00 <= hour < 20:00`.
- Lookback = previous 24 completed M1 bars.
- Minimum penetration = 5 ticks beyond the prior rolling extreme.
- Candle body/range >= 0.20.
- LONG: low <= prior-24 low - 5 ticks, close reclaims above prior-24 low, bullish candle, previous-session momentum <= -30 ticks.
- SHORT: high >= prior-24 high + 5 ticks, close reclaims below prior-24 high, bearish candle, previous-session momentum >= +30 ticks.
- SL = 100 ticks; TP = 45 ticks.

Golden expectation:
- Trades: **342**
- Net: **+$19,127.60**
- PF: **1.2488110724**
- WR: **69.2982%**
- Trade-sequence DD: **-$7,654.80**
- Golden log SHA256: `a4e1bc1c54e150d7733cedd5a7ebeca2b172695db7c6d11fba44bdd5f6fc10b2`

## 7. A+C diagnostic portfolio
This is an additive daily research portfolio: setup-level overlap restrictions are enforced independently; A and C may both trade simultaneously. A future production portfolio may impose a portfolio-wide priority/overlap rule and must then be replayed separately.
- Sum of setup trades: **961**
- Net: **+$50,810.80**
- Daily-close MaxDD: **-$7,654.80**
- Worst combined day: **-$3,623.20**
- Active trading days: **691**
- Daily-PnL correlation A vs C: approximately **-0.00634**.

## 8. SETUP B — EXPLICITLY REMOVED
The former HV Compression Setup B and its post-09:30 variant are **not part of this master**.
Reason: when `entry >= 09:30 ET` is replayed causally rather than merely filtering an old trade log, previously blocked later signals become eligible and the setup deteriorates to roughly PF 1.03 / +$1.7k. It is therefore removed as economically immaterial and must not be counted in A+C metrics.
Old B files may remain on disk only as historical research artifacts; they are not authoritative.

## 9. Authoritative files for this checkpoint
- `S3_AC_MASTER_CHECKPOINT.md` — this specification.
- `rebuild_s3_ac_master.py` — standalone rebuild from raw CL-3 + CL-4(6).
- `S3_AC_MASTER_METRICS.json` — machine-readable expected metrics.
- `S3_MASTER_A_LV_CONT_GOLDEN_TRADES.csv` — A Golden log.
- `S3_MASTER_C_HV200_FADE_GOLDEN_TRADES.csv` — C Golden log.
- `S3_AC_MASTER_SHA256SUMS.txt` — integrity hashes.

A new chat must reproduce the Golden logs and compare hashes/metrics before modifying A or C. New setup development should start from this A+C-only base, not from the superseded A+B+C master.

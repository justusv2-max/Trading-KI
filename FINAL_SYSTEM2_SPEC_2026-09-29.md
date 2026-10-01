# CL/WTI SYSTEM 2 — FINAL FROZEN REFERENCE

Freeze date: 2026-09-29 Status: FINAL / FROZEN Purpose: sole reference
for later Railway/live implementation. System 1 is NOT part of this
reference. Level-BOS is EXCLUDED.

## Verified final result

Period in final trade log: 2016-02-02 through 2026-09-22 Trades: 6,542
Net PnL: +\$120,787.60 Win rate: 61.8771% Profit factor: 1.40196
Trade-sequence MaxDD: -\$2,532.00 Commission: \$7.20 round-trip per
executed trade Contract: 1 CL Tick size: \$0.01 Tick value: \$10

HV-1: 2,553 trades \| +\$59,318.40 \| WR 60.2037% HV-2: 483 trades \|
+\$11,852.40 \| WR 60.4555% LV-1: 2,174 trades \| +\$30,027.20 \| WR
63.1095% LV-2: 787 trades \| +\$6,433.60 \| WR 59.4663% LV-3: 545 trades
\| +\$13,156.00 \| WR 69.5413%

## Final global rules

- Monday-Friday allowed. Older Monday blocking is superseded.
- No new entries at or after 20:00 Europe/Berlin.
- All open positions flat no later than 20:00 Europe/Berlin.
- No overnight.
- Europe/Berlin DST handled timezone-aware.
- Only completed bars may generate signals/context.
- M1 execution/fill sequencing.
- Level-BOS excluded.
- RANGE context not traded.
- \$7.20 commission per executed round trip.
- Cancelled/unfilled orders are not trades.
- Fill-bar blow-through of stop = stop, never skip.
- Conservative stop-first handling when intrabar order is ambiguous.
- De-dup: max one executed trade per \$0.50 bucket/session/subsystem.
- LV-2 additionally max one trade/session.

## Volatility regime

ATR5 = prior five completed session ranges in ticks:
daily_range_ticks.shift(1).rolling(5).mean() Current day excluded. ATR5
\> 150T = HV. ATR5 \<= 150T = LV.

## Context

70% TPO Value Area on M30. Previous-week VAH/VAL and previous-month
VAH/VAL. Reference session open = 09:00 ET M1 open.

Priority: 1. open \> PW_VAH and PM_VAH =\> TREND_BULL 2. open \< PW_VAL
and PM_VAL =\> TREND_BEAR 3. open \> PM_VAH =\> MONTHLY_BULL 4. open \<
PM_VAL =\> MONTHLY_BEAR 5. open \> PW_VAH =\> WEEKLY_BULL 6. open \<
PW_VAL =\> WEEKLY_BEAR 7. otherwise RANGE

Bull: TREND_BULL, WEEKLY_BULL, MONTHLY_BULL Bear: TREND_BEAR,
WEEKLY_BEAR, MONTHLY_BEAR

The authoritative final log uses the independently raw-derived context
methodology. Do not silently substitute an older context_new.csv and
call it the same final reference.

## Round-number grid

Step \$0.50. Radius +/-\$5 around session open. Base = nearest \$0.50 to
session open. 21 levels. De-dup bucket = round(zone \* 2) / 2.

## HV-1

Regime HV; all directional contexts. 15T stop / 15T target. 80 M1 bars
max limit wait. 10T bounce.

Completed bar i-1: BULL: Low\<=RN, Close\>RN, Close\>Open,
(High-RN)/0.01 \>=10. BEAR: High\>=RN, Close\<RN, Close\<Open,
(RN-Low)/0.01 \>=10. Limit at RN from bar i.

## HV-2

Regime HV; all directional contexts. 15T stop / 15T target. 80 M1 bars
max limit wait. 4T confirmation bounce.

Using completed bars only, bar i-1 creates a new running session
extreme. BULL: new session high; zone=High\[i-1\]. Confirmation bar i:
Low\<=zone, Close\>zone, Close\>Open, (High-zone)/0.01\>=4. BEAR: new
session low; zone=Low\[i-1\]. Confirmation bar i: High\>=zone,
Close\<zone, Close\<Open, (zone-Low)/0.01\>=4. Limit at zone from bar
i+1.

## LV-1

Regime LV; all directional contexts. 8T stop / 8T target. 80 M1 bars max
limit wait. 5T bounce. Same structure as HV-1 with 5T threshold and 8/8
risk/reward. Limit at RN from bar i.

## LV-2

Regime LV; all directional contexts. 8T stop / 8T target. 80 M1 bars max
limit wait. Cumulative bounce \>=8T. Max one LV-2 trade/session.

Rolling levels use only M30 bars completed before current M1 bar:
roll_vah=max High of completed current-session M30 bars. roll_val=min
Low of completed current-session M30 bars.

BULL: zone=roll_val; completed i-1 has Low\<=zone, Close\>zone,
Close\>Open. BEAR: zone=roll_vah; completed i-1 has High\>=zone,
Close\<zone, Close\<Open. Track maximum favorable bounce after
activation. When \>=8T, limit is eligible at zone.

## LV-3

Regime LV; all directional contexts. 8T stop / 8T target. 80 M1 bars max
limit wait. NO bounce threshold.

Bar i-1 creates a new running session extreme. BULL: new session high;
zone=High\[i-1\]. Confirmation i: Low\<=zone, Close\>zone, Close\>Open.
BEAR: new session low; zone=Low\[i-1\]. Confirmation i: High\>=zone,
Close\<zone, Close\<Open. Limit at zone from bar i+1.

## Fill/PnL

Long stop=zone-risk*0.01; target=zone+reward*0.01. Short
stop=zone+risk*0.01; target=zone-reward*0.01. Win PnL =
reward_ticks*\$10 - \$7.20. Loss PnL = -risk_ticks*\$10 - \$7.20. Never
multiply tick PnL by tick size again. Unfilled after 80 M1 bars or final
cutoff =\> cancel. Open positions forced flat at 20:00 Europe/Berlin.

## Frozen files

streaming_final_s2_rawctx.csv = authoritative 6,542-trade golden log.
context_raw_comparison.csv = raw-context audit material.
CL_unified_system_REFERENCE_ONLY.py = historical detailed setup source.
WARNING: the reference-only Python source still contains older Monday
blocking and BOS. It is not the final Railway executable. This
FINAL_SYSTEM2_SPEC and the authoritative trade log supersede conflicts.

## Railway acceptance test

A future implementation must: 1. Contain only HV-1/HV-2/LV-1/LV-2/LV-3.
2. Exclude BOS. 3. Allow Monday-Friday. 4. Enforce timezone-aware 20:00
Europe/Berlin no-entry/forced-flat. 5. Use \$10/tick and \$7.20
round-trip. 6. Have no current/future-bar leakage. 7. Use only completed
M30 bars for rolling levels. 8. Preserve de-dup/state correctly in
streaming operation. 9. Reproduce the frozen historical reference under
the final-data methodology. 10. Investigate any deviation rather than
silently accepting it.

END OF FINAL FROZEN SYSTEM 2 REFERENCE.

# APEX WEEKEND LIVE CHECKPOINT — 2026-10-03

## Live input
TradingView live strategy feed is M1 only. M5 live webhook is not required and does not drive strategy execution. The engine causally aggregates M30/session context from completed M1 bars. Historical M5 is used only before the first M1 bootstrap bar for warm-up.

## Updated bootstrap data
M1: 20,639 bars, 2026-09-13 18:00 ET through 2026-10-02 16:59 ET.
M5: 19,298 bars, 2026-06-26 12:20 ET through 2026-10-02 16:55 ET.
M5 warm-up bars before first M1: 15,158.
Seed completed sessions: 20.
Seed SHA256: d52b284a943a64c564902c0c8b43bccdb69815df5d3a1c575285487d4d445d28.

## APEX protection phase
TRADING_MODE=APEX.
Preventive budget $825. Max 9 approved entries/day. Entry allowed only when realized day PnL minus setup reserved worst-case risk is >= -$825. Risk map remains frozen setup risk including $7.20 commission. No entry >=20:00 Europe/Berlin and forced flat by 20:00.
This $825 gate is preventive, not a guaranteed hard realized daily stop because overlapping/open risk can make final daily PnL worse. Operational target accepted by user: occasional ~-$1,050 is acceptable; no day <=-$1,400 desired.

## Updated-data replay
Using the exact engine in this package after historical M5 warm-up and then all updated M1 bars:
- approved entries: 88
- closed paper trades: 88
- net: +$2,716.40
- wins/losses: 57/31
- win rate: 64.7727%
- PF: 1.47463
- Daily-Close MaxDD: -$1,207.60
- worst day: -$1,007.20
- best day: +$985.20
- risk blocks: 79
- approved setup counts: HV-1 49, HV-2 37, S3-C 2
- S3-D: 23 raw signals, 0 approved, 23 risk-blocked
- no observed day <= -$1,400 in this updated sample.

## Telegram behavior
Telegram sends approved S2 fills, approved S3 paper entries, paper exits, and risk blocks. Raw S3_SIGNAL and unfilled S2_LIMIT are not sent, preventing a blocked raw signal from looking like an executable Apex trade.

## Later relaxation
Do not remove the APEX throttles automatically. When account buffer is sufficiently positive, re-test a relaxed configuration and deploy only after explicit user approval.

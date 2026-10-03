# CURRENT LIVE OVERRIDE — 2026-10-03
Read APEX_WEEKEND_2026_10_03_CHECKPOINT.md first. Current live input is M1-only; M5 live webhook is not required. Current APEX protection uses the $825 preventive gate and max 9 approved entries/day.

# START HERE — AUTHORITATIVE RECOVERY POINT

Frozen live/recovery point: 2026-10-01.

## Purpose
This repository is the authoritative Railway + TradingView signal/paper implementation of the frozen CL master. Do not redesign strategy rules from memory. The code and reference files in this repo are authoritative.

## Modes
- `TRADING_MODE=APEX`: APEX Dynamic V1 risk layer enabled.
- `TRADING_MODE=EK`: original S2 + S3 A/B/C/D master without Apex risk gates.

## Frozen historical references
### EK master
- 8,342 trades
- net +225,467.58821258627 USD
- Daily-Close MaxDD -6,777.206408691418 USD
- 11/11 positive years
- See `reference/ek/` and `reference/S2_S3_ABCD_COMBINED_MASTER_CHECKPOINT.md`.

### APEX Dynamic V1
- 7,067 executed trades
- 1,275 blocked trades
- net +156,807.6009918219 USD
- EOD/Daily-Close MaxDD -2,497.199084472668 USD
- worst day -1,178.80 USD
- 0 days <= -1,400 USD
- 11/11 positive years
- See `reference/apex/`.

APEX exact gate:
1. At start of NY trade date, compute prior Daily-Close DD.
2. Base preventive budget = 1200 USD.
3. If start-day DD <= -1000: subtract 200.
4. If start-day DD <= -1800: subtract another 450.
5. Intraday effective budget = min(adjusted_base + 0.60*max(realized_day_pnl,0), 1400).
6. Before a trade: require realized_day_pnl - setup_reserved_risk >= -effective_budget.
7. Max 9 executed trades per NY trade date.
8. Risk map: S2_HV-1 157.2; S2_HV-2 157.2; S2_LV-1 87.2; S2_LV-2 87.2; S2_LV-3 87.2; S3_A 1827.2; S3_B 807.2; S3_C 1007.2; S3_D 1407.2.
9. Source trade PnL already includes 7.20 USD round-trip fee; never deduct twice.

## Market/execution invariants
- CL tick size 0.01; tick value 10 USD for 1 CL.
- Completed bars only; no lookahead.
- No new entries at/after 20:00 Europe/Berlin; force-flat by 20:00 Europe/Berlin; no overnight.
- Stop-first if SL and TP are touched in same bar.
- S3 signals on completed M1 and entry on next M1 open.
- Preserve exact S2 rules in `reference/FINAL_SYSTEM2_SPEC_2026-09-29.md`.
- Do not replace M1/M30 calculations with M5 merely because M5 history is longer. Bootstrap M5 may only provide mathematically equivalent historical context.

## Current TradingView bootstrap
Raw current exports are retained in `bootstrap_data/` and duplicated at repository root with explicit dates. The generated `seed_state.pkl` is a derived artifact. Market history warms filters only; it must not fabricate historical account PnL/open positions when starting a fresh live account.

## Live architecture
TradingView closed M1/M5 bars -> `/tv` Railway endpoint -> persistent server state -> exact strategy engine -> APEX or EK gate -> Telegram/paper signal. Broker auto-execution is NOT enabled in this frozen version.

## Reproduction order for a new chat
1. Read this file.
2. Read `DUAL_MODE_SPEC.md`, `TRADINGVIEW_SETUP.md`, `LIVE_STATUS_2026-10-01.md`.
3. Verify `REPOSITORY_SHA256SUMS.txt`.
4. Run `pytest -q`.
5. Run `python verify_reference.py`.
6. If rebuilding bootstrap state, use the raw CSVs and `bootstrap_current.py`; compare metadata/hash before deployment.
7. Never change strategy logic to make live data convenient. If parity fails, stop and diagnose.

## Known scope
This is a signal/Telegram/paper-reconciliation server. Historical APEX EOD DD is authoritative for the stated Apex criterion. It is not a broker auto-execution implementation.

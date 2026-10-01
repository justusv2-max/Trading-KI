# CL Railway Live Status — 2026-10-01

Frozen strategy logic: S2 + S3 A/B/C/D, dual mode APEX Dynamic v1 / EK unrestricted.

## Current bootstrap
- TradingView M1 source: 2026-09-06 18:00 ET through 2026-10-01 13:33 ET, 25,784 bars.
- TradingView M5 source: 2026-06-18 18:00 ET through 2026-10-01 13:30 ET, 20,533 bars.
- Historical M5 used only before first M1: 15,360 bars.
- M1 is authoritative once available and for live strategy evaluation.
- M5 live webhook is audit/heartbeat only; no strategy timeframe is changed.
- Seed market state has 20 completed rolling sessions.
- Account/risk execution state is reset to zero for a fresh live start; historical warm-up does not create fictional account PnL or positions.

## TradingView contract
TradingView sends a webhook only on confirmed M1/M5 bar close. Payload contains bar-open timestamp in UTC plus OHLCV. Railway stores/uses the completed bar. `/tv` accepts JSON secret because TradingView alerts do not rely on a custom auth header.

## Persistence
Use Railway persistent volume mounted at `/data`, with `STATE_DB=/data/master.sqlite3`. SQLite state survives restarts. Seed state is used only when the persistent DB has no saved engine state.

## Modes
- APEX: Dynamic v1 preventive risk manager.
- EK: no Apex daily/DD/trade-count risk gate; frozen underlying strategy logic remains unchanged.

## Acceptance tests
- Python compile: PASS.
- Existing unit tests: 4/4 PASS.
- `/health` from seed: ready=true, last bar 2026-10-01 13:33 ET.
- `/tv` M5 acceptance: PASS.
- `/tv` M1 ingestion: PASS.
- duplicate event idempotency: PASS.
- bad secret rejection: PASS (401).

## Scope
This package is signal/paper-reconciliation infrastructure. It does not submit broker orders. Telegram delivery is optional via environment variables.

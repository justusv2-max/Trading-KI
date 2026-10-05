# CL Railway / ATAS — Apex EOD Multi-Account Server V3

This build is intended for the same S2 + S3 A/B/C/D strategy master, with the frozen $1,400 nominal strategy gate + max 9 trades/day, plus account-aware Apex EOD safety.

## For the requested setup
Run one ATAS strategy instance per account:
- each 50K evaluation: `AccountProfile = 50K_EOD_EVAL`
- the 100K evaluation: `AccountProfile = 100K_EOD_EVAL`
- set `ApexVendor` to the account's actual vendor (`RITHMIC`, `WEALTHCHARTS`, or `TRADOVATE`)
- keep Quantity = 1 CL (hard-coded in bridge)
- keep each account ID in that instance's `AllowedAccounts`

Two 50K accounts remain independent because the server stores risk state by `account_id`.

## What changed versus Bridge V2 / old server
1. `/bridge/status` is account-aware (`account_id`, `profile`, `vendor`).
2. The bridge reports actual ENTRY / EXIT / CANCEL fills to `/bridge/execution`.
3. Each account has separate balance, EOD threshold, DLL, daily realized PnL, daily entry count, reservations and open stop-risk.
4. New entries are blocked if worst-case stop exposure would touch the account DLL or active EOD threshold.
5. Execution reports are idempotent, so retrying cannot double-book PnL.
6. Bridge retries execution sync 3 times; after persistent failure it fails closed for new entries until restart. Existing broker brackets remain active.
7. Frozen strategy protection remains: $1,400 nominal gate + max 9/day.

## Important 50K consequence
The 50K EOD evaluation DLL is $1,000. The server reserves stop risk INCLUDING $7.20 commission.
Therefore from a flat day:
- S3-B: $807.20 -> can pass the DLL gate.
- S3-C: $1,007.20 -> blocked by the 50K DLL preventive gate.
- S3-A / S3-D: $1,407.20 -> blocked by the 50K DLL preventive gate.
S2 trades remain possible subject to aggregate reserved/open exposure.

The 100K evaluation DLL is $1,500, so A/D at $1,407.20 can pass the Apex-DLL layer when other exposure/day loss leaves enough room. The strategy's own $1,400 nominal gate still applies.

## Railway deploy files
Deploy:
- `server.py`
- `engine.py`
- `requirements.txt`
- `Procfile`

Railway environment remains:
- `TRADING_MODE=APEX`
- `WEBHOOK_SECRET=<existing secret>`
- `STATE_DB=/data/master.sqlite3`
- optional Telegram variables
- optional `APEX_SAFETY_BUFFER=0` (default 0; set a positive dollar buffer if desired)

## ATAS bridge
Compile `ApexRailwayBridgeV3Eod.cs` using `ApexRailwayBridge.csproj` on the Windows machine with ATAS installed, then replace/add the strategy DLL and restart ATAS.

The server cannot be safely used with the old V2 bridge for these new account-specific rules because V2 does not send account/profile/fill synchronization.

## Tests
Run:
`python test_server_rules.py`

Expected two PASS lines. Also check `/health` and each account's `/account/risk` before arming live trading.

## Scope
The preventive server model tracks actual strategy fills reported by the bridge. Manual trades, external position changes, payouts, or missed execution reports can make server state differ from the Apex account. Do not mix manual trading into these accounts without reconciling/resetting server state.

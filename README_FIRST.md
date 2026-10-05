# Railway V3 EOD — complete ready-to-upload package

This package is built to be extracted and uploaded at the repository root.

## What is preloaded
- `seed_state.pkl` was rebuilt from the included current TradingView CSV files.
- M5 is used only as causal context warm-up **before the first M1 row**.
- From the first M1 row onward, the engine itself aggregates completed M1 into M30 and therefore builds TPO/value-area, weekly/monthly context and S2 ATR state from the M1 stream.
- The seed contains no open paper position at the CSV end. Historical `s3_pending` is deliberately cleared so deployment cannot fire an old market command.

## Persistent Railway volume behavior
`server.py` automatically migrates older pickled engine states. If the packaged seed has a newer `last_bar` than the persistent engine state, it automatically replaces **only the strategy engine state** with the packaged seed. Account/fill tables are not deleted. After live data advances beyond the seed, the database state remains authoritative.

Duplicate/stale TradingView M1 bars at or before `last_bar` are acknowledged with HTTP 200 (`STALE_OR_DUPLICATE`) instead of causing TradingView delivery errors.

## Upload
Upload/extract all files at the GitHub repository root, commit, and let Railway redeploy. Keep your existing Railway environment variables, especially `WEBHOOK_SECRET`, `STATE_DB`/volume settings, and `TRADING_MODE`.

TradingView webhook remains:
`https://web-production-9acfcd.up.railway.app/tv`

After deploy check `/health`. `last_bar` and `seed_last_bar` should initially match the seed. When a new M1 arrives, `last_bar` must advance beyond `seed_last_bar`.

The ATAS bridge source is included for completeness but is not required by Railway itself.

# Railway CL Signal Server — S2 + S3 A/B/C/D — 2026-09-30 Master

This package implements the frozen research master as a **signal-only + paper/reconciliation server**. It does not send broker orders.

## Frozen strategy source
- S2: HV-1, HV-2, LV-1, LV-2, LV-3 only. No BOS. Monday-Friday. Exact final rules are in `reference/FINAL_SYSTEM2_SPEC_2026-09-29.md`.
- S3 A: LV continuation, ATR5 (100,150], LB6 breakout, body>=0.80, SL140/TP60.
- S3 B: quality momentum continuation, ATR5 (150,200], abs(prev-session momentum)<40, LB6 momentum >=12T, body>=0.50, SL80/TP25.
- S3 C: failed-break fade, ATR5>200, prior-24 extreme +5T penetration/reclaim, body>=0.20, prev-session momentum opposite >=30T, SL100/TP45.
- S3 D: extreme-HV continuation, ATR5>400, LB4 momentum >=20T, body>=0.80, prev-session momentum aligned >=60T, SL140/TP45.
- S3 only trades NON-TREND context: MONTHLY/WEEKLY BULL/BEAR or RANGE; TB/TS excluded.
- CL tick 0.01 = $10, research fee $7.20 round trip. Completed-bar signals only. Next-M1-open entry for S3. Europe/Berlin DST-aware no entry >=20:00 and no overnight inherited from master.

## Important live-feed contract
`POST /bar` accepts **completed M1 CL bars in strict chronological order**, with an offset-aware timestamp. The engine reconstructs CL 18:00 ET futures-session ATR5/previous-session momentum, 09:00 ET reference-open context, completed M30 rolling levels, and completed week/month 70% TPO value areas.

A new deployment has no history. Bootstrap it with enough chronological M1 history to cover at least the previous completed calendar month/week and >=5 completed futures sessions. `GET /health` stays `ready:false` until >=5 sessions exist; operationally you should bootstrap more history so PW/PM context is also available. `/bootstrap` deliberately suppresses Telegram output and replaces state from scratch.

### POST /bootstrap
Header `X-Webhook-Secret: ...`
```json
{"bars":[{"event_id":"hist-1","timestamp":"2026-09-01T09:00:00-04:00","open":70.0,"high":70.1,"low":69.9,"close":70.05}]}
```
Use a chronological list. For large histories, send a purpose-built adapter or pre-seed the state DB; do not repeatedly reset between chunks.

### POST /bar
```json
{"event_id":"cl-2026-09-30T09:31-04:00","timestamp":"2026-09-30T09:31:00-04:00","open":70.00,"high":70.10,"low":69.95,"close":70.07,"volume":1234}
```
Header: `X-Webhook-Secret`.

Responses contain `events` such as `S2_LIMIT`, `S2_FILL`, `S3_SIGNAL`, `S3_PAPER_ENTRY`, `PAPER_EXIT`. `S3_SIGNAL` means entry at the **next M1 open**; it is emitted immediately after the completed signal bar is received.

## Railway deployment
1. Create a Railway service from this folder/repository.
2. Add a persistent volume mounted at `/data`.
3. Variables:
   - `WEBHOOK_SECRET` = long random secret (required in production)
   - `STATE_DB=/data/master.sqlite3`
   - optional `TELEGRAM_BOT_TOKEN`
   - optional `TELEGRAM_CHAT_ID`
4. Deploy. `railway.json`/`Procfile` start Uvicorn.
5. Bootstrap historical M1 data, then check `/health` and `/state`.
6. Point the live M1 feed to `/bar`.

## Safety / integrity
- Event IDs are idempotent in SQLite.
- Bars must be strictly increasing and valid OHLC.
- State persists after every accepted live bar.
- Old CP017/BOS/old-S3 rules are NOT strategy sources for this package.
- The `reference/` folder contains the frozen specifications, golden logs, metrics and hashes needed by another ChatGPT session to identify the exact research master.

## Acceptance boundary
The combined historical master is 8,342 trades, +$225,467.59 net, aggregate PF 1.365348, Daily-Close MaxDD -$6,777.21, 11/11 positive years, 109/128 positive months. Those are research/golden-log metrics, not a promise of live results.

The frozen S2 golden log does not contain exact exit timestamps, so the combined authoritative risk statistic is Daily-Close DD, not a fabricated portfolio intraday DD. Before broker auto-execution, run a full raw-data streaming replay and reconcile generated signals/fills against the frozen logs; investigate every mismatch.

## FINAL DUAL-MODE OVERLAY (2026-09-30)
This package supersedes the earlier single-mode Railway package for deployment.
Use `TRADING_MODE=APEX` for Apex Dynamic v1. Use `TRADING_MODE=EK` for the unrestricted frozen S2+S3 A/B/C/D master. See `DUAL_MODE_SPEC.md` and `MODE_SWITCH.md`.
The complete Apex and EK historical references are under `reference/apex` and `reference/ek`.

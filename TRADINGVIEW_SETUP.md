# TradingView -> Railway setup

Create two TradingView alerts on NYMEX:CL1! using `tradingview_cl_bar_sender.pine`:

1. Chart timeframe **1 minute**. Condition: `Any alert() function call`. Frequency: once per bar close.
2. Chart timeframe **5 minutes**. Same condition/frequency.
3. Webhook URL for both: `https://YOUR-RAILWAY-DOMAIN/tv`
4. Set the Pine `Webhook secret` input equal to Railway variable `WEBHOOK_SECRET`.

M1 is authoritative for live strategy evaluation. M5 is persisted as an audit/heartbeat stream. Historical M5 is used only before the first available M1 bar to warm session/M30/week/month context. Strategy rules are not changed to M5.

The timestamp sent is the TradingView bar OPEN timestamp in UTC. The alert itself fires only after the bar is confirmed/closed. This matches the engine convention: completed bar data, timestamped by bar start.

Railway variables:
- `TRADING_MODE=APEX` for Dynamic v1.
- `TRADING_MODE=EK` for unrestricted S2+S3 A/B/C/D.
- `WEBHOOK_SECRET=<long random value>`.
- `STATE_DB=/data/master.sqlite3` and attach a Railway persistent volume at `/data`.
- Optional Telegram: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.

Never use `CHANGE_ME` in production.

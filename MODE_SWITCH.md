# Switching modes on Railway
For Apex: set `TRADING_MODE=APEX` and redeploy/restart.
For own-capital/unrestricted master: set `TRADING_MODE=EK` and redeploy/restart.
Check `/health`; field `mode` must match the intended mode before feeding live bars.
Because mode is applied from the environment on every state load, stale persisted state cannot silently change the selected mode. For a clean account/mode transition, use the authenticated `/reset` then `/bootstrap` historical bars before live feed.

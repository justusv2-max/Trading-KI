# APEX PROTECTION PHASE — $825

Live input: TradingView M1 only. M5 live webhook is not required. Historical M5 is used only before the first M1 bootstrap bar to warm session/M30/week/month context. From first M1 onward all live strategy state is driven by completed M1 bars.

Risk protection while account buffer is small:
- TRADING_MODE=APEX
- preventive risk budget: $825
- max 9 approved entries/day
- before entry: realized day PnL - setup reserved worst-case risk >= -$825
- setup risk includes $7.20 round-trip commission
- no new entries >=20:00 Europe/Berlin; hard flat by 20:00
- $7.20 fee included in paper PnL

Historical APEX-$825 checkpoint on 8,342 source trades: 6,982 executed, +$145,079.59 net, daily-close MaxDD -$2,397.59, worst day -$814.80, 0 days <= -$1,400. The short recent replay previously showed that overlapping/open risk can make a realized day somewhat worse than -$825; $825 is a preventive gate, not a guaranteed hard daily loss. User accepts occasional ~-$1,050 days; target is no day at or below -$1,400.

Later, when account equity has a sufficient buffer, trade throttling/risk restrictions may be relaxed only after a new backtest and explicit deployment.

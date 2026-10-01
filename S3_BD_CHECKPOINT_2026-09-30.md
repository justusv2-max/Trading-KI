# S3 B+D research checkpoint — 2026-09-30

Status: reproducible research checkpoint. A and C remain frozen by S3_AC_MASTER_CHECKPOINT.md. B and D are current candidates, not yet final live portfolio.

## Raw data (authoritative)
- CL-3.txt SHA256 692cffe704387037db8219423eb79f49358ec570616a4f9817f032b505991456
- CL-4(6).txt SHA256 79d1e1f3b6dd30509b90cf0733c12d7996356893cd17b21fa63cc13a0d57d026
- S3_FEATURE_CACHE.npz SHA256 fbd257fc9c2871815aa4d552998a466fc83730efc9bc95450eb4483d5a299a77

## Shared causal execution
NON-TREND only (MB/MS/WB/WS/RANGE), TB/TS excluded. Daily context only after 09:00 ET reference open is known. ATR5 = previous 5 completed futures sessions; current session excluded. Previous-session momentum is shifted. Signal uses completed M1 bar; entry next M1 open. Berlin DST via Europe/Berlin; bh>=10 and bh<20; no entry >=20:00 Berlin; force flat at 20:00; stop-first if SL and TP touched same bar. CL 0.01=$10; fee $7.20/trade. Within each setup trades do not overlap; next signal may execute only after prior trade exits.

## Candidate B — quality momentum continuation
Regime: 150 < ATR5 <= 200 ticks. Previous-session momentum weak: abs(pmom) < 40 ticks. Momentum lookback 6 completed M1 bars: close[t-1]-close[t-7]. Long if momentum >= +12 ticks AND signal candle bullish AND body/range >=0.50. Short symmetric <=-12. SL80 ticks; TP25 ticks.
Result 2016-2026 development sample: 579 trades; +$26,301.18 net; PF 1.374428; daily-close DD -$2,500.40; worst day -$1,488.80; 9 positive active years out of 10 (2022 no trades; 2026 -$964.81).
Golden log: S3_B_QUALITY_GOLDEN_TRADES.csv SHA256 8106ce206422bb68270aadc1495e044dd3d447f5855e2d5cd970707d21937635.
Fine grid: S3_B_QUALITY_FINE_RESULTS.csv SHA256 8e0c2d20bd92496a557ea915b100aa862e9a88a5033f2cace14678622355ce2e. Neighborhood includes weak30/40, body40-60%, nearby exits; selected point improves portfolio rather than maximizing standalone net.

## Candidate D — extreme-HV continuation
Regime ATR5 >400 ticks. Momentum LB4 completed bars: close[t-1]-close[t-5]. Long momentum >=+20, bullish signal candle, body/range>=0.80, previous-session momentum >=+60; short symmetric. SL140; TP45.
Result: 260 trades; +$27,568.01 net; PF1.481147; daily-close DD -$5,024.81 (trade-sequence DD in earlier checkpoint approx -$5,232.80); worst day -$3,101.61; 6/6 active years positive.
Golden log: S3_D_EXTREME_HV_GOLDEN_TRADES.csv SHA256 55443790041afa23c5b70bdd4bb4ec5f4089d42b2c32fcc2a72df1f287fdfce9.
Fine grid: S3_D_FINE_RESULTS.csv SHA256 f68b0660f2cb12e120e936e45e816533b9aedfe58dfc09a8ec79d477acf79a6c.

## Additive diagnostic A+B+C+D
This is a daily-PnL additive diagnostic, NOT yet a single-account conflict/priority replay across simultaneous setup positions.
1800 setup-trades; +$104,679.99; PF1.330602; daily-close MaxDD -$6,602.01; worst day -$3,101.61; 10/11 calendar years positive. Only 2016 negative (-$865.61). A+C+D without B: +$78,378.81 and DD -$7,612.00, so selected B improves DD by about $1,010 while adding ~$26.3k.

## Reproduction files
- A/C: rebuild_s3_ac_master.py + S3_AC_MASTER_CHECKPOINT.md
- B fine search: opt_b_quality_fine.py
- B/D portfolio diagnostic and exact execution helper: compare_b_portfolio.py
- Freeze/export: freeze_bd_checkpoint.py
- Machine metrics: S3_BD_CURRENT_METRICS.json

Next required step before final freeze: optimize B/D only if neighborhood robustness and portfolio DD improve; then run a chronological single-account portfolio replay with explicit simultaneous-signal priority / overlap policy. Do not call additive diagnostic the final live portfolio.

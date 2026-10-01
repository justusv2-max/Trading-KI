# CL Railway Dual Mode — FINAL 2026-09-30

## Mode selection
Set exactly one Railway environment variable and redeploy/restart:
- `TRADING_MODE=APEX`: Apex Dynamic v1 risk overlay is active.
- `TRADING_MODE=EK`: no Apex portfolio risk gate; original frozen S2 + S3 A/B/C/D master signals are allowed.
Changing mode does NOT change setup definitions.

## APEX Dynamic v1
1 CL only; no fractional sizing. Day key is New York calendar date, matching the historical combined master `date` field. Europe/Berlin 20:00 no-entry/forced-flat remains unchanged.
At start of day compute prior daily-close drawdown = cumulative closed PnL - running peak.
Base budget = $1200. If start-day DD <= -$1000 subtract $200. If start-day DD <= -$1800 subtract an additional $450.
During day: effective budget = min(adjusted base + 0.60 * max(realized day PnL, 0), $1400).
Before every actual entry/fill reserve setup risk. Permit only if realized day PnL - reserved risk >= -effective budget. Maximum 9 executed trades per day.
Reserved risks: S2 HV-1/HV-2 $157.20; S2 LV-1/LV-2/LV-3 $87.20; S3-A $1827.20; S3-B $807.20; S3-C $1007.20; S3-D $1407.20.
Therefore S3-A is structurally blocked in APEX at 1 CL. It remains enabled in EK.
Historical reference: 7,067 trades; +$156,807.600992 net; Daily-Close MaxDD -$2,497.199084; worst day -$1,178.80; 0 days below -$1,400; 11/11 positive years. Commission already included in source logs.

## EK
No daily risk budget, no max-9 overlay, no Apex DD throttling. Frozen combined reference: 8,342 trades; +$225,467.588213 net; Daily-Close MaxDD -$6,777.206409; 11/11 positive years. All S2 and S3 A/B/C/D setup rules remain as frozen in the included reference package.

## Limitation
The frozen S2 Golden log does not contain exact exit timestamps. Historical Apex acceptance is therefore an entry-order preventive-risk replay with exact end-of-day PnL/DD, not an exact intraday trailing-DD reconstruction. The live server tracks paper exits as they occur, but historical claims must retain this limitation.

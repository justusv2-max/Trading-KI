# S2 + S3 A+B+C+D — COMBINED MASTER CHECKPOINT — 2026-09-30

Status: authoritative combined research replay with simultaneous subsystem positions allowed. No portfolio-wide single-position restriction has been invented.

## Frozen inputs
S2: streaming_final_s2_rawctx.csv, 6,542 trades, frozen System 2.
S3 A: S3_MASTER_A_LV_CONT_GOLDEN_TRADES.csv
S3 B: S3_B_QUALITY_GOLDEN_TRADES.csv
S3 C: S3_MASTER_C_HV200_FADE_GOLDEN_TRADES.csv
S3 D: S3_D_EXTREME_HV_GOLDEN_TRADES.csv
Raw reconstruction source: CL-3.txt and CL-4(6).txt.

## Common execution assumptions
1 CL per subsystem trade. Each subsystem retains its own no-overlap/execution rules. Different subsystems may hold positions simultaneously. $7.20 round-trip commission is already included in every golden-log PnL. No new entries >=20:00 Europe/Berlin and forced flat by 20:00 are inherited from the frozen subsystem definitions. S2 authoritative session indices are 09:00-15:00 ET M1: entry_time_ny = date 09:00 ET + entry_idx minutes.

## Combined verified metrics
Trades: 8342 = 6542 S2 + 1800 S3.
Net: $225467.59. Aggregate trade PF: 1.365348. Daily-close MaxDD: $-6777.21. Worst day: $-2859.21. Positive years: 11/11. Positive months: 109/128. S2/S3 daily correlation: -0.003284. Both active on 670 days.

## Important scope
Daily-close equity/DD is the authoritative combined metric in this checkpoint because the frozen S2 golden log does not contain exit timestamps. `entry_order_dd_diagnostic_not_exit_order` is only a diagnostic and MUST NOT be called true intraday/trade-sequence DD. A portfolio-wide one-position-only or realized-PnL daily-stop replay requires exact S2 exit timestamps or a fully reconstructed S2 execution log; do not fabricate them.

## Reproduction
Run build_final_combined.py in the same directory as the five golden logs. It creates combined trades, daily equity, yearly/monthly tables and metrics. For full raw regeneration of S3 A/C use rebuild_s3_ac_master.py; B/D use the checkpoint optimization/replay scripts. S2 is governed by FINAL_SYSTEM2_SPEC_2026-09-29.md and streaming_final_s2_rawctx.csv.

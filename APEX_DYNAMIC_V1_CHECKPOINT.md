# APEX DYNAMIC V1 CHECKPOINT — 2026-09-30
Source: S2_S3_ABCD_COMBINED_TRADES_CHRONO.csv.
Process by entry_time_ny. At start of day use prior daily-close portfolio DD.
Base risk budget $1200. If start-day DD <= -$1000 subtract $200. If <= -$1800 subtract an additional $450. During day effective budget = min(adjusted_base + 0.60 * max(realized_day_pnl,0), $1400). Before each trade execute only if realized_day_pnl - setup_reserved_risk >= -effective_budget. Max 9 executed trades/day.
Reserved risk map: {'S2_HV-1': 157.2, 'S2_HV-2': 157.2, 'S2_LV-1': 87.2, 'S2_LV-2': 87.2, 'S2_LV-3': 87.2, 'S3_A': 1827.2, 'S3_B': 807.2, 'S3_C': 1007.2, 'S3_D': 1407.2}
Expected: 7067 trades, net $156807.600992, Daily-Close MaxDD $-2497.199084, worst day $-1178.800000, days < -$1400 0, positive years 11/11.
S3_A count = 0; A is structurally excluded because one-CL observed worst loss $1827.20 exceeds the hard effective budget cap.
Limitation: exact S2 exit timestamps unavailable; this is entry-order preventive risk plus exact end-of-day PnL/DD, not true intraday trailing-DD reconstruction.

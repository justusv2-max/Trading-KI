#!/usr/bin/env python3
"""
CL/WTI LIVE SIGNAL ENGINE — CP017 APEX50K MAX4
Checkpoint: MASTER_REPRODUCTION_CHECKPOINT_017_APEX50K_MAX4.md

IMPORTANT
- This is the deployment/live signal engine specification for the exact CP015 rules.
- It consumes completed M5 bars plus precomputed causal context fields.
- It never uses future bars.
- Europe/Berlin entry window and hard-flat rules are mandatory.
- Fees are accounting/backtest assumptions; broker fills remain broker-side.
"""

import os
from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo
from typing import Optional, Dict, Any, List

TICK = 0.01
TICK_VALUE = 10.0
ROUND_TRIP_FEE = 7.20
BERLIN = ZoneInfo("Europe/Berlin")
NY = ZoneInfo("America/New_York")

# CP015/CP016 retained + CP017 combined daily cap
MAX_COMBINED_TRADES_PER_BERLIN_DAY = 4
MAX_S3_TRADES_PER_BERLIN_DAY = 2
S2_MAX_REALIZED_LOSSES_PER_DAY = 4
PRIORITY = {"C_MOM_CONT": 0, "D_RANGE_FAIL": 1, "B_DIR_SWEEP": 2, "A_DIR_BREAK": 3}
APEX_DAILY_RISK_BUDGET = 1500.0
STOP_RISK = {"HV-1":157.20,"HV-2":157.20,"LV-1":87.20,"LV-2":87.20,"LV-3":87.20,
             "A_DIR_BREAK":807.20,"C_MOM_CONT":607.20,"D_RANGE_FAIL":1007.20}
def apex_risk_gate(realized_day_pnl: float, setup: str) -> bool:
    return realized_day_pnl - STOP_RISK[setup] >= -APEX_DAILY_RISK_BUDGET - 1e-9


@dataclass(frozen=True)
class Signal:
    setup: str
    direction: int   # +1 long, -1 short
    signal_close_et: datetime
    entry_eligible_berlin: datetime
    sl_ticks: int
    tp_ticks: int
    metadata: Dict[str, Any]

def berlin_minutes(dt: datetime) -> int:
    x = dt.astimezone(BERLIN)
    return x.hour * 60 + x.minute

def weekday_ok(dt: datetime) -> bool:
    return dt.astimezone(BERLIN).weekday() < 5

def in_window(dt: datetime, start_min: int, end_min: int) -> bool:
    m = berlin_minutes(dt)
    return weekday_ok(dt) and start_min <= m < end_min

def directional_context(ctx: str, direction: int) -> bool:
    bulls = {"TREND_BULL", "MONTHLY_BULL", "WEEKLY_BULL"}
    bears = {"TREND_BEAR", "MONTHLY_BEAR", "WEEKLY_BEAR"}
    return ctx in (bulls if direction == 1 else bears)

def cp015_signal(row: Dict[str, Any]) -> List[Signal]:
    """
    row = one COMPLETED M5 bar enriched causally with:
      dt_et, open, high, low, close,
      ATR5, context, prev_momT,
      ph8, pl8, ph16, pl16
    dt_et is the M5 BAR START in America/New_York.
    Signal becomes entry-eligible at bar end = dt_et + 5 minutes.
    """
    from datetime import timedelta
    dt_et = row["dt_et"]
    if dt_et.tzinfo is None:
        dt_et = dt_et.replace(tzinfo=NY)
    entry_b = (dt_et + timedelta(minutes=5)).astimezone(BERLIN)
    o,h,l,c = map(float, (row["open"],row["high"],row["low"],row["close"]))
    atr5=float(row["ATR5"]); ctx=str(row["context"]); pm=float(row["prev_momT"])
    ph8=float(row["ph8"]); pl8=float(row["pl8"]); ph16=float(row["ph16"]); pl16=float(row["pl16"])
    rng=max(h-l, 0.0); body=abs(c-o)
    body_ratio=(body/rng) if rng > 0 else 0.0
    bodyT=body/TICK
    out=[]

    # A_DIR_BREAK — CP015 filters: 08:00-10:30, break<=13T, aligned prev momentum>=-75T, body<=45T
    if atr5 > 150 and body_ratio >= 0.40 and in_window(entry_b,480,630):
        if c > ph8 and c > o and directional_context(ctx,1):
            br=(c-ph8)/TICK
            mom=pm
            if br <= 13 + 1e-9 and mom >= -75 - 1e-9 and bodyT <= 45 + 1e-9:
                out.append(Signal("A_DIR_BREAK",1,dt_et,entry_b,80,60,
                                  {"breakT":br,"mom_alignT":mom,"bodyT":bodyT}))
        if c < pl8 and c < o and directional_context(ctx,-1):
            br=(pl8-c)/TICK
            mom=-pm
            if br <= 13 + 1e-9 and mom >= -75 - 1e-9 and bodyT <= 45 + 1e-9:
                out.append(Signal("A_DIR_BREAK",-1,dt_et,entry_b,80,60,
                                  {"breakT":br,"mom_alignT":mom,"bodyT":bodyT}))

    # C_MOM_CONT — LV, directional context, prev-session momentum >=60T intended direction,
    # signal body >=20T, close within 5T of intended candle extreme; 08:00-17:00
    if atr5 <= 150 and in_window(entry_b,480,1020):
        if directional_context(ctx,1) and pm >= 60 and c > o and bodyT >= 20 and (h-c)/TICK <= 5+1e-9:
            out.append(Signal("C_MOM_CONT",1,dt_et,entry_b,60,60,{}))
        if directional_context(ctx,-1) and -pm >= 60 and c < o and bodyT >= 20 and (c-l)/TICK <= 5+1e-9:
            out.append(Signal("C_MOM_CONT",-1,dt_et,entry_b,60,60,{}))

    # D_RANGE_FAIL — HV RANGE, LB16, penetration >=5T, 08:00-14:00
    if atr5 > 150 and ctx == "RANGE" and in_window(entry_b,480,840):
        pen=(pl16-l)/TICK
        if l < pl16 and c > pl16 and c > o and pen >= 5-1e-9:
            out.append(Signal("D_RANGE_FAIL",1,dt_et,entry_b,100,140,{"penetrationT":pen}))
        pen=(h-ph16)/TICK
        if h > ph16 and c < ph16 and c < o and pen >= 5-1e-9:
            out.append(Signal("D_RANGE_FAIL",-1,dt_et,entry_b,100,140,{"penetrationT":pen}))

    # B intentionally disabled in CP015.
    return sorted(out, key=lambda s: PRIORITY[s.setup])

class PortfolioState:
    def __init__(self):
        self.day = None
        self.combined_trades_today = 0
        self.s3_trades_today = 0
        self.s2_realized_losses_today = 0
        self.s3_position_open = False

    def roll_day(self, now: datetime):
        d=now.astimezone(BERLIN).date()
        if d != self.day:
            self.day=d
            self.combined_trades_today=0
            self.s3_trades_today=0
            self.s2_realized_losses_today=0
            self.s3_position_open=False

    def allow_s3(self, sig: Signal) -> bool:
        self.roll_day(sig.entry_eligible_berlin)
        return (not self.s3_position_open and
                self.combined_trades_today < MAX_COMBINED_TRADES_PER_BERLIN_DAY and
                self.s3_trades_today < MAX_S3_TRADES_PER_BERLIN_DAY and
                in_window(sig.entry_eligible_berlin,480,1200))

    def register_s3_entry(self):
        self.combined_trades_today += 1
        self.s3_trades_today += 1
        self.s3_position_open = True

    def register_s3_exit(self):
        self.s3_position_open = False

    def allow_s2_entry(self, now: datetime) -> bool:
        self.roll_day(now)
        return (self.combined_trades_today < MAX_COMBINED_TRADES_PER_BERLIN_DAY and
                self.s2_realized_losses_today < S2_MAX_REALIZED_LOSSES_PER_DAY and
                in_window(now,480,1200))

    def register_s2_entry(self, now: datetime):
        self.roll_day(now)
        if self.combined_trades_today >= MAX_COMBINED_TRADES_PER_BERLIN_DAY:
            raise RuntimeError("CP017 combined daily trade cap exhausted")
        self.combined_trades_today += 1

    def register_s2_realized_pnl(self, now: datetime, pnl: float):
        self.roll_day(now)
        if pnl < 0:
            self.s2_realized_losses_today += 1

def order_prices(entry: float, sig: Signal):
    stop = entry - sig.direction * sig.sl_ticks * TICK
    target = entry + sig.direction * sig.tp_ticks * TICK
    return round(stop, 2), round(target, 2)

def must_flat(now: datetime) -> bool:
    return berlin_minutes(now) >= 1200

# IMPORTANT CP017 acceptance order for every candidate entry:
# 1) roll Berlin day; 2) candidate must satisfy setup rules;
# 3) apex_risk_gate(realized_day_pnl, setup) must pass;
# 4) PortfolioState daily/S2/S3/no-overlap gates must pass;
# 5) only an ACTUALLY EXECUTED entry calls register_s2_entry/register_s3_entry.
# Unfilled/cancelled/rejected candidates do NOT consume the four daily slots.
#
# Railway process should call cp015_signal() only after a completed M5 candle,
# execute at the first available M1/open/live price at-or-after bar completion,
# enforce PortfolioState, and force-close any open position at 20:00 Europe/Berlin.
# Exact context/TPO construction remains defined in MASTER_REPRODUCTION_CHECKPOINT_015_EXACT.md.

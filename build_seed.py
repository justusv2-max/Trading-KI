from pathlib import Path
import pickle
import pandas as pd
from zoneinfo import ZoneInfo
from engine import Engine

ROOT=Path(__file__).resolve().parent
M1=ROOT/"bootstrap_m1.csv"
M5=ROOT/"bootstrap_m5.csv"
NY=ZoneInfo("America/New_York")

def load_csv(path):
    df=pd.read_csv(path)
    need={"time","open","high","low","close","Volume"}
    missing=need-set(df.columns)
    if missing:
        raise ValueError(f"{path.name}: missing columns {sorted(missing)}")
    df["dt"]=pd.to_datetime(df["time"],unit="s",utc=True).dt.tz_convert(NY)
    return df.sort_values("dt").reset_index(drop=True)

m1=load_csv(M1)
m5=load_csv(M5)
e=Engine(); e.set_mode("APEX")

first_m1=m1["dt"].iloc[0]
warm=m5[m5["dt"]<first_m1]
for r in warm.itertuples(index=False):
    e.warmup_m5({
        "timestamp":r.dt.isoformat(),"open":r.open,"high":r.high,
        "low":r.low,"close":r.close,"volume":r.Volume
    })

for r in m1.itertuples(index=False):
    e.ingest({
        "timestamp":r.dt.isoformat(),"open":r.open,"high":r.high,
        "low":r.low,"close":r.close,"volume":r.Volume
    })

(ROOT/"seed_state.pkl").write_bytes(pickle.dumps(e))
print({
    "m5_warmup_bars":len(warm),
    "m1_bars":len(m1),
    "last_bar":e.last_ts,
    "completed_sessions":len(e.completed_sessions),
    "risk_day":e.risk_day,
    "risk_day_trades":e.risk_day_trades,
    "risk_day_realized":e.risk_day_realized,
    "open_paper_positions":len(e.positions),
    "pending_s3":len(e.s3_pending),
    "pending_s2":len(e.pending_limits),
})

from pathlib import Path
import pandas as pd, pickle, hashlib, json
from engine import Engine, NY
ROOT=Path(__file__).resolve().parent
M1=ROOT/'bootstrap_data'/'NYMEX_CL1_M1.csv'
M5=ROOT/'bootstrap_data'/'NYMEX_CL1_M5.csv'
def rows(path):
 d=pd.read_csv(path)
 for r in d.itertuples(index=False):
  ts=pd.to_datetime(int(r.time),unit='s',utc=True).tz_convert('America/New_York').isoformat()
  yield {'timestamp':ts,'open':r.open,'high':r.high,'low':r.low,'close':r.close,'volume':getattr(r,'Volume',None)}
def main():
 e=Engine(); e.set_mode('APEX')
 m1=pd.read_csv(M1); first=int(m1.time.iloc[0])
 n5=0
 for b in rows(M5):
  if int(pd.Timestamp(b['timestamp']).timestamp())>=first: break
  e.warmup_m5(b); n5+=1
 n1=0
 for b in rows(M1): e.ingest(b); n1+=1
 # Start LIVE with warmed market state, but no fictional account/execution state.
 e.positions=[]; e.pending_limits=[]; e.s3_pending=[]; e.used_buckets=set(); e.lv2_filled=False
 e.risk_day=None; e.risk_day_realized=0.0; e.risk_day_trades=0; e.risk_equity=0.0; e.risk_peak=0.0; e.risk_start_dd=0.0; e.risk_base_budget=825.0
 out=ROOT/'seed_state.pkl'; out.write_bytes(pickle.dumps(e))
 meta={'m5_warmup_bars':n5,'m1_bars':n1,'first_m1':pd.to_datetime(first,unit='s',utc=True).isoformat(),'last_m1':pd.to_datetime(int(m1.time.iloc[-1]),unit='s',utc=True).isoformat(),'completed_sessions':len(e.completed_sessions),'last_bar':e.last_ts,'context_days':len(e.day_context),'sha256':hashlib.sha256(out.read_bytes()).hexdigest()}
 (ROOT/'BOOTSTRAP_CURRENT_META.json').write_text(json.dumps(meta,indent=2))
 print(json.dumps(meta,indent=2))
if __name__=='__main__':main()

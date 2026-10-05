from pathlib import Path
from datetime import datetime, timezone
import csv, hashlib, json, pickle
from engine import Engine

ROOT=Path(__file__).resolve().parent
M1=ROOT/'tradingview_m1_current.csv'
M5=ROOT/'tradingview_m5_current.csv'
OUT=ROOT/'seed_state.pkl'
META=ROOT/'seed_meta.json'

def rows(path):
    with path.open(newline='', encoding='utf-8-sig') as f:
        data=list(csv.DictReader(f))
    def val(r,n): return float(r[n])
    out=[]
    for r in data:
        out.append({
            'time':int(float(r['time'])),
            'open':val(r,'open'),'high':val(r,'high'),'low':val(r,'low'),'close':val(r,'close'),
            'volume':float(r.get('Volume') or r.get('volume') or 0.0)
        })
    out.sort(key=lambda x:x['time'])
    return out

def iso(ts): return datetime.fromtimestamp(ts,timezone.utc).isoformat()
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

m1=rows(M1); m5=rows(M5)
if not m1 or not m5: raise SystemExit('M1/M5 CSV must not be empty')
first_m1=m1[0]['time']
e=Engine(); e.set_mode('APEX')
# M5 is context warm-up only before the first available M1. After that M1 causally builds M30/TPO context.
warm=[r for r in m5 if r['time'] < first_m1]
for r in warm:
    e.warmup_m5({'timestamp':iso(r['time']),'open':r['open'],'high':r['high'],'low':r['low'],'close':r['close'],'volume':r['volume']})
for r in m1:
    e.ingest({'timestamp':iso(r['time']),'open':r['open'],'high':r['high'],'low':r['low'],'close':r['close'],'volume':r['volume']})
# A packaged bootstrap must never create a historical broker action after deployment.
# Keep all market/context/risk calculations, but require fresh live bars for any future command.
e.s3_pending=[]
if e.positions:
    raise SystemExit(f'Unsafe seed: {len(e.positions)} paper position(s) still open at CSV end')
OUT.write_bytes(pickle.dumps(e, protocol=pickle.HIGHEST_PROTOCOL))
meta={
  'm1_file':M1.name,'m1_sha256':sha(M1),'m1_rows':len(m1),'m1_first_utc':iso(m1[0]['time']),'m1_last_utc':iso(m1[-1]['time']),
  'm5_file':M5.name,'m5_sha256':sha(M5),'m5_rows':len(m5),'m5_first_utc':iso(m5[0]['time']),'m5_last_utc':iso(m5[-1]['time']),
  'm5_warmup_rows_used':len(warm),'seed_last_bar':e.last_ts,'completed_sessions':len(e.completed_sessions),
  'week_context_keys':len(e.week_bars),'month_context_keys':len(e.month_bars),'s2_daily_ranges':len(e.s2_daily_ranges),
  'pending_s2_limits':len(e.pending_limits),'open_paper_positions':len(e.positions),'s3_pending_cleared':True,
  'note':'M5 is used only before first M1. From first M1 onward M30/TPO/value-area context is built causally from M1.'
}
META.write_text(json.dumps(meta,indent=2),encoding='utf-8')
print(json.dumps(meta,indent=2))

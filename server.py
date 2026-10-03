import os,json,pickle,sqlite3,urllib.request,time,hashlib
from pathlib import Path
from fastapi import FastAPI,Header,HTTPException
from pydantic import BaseModel
from engine import Engine
DB=os.getenv('STATE_DB','/data/master.sqlite3'); MODE=os.getenv('TRADING_MODE','APEX').upper(); SECRET=os.getenv('WEBHOOK_SECRET',''); TOKEN=os.getenv('TELEGRAM_TOKEN',os.getenv('TELEGRAM_BOT_TOKEN','')); CHAT=os.getenv('TELEGRAM_CHAT_ID','')
Path(DB).parent.mkdir(parents=True,exist_ok=True)
def conn():
 c=sqlite3.connect(DB);c.execute('CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY,v BLOB)');c.execute('CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,reply TEXT)');c.execute('CREATE TABLE IF NOT EXISTS bridge_cmd(id TEXT PRIMARY KEY,created REAL,payload TEXT)');return c
def load():
 c=conn();r=c.execute("SELECT v FROM kv WHERE k='engine'").fetchone();c.close()
 if r:e=pickle.loads(r[0])
 elif Path(__file__).with_name('seed_state.pkl').exists():e=pickle.loads(Path(__file__).with_name('seed_state.pkl').read_bytes())
 else:e=Engine()
 e.set_mode(MODE);return e
def save(e):
 c=conn();c.execute("INSERT OR REPLACE INTO kv(k,v) VALUES('engine',?)",(pickle.dumps(e),));c.commit();c.close()
def auth(x):
 if SECRET and x!=SECRET:raise HTTPException(401,'bad secret')
def telegram(events):
 if not(TOKEN and CHAT):return
 for e in events:
  if e['kind'] not in {'S2_FILL','S3_PAPER_ENTRY','PAPER_EXIT','RISK_BLOCK'}:continue
  d='LONG' if e.get('direction')==1 else 'SHORT' if e.get('direction')==-1 else ''
  txt=f"CL MASTER | {e.get('setup','')} | {e['kind']} {d}\n"+json.dumps(e,ensure_ascii=False)
  try:
   req=urllib.request.Request(f'https://api.telegram.org/bot{TOKEN}/sendMessage',json.dumps({'chat_id':CHAT,'text':txt}).encode(),{'Content-Type':'application/json'});urllib.request.urlopen(req,timeout=4).read()
  except Exception:pass
class Bar(BaseModel):
 event_id:str; timestamp:str; open:float; high:float; low:float; close:float; volume:float|None=None; secret:str|None=None; timeframe:str='1'
class TVBar(BaseModel):
 secret:str; event_id:str; timeframe:str; timestamp:str; open:float; high:float; low:float; close:float; volume:float|None=None
class Bootstrap(BaseModel): bars:list[Bar]
app=FastAPI(title='CL S2+S3 Master Signal Server',version='2026.10.03-apex-bridge')

def _bridge_id(event_id,idx,ev):
 raw=f"{event_id}|{idx}|{ev.get('setup')}|{ev.get('direction')}|{ev.get('kind')}".encode();return hashlib.sha256(raw).hexdigest()[:24]
def _publish_s3_commands(event_id,bar_ts,events,e):
 # Live S3 must be dispatched at the close of the signal M1, i.e. as close as possible to NEXT_M1_OPEN.
 # Mirror historical max-trade sequencing for multiple same-bar S3 signals without mutating paper state early.
 temp_count=e.risk_day_trades
 rows=[]
 for i,ev in enumerate(events):
  if ev.get('kind')!='S3_SIGNAL':continue
  setup=ev['setup']; allowed,reason=e._risk_allow(setup)
  if MODE=='APEX' and temp_count>=9:allowed=False;reason='APEX_MAX_9_TRADES'
  if not allowed:continue
  if MODE=='APEX':temp_count+=1
  cmd={'signal_id':_bridge_id(event_id,i,ev),'created_epoch':time.time(),'kind':'S3_MARKET','setup':setup,'direction':ev['direction'],'sl_ticks':ev['sl_ticks'],'tp_ticks':ev['tp_ticks'],'signal_bar_ts':bar_ts,'max_age_seconds':75}
  rows.append(cmd)
 if rows:
  c=conn();now=time.time()
  for x in rows:c.execute('INSERT OR IGNORE INTO bridge_cmd(id,created,payload) VALUES(?,?,?)',(x['signal_id'],now,json.dumps(x)))
  c.execute('DELETE FROM bridge_cmd WHERE created<?',(now-3600,));c.commit();c.close()

def _active_s2(e):
 # Conservative live synchronization. Only expose currently pending/active limits while the gate presently allows them.
 # If capacity shrinks, ATAS cancels orders on the next poll. At most remaining daily trade slots are exposed.
 cap=999 if MODE=='EK' else max(0,9-e.risk_day_trades);out=[]
 for L in list(e.pending_limits):
  if len(out)>=cap:break
  if not L.active:continue
  allowed,_=e._risk_allow(L.setup)
  if not allowed:continue
  sl,tp=(15,15) if L.setup.startswith('HV') else (8,8)
  entry=L.zone/100.0; d=L.direction
  raw=f"{e.s2_day}|{L.setup}|{d}|{L.zone}|{L.first_i}|{L.last_i}".encode()
  out.append({'signal_id':hashlib.sha256(raw).hexdigest()[:24],'kind':'S2_LIMIT','setup':L.setup,'direction':d,'entry':entry,'stop':entry-d*sl*.01,'target':entry+d*tp*.01,'sl_ticks':sl,'tp_ticks':tp})
 return out

@app.get('/health')
def health():
 e=load();ready=len(e.completed_sessions)>=5 and bool(e.last_ts);return {'ok':True,'ready':ready,'last_bar':e.last_ts,'completed_sessions':len(e.completed_sessions),'telegram':bool(TOKEN and CHAT),'mode':MODE,'execution':'SIGNAL_ONLY_PAPER_RECONCILIATION+ATAS_BRIDGE_API','master':'S2+S3 A/B/C/D | APEX protection $825 | M1-live'}
@app.get('/state')
def state(x_webhook_secret:str|None=Header(None)):
 auth(x_webhook_secret);e=load();return {'last_bar':e.last_ts,'completed_sessions':len(e.completed_sessions),'pending_s2':len(e.pending_limits),'pending_s3':len(e.s3_pending),'paper_positions':[p.__dict__ for p in e.positions],'trading_mode':e.mode,'risk_day':e.risk_day,'risk_day_realized':e.risk_day_realized,'risk_day_trades':e.risk_day_trades,'risk_start_dd':e.risk_start_dd,'risk_base_budget':e.risk_base_budget,'risk_effective_budget':e._risk_effective_budget()}
@app.get('/bridge/status')
def bridge_status(x_webhook_secret:str|None=Header(None)):
 auth(x_webhook_secret);e=load();now=time.time();c=conn();rows=c.execute('SELECT payload FROM bridge_cmd WHERE created>=? ORDER BY created,id',(now-120,)).fetchall();c.close()
 cmds=[json.loads(x[0]) for x in rows]
 return {'ok':True,'ready':len(e.completed_sessions)>=5 and bool(e.last_ts),'mode':MODE,'server_time':now,'last_bar':e.last_ts,'risk_day':e.risk_day,'risk_day_realized':e.risk_day_realized,'risk_day_trades':e.risk_day_trades,'risk_effective_budget':e._risk_effective_budget(),'s3_commands':cmds,'active_s2_limits':_active_s2(e)}
@app.post('/bar')
def bar(b:Bar,x_webhook_secret:str|None=Header(None)):
 auth(x_webhook_secret);c=conn();old=c.execute('SELECT reply FROM events WHERE id=?',(b.event_id,)).fetchone()
 if old:c.close();return json.loads(old[0])
 c.close();e=load()
 try:r=e.ingest({k:v for k,v in b.model_dump().items() if k in {'timestamp','open','high','low','close','volume'}})
 except Exception as ex:raise HTTPException(400,str(ex))
 _publish_s3_commands(b.event_id,b.timestamp,r['events'],e)
 save(e);c=conn();c.execute('INSERT INTO events(id,reply) VALUES(?,?)',(b.event_id,json.dumps(r)));c.commit();c.close();telegram(r['events']);return r
@app.post('/bootstrap')
def bootstrap(req:Bootstrap,x_webhook_secret:str|None=Header(None)):
 auth(x_webhook_secret);e=Engine();e.set_mode(MODE);n=0
 for b in req.bars:e.ingest(b.model_dump());n+=1
 save(e);return {'ok':True,'bars':n,'last_bar':e.last_ts,'completed_sessions':len(e.completed_sessions),'ready':len(e.completed_sessions)>=5}
@app.post('/reset')
def reset(x_webhook_secret:str|None=Header(None)):
 auth(x_webhook_secret);e=Engine();e.set_mode(MODE);save(e);return {'ok':True,'reset':True,'mode':MODE}
@app.post('/tv')
def tradingview(b:TVBar):
 if SECRET and b.secret!=SECRET:raise HTTPException(401,'bad secret')
 tf=str(b.timeframe).upper().replace('M','')
 if tf not in {'1','5'}:raise HTTPException(400,'timeframe must be 1 or 5')
 if tf=='5':
  c=conn();c.execute('CREATE TABLE IF NOT EXISTS tv_m5(event_id TEXT PRIMARY KEY,payload TEXT)');c.execute('INSERT OR IGNORE INTO tv_m5(event_id,payload) VALUES(?,?)',(b.event_id,b.model_dump_json()));c.commit();c.close();return {'ok':True,'accepted':'M5_AUDIT','event_id':b.event_id}
 bb=Bar(event_id=b.event_id,timestamp=b.timestamp,open=b.open,high=b.high,low=b.low,close=b.close,volume=b.volume,timeframe='1')
 return bar(bb,SECRET if SECRET else None)

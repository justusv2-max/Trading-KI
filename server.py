import os, json, pickle, sqlite3, urllib.request, time, hashlib, copy, threading
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from fastapi import FastAPI, Header, HTTPException, Query
from pydantic import BaseModel
from engine import Engine

DB=os.getenv('STATE_DB','/data/master.sqlite3')
MODE=os.getenv('TRADING_MODE','APEX').upper()
SECRET=os.getenv('WEBHOOK_SECRET','')
TOKEN=os.getenv('TELEGRAM_TOKEN',os.getenv('TELEGRAM_BOT_TOKEN',''))
CHAT=os.getenv('TELEGRAM_CHAT_ID','')
FEE=float(os.getenv('ROUND_TRIP_FEE','7.20'))
SAFETY_BUFFER=float(os.getenv('APEX_SAFETY_BUFFER','0'))
NY=ZoneInfo('America/New_York')
Path(DB).parent.mkdir(parents=True,exist_ok=True)
DB_LOCK=threading.RLock()

RISK_NOMINAL={'HV-1':150.0,'HV-2':150.0,'LV-1':80.0,'LV-2':80.0,'LV-3':80.0,
              'S3-A':1400.0,'S3-B':800.0,'S3-C':1000.0,'S3-D':1400.0}

PROFILES={
 '50K_EOD_EVAL': {'start':50000.0,'max_dd':2000.0,'dll':1000.0,'target':3000.0,'max_contracts':6,'kind':'EVAL'},
 '100K_EOD_EVAL':{'start':100000.0,'max_dd':3000.0,'dll':1500.0,'target':6000.0,'max_contracts':8,'kind':'EVAL'},
 '50K_EOD_PA':   {'start':50000.0,'max_dd':2000.0,'dll':1000.0,'target':None,'max_contracts':4,'kind':'PA'},
 '100K_EOD_PA':  {'start':100000.0,'max_dd':3000.0,'dll':1750.0,'target':None,'max_contracts':6,'kind':'PA'},
}

# ---- persistence ----
def conn():
 c=sqlite3.connect(DB, timeout=30.0)
 c.execute('PRAGMA busy_timeout=30000')
 return c

def init_db():
 c=sqlite3.connect(DB, timeout=30.0)
 c.execute('PRAGMA busy_timeout=30000')
 c.execute('PRAGMA journal_mode=WAL')
 c.execute('PRAGMA synchronous=NORMAL')
 c.execute('CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY,v BLOB)')
 c.execute('CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,reply TEXT)')
 c.execute('CREATE TABLE IF NOT EXISTS bridge_cmd(id TEXT PRIMARY KEY,created REAL,payload TEXT)')
 c.execute('CREATE TABLE IF NOT EXISTS tv_m5(event_id TEXT PRIMARY KEY,payload TEXT)')
 c.execute('''CREATE TABLE IF NOT EXISTS account_state(
   account_id TEXT PRIMARY KEY, profile TEXT NOT NULL, vendor TEXT NOT NULL,
   balance REAL NOT NULL, high_eod REAL NOT NULL, threshold REAL NOT NULL,
   trade_day TEXT, day_start_balance REAL NOT NULL, day_realized REAL NOT NULL,
   day_entries INTEGER NOT NULL, dll_paused INTEGER NOT NULL,
   updated REAL NOT NULL)''')
 c.execute('''CREATE TABLE IF NOT EXISTS account_reservation(
   account_id TEXT NOT NULL, signal_id TEXT NOT NULL, setup TEXT NOT NULL,
   risk_with_fee REAL NOT NULL, created REAL NOT NULL, kind TEXT NOT NULL,
   PRIMARY KEY(account_id,signal_id))''')
 c.execute('''CREATE TABLE IF NOT EXISTS account_open(
   account_id TEXT NOT NULL, signal_id TEXT NOT NULL, setup TEXT NOT NULL,
   direction INTEGER NOT NULL, entry_price REAL NOT NULL, risk_with_fee REAL NOT NULL,
   opened REAL NOT NULL, PRIMARY KEY(account_id,signal_id))''')
 c.execute('''CREATE TABLE IF NOT EXISTS account_exec_event(
   account_id TEXT NOT NULL, signal_id TEXT NOT NULL, event TEXT NOT NULL, payload TEXT NOT NULL, created REAL NOT NULL,
   PRIMARY KEY(account_id,signal_id,event))''')
 c.commit();c.close()

init_db()

def _migrate_engine_state(e):
 # Persistent Railway volumes can contain a pickle created by an older
 # Engine dataclass.  Unpickling succeeds, but newly-added instance fields
 # are absent and later live-bar processing would fail with AttributeError.
 # Add every missing current Engine field from a fresh instance while
 # preserving all existing strategy/session state.
 fresh=Engine()
 for name,value in vars(fresh).items():
  if not hasattr(e,name):
   setattr(e,name,copy.deepcopy(value))
 return e

def load():
 c=conn();r=c.execute("SELECT v FROM kv WHERE k='engine'").fetchone();c.close()
 db_e=pickle.loads(r[0]) if r else None
 seed_path=Path(__file__).with_name('seed_state.pkl')
 seed_e=pickle.loads(seed_path.read_bytes()) if seed_path.exists() else None
 if db_e is None:
  e=seed_e if seed_e is not None else Engine()
 elif seed_e is not None and getattr(seed_e,'last_ts',None) and (not getattr(db_e,'last_ts',None) or datetime.fromisoformat(seed_e.last_ts)>datetime.fromisoformat(db_e.last_ts)):
  e=seed_e
 else:e=db_e
 e=_migrate_engine_state(e)
 e.set_mode(MODE);return e

def save(e):
 c=conn();c.execute("INSERT OR REPLACE INTO kv(k,v) VALUES('engine',?)",(pickle.dumps(e),));c.commit();c.close()

def auth(x):
 if SECRET and x!=SECRET: raise HTTPException(401,'bad secret')

def trading_day_now():
 now=datetime.now(timezone.utc).astimezone(NY)
 # Apex resets the trading day at 18:00 ET. 18:00+ belongs to next trade date.
 d=now.date()
 if now.hour>=18:
  from datetime import timedelta
  d=d+timedelta(days=1)
 return d.isoformat()

def _profile(profile):
 p=PROFILES.get((profile or '').upper())
 if not p: raise HTTPException(400,f'unknown profile {profile}; allowed={list(PROFILES)}')
 return p

def _initial_threshold(p): return p['start']-p['max_dd']

def _threshold_cap(profile,vendor):
 p=_profile(profile); vendor=(vendor or 'RITHMIC').upper()
 if p['kind']=='PA': return p['start']+100.0
 if vendor in {'RITHMIC','WEALTHCHARTS'}: return p['start']+p['target']
 return float('inf') # Tradovate eval trails indefinitely

def _current_dll(profile,balance):
 p=_profile(profile)
 if p['kind']=='EVAL': return p['dll']
 profit=balance-p['start']
 if profile.upper()=='50K_EOD_PA':
  if profit>=6000:return 3000.0
  if profit>=3000:return 2000.0
  return 1000.0
 if profile.upper()=='100K_EOD_PA':
  if profit>=10000:return 3500.0
  if profit>=5000:return 2500.0
  return 1750.0
 return p['dll']

def _get_state(account_id,profile,vendor):
 p=_profile(profile); vendor=(vendor or 'RITHMIC').upper(); td=trading_day_now(); now=time.time()
 c=conn();r=c.execute('SELECT account_id,profile,vendor,balance,high_eod,threshold,trade_day,day_start_balance,day_realized,day_entries,dll_paused,updated FROM account_state WHERE account_id=?',(account_id,)).fetchone()
 if not r:
  st={'account_id':account_id,'profile':profile.upper(),'vendor':vendor,'balance':p['start'],'high_eod':p['start'],
      'threshold':_initial_threshold(p),'trade_day':td,'day_start_balance':p['start'],'day_realized':0.0,
      'day_entries':0,'dll_paused':0,'updated':now}
  c.execute('INSERT INTO account_state VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',tuple(st[k] for k in ['account_id','profile','vendor','balance','high_eod','threshold','trade_day','day_start_balance','day_realized','day_entries','dll_paused','updated']))
  c.commit();c.close();return st
 keys=['account_id','profile','vendor','balance','high_eod','threshold','trade_day','day_start_balance','day_realized','day_entries','dll_paused','updated']
 st=dict(zip(keys,r))
 if st['profile']!=profile.upper() or st['vendor']!=vendor:
  c.close(); raise HTTPException(409,f'account {account_id} already bound to {st["profile"]}/{st["vendor"]}; reset account state before changing profile')
 if st['trade_day']!=td:
  # previous EOD balance becomes eligible to move the threshold for the new session
  st['high_eod']=max(st['high_eod'],st['balance'])
  cap=_threshold_cap(st['profile'],st['vendor'])
  st['threshold']=max(st['threshold'],min(st['high_eod']-p['max_dd'],cap))
  st['trade_day']=td;st['day_start_balance']=st['balance'];st['day_realized']=0.0;st['day_entries']=0;st['dll_paused']=0;st['updated']=now
  c.execute('''UPDATE account_state SET balance=?,high_eod=?,threshold=?,trade_day=?,day_start_balance=?,day_realized=?,day_entries=?,dll_paused=?,updated=? WHERE account_id=?''',
            (st['balance'],st['high_eod'],st['threshold'],td,st['day_start_balance'],0.0,0,0,now,account_id));c.commit()
  c.execute('DELETE FROM account_reservation WHERE account_id=?',(account_id,));c.commit()
 c.close();return st

def _reserved_risk(account_id):
 c=conn();cut=time.time()-180
 x=c.execute('SELECT COALESCE(SUM(risk_with_fee),0) FROM account_reservation WHERE account_id=? AND created>=?',(account_id,cut)).fetchone()[0]
 y=c.execute('SELECT COALESCE(SUM(risk_with_fee),0) FROM account_open WHERE account_id=?',(account_id,)).fetchone()[0]
 c.close();return float(x or 0),float(y or 0)

def _can_reserve(st,setup,signal_id):
 if setup not in RISK_NOMINAL:return False,'UNKNOWN_SETUP',{}
 if st['dll_paused']:return False,'DLL_PAUSED',{}
 if st['day_entries']>=9:return False,'MAX_9_TRADES',{}
 nominal=RISK_NOMINAL[setup]
 # Preserve the frozen strategy rule: realized PnL minus nominal candidate risk must remain >= -1400.
 if st['day_realized']-nominal < -1400.0-1e-9:return False,'STRATEGY_1400_GATE',{}
 fee_risk=nominal+FEE
 reserved,openrisk=_reserved_risk(st['account_id'])
 dll=_current_dll(st['profile'],st['balance'])
 projected_day=st['day_realized']-reserved-openrisk-fee_risk
 if projected_day <= -dll+SAFETY_BUFFER+1e-9:
  return False,'APEX_DLL_PREVENTIVE_GATE',{'dll':dll,'projected_day':projected_day,'reserved':reserved,'open_risk':openrisk}
 projected_balance=st['balance']-reserved-openrisk-fee_risk
 if projected_balance <= st['threshold']+SAFETY_BUFFER+1e-9:
  return False,'APEX_EOD_THRESHOLD_PREVENTIVE_GATE',{'threshold':st['threshold'],'projected_balance':projected_balance,'reserved':reserved,'open_risk':openrisk}
 return True,'ALLOWED',{'dll':dll,'projected_day':projected_day,'threshold':st['threshold'],'projected_balance':projected_balance}

def _reserve(account_id,signal_id,setup,kind):
 risk=RISK_NOMINAL[setup]+FEE;c=conn();c.execute('INSERT OR IGNORE INTO account_reservation VALUES(?,?,?,?,?,?)',(account_id,signal_id,setup,risk,time.time(),kind));c.commit();c.close()

def _release_reservation(account_id,signal_id):
 c=conn();c.execute('DELETE FROM account_reservation WHERE account_id=? AND signal_id=?',(account_id,signal_id));c.commit();c.close()

def telegram(events):
 if not(TOKEN and CHAT):return
 for e in events:
  if e.get('kind') not in {'S2_FILL','S3_PAPER_ENTRY','PAPER_EXIT','RISK_BLOCK'}:continue
  try:
   req=urllib.request.Request(f'https://api.telegram.org/bot{TOKEN}/sendMessage',json.dumps({'chat_id':CHAT,'text':'CL MASTER | '+json.dumps(e,ensure_ascii=False)}).encode(),{'Content-Type':'application/json'});urllib.request.urlopen(req,timeout=4).read()
  except Exception:pass

class Bar(BaseModel):
 event_id:str; timestamp:str; open:float; high:float; low:float; close:float; volume:float|None=None; secret:str|None=None; timeframe:str='1'
class TVBar(BaseModel):
 secret:str; event_id:str; timeframe:str; timestamp:str; open:float; high:float; low:float; close:float; volume:float|None=None
class Bootstrap(BaseModel): bars:list[Bar]
class Execution(BaseModel):
 account_id:str; profile:str; vendor:str='RITHMIC'; signal_id:str; setup:str; direction:int; event:str; fill_price:float|None=None; timestamp_utc:str|None=None

app=FastAPI(title='CL S2+S3 Apex EOD Multi-Account Server',version='2026.10.05-eod-multi-v3-sqlite-wal')

def _bridge_id(event_id,idx,ev):
 raw=f"{event_id}|{idx}|{ev.get('setup')}|{ev.get('direction')}|{ev.get('kind')}".encode();return hashlib.sha256(raw).hexdigest()[:24]

def _publish_s3_commands(event_id,bar_ts,events,e):
 rows=[]
 for i,ev in enumerate(events):
  if ev.get('kind')!='S3_SIGNAL':continue
  cmd={'signal_id':_bridge_id(event_id,i,ev),'created_epoch':time.time(),'kind':'S3_MARKET','setup':ev['setup'],'direction':ev['direction'],'sl_ticks':ev['sl_ticks'],'tp_ticks':ev['tp_ticks'],'signal_bar_ts':bar_ts,'max_age_seconds':75}
  rows.append(cmd)
 if rows:
  c=conn();now=time.time()
  for x in rows:c.execute('INSERT OR IGNORE INTO bridge_cmd(id,created,payload) VALUES(?,?,?)',(x['signal_id'],now,json.dumps(x)))
  c.execute('DELETE FROM bridge_cmd WHERE created<?',(now-3600,));c.commit();c.close()

def _raw_active_s2(e):
 out=[]
 for L in list(e.pending_limits):
  if not L.active:continue
  sl,tp=(15,15) if L.setup.startswith('HV') else (8,8);entry=L.zone/100.0;d=L.direction
  raw=f"{e.s2_day}|{L.setup}|{d}|{L.zone}|{L.first_i}|{L.last_i}".encode()
  out.append({'signal_id':hashlib.sha256(raw).hexdigest()[:24],'kind':'S2_LIMIT','setup':L.setup,'direction':d,'entry':entry,'stop':entry-d*sl*.01,'target':entry+d*tp*.01,'sl_ticks':sl,'tp_ticks':tp})
 return out

def _account_filter(account_id,profile,vendor,s3,s2):
 st=_get_state(account_id,profile,vendor); out3=[];out2=[]; active_ids=set(); cut=time.time()-180
 c=conn(); existing={r[0] for r in c.execute('SELECT signal_id FROM account_reservation WHERE account_id=? AND created>=?',(account_id,cut)).fetchall()};c.close()
 for x in s2+s3:
  sid=x['signal_id'];active_ids.add(sid)
  if sid in existing:
   (out2 if x['kind']=='S2_LIMIT' else out3).append(x);continue
  allowed,reason,detail=_can_reserve(st,x['setup'],sid)
  if allowed:
   _reserve(account_id,sid,x['setup'],x['kind']);existing.add(sid);(out2 if x['kind']=='S2_LIMIT' else out3).append(x)
 c=conn();rows=c.execute("SELECT signal_id FROM account_reservation WHERE account_id=? AND kind='S2_LIMIT' AND created>=?",(account_id,cut)).fetchall();c.close()
 stale=[sid for (sid,) in rows if sid not in active_ids]
 if stale:
  c=conn();c.executemany('DELETE FROM account_reservation WHERE account_id=? AND signal_id=?',[(account_id,sid) for sid in stale]);c.commit();c.close()
 st=_get_state(account_id,profile,vendor);reserved,openrisk=_reserved_risk(account_id)
 risk={'profile':profile.upper(),'vendor':vendor.upper(),'balance':st['balance'],'eod_threshold':st['threshold'],'dll':_current_dll(profile,st['balance']),
       'day_realized':st['day_realized'],'day_entries':st['day_entries'],'dll_paused':bool(st['dll_paused']),'reserved_risk':reserved,'open_stop_risk':openrisk}
 return out3,out2,risk

@app.get('/health')
def health():
 e=load();return {'ok':True,'ready':len(e.completed_sessions)>=5 and bool(e.last_ts),'last_bar':e.last_ts,'completed_sessions':len(e.completed_sessions),'mode':MODE,
  'execution':'ATAS_BRIDGE_V3_ACCOUNT_AWARE','master':'S2+S3 A/B/C/D | frozen $1400/max9 strategy gate + Apex EOD account safety','profiles':list(PROFILES)}

@app.get('/bridge/status')
def bridge_status(account_id:str=Query(...),profile:str=Query(...),vendor:str=Query('RITHMIC'),x_webhook_secret:str|None=Header(None)):
 auth(x_webhook_secret)
 with DB_LOCK:
  e=load();now=time.time();c=conn();rows=c.execute('SELECT payload FROM bridge_cmd WHERE created>=? ORDER BY created,id',(now-120,)).fetchall();c.close()
  s3=[json.loads(x[0]) for x in rows];s2=_raw_active_s2(e)
  fs3,fs2,risk=_account_filter(account_id,profile,vendor,s3,s2)
 return {'ok':True,'ready':len(e.completed_sessions)>=5 and bool(e.last_ts),'mode':MODE,'server_time':now,'last_bar':e.last_ts,'account_id':account_id,'risk':risk,'s3_commands':fs3,'active_s2_limits':fs2}

@app.post('/bridge/execution')
def bridge_execution(x:Execution,x_webhook_secret:str|None=Header(None)):
 with DB_LOCK:
  auth(x_webhook_secret);st=_get_state(x.account_id,x.profile,x.vendor);event=x.event.upper();now=time.time()
  c=conn();dup=c.execute('SELECT payload FROM account_exec_event WHERE account_id=? AND signal_id=? AND event=?',(x.account_id,x.signal_id,event)).fetchone();c.close()
  if dup:return json.loads(dup[0])
  if event=='CANCEL':
   _release_reservation(x.account_id,x.signal_id);reply={'ok':True,'event':'CANCEL'}
   c=conn();c.execute('INSERT OR IGNORE INTO account_exec_event VALUES(?,?,?,?,?)',(x.account_id,x.signal_id,event,json.dumps(reply),now));c.commit();c.close();return reply
  if event=='ENTRY':
   if x.fill_price is None:raise HTTPException(400,'fill_price required')
   risk=RISK_NOMINAL.get(x.setup)
   if risk is None:raise HTTPException(400,'unknown setup')
   c=conn();c.execute('DELETE FROM account_reservation WHERE account_id=? AND signal_id=?',(x.account_id,x.signal_id))
   c.execute('INSERT INTO account_open VALUES(?,?,?,?,?,?,?)',(x.account_id,x.signal_id,x.setup,x.direction,float(x.fill_price),risk+FEE,now))
   c.execute('UPDATE account_state SET day_entries=day_entries+1,updated=? WHERE account_id=?',(now,x.account_id))
   reply={'ok':True,'event':'ENTRY'};c.execute('INSERT INTO account_exec_event VALUES(?,?,?,?,?)',(x.account_id,x.signal_id,event,json.dumps(reply),now));c.commit();c.close();return reply
  if event=='EXIT':
   if x.fill_price is None:raise HTTPException(400,'fill_price required')
   c=conn();r=c.execute('SELECT direction,entry_price FROM account_open WHERE account_id=? AND signal_id=?',(x.account_id,x.signal_id)).fetchone()
   if not r:c.close();raise HTTPException(409,'no matching open trade')
   direction,entry=float(r[0]),float(r[1]);pnl=direction*(float(x.fill_price)-entry)*1000.0-FEE
   c.execute('DELETE FROM account_open WHERE account_id=? AND signal_id=?',(x.account_id,x.signal_id))
   c.execute('UPDATE account_state SET balance=balance+?,day_realized=day_realized+?,updated=? WHERE account_id=?',(pnl,pnl,now,x.account_id));c.commit();c.close()
   st=_get_state(x.account_id,x.profile,x.vendor);dll=_current_dll(x.profile,st['balance'])
   if st['day_realized']<=-dll:
    c=conn();c.execute('UPDATE account_state SET dll_paused=1 WHERE account_id=?',(x.account_id,));c.commit();c.close()
   reply={'ok':True,'event':'EXIT','pnl_net':pnl,'balance':st['balance'],'day_realized':st['day_realized']}
   c=conn();c.execute('INSERT INTO account_exec_event VALUES(?,?,?,?,?)',(x.account_id,x.signal_id,event,json.dumps(reply),now));c.commit();c.close();return reply
  raise HTTPException(400,'event must be ENTRY, EXIT or CANCEL')

@app.get('/account/risk')
def account_risk(account_id:str,profile:str,vendor:str='RITHMIC',x_webhook_secret:str|None=Header(None)):
 auth(x_webhook_secret)
 with DB_LOCK:
  st=_get_state(account_id,profile,vendor);r,o=_reserved_risk(account_id)
 return {**st,'dll':_current_dll(profile,st['balance']),'reserved_risk':r,'open_stop_risk':o}

@app.post('/account/reset')
def account_reset(account_id:str,profile:str,vendor:str='RITHMIC',x_webhook_secret:str|None=Header(None)):
 auth(x_webhook_secret)
 with DB_LOCK:
  p=_profile(profile);c=conn();c.execute('DELETE FROM account_state WHERE account_id=?',(account_id,));c.execute('DELETE FROM account_reservation WHERE account_id=?',(account_id,));c.execute('DELETE FROM account_open WHERE account_id=?',(account_id,));c.commit();c.close();st=_get_state(account_id,profile,vendor)
 return st

@app.post('/bar')
def bar(b:Bar,x_webhook_secret:str|None=Header(None)):
 auth(x_webhook_secret)
 with DB_LOCK:
  c=conn();old=c.execute('SELECT reply FROM events WHERE id=?',(b.event_id,)).fetchone();c.close()
  if old:return json.loads(old[0])
  e=load()
  try:r=e.ingest({k:v for k,v in b.model_dump().items() if k in {'timestamp','open','high','low','close','volume'}})
  except ValueError as ex:
   if 'strictly increasing' in str(ex):
    return {'ok':True,'accepted':'STALE_OR_DUPLICATE','event_id':b.event_id,'last_bar':e.last_ts}
   raise HTTPException(400,str(ex))
  except Exception as ex:raise HTTPException(400,str(ex))
  _publish_s3_commands(b.event_id,b.timestamp,r['events'],e);save(e);c=conn();c.execute('INSERT OR IGNORE INTO events(id,reply) VALUES(?,?)',(b.event_id,json.dumps(r)));c.commit();c.close()
 telegram(r['events']);return r

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
  with DB_LOCK:
   c=conn();c.execute('INSERT OR IGNORE INTO tv_m5(event_id,payload) VALUES(?,?)',(b.event_id,b.model_dump_json()));c.commit();c.close()
  return {'ok':True,'accepted':'M5_AUDIT','event_id':b.event_id}
 bb=Bar(event_id=b.event_id,timestamp=b.timestamp,open=b.open,high=b.high,low=b.low,close=b.close,volume=b.volume,timeframe='1')
 return bar(bb,SECRET if SECRET else None)

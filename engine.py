from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from collections import deque, Counter
from typing import Optional
import math, struct
NY=ZoneInfo('America/New_York'); BERLIN=ZoneInfo('Europe/Berlin')
TICK=.01; TICK_VALUE=10.0; FEE=7.20
BULL={'TREND_BULL','MONTHLY_BULL','WEEKLY_BULL'}; BEAR={'TREND_BEAR','MONTHLY_BEAR','WEEKLY_BEAR'}
NON_TREND={'MONTHLY_BULL','MONTHLY_BEAR','WEEKLY_BULL','WEEKLY_BEAR','RANGE'}

def cents(x): return int(round(float(x)*100))
def f32(x):
    """Round exactly to IEEE-754 float32 (needed to reproduce frozen S3-B/D research cache semantics)."""
    return struct.unpack('!f',struct.pack('!f',float(x)))[0]
def px(x): return x/100.0

def session_id(ts:datetime):
    t=ts.astimezone(NY); d=t.date() if t.hour>=18 else (t-timedelta(days=1)).date(); return d.isoformat()
def berlin_entry_ok(ts):
    b=ts.astimezone(BERLIN); return b.weekday()<5 and (b.hour*60+b.minute)<20*60

def value_area(bars):
    cnt=Counter()
    for lo,hi in bars: cnt.update(range(lo,hi+1))
    if not cnt:return None
    poc=min(k for k,v in cnt.items() if v==max(cnt.values())); lo=hi=poc; cov=cnt[poc]; target=.70*sum(cnt.values()); floor=min(cnt);ceil=max(cnt)
    while cov<target:
        dn=cnt.get(lo-1,0) if lo>floor else -1; up=cnt.get(hi+1,0) if hi<ceil else -1
        if dn<0 and up<0:break
        if dn>=up: lo-=1;cov+=cnt[lo]
        else: hi+=1;cov+=cnt[hi]
    return {'val':px(lo),'vah':px(hi),'poc':px(poc)}

def classify(o,pw,pm):
    if not pw or not pm:return None
    if o>pw['vah'] and o>pm['vah']:return 'TREND_BULL'
    if o<pw['val'] and o<pm['val']:return 'TREND_BEAR'
    if o>pm['vah']:return 'MONTHLY_BULL'
    if o<pm['val']:return 'MONTHLY_BEAR'
    if o>pw['vah']:return 'WEEKLY_BULL'
    if o<pw['val']:return 'WEEKLY_BEAR'
    return 'RANGE'

@dataclass
class Limit:
    setup:str; direction:int; zone:int; first_i:int; last_i:int; bounce:int=0; active:bool=True
@dataclass
class Position:
    setup:str; direction:int; entry:float; sl_ticks:int; tp_ticks:int; opened_at:str
    @property
    def stop(self): return self.entry-self.direction*self.sl_ticks*TICK
    @property
    def target(self): return self.entry+self.direction*self.tp_ticks*TICK

@dataclass
class Engine:
    bars:list=field(default_factory=list)              # recent M1 completed bars
    session_stats:dict=field(default_factory=dict)    # sid -> O/H/L/C, finalized lazily
    current_sid:str|None=None
    completed_sessions:list=field(default_factory=list)
    week_bars:dict=field(default_factory=dict)
    month_bars:dict=field(default_factory=dict)
    m30_bucket:str|None=None; m30_ohlc:dict|None=None
    day_open9:dict=field(default_factory=dict); day_context:dict=field(default_factory=dict)
    day_roll_hi:dict=field(default_factory=dict); day_roll_lo:dict=field(default_factory=dict)
    s2_index:int=0; s2_day:str|None=None; s2_hi:int|None=None; s2_lo:int|None=None; s2_extreme:dict|None=None
    pending_limits:list=field(default_factory=list); used_buckets:set=field(default_factory=set); lv2_filled:bool=False
    s3_pending:list=field(default_factory=list); positions:list=field(default_factory=list)
    last_ts:str|None=None
    mode:str='APEX'
    risk_day:str|None=None; risk_day_realized:float=0.0; risk_day_trades:int=0
    risk_equity:float=0.0; risk_peak:float=0.0; risk_start_dd:float=0.0; risk_base_budget:float=1400.0
    # Frozen S2 uses prior five completed 09:00-15:00 ET ranges, with the hard Berlin <20:00 cutoff.
    s2_daily_ranges:dict=field(default_factory=dict)


    RISK_MAP={'HV-1':150.0,'HV-2':150.0,'LV-1':80.0,'LV-2':80.0,'LV-3':80.0,
              'S3-A':1400.0,'S3-B':800.0,'S3-C':1000.0,'S3-D':1400.0}
    def set_mode(self,mode):
        mode=str(mode).upper()
        if mode not in {'APEX','EK'}: raise ValueError('TRADING_MODE must be APEX or EK')
        self.mode=mode
    def _risk_roll_day(self,d):
        if self.risk_day is None:
            self.risk_day=d; self.risk_start_dd=self.risk_equity-self.risk_peak; self._risk_set_base(); return
        if d!=self.risk_day:
            self.risk_equity += self.risk_day_realized; self.risk_peak=max(self.risk_peak,self.risk_equity)
            self.risk_day=d; self.risk_day_realized=0.0; self.risk_day_trades=0; self.risk_start_dd=self.risk_equity-self.risk_peak; self._risk_set_base()
    def _risk_set_base(self):
        # APEX 100K: fixed $1,400 nominal preventive risk budget.
        # Candidate risk excludes commission; realized PnL already includes the $7.20 round-trip fee.
        self.risk_base_budget=1400.0
    def _risk_effective_budget(self): return 1400.0
    def _risk_allow(self,setup):
        if self.mode=='EK': return True,'EK_UNLIMITED'
        if self.risk_day_trades>=9:return False,'APEX_MAX_9_TRADES'
        r=self.RISK_MAP[setup]; b=self._risk_effective_budget()
        return (self.risk_day_realized-r>=-b),('APEX_ALLOWED' if self.risk_day_realized-r>=-b else 'APEX_PREVENTIVE_RISK_GATE')
    def _risk_entry(self):
        if self.mode=='APEX': self.risk_day_trades+=1
    def _risk_exit(self,pnl):
        if self.mode=='APEX': self.risk_day_realized+=float(pnl)

    def _finalize_session(self,sid):
        s=self.session_stats.get(sid)
        if s and sid not in self.completed_sessions:
            s['range_ticks']=(s['H']-s['L'])*100; s['mom_ticks']=(s['C']-s['O'])*100; self.completed_sessions.append(sid)
            self.completed_sessions=self.completed_sessions[-20:]
    def _features(self):
        done=[self.session_stats[x] for x in self.completed_sessions if x in self.session_stats]
        atr=sum(x['range_ticks'] for x in done[-5:])/5 if len(done)>=5 else None
        pmom=done[-1]['mom_ticks'] if done else None
        return atr,pmom
    def _features_bd(self):
        done=[self.session_stats[x] for x in self.completed_sessions if x in self.session_stats]
        if not done:return None,None
        rr=[]
        for x in done[-5:]:
            H=f32(x['H']); L=f32(x['L'])
            rr.append(f32(f32(H-L)*100.0))
        atr=sum(rr)/5.0 if len(rr)>=5 else None
        x=done[-1]; pmom=f32(f32(f32(x['C'])-f32(x['O']))*100.0)
        return atr,pmom
    def _s2_atr5(self,current_ny_date):
        keys=sorted(k for k in self.s2_daily_ranges if k<current_ny_date)
        if len(keys)<5:return None
        return sum(self.s2_daily_ranges[k]['range_ticks'] for k in keys[-5:])/5.0
    def _finish_m30(self):
        if not self.m30_ohlc:return
        x=self.m30_ohlc; start=datetime.fromisoformat(x['start']).astimezone(NY)
        if 9<=start.hour<15:
            iso=start.isocalendar(); wk=f'{iso.year}-W{iso.week:02d}'; mo=f'{start.year}-{start.month:02d}'
            pair=(cents(x['low']),cents(x['high'])); self.week_bars.setdefault(wk,[]).append(pair);self.month_bars.setdefault(mo,[]).append(pair)
            d=start.date().isoformat();self.day_roll_hi[d]=max(self.day_roll_hi.get(d,pair[1]),pair[1]);self.day_roll_lo[d]=min(self.day_roll_lo.get(d,pair[0]),pair[0])
        self.m30_ohlc=None
    def _period_levels(self,t):
        iso=t.isocalendar(); cw=f'{iso.year}-W{iso.week:02d}'; cm=f'{t.year}-{t.month:02d}'
        ws=sorted(k for k in self.week_bars if k<cw); ms=sorted(k for k in self.month_bars if k<cm)
        return (value_area(self.week_bars[ws[-1]]) if ws else None,value_area(self.month_bars[ms[-1]]) if ms else None)
    def _direction(self,ctx): return 1 if ctx in BULL else -1 if ctx in BEAR else 0
    def _reset_s2_day(self,d):
        self.s2_day=d;self.s2_index=0;self.s2_hi=None;self.s2_lo=None;self.s2_extreme=None;self.pending_limits=[];self.used_buckets=set();self.lv2_filled=False
    def _s2_add(self,setup,d,z,first,active=True):
        bucket=int(round(z/50))*50
        if (setup,bucket) in self.used_buckets:return None
        if setup=='LV-2' and self.lv2_filled:return None
        if any(x.setup==setup and x.zone==z for x in self.pending_limits):return None
        L=Limit(setup,d,z,first,first+79,0,active);self.pending_limits.append(L)
        sl,tp=(15,15) if setup.startswith('HV') else (8,8)
        return {'kind':'S2_LIMIT','setup':setup,'direction':d,'entry':px(z),'sl_ticks':sl,'tp_ticks':tp,'valid_bars':80}
    def _eval_positions(self,bar):
        events=[]; h,l=bar['high'],bar['low']
        keep=[]
        bt=datetime.fromisoformat(bar['timestamp']).astimezone(BERLIN)
        for p in self.positions:
            opened_bt=datetime.fromisoformat(p.opened_at).astimezone(BERLIN)
            if bt.date()!=opened_bt.date() or bt.hour>=20:
                xp=bar['open'];pnl=p.direction*(xp-p.entry)*1000-FEE
                self._risk_exit(pnl); events.append({'kind':'PAPER_EXIT','setup':p.setup,'outcome':'berlin_date_or_20_flat','pnl_net':round(pnl,4)})
                continue
            stop=(p.direction==1 and l<=p.stop) or (p.direction==-1 and h>=p.stop)
            target=(p.direction==1 and h>=p.target) or (p.direction==-1 and l<=p.target)
            if stop or target:
                xp=p.stop if stop else p.target; pnl=p.direction*(xp-p.entry)*1000-FEE
                self._risk_exit(pnl); events.append({'kind':'PAPER_EXIT','setup':p.setup,'outcome':'stop' if stop else 'target','pnl_net':round(pnl,4)})
            else:keep.append(p)
        self.positions=keep;return events
    def _fill_s2(self,bar):
        events=[]; i=self.s2_index
        for L in list(self.pending_limits):
            if not(L.active and L.first_i<=i<=L.last_i):continue
            if bar['low']<=px(L.zone)<=bar['high']:
                allowed,reason=self._risk_allow(L.setup)
                if not allowed:
                    self.pending_limits.remove(L); events.append({'kind':'RISK_BLOCK','setup':L.setup,'reason':reason,'realized_day':round(self.risk_day_realized,4),'effective_budget':round(self._risk_effective_budget(),4)}); continue
                sl,tp=(15,15) if L.setup.startswith('HV') else (8,8);p=Position(L.setup,L.direction,px(L.zone),sl,tp,bar['timestamp'])
                self.positions.append(p);self._risk_entry();self.used_buckets.add((L.setup,int(round(L.zone/50))*50));self.pending_limits.remove(L)
                if L.setup=='LV-2':self.lv2_filled=True
                events.append({'kind':'S2_FILL','setup':L.setup,'direction':L.direction,'entry':p.entry,'sl':p.stop,'target':p.target,'trading_mode':self.mode})
        return events
    def warmup_m5(self,bar):
        """Historical context warm-up from a COMPLETED TradingView M5 bar.
        It updates only session OHLC and completed M30/weekly/monthly context.
        It never evaluates S2/S3 signals, limits, positions, or risk state.
        Use only strictly before the first M1 bootstrap timestamp.
        """
        ts=datetime.fromisoformat(bar['timestamp'])
        if ts.tzinfo is None: raise ValueError('timestamp must include timezone')
        ts=ts.astimezone(NY)
        o,h,l,c=map(float,(bar['open'],bar['high'],bar['low'],bar['close']))
        if not(l<=min(o,c)<=max(o,c)<=h): raise ValueError('invalid OHLC')
        sid=session_id(ts)
        if self.current_sid and sid!=self.current_sid:self._finalize_session(self.current_sid)
        self.current_sid=sid
        st=self.session_stats.setdefault(sid,{'O':o,'H':h,'L':l,'C':c})
        st['H']=max(st['H'],h);st['L']=min(st['L'],l);st['C']=c
        bstart=ts.replace(minute=(ts.minute//30)*30,second=0,microsecond=0); key=bstart.isoformat()
        if self.m30_bucket and key!=self.m30_bucket:self._finish_m30()
        if self.m30_ohlc is None:self.m30_bucket=key;self.m30_ohlc={'start':key,'high':h,'low':l}
        else:self.m30_ohlc['high']=max(self.m30_ohlc['high'],h);self.m30_ohlc['low']=min(self.m30_ohlc['low'],l)
        return {'timestamp':ts.isoformat(),'session':sid}

    def ingest(self,bar):
        ts=datetime.fromisoformat(bar['timestamp']);
        if ts.tzinfo is None:raise ValueError('timestamp must include timezone')
        ts=ts.astimezone(NY); bar={**bar,'timestamp':ts.isoformat(),'open':float(bar['open']),'high':float(bar['high']),'low':float(bar['low']),'close':float(bar['close'])}
        if self.last_ts and ts<=datetime.fromisoformat(self.last_ts):raise ValueError('bars must be strictly increasing')
        if not(bar['low']<=min(bar['open'],bar['close'])<=max(bar['open'],bar['close'])<=bar['high']):raise ValueError('invalid OHLC')
        sid=session_id(ts)
        if self.current_sid and sid!=self.current_sid:self._finalize_session(self.current_sid)
        self.current_sid=sid;s=self.session_stats.setdefault(sid,{'O':bar['open'],'H':bar['high'],'L':bar['low'],'C':bar['close']});s['H']=max(s['H'],bar['high']);s['L']=min(s['L'],bar['low']);s['C']=bar['close']
        # M30 aggregation, bucket by NY floor
        bstart=ts.replace(minute=(ts.minute//30)*30,second=0,microsecond=0); key=bstart.isoformat()
        if self.m30_bucket and key!=self.m30_bucket:self._finish_m30()
        if self.m30_ohlc is None:self.m30_bucket=key;self.m30_ohlc={'start':key,'high':bar['high'],'low':bar['low']}
        else:self.m30_ohlc['high']=max(self.m30_ohlc['high'],bar['high']);self.m30_ohlc['low']=min(self.m30_ohlc['low'],bar['low'])
        d=ts.date().isoformat(); self._risk_roll_day(d)
        if ts.hour==9 and d not in self.day_open9:
            self.day_open9[d]=bar['open'];pw,pm=self._period_levels(ts);self.day_context[d]=classify(bar['open'],pw,pm)
        ctx=self.day_context.get(d);atr,pmom=self._features();atr_bd,pmom_bd=self._features_bd()
        bt=ts.astimezone(BERLIN)
        if 9 <= ts.hour < 15 and bt.hour < 20 and bt.weekday()<5:
            ds=self.s2_daily_ranges.setdefault(d,{'H':bar['high'],'L':bar['low'],'range_ticks':0.0})
            ds['H']=max(ds['H'],bar['high']); ds['L']=min(ds['L'],bar['low'])
            ds['range_ticks']=(ds['H']-ds['L'])*100.0
        atr_s2=self._s2_atr5(d)
        events=[]
        # paper exits then S2 fills on this completed bar (stop-first is enforced in next evaluation for pre-existing positions)
        events+=self._eval_positions(bar)
        in_s2_window = 9 <= ts.hour < 15
        if in_s2_window and self.s2_day!=d:self._reset_s2_day(d)
        if in_s2_window: events+=self._fill_s2(bar)
        # newly filled positions: same-bar stop-first/blow-through
        events+=self._eval_positions(bar)
        # S3 pending signal enters at THIS bar open; this is paper/reconciliation only
        for q in self.s3_pending:
            allowed,reason=self._risk_allow(q['setup'])
            if not allowed:
                events.append({'kind':'RISK_BLOCK','setup':q['setup'],'reason':reason,'realized_day':round(self.risk_day_realized,4),'effective_budget':round(self._risk_effective_budget(),4)}); continue
            p=Position(q['setup'],q['direction'],bar['open'],q['sl_ticks'],q['tp_ticks'],bar['timestamp']);self.positions.append(p);self._risk_entry();events.append({'kind':'S3_PAPER_ENTRY','setup':p.setup,'direction':p.direction,'entry':p.entry,'sl':p.stop,'target':p.target,'trading_mode':self.mode})
        self.s3_pending=[];events+=self._eval_positions(bar)
        # only build signals once causal context/features exist and next minute is before Berlin cutoff
        if ctx and atr is not None and pmom is not None and berlin_entry_ok(ts+timedelta(minutes=1)):
            if in_s2_window and atr_s2 is not None: events+=self._s2_signals(bar,ctx,atr_s2,d)
            events+=self._s3_signals(bar,ctx,atr,pmom,atr_bd,pmom_bd)
        # S2 running extreme/index exist only inside authoritative 09:00-15:00 ET window
        if in_s2_window:
            zhi,zlo=cents(bar['high']),cents(bar['low']); nh=self.s2_hi is None or zhi>self.s2_hi;nl=self.s2_lo is None or zlo<self.s2_lo
            self.s2_extreme={'index':self.s2_index,'zone':zhi,'direction':1} if nh else {'index':self.s2_index,'zone':zlo,'direction':-1} if nl else None
            self.s2_hi=zhi if self.s2_hi is None else max(self.s2_hi,zhi);self.s2_lo=zlo if self.s2_lo is None else min(self.s2_lo,zlo);self.s2_index+=1
        self.bars.append(bar);self.bars=self.bars[-200:];self.last_ts=ts.isoformat()
        return {'timestamp':ts.isoformat(),'session':sid,'context':ctx,'atr5':atr,'prev_session_mom':pmom,'events':events}
    def _s2_signals(self,b,ctx,atr,dkey):
        ev=[];di=self._direction(ctx)
        if not di:return ev
        o,h,l,c=map(cents,(b['open'],b['high'],b['low'],b['close']));hv=atr>150;i=self.s2_index
        self.pending_limits=[x for x in self.pending_limits if i<=x.last_i]
        for x in self.pending_limits:
            if x.setup=='LV-2':
                fav=h-x.zone if x.direction==1 else x.zone-l;x.bounce=max(x.bounce,fav);x.active=x.active or x.bounce>=8
        base=int(round(cents(self.day_open9[dkey])/50))*50
        for z in [base+50*k for k in range(-10,11)]:
            th=10 if hv else 5
            ok=(di==1 and l<=z and c>z and c>o and h-z>=th) or (di==-1 and h>=z and c<z and c<o and z-l>=th)
            if ok:
                q=self._s2_add('HV-1' if hv else 'LV-1',di,z,i+1)
                if q:ev.append(q)
        if self.s2_extreme and self.s2_extreme['index']==i-1 and self.s2_extreme['direction']==di:
            z=self.s2_extreme['zone'];th=4 if hv else 0;ok=(di==1 and l<=z and c>z and c>o and h-z>=th) or (di==-1 and h>=z and c<z and c<o and z-l>=th)
            if ok:
                q=self._s2_add('HV-2' if hv else 'LV-3',di,z,i+1)
                if q:ev.append(q)
        if not hv and dkey in self.day_roll_hi and dkey in self.day_roll_lo:
            z=self.day_roll_lo[dkey] if di==1 else self.day_roll_hi[dkey];ok=(di==1 and l<=z and c>z and c>o) or (di==-1 and h>=z and c<z and c<o)
            if ok:
                q=self._s2_add('LV-2',di,z,i+1,False)
                if q:ev.append(q)
        return ev
    def _s3_signals(self,b,ctx,atr,pmom,atr_bd=None,pmom_bd=None):
        if ctx not in NON_TREND:return []
        bt=datetime.fromisoformat(b['timestamp']).astimezone(BERLIN)
        # Frozen S3 A/B/C/D signal window: 10:00 <= Berlin signal time < 20:00.
        if bt.weekday()>=5 or bt.hour<10 or bt.hour>=20:return []
        hist=self.bars
        o,h,l,c=b['open'],b['high'],b['low'],b['close']
        rng=max(h-l,1e-12); body=abs(c-o)/rng; out=[]
        def emit(name,d,sl,tp):
            # Frozen S3 execution: one open trade per setup; other setups may overlap.
            if any(p.setup==name for p in self.positions): return
            if any(q.get('setup')==name for q in self.s3_pending): return
            q={'kind':'S3_SIGNAL','setup':name,'direction':d,'entry_rule':'NEXT_M1_OPEN','sl_ticks':sl,'tp_ticks':tp}
            out.append(q);self.s3_pending.append(q)

        # A: float64/raw-master branch
        if 100<atr<=150 and len(hist)>=6 and body>=.8:
            ph=max(x['high'] for x in hist[-6:]);pl=min(x['low'] for x in hist[-6:])
            if c>ph and c>o:emit('S3-A',1,140,60)
            elif c<pl and c<o:emit('S3-A',-1,140,60)

        # B: frozen B/D research cache was float32. Reproduce its exact threshold semantics.
        if atr_bd is not None and pmom_bd is not None and 150<atr_bd<=200 and abs(pmom_bd)<40 and len(hist)>=7:
            o32,c32,h32,l32=map(f32,(o,c,h,l))
            den=f32(max(f32(h32-l32),f32(1e-9)))
            body32=f32(f32(abs(f32(c32-o32)))/den)
            c1=f32(hist[-1]['close']); c7=f32(hist[-7]['close'])
            mom=f32(f32(c1-c7)*100.0)
            if body32>=f32(.5):
                if mom>=f32(12) and c32>o32:emit('S3-B',1,80,25)
                elif mom<=f32(-12) and c32<o32:emit('S3-B',-1,80,25)

        # C: float64/raw-master branch
        if atr>200 and len(hist)>=24 and body>=.2:
            ph=max(x['high'] for x in hist[-24:]);pl=min(x['low'] for x in hist[-24:])
            if l<=pl-.05 and c>pl and c>o and pmom<=-30:emit('S3-C',1,100,45)
            elif h>=ph+.05 and c<ph and c<o and pmom>=30:emit('S3-C',-1,100,45)

        # D: same float32 provenance as frozen B.
        if atr_bd is not None and pmom_bd is not None and atr_bd>400 and len(hist)>=5:
            o32,c32,h32,l32=map(f32,(o,c,h,l))
            den=f32(max(f32(h32-l32),f32(1e-9)))
            body32=f32(f32(abs(f32(c32-o32)))/den)
            c1=f32(hist[-1]['close']); c5=f32(hist[-5]['close'])
            mom=f32(f32(c1-c5)*100.0)
            if body32>=f32(.8):
                if mom>=f32(20) and c32>o32 and pmom_bd>=f32(60):emit('S3-D',1,140,45)
                elif mom<=f32(-20) and c32<o32 and pmom_bd<=f32(-60):emit('S3-D',-1,140,45)
        return out


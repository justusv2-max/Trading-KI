"""
System 1 + System 2 | CL Futures M5 | Railway Server v3.0
==========================================================
1:1 Backtest Logik!

SESSIONS:
- EU Session: 09:00-15:30 MESZ (02:00-08:30 CT)
- US Session: 15:30-21:00 MESZ (08:30-14:00 CT)

ZONE LOCK (wie Backtest!):
- Pre-Session: NUR Lookback Buffer, KEIN Lock, KEIN Signal
- In Session:  Zone Lock + Signal + Telegram ✅
"""

from flask import Flask, request, jsonify
import json, os, datetime, time as time_module
from collections import deque
from zoneinfo import ZoneInfo

app = Flask(__name__)

TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
CET = ZoneInfo("Europe/Berlin")

# Parameter (identisch Backtest!)
MM=0.08; SB=0.05; MR=1.00; MAX_TICKS=15
CRV_S1=1.5; CRV_S2=1.0; LOOKBACK=12
ATR_MAX=0.30; ATR_LEN=14; MOM_THRESH=2.5
MOM_DAYS=20; ZONE_LOCK_B=96; LEVEL_TOL=0.05
COMM=7.80

# Session CT Minuten
EU_START=2*60+0; EU_END=8*60+30
US_START=8*60+30; US_END=14*60+0

# Initial-Daten (aus TradingView CSV, bis 02.09.2026)
INITIAL_DAYS=[
    {"date":"2026-07-30","h":85.94,"l":81.6,"c":81.66},
    {"date":"2026-07-31","h":86.87,"l":81.06,"c":86.8},
    {"date":"2026-08-02","h":81.3,"l":78.78,"c":79.52},
    {"date":"2026-08-03","h":81.3,"l":78.43,"c":81.23},
    {"date":"2026-08-04","h":82.33,"l":74.24,"c":75.15},
    {"date":"2026-08-05","h":76.7,"l":74.45,"c":74.81},
    {"date":"2026-08-06","h":78.77,"l":74.57,"c":78.32},
    {"date":"2026-08-07","h":78.5,"l":76.53,"c":77.08},
    {"date":"2026-08-09","h":79.43,"l":78.18,"c":78.45},
    {"date":"2026-08-10","h":82.52,"l":77.79,"c":82.24},
    {"date":"2026-08-11","h":84.61,"l":81.27,"c":83.7},
    {"date":"2026-08-12","h":84.1,"l":81.9,"c":83.0},
    {"date":"2026-08-13","h":83.3,"l":80.09,"c":81.38},
    {"date":"2026-08-14","h":82.99,"l":80.76,"c":82.4},
    {"date":"2026-08-16","h":83.04,"l":81.72,"c":82.15},
    {"date":"2026-08-17","h":85.04,"l":81.5,"c":84.34},
    {"date":"2026-08-18","h":85.14,"l":83.78,"c":84.61},
    {"date":"2026-08-19","h":85.84,"l":83.45,"c":84.47},
    {"date":"2026-08-20","h":87.69,"l":84.33,"c":86.24},
    {"date":"2026-08-21","h":87.51,"l":85.8,"c":86.64},
    {"date":"2026-08-23","h":86.57,"l":84.84,"c":85.61},
    {"date":"2026-08-24","h":86.24,"l":84.36,"c":85.08},
    {"date":"2026-08-25","h":85.09,"l":80.08,"c":80.61},
    {"date":"2026-08-26","h":83.31,"l":79.62,"c":81.83},
    {"date":"2026-08-27","h":84.27,"l":80.65,"c":83.27},
    {"date":"2026-08-28","h":83.71,"l":82.25,"c":83.44},
    {"date":"2026-08-30","h":85.69,"l":84.11,"c":85.35},
    {"date":"2026-08-31","h":87.09,"l":84.47,"c":87.0},
    {"date":"2026-09-01","h":92.29,"l":86.22,"c":90.54},
    {"date":"2026-09-02","h":91.48,"l":88.97,"c":90.57},
]

# Session Check
def get_ct_min(ts):
    dt=datetime.datetime.fromtimestamp(ts,tz=ZoneInfo("America/Chicago"))
    return dt.hour*60+dt.minute

def in_eu(ts): ct=get_ct_min(ts); return EU_START<=ct<EU_END
def in_us(ts): ct=get_ct_min(ts); return US_START<=ct<=US_END
def in_sess(ts): return in_eu(ts) or in_us(ts)
def is_weekday(ts):
    return datetime.datetime.fromtimestamp(ts,tz=CET).weekday()<5

# Bar Buffer (24h für Lookback!)
class BarBuffer:
    def __init__(self): self.bars=deque(maxlen=500)
    def add(self,o,h,l,c,v,ts): self.bars.append({'o':o,'h':h,'l':l,'c':c,'v':v,'ts':ts})
    def get(self,f): return [b[f] for b in self.bars]
    def size(self): return len(self.bars)

bar_buffer=BarBuffer()

def calc_atr():
    h=bar_buffer.get('h'); l=bar_buffer.get('l'); c=bar_buffer.get('c')
    if len(h)<ATR_LEN+1: return None
    trs=[max(h[i]-l[i],abs(h[i]-c[i-1]),abs(l[i]-c[i-1])) for i in range(1,len(h))]
    return sum(trs[-ATR_LEN:])/ATR_LEN

# Daily Cache
CACHE_FILE="daily_cache.json"

class DailyCache:
    def __init__(self):
        self.days=[]; self.cur_day=None
        self.cur_h=-999; self.cur_l=999; self.cur_c=None

    def update(self,ts,h,l,c):
        dt=datetime.datetime.fromtimestamp(ts,tz=CET)
        day=dt.date().isoformat()
        if self.cur_day is None: self.cur_day=day
        if day!=self.cur_day:
            if self.cur_c is not None:
                self.days.append({'date':self.cur_day,'h':self.cur_h,'l':self.cur_l,'c':self.cur_c})
                if len(self.days)>50: self.days=self.days[-50:]
                save_cache()
            self.cur_day=day; self.cur_h=h; self.cur_l=l; self.cur_c=c
        else:
            self.cur_h=max(self.cur_h,h); self.cur_l=min(self.cur_l,l); self.cur_c=c

    def get_momentum(self):
        if len(self.days)<MOM_DAYS+1: return None,None,False,False
        cp=self.days[-1]['c']; cn=self.days[-(MOM_DAYS+1)]['c']
        atr_d=sum(d['h']-d['l'] for d in self.days[-ATR_LEN:])/ATR_LEN
        if atr_d<=0: return None,None,False,False
        mom=abs(cp-cn)/atr_d; up=cp>cn
        return mom,up,mom<=MOM_THRESH,mom>MOM_THRESH

daily_cache=DailyCache()

def save_cache():
    try:
        with open(CACHE_FILE,'w') as f: json.dump(daily_cache.days,f)
    except: pass

def auto_init():
    try:
        with open(CACHE_FILE,'r') as f: daily_cache.days=json.load(f)[-50:]
        print(f"[CACHE] {len(daily_cache.days)} Tage geladen")
    except:
        daily_cache.days=[dict(d) for d in INITIAL_DAYS]
        save_cache()
        print(f"[CACHE] Initial-Daten: {len(daily_cache.days)} Tage")
    mom,up,s1,s2=daily_cache.get_momentum()
    if mom: print(f"[INIT] ATR-Mom:{mom:.2f}x | {'S1' if s1 else 'S2'} | {'UP' if up else 'DOWN'}")

auto_init()

# Zone Lock (NUR in Session registrieren!)
class ZoneLock:
    def __init__(self): self.ll=[]; self.sl=[]; self.bar=0
    def tick(self):
        self.bar+=1
        self.ll=[(l,e) for l,e in self.ll if e>self.bar]
        self.sl=[(l,e) for l,e in self.sl if e>self.bar]
    def locked_long(self,lv): return any(abs(l-lv)<=LEVEL_TOL for l,_ in self.ll)
    def locked_short(self,lv): return any(abs(l-lv)<=LEVEL_TOL for l,_ in self.sl)
    def reg_long(self,lv): self.ll.append((lv,self.bar+ZONE_LOCK_B))
    def reg_short(self,lv): self.sl.append((lv,self.bar+ZONE_LOCK_B))
    def status(self): return {
        'long_count':len(self.ll),'short_count':len(self.sl),
        'long_levels':[round(l,2) for l,_ in self.ll],
        'short_levels':[round(l,2) for l,_ in self.sl]}

zl=ZoneLock()

# Signal Erkennung (1:1 Backtest!)
def detect(in_session,s1_ok,s2_ok,trend_up,atr_m5):
    if atr_m5 is None or atr_m5>ATR_MAX: return []
    bh=bar_buffer.get('h'); bl=bar_buffer.get('l'); bc=bar_buffer.get('c')
    if len(bc)<LOOKBACK+3: return []
    close=bc[-1]; sigs=[]

    def check_long(system,crv):
        for k in range(2,LOOKBACK+1):
            il=-(k+2); ie=-(k+1)
            if abs(il)>len(bl) or abs(ie)>len(bl): break
            liq=bl[il]; extr=bl[ie]
            if extr<liq and close>=liq+MM:
                en=liq; st=extr-SB; rk=en-st; tks=round(rk/0.01)
                if 0<rk<=MR and tks<=MAX_TICKS:
                    if not zl.locked_long(en):
                        if in_session:
                            zl.reg_long(en)
                            sigs.append({'system':system,'dir':'LONG',
                                'entry':round(en,2),'stop':round(st,2),
                                'target':round(en+rk*crv,2),
                                'risk_ticks':tks,'crv':crv})
                        break
                    else: break

    def check_short(system,crv):
        for k in range(2,LOOKBACK+1):
            il=-(k+2); ie=-(k+1)
            if abs(il)>len(bh) or abs(ie)>len(bh): break
            liq=bh[il]; extr=bh[ie]
            if extr>liq and close<=liq-MM:
                en=liq; st=extr+SB; rk=st-en; tks=round(rk/0.01)
                if 0<rk<=MR and tks<=MAX_TICKS:
                    if not zl.locked_short(en):
                        if in_session:
                            zl.reg_short(en)
                            sigs.append({'system':system,'dir':'SHORT',
                                'entry':round(en,2),'stop':round(st,2),
                                'target':round(en-rk*crv,2),
                                'risk_ticks':tks,'crv':crv})
                        break
                    else: break

    if s1_ok:
        check_long('S1',CRV_S1)
        check_short('S1',CRV_S1)
    if s2_ok:
        if trend_up: check_long('S2',CRV_S2)
        else: check_short('S2',CRV_S2)

    return sigs

# Telegram
def send_tg(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"[TG] {msg}"); return False
    import urllib.request
    try:
        data=json.dumps({"chat_id":TELEGRAM_CHAT_ID,"text":msg,"parse_mode":"HTML"}).encode()
        req=urllib.request.Request(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data=data,headers={"Content-Type":"application/json"})
        with urllib.request.urlopen(req,timeout=5) as r: return r.status==200
    except Exception as e: print(f"[TG] Fehler:{e}"); return False

def fmt_signal(sig,mom,atr,sess):
    now=datetime.datetime.now(CET).strftime("%H:%M")
    d=sig['dir']; s=sig['system']
    em="🟢" if d=="LONG" else "🔴"
    ar="▲" if d=="LONG" else "▼"
    risk=sig['risk_ticks']*10
    rew=round(sig['risk_ticks']*sig['crv']*10)
    rewt=round(sig['risk_ticks']*sig['crv'])
    sl=f"{'1 (Seitwärts)' if s=='S1' else '2 (Trend)'}"
    return (f"{em} <b>System {sl} | {d} {ar}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📍 Entry:  <b>${sig['entry']:.2f}</b>\n"
            f"🛑 Stop:   <b>${sig['stop']:.2f}</b> (-{sig['risk_ticks']}T/-${risk})\n"
            f"🎯 Target: <b>${sig['target']:.2f}</b> (+{rewt}T/+${rew})\n"
            f"📊 CRV 1:{sig['crv']} | ATR-Mom:{mom:.1f}× | ATR:${atr:.3f}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🕐 {now} MEZ | {sess} | CL M5")

# Stats
stats={'bars':0,'signals':[],'wins':0,'losses':0,'last_bar':None}

# Webhook
@app.route("/webhook",methods=["POST"])
def webhook():
    try:
        data=json.loads(request.get_data(as_text=True))
        o=float(data['o']); h=float(data['h'])
        l=float(data['l']); c=float(data['c'])
        v=float(data.get('v',0))
        ts=float(data.get('t',time_module.time()))

        if not is_weekday(ts):
            return jsonify({"status":"ok","message":"Weekend"}),200

        # Buffer immer füllen (24h für Lookback!)
        bar_buffer.add(o,h,l,c,v,ts)
        zl.tick()
        stats['bars']+=1

        # Daily Cache
        daily_cache.update(ts,h,l,c)

        # Session
        eu=in_eu(ts); us=in_us(ts); sess=eu or us
        sess_name="EU Session" if eu else ("US Session" if us else "")
        stats['last_bar']={'o':o,'h':h,'l':l,'c':c,
            'ts':datetime.datetime.fromtimestamp(ts,tz=CET).strftime("%H:%M MEZ"),
            'session':sess_name if sess else "Pre-Session"}

        # Momentum
        mom,up,s1,s2=daily_cache.get_momentum()
        if mom is None:
            return jsonify({"status":"ok","message":f"Warming up ({len(daily_cache.days)}T)"}),200

        # ATR
        atr=calc_atr()
        if atr is None:
            return jsonify({"status":"ok","message":"ATR warming up"}),200

        # Pre-Session: NUR Buffer, kein Signal!
        if not sess:
            return jsonify({"status":"ok","message":"Pre-Session: buffer only",
                "mom_atr":round(mom,2),"atr_m5":round(atr,3)}),200

        # Signale (nur in Session)
        sigs=detect(sess,s1,s2,up,atr)
        sent=[]
        for sig in sigs:
            msg=fmt_signal(sig,mom,atr,sess_name)
            send_tg(msg)
            stats['signals'].append({
                'time':datetime.datetime.fromtimestamp(ts,tz=CET).strftime("%H:%M"),
                'system':sig['system'],'dir':sig['dir'],
                'entry':sig['entry'],'stop':sig['stop'],
                'target':sig['target'],'session':sess_name})
            sent.append(f"{sig['system']} {sig['dir']} {sig['entry']}")
            print(f"[SIGNAL] {sess_name}|{sig['system']} {sig['dir']} {sig['entry']}")

        return jsonify({"status":"ok","session":sess_name,
            "mom_atr":round(mom,2),"atr_m5":round(atr,3),
            "s1":s1,"s2":s2,"trend_up":up,
            "signals":sent,"zone_lock":zl.status()}),200

    except Exception as e:
        print(f"[WEBHOOK] {e}")
        return jsonify({"status":"error","message":str(e)}),500

@app.route("/daily",methods=["POST"])
def daily():
    try:
        data=json.loads(request.get_data(as_text=True))
        h=float(data['h']); l=float(data['l']); c=float(data['c'])
        date=data.get('date',datetime.datetime.now(CET).date().isoformat())
        daily_cache.days.append({'date':date,'h':h,'l':l,'c':c})
        if len(daily_cache.days)>50: daily_cache.days=daily_cache.days[-50:]
        save_cache()
        mom,up,s1,s2=daily_cache.get_momentum()
        print(f"[DAILY] {date} C:{c} Mom:{mom:.2f}x")
        if mom:
            sys="S1 Seitwärts" if s1 else "S2 Trend"
            dir_="UP 📈" if up else "DOWN 📉"
            send_tg(f"📅 <b>Tagesabschluss {date}</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"💰 Close: ${c:.2f}\n"
                    f"📊 ATR-Mom: {mom:.2f}×\n"
                    f"{'✅ Morgen: System 1' if s1 else '📈 Morgen: System 2'}\n"
                    f"Trend: {dir_}")
        stats['signals']=[]; stats['wins']=0; stats['losses']=0
        return jsonify({"status":"ok","date":date,
            "mom_atr":round(mom,2) if mom else None,
            "system":"S1" if s1 else "S2"}),200
    except Exception as e:
        return jsonify({"status":"error","message":str(e)}),500

@app.route("/outcome/<result>",methods=["POST"])
def outcome(result):
    if result not in ["win","loss"]: return jsonify({"status":"error"}),400
    if result=="win": stats['wins']+=1; em="✅"
    else: stats['losses']+=1; em="❌"
    tot=stats['wins']+stats['losses']
    tq=stats['wins']/tot*100 if tot>0 else 0
    now=datetime.datetime.now(CET).strftime("%H:%M")
    send_tg(f"{em} <b>Trade {result.upper()}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 Heute: {stats['wins']}W/{stats['losses']}L ({tq:.0f}% TQ)\n"
            f"🕐 {now} MEZ")
    return jsonify({"status":"ok","tq":round(tq,1)}),200

@app.route("/status",methods=["GET"])
def status():
    now=datetime.datetime.now(CET)
    mom,up,s1,s2=daily_cache.get_momentum()
    tot=stats['wins']+stats['losses']
    tq=stats['wins']/tot*100 if tot>0 else 0
    return jsonify({
        "status":"online","system":"System 1+2 CL Futures M5","version":"3.0",
        "time_cet":now.strftime("%H:%M MEZ"),
        "daily_cache":{"days":len(daily_cache.days),"ready":mom is not None,
            "mom_atr":round(mom,2) if mom else None,"sideway":s1,"trend":s2,"trend_up":up},
        "atr_filter":f"< {ATR_MAX}$",
        "sessions":{"eu":"09:00-15:30 MESZ","us":"15:30-21:00 MESZ"},
        "bars_received":stats['bars'],"last_bar":stats['last_bar'],
        "zone_lock":zl.status(),
        "today":{"signals":len(stats['signals']),"wins":stats['wins'],
            "losses":stats['losses'],"tq_pct":round(tq,1)},
        "signals_today":stats['signals'][-10:]}),200

@app.route("/reset",methods=["POST"])
def reset():
    stats['signals']=[]; stats['wins']=0; stats['losses']=0
    send_tg("🔄 <b>System 1+2 CL v3.0</b> – Reset")
    return jsonify({"status":"ok"}),200

@app.route("/test",methods=["GET","POST"])
def test():
    now=datetime.datetime.now(CET).strftime("%H:%M")
    mom,up,s1,s2=daily_cache.get_momentum()
    sys="S1 Seitwärts" if s1 else "S2 Trend"
    success=send_tg(f"🧪 <b>System 1+2 CL v3.0</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ Server Online\n"
        f"📊 Cache: {len(daily_cache.days)} Tage\n"
        f"📈 ATR-Mom: {mom:.2f}× → {sys}\n"
        f"🕐 {now} MEZ\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"EU: 09:00-15:30 MESZ ✅\n"
        f"US: 15:30-21:00 MESZ ✅\n"
        f"Zone Lock: NUR in Session ✅")
    return jsonify({"status":"ok","telegram":"ok" if success else "error"}),200

@app.route("/",methods=["GET"])
def health():
    return jsonify({"status":"online","system":"System 1+2 CL","version":"3.0"}),200

if __name__=="__main__":
    port=int(os.environ.get("PORT",5000))
    print(f"Server v3.0 | EU+US Session | Zone Lock 1:1 Backtest")
    app.run(host="0.0.0.0",port=port,debug=False)

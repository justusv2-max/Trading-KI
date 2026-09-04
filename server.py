"""
CL Futures M5 | System 1+2 | Server v5.0
=========================================
REGELN (1:1 Backtest):
- EU Session: 09:00-15:30 MESZ (02:00-08:30 CT)
- US Session: 15:30-21:00 MESZ (08:30-14:00 CT)
- Pre-Session: NUR Buffer füllen, KEIN Signal, KEIN Zone Lock
- Zone Lock: 8h (96 Bars), NUR in Session registrieren
- System 1: ATR-Mom <= 2.5x, LONG+SHORT, CRV 1.5R
- System 2: ATR-Mom > 2.5x, NUR Trendrichtung, CRV 1.0R
- ATR M5 Filter: < $0.30
- Auto-Reset: täglich bei erster Kerze des neuen Tages
- Daily Cache: täglich per /daily Endpoint aktualisiert
"""

from flask import Flask, request, jsonify
import json, os, datetime, time as time_module
from collections import deque
from zoneinfo import ZoneInfo

app = Flask(__name__)
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
CET = ZoneInfo("Europe/Berlin")
CT  = ZoneInfo("America/Chicago")

# ─── PARAMETER ────────────────────────────────────────────
MM          = 0.08   # Min Momentum Entry
SB          = 0.05   # Stop Buffer
MAX_RISK    = 1.00   # Max Risiko $
MAX_TICKS   = 15     # Max Stop Ticks
CRV_S1      = 1.5
CRV_S2      = 1.0
LOOKBACK    = 12     # Kerzen zurück
ATR_MAX     = 0.30   # Max ATR M5
ATR_LEN     = 14     # ATR Periode
MOM_THRESH  = 2.5    # Momentum Schwelle
MOM_WINDOW  = 20     # Momentum Fenster (Tage)
ZONE_BARS   = 96     # Zone Lock (8h)
LEVEL_TOL   = 0.05   # Level Toleranz

# Session in CT Minuten
EU_S = 2*60          # 02:00 CT = 09:00 MESZ
EU_E = 8*60+30       # 08:30 CT = 15:30 MESZ
US_S = 8*60+30       # 08:30 CT = 15:30 MESZ
US_E = 14*60         # 14:00 CT = 21:00 MESZ

# ─── INITIAL DATEN (TV CSV bis 03.09.2026) ────────────────
INITIAL_DAYS = [
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
    {"date":"2026-09-03","h":93.14,"l":89.57,"c":91.61},
]

# ─── SESSION CHECK ─────────────────────────────────────────
def ct_min(ts):
    dt = datetime.datetime.fromtimestamp(ts, tz=CT)
    return dt.hour * 60 + dt.minute

def in_eu(ts):  return EU_S <= ct_min(ts) <  EU_E
def in_us(ts):  return US_S <= ct_min(ts) <= US_E
def in_any(ts): return in_eu(ts) or in_us(ts)
def weekday(ts): return datetime.datetime.fromtimestamp(ts, tz=CT).weekday() < 5
def ct_date(ts): return datetime.datetime.fromtimestamp(ts, tz=CT).date()

# ─── BAR BUFFER (24h für Lookback) ────────────────────────
bars = deque(maxlen=600)

def add_bar(o,h,l,c,v):
    bars.append({'o':o,'h':h,'l':l,'c':c,'v':v})

def atr_m5():
    if len(bars) < ATR_LEN + 1: return None
    b = list(bars)
    trs = [max(b[i]['h']-b[i]['l'],
               abs(b[i]['h']-b[i-1]['c']),
               abs(b[i]['l']-b[i-1]['c'])) for i in range(1,len(b))]
    return sum(trs[-ATR_LEN:]) / ATR_LEN

# ─── DAILY CACHE ───────────────────────────────────────────
CACHE = "daily_cache.json"
days  = []   # Liste von {date, h, l, c}

def save():
    try:
        with open(CACHE,'w') as f: json.dump(days, f)
    except: pass

def load():
    global days
    try:
        with open(CACHE,'r') as f: days = json.load(f)
        days = days[-50:]
        print(f"[CACHE] {len(days)} Tage geladen | letzter: {days[-1]['date']}")
    except:
        days = [dict(d) for d in INITIAL_DAYS]
        save()
        print(f"[CACHE] Initial: {len(days)} Tage | letzter: {days[-1]['date']}")

def add_day(date, h, l, c):
    """Fügt Tag hinzu oder aktualisiert letzten Tag"""
    if days and days[-1]['date'] == date:
        days[-1] = {'date':date,'h':h,'l':l,'c':c}
    else:
        days.append({'date':date,'h':h,'l':l,'c':c})
    if len(days) > 50: days[:] = days[-50:]
    save()
    print(f"[DAILY] {date} H:{h} L:{l} C:{c} | Cache: {len(days)} Tage")

def momentum():
    """
    Exakt wie Backtest:
    close[1]  = days[-1]['c']   (gestriger Close)
    close[21] = days[-21]['c']  (Close vor 20 Tagen)
    ATR Daily = letzte 14 Tage H-L
    """
    if len(days) < 22: return None, None, False, False
    cp  = days[-1]['c']
    cn  = days[-21]['c']
    atr = sum(d['h']-d['l'] for d in days[-14:]) / 14
    if atr <= 0: return None, None, False, False
    mom = abs(cp - cn) / atr
    up  = cp > cn
    return mom, up, mom <= MOM_THRESH, mom > MOM_THRESH

load()

# ─── ZONE LOCK ─────────────────────────────────────────────
long_zones  = []   # (level, expire_bar)
short_zones = []
bar_num     = 0

def zone_tick():
    global long_zones, short_zones
    long_zones  = [(l,e) for l,e in long_zones  if e > bar_num]
    short_zones = [(l,e) for l,e in short_zones if e > bar_num]

def zone_locked_long(lv):
    return any(abs(l-lv) <= LEVEL_TOL for l,_ in long_zones)

def zone_locked_short(lv):
    return any(abs(l-lv) <= LEVEL_TOL for l,_ in short_zones)

def zone_add_long(lv):
    long_zones.append((lv, bar_num + ZONE_BARS))

def zone_add_short(lv):
    short_zones.append((lv, bar_num + ZONE_BARS))

def zone_reset():
    long_zones.clear()
    short_zones.clear()
    print("[ZONE] Zone Lock resettet")

# ─── TAGES-RESET ───────────────────────────────────────────
current_date = None
sig_today    = []
wins_today   = 0
losses_today = 0

def check_new_day(ts):
    global current_date, sig_today, wins_today, losses_today
    d = ct_date(ts)
    if current_date is None:
        current_date = d
        return
    if d != current_date:
        print(f"[DAY] Neuer Tag: {d}")
        current_date = d
        sig_today    = []
        wins_today   = 0
        losses_today = 0
        zone_reset()

# ─── SIGNAL ERKENNUNG ──────────────────────────────────────
def find_signals(in_session, s1, s2, up, atr):
    if atr is None or atr > ATR_MAX: return []
    b = list(bars)
    if len(b) < LOOKBACK + 3: return []
    close = b[-1]['c']
    sigs  = []

    def long_signal(sys, crv):
        for k in range(2, LOOKBACK+1):
            i_liq  = -(k+2)
            i_extr = -(k+1)
            if abs(i_liq) > len(b): break
            liq  = b[i_liq]['l']
            extr = b[i_extr]['l']
            if extr < liq and close >= liq + MM:
                en = liq
                st = extr - SB
                rk = en - st
                tk = round(rk / 0.01)
                if 0 < rk <= MAX_RISK and tk <= MAX_TICKS:
                    if not zone_locked_long(en):
                        if in_session:
                            zone_add_long(en)
                            sigs.append({
                                'system': sys, 'dir': 'LONG',
                                'entry':  round(en, 2),
                                'stop':   round(st, 2),
                                'target': round(en + rk*crv, 2),
                                'ticks':  tk, 'crv': crv
                            })
                        break
                    else:
                        break  # Level gesperrt → nächste Kerze

    def short_signal(sys, crv):
        for k in range(2, LOOKBACK+1):
            i_liq  = -(k+2)
            i_extr = -(k+1)
            if abs(i_liq) > len(b): break
            liq  = b[i_liq]['h']
            extr = b[i_extr]['h']
            if extr > liq and close <= liq - MM:
                en = liq
                st = extr + SB
                rk = st - en
                tk = round(rk / 0.01)
                if 0 < rk <= MAX_RISK and tk <= MAX_TICKS:
                    if not zone_locked_short(en):
                        if in_session:
                            zone_add_short(en)
                            sigs.append({
                                'system': sys, 'dir': 'SHORT',
                                'entry':  round(en, 2),
                                'stop':   round(st, 2),
                                'target': round(en - rk*crv, 2),
                                'ticks':  tk, 'crv': crv
                            })
                        break
                    else:
                        break

    if s1:
        long_signal('S1', CRV_S1)
        short_signal('S1', CRV_S1)
    if s2:
        if up:  long_signal('S2',  CRV_S2)
        else:   short_signal('S2', CRV_S2)

    return sigs

# ─── TELEGRAM ──────────────────────────────────────────────
def tg(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"[TG] {msg[:80]}")
        return False
    import urllib.request
    try:
        d = json.dumps({"chat_id":TELEGRAM_CHAT_ID,"text":msg,"parse_mode":"HTML"}).encode()
        r = urllib.request.Request(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data=d, headers={"Content-Type":"application/json"})
        with urllib.request.urlopen(r, timeout=5) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"[TG] {e}")
        return False

def fmt(sig, mom, atr, sess):
    now  = datetime.datetime.now(CET).strftime("%H:%M")
    em   = "🟢" if sig['dir']=="LONG" else "🔴"
    ar   = "▲"  if sig['dir']=="LONG" else "▼"
    risk = sig['ticks'] * 10
    rew  = round(sig['ticks'] * sig['crv'] * 10)
    rewt = round(sig['ticks'] * sig['crv'])
    name = "1 (Seitwärts)" if sig['system']=="S1" else "2 (Trend)"
    return (
        f"{em} <b>System {name} | {sig['dir']} {ar}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📍 Entry:  <b>${sig['entry']:.2f}</b>\n"
        f"🛑 Stop:   <b>${sig['stop']:.2f}</b>  (-{sig['ticks']}T / -${risk})\n"
        f"🎯 Target: <b>${sig['target']:.2f}</b>  (+{rewt}T / +${rew})\n"
        f"📊 CRV 1:{sig['crv']} | ATR-Mom:{mom:.1f}× | ATR:${atr:.3f}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🕐 {now} MEZ | {sess} | CL M5"
    )

# ─── ENDPOINTS ─────────────────────────────────────────────

@app.route("/webhook", methods=["POST"])
def webhook():
    global bar_num
    try:
        raw = request.get_data(as_text=True)
        print(f"[RECV] {raw[:200]}")
        if not raw or not raw.strip():
            return jsonify({"status":"ok","msg":"empty body"}), 200
        try:
            d = json.loads(raw)
        except Exception as je:
            print(f"[JSON ERR] {je} | raw: {raw[:100]}")
            return jsonify({"status":"ok","msg":"json parse error"}), 200
        o  = float(d.get('o', d.get('open', 0)))
        h  = float(d.get('h', d.get('high', 0)))
        l  = float(d.get('l', d.get('low', 0)))
        c  = float(d.get('c', d.get('close', 0)))
        v  = float(d.get('v', d.get('volume', 0)))
        # Timestamp: Server nutzt eigene Zeit (CET→CT konvertiert)
        ts = time_module.time()
        if o==0 and h==0 and l==0 and c==0:
            return jsonify({"status":"ok","msg":"invalid prices"}), 200

        if not weekday(ts):
            return jsonify({"status":"ok","msg":"weekend"}), 200

        # Neuen Tag erkennen → Auto Reset
        check_new_day(ts)

        # Bar immer hinzufügen (24h Buffer für Lookback!)
        add_bar(o, h, l, c, v)
        bar_num += 1
        zone_tick()

        # Session
        sess = "EU Session" if in_eu(ts) else ("US Session" if in_us(ts) else "")
        in_session = in_any(ts)

        # Momentum
        mom, up, s1, s2 = momentum()
        if mom is None:
            return jsonify({"status":"ok","msg":f"warming up ({len(days)} days)"}), 200

        # ATR
        atr = atr_m5()
        if atr is None:
            return jsonify({"status":"ok","msg":"atr warming up"}), 200

        # Pre-Session → NUR Buffer, kein Signal!
        if not in_session:
            return jsonify({
                "status": "ok", "msg": "pre-session buffer only",
                "mom_atr": round(mom,2), "atr_m5": round(atr,3)
            }), 200

        # Signale suchen
        signals = find_signals(in_session, s1, s2, up, atr)
        for sig in signals:
            tg(fmt(sig, mom, atr, sess))
            sig_today.append({
                "time":   datetime.datetime.fromtimestamp(ts,tz=CET).strftime("%H:%M"),
                "system": sig['system'], "dir": sig['dir'],
                "entry":  sig['entry'], "stop": sig['stop'],
                "target": sig['target'], "session": sess
            })
            print(f"[SIG] {sess} | {sig['system']} {sig['dir']} @{sig['entry']}")

        return jsonify({
            "status":   "ok",
            "session":  sess,
            "mom_atr":  round(mom,2),
            "atr_m5":   round(atr,3),
            "s1":       s1, "s2": s2, "trend_up": up,
            "signals":  [f"{s['system']} {s['dir']} {s['entry']}" for s in signals],
            "zone_lock":{"long": [round(l,2) for l,_ in long_zones],
                         "short":[round(l,2) for l,_ in short_zones]}
        }), 200

    except Exception as e:
        print(f"[ERR] {e}")
        return jsonify({"status":"error","msg":str(e)}), 500


@app.route("/daily", methods=["POST"])
def daily_endpoint():
    try:
        d    = json.loads(request.get_data(as_text=True))
        h    = float(d['h']); l = float(d['l']); c = float(d['c'])
        date = d.get('date', datetime.datetime.now(CET).date().isoformat())

        add_day(date, h, l, c)

        mom, up, s1, s2 = momentum()
        sys_ = "S1 Seitwärts" if s1 else "S2 Trend"
        dir_ = "📈 UP" if up else "📉 DOWN"

        if mom:
            tg(
                f"📅 <b>Tagesabschluss {date}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"💰 Close: <b>${c:.2f}</b>\n"
                f"📊 ATR-Mom: {mom:.2f}×\n"
                f"{'✅ Morgen: System 1 (Seitwärts)' if s1 else '📈 Morgen: System 2 (Trend)'}\n"
                f"Trend: {dir_}"
            )

        return jsonify({
            "status": "ok", "date": date,
            "mom_atr": round(mom,2) if mom else None,
            "system": "S1" if s1 else "S2",
            "trend":  "up" if up else "down",
            "days_cached": len(days)
        }), 200

    except Exception as e:
        return jsonify({"status":"error","msg":str(e)}), 500


@app.route("/outcome/<result>", methods=["POST"])
def outcome(result):
    global wins_today, losses_today
    if result not in ["win","loss"]:
        return jsonify({"status":"error"}), 400
    if result == "win": wins_today  += 1; em = "✅"
    else:               losses_today += 1; em = "❌"
    tot = wins_today + losses_today
    tq  = wins_today / tot * 100 if tot > 0 else 0
    now = datetime.datetime.now(CET).strftime("%H:%M")
    tg(
        f"{em} <b>Trade {result.upper()}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 Heute: {wins_today}W / {losses_today}L  ({tq:.0f}% TQ)\n"
        f"🕐 {now} MEZ"
    )
    return jsonify({"status":"ok","tq":round(tq,1)}), 200


@app.route("/status", methods=["GET"])
def status():
    mom, up, s1, s2 = momentum()
    tot = wins_today + losses_today
    tq  = wins_today / tot * 100 if tot > 0 else 0
    now = datetime.datetime.now(CET).strftime("%H:%M MEZ")
    return jsonify({
        "status":      "online",
        "version":     "5.0",
        "time_cet":    now,
        "trade_date":  str(current_date),
        "sessions":    {"eu":"09:00-15:30 MESZ","us":"15:30-21:00 MESZ"},
        "daily_cache": {
            "days":      len(days),
            "last_day":  days[-1]['date'] if days else None,
            "last_close":days[-1]['c']    if days else None,
            "mom_atr":   round(mom,2)     if mom  else None,
            "s1":        s1, "s2": s2, "trend_up": up,
        },
        "atr_filter":  f"< {ATR_MAX}$",
        "bars_today":  bar_num,
        "zone_lock":   {
            "long":  [round(l,2) for l,_ in long_zones],
            "short": [round(l,2) for l,_ in short_zones]
        },
        "today": {
            "signals": len(sig_today),
            "wins":    wins_today,
            "losses":  losses_today,
            "tq_pct":  round(tq,1)
        },
        "signals_today": sig_today[-10:]
    }), 200


@app.route("/reset", methods=["GET","POST"])
def reset():
    global sig_today, wins_today, losses_today
    sig_today    = []
    wins_today   = 0
    losses_today = 0
    zone_reset()
    tg("🔄 <b>CL System 1+2 v5.0</b> – Reset")
    return jsonify({"status":"ok"}), 200


@app.route("/test", methods=["GET","POST"])
def test():
    mom, up, s1, s2 = momentum()
    now  = datetime.datetime.now(CET).strftime("%H:%M")
    sys_ = "S1 Seitwärts" if s1 else "S2 Trend"
    ok   = tg(
        f"🧪 <b>CL System 1+2 v5.0</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ Server Online\n"
        f"📊 Cache: {len(days)} Tage | letzter: {days[-1]['date'] if days else '-'}\n"
        f"📈 ATR-Mom: {mom:.2f}× → {sys_}\n"
        f"🕐 {now} MEZ\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"EU Session: 09:00-15:30 MESZ ✅\n"
        f"US Session: 15:30-21:00 MESZ ✅\n"
        f"Auto-Reset: täglich ✅\n"
        f"Zone Lock:  NUR in Session ✅"
    )
    return jsonify({"status":"ok","telegram":"ok" if ok else "error"}), 200


@app.route("/", methods=["GET"])
def health():
    return jsonify({"status":"online","version":"5.0"}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("CL System 1+2 v5.0 | EU+US | Auto-Reset | Zone Lock 1:1")
    app.run(host="0.0.0.0", port=port, debug=False)

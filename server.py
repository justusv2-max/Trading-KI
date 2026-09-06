"""
CL Futures M5 | System 1+2 | Server v5.1
=========================================
ZIEL
----
Technisch robustere Produktionsversion von v5.0, OHNE Änderung der
validierten Handelslogik.

STRATEGIELOGIK (absichtlich 1:1 wie v5.0 / Backtest):
- EU Session: 02:00-08:30 CT, Ende exklusiv
- US Session: 08:30-14:00 CT, Ende inklusiv
- Pre-/Post-Session: nur Buffer, keine Signale, keine neuen Zone-Locks
- Zone-Lock: 96 akzeptierte M5-Bars, ABER Reset bei jedem Sessionwechsel
  (EU -> US) und beim neuen CT-Handelstag; das ist die validierte Variante.
- System 1: Daily ATR-Momentum <= 2.5x, LONG + SHORT, CRV 1.5R
- System 2: Daily ATR-Momentum > 2.5x, nur Trendrichtung, CRV 1.0R
- M5 ATR Filter: Signal erlaubt solange ATR <= 0.30 (wie v5.0-Code)
- Entry-/Stop-/Target-Berechnung inklusive Python round(..., 2) bleibt
  absichtlich identisch zu v5.0, damit der Backtest nicht verändert wird.

TECHNISCHE VERBESSERUNGEN:
- strikte Timestamp-Verarbeitung; kein stiller Fallback auf Serverzeit
- Duplicate- und Out-of-order-M5-Schutz
- atomar persistierter Runtime-State (Bars, Zonen, Session, Tagesstatus)
- persistierter Daily-Cache in demselben State
- Input-/OHLC-Validierung
- Thread-Lock gegen parallele Requests innerhalb eines Workers
- Status zeigt tatsächliche Bars des CT-Tages statt globalen Barzähler
- Signal enthält eindeutige signal_id und Bar-Timestamp

WICHTIG FÜR GUNICORN/RAILWAY:
Diese Engine verwendet absichtlich genau EINEN In-Memory-Worker, damit jede
M5-Kerze dieselbe deterministische Zustandsmaschine durchläuft. Starte daher:
    gunicorn cl_server_v5_1:app --workers 1 --threads 4 --timeout 30
Für Persistenz über Railway-Redeploys STATE_FILE auf ein gemountetes Volume
legen, z.B. /data/cl_v5_1_state.json.
"""

from __future__ import annotations

from flask import Flask, request, jsonify
from collections import deque
from zoneinfo import ZoneInfo
from pathlib import Path
from threading import RLock
import datetime as dt
import hashlib
import json
import math
import os
import tempfile
import urllib.request

app = Flask(__name__)
LOCK = RLock()

# ─── ENV / TIMEZONES ──────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
STATE_FILE = Path(os.environ.get("STATE_FILE", "cl_v5_1_state.json"))

CET = ZoneInfo("Europe/Berlin")
CT = ZoneInfo("America/Chicago")
UTC = dt.timezone.utc

# ─── PARAMETER: NICHT ÄNDERN OHNE NEUEN BACKTEST ─────────
MM = 0.08
SB = 0.05
MAX_RISK = 1.00
MAX_TICKS = 15
CRV_S1 = 1.5
CRV_S2 = 1.0
LOOKBACK = 12
ATR_MAX = 0.30
ATR_LEN = 14
MOM_THRESH = 2.5
MOM_WINDOW = 20
ZONE_BARS = 96
LEVEL_TOL = 0.05
TICK_SIZE = 0.01

EU_S = 2 * 60
EU_E = 8 * 60 + 30
US_S = 8 * 60 + 30
US_E = 14 * 60

# ─── INITIAL DAILY DATA: exakt aus v5.0 ───────────────────
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

# ─── RUNTIME STATE ────────────────────────────────────────
bars = deque(maxlen=600)
days = []
long_zones = []
short_zones = []
bar_num = 0
bars_today = 0
prev_session = None
current_date = None
sig_today = []
wins_today = 0
losses_today = 0
last_bar_ts = None
recent_bar_ts = deque(maxlen=2000)


def _state_dict():
    return {
        "version": 1,
        "bars": list(bars),
        "days": days[-50:],
        "long_zones": long_zones,
        "short_zones": short_zones,
        "bar_num": bar_num,
        "bars_today": bars_today,
        "prev_session": prev_session,
        "current_date": current_date,
        "sig_today": sig_today[-100:],
        "wins_today": wins_today,
        "losses_today": losses_today,
        "last_bar_ts": last_bar_ts,
        "recent_bar_ts": list(recent_bar_ts),
    }


def save_state():
    """Atomic JSON replace: nie eine halb geschriebene State-Datei."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(_state_dict(), separators=(",", ":"), ensure_ascii=False)
    fd, tmp_name = tempfile.mkstemp(prefix=STATE_FILE.name + ".", dir=str(STATE_FILE.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, STATE_FILE)
    finally:
        if os.path.exists(tmp_name):
            try:
                os.unlink(tmp_name)
            except OSError:
                pass


def load_state():
    global days, long_zones, short_zones, bar_num, bars_today
    global prev_session, current_date, sig_today, wins_today, losses_today
    global last_bar_ts

    if not STATE_FILE.exists():
        days = [dict(x) for x in INITIAL_DAYS]
        save_state()
        print(f"[STATE] neu | {len(days)} Initial-Tage")
        return

    try:
        s = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        bars.clear()
        bars.extend(s.get("bars", [])[-600:])
        days = s.get("days", [])[-50:] or [dict(x) for x in INITIAL_DAYS]
        long_zones = [tuple(x) for x in s.get("long_zones", [])]
        short_zones = [tuple(x) for x in s.get("short_zones", [])]
        bar_num = int(s.get("bar_num", 0))
        bars_today = int(s.get("bars_today", 0))
        prev_session = s.get("prev_session")
        current_date = s.get("current_date")
        sig_today = s.get("sig_today", [])[-100:]
        wins_today = int(s.get("wins_today", 0))
        losses_today = int(s.get("losses_today", 0))
        last_bar_ts = s.get("last_bar_ts")
        recent_bar_ts.clear()
        recent_bar_ts.extend(s.get("recent_bar_ts", [])[-2000:])
        print(f"[STATE] geladen | bars={len(bars)} days={len(days)} last_ts={last_bar_ts}")
    except Exception as e:
        raise RuntimeError(f"State-Datei unlesbar: {STATE_FILE}: {e}") from e


# ─── TIME / SESSION ───────────────────────────────────────
def ct_dt(ts):
    return dt.datetime.fromtimestamp(ts, tz=CT)


def ct_min(ts):
    x = ct_dt(ts)
    return x.hour * 60 + x.minute


def in_eu(ts):
    return EU_S <= ct_min(ts) < EU_E


def in_us(ts):
    return US_S <= ct_min(ts) <= US_E


def in_any(ts):
    return in_eu(ts) or in_us(ts)


def weekday(ts):
    return ct_dt(ts).weekday() < 5


def ct_date_str(ts):
    return ct_dt(ts).date().isoformat()


def session_code(ts):
    if in_eu(ts):
        return "EU"
    if in_us(ts):
        return "US"
    return None


def session_label(ts):
    code = session_code(ts)
    return "EU Session" if code == "EU" else ("US Session" if code == "US" else "")


def parse_timestamp(value):
    """Akzeptiert epoch sec/ms oder ISO-8601. Kein Serverzeit-Fallback."""
    if value is None or value == "":
        raise ValueError("timestamp 't' fehlt")

    if isinstance(value, (int, float)):
        ts = float(value)
    else:
        s = str(value).strip()
        if s.replace(".", "", 1).isdigit():
            ts = float(s)
        else:
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            try:
                x = dt.datetime.fromisoformat(s)
            except ValueError as e:
                raise ValueError(f"ungültiger ISO timestamp: {value}") from e
            if x.tzinfo is None:
                raise ValueError("ISO timestamp benötigt Zeitzone/Z")
            ts = x.timestamp()

    # Millisekunden erkennen
    if ts > 10_000_000_000:
        ts /= 1000.0
    if not math.isfinite(ts) or ts <= 0:
        raise ValueError("ungültiger timestamp")
    return ts


# ─── MARKET DATA / INDICATORS ─────────────────────────────
def add_bar(o, h, l, c, v, ts):
    bars.append({"o": o, "h": h, "l": l, "c": c, "v": v, "ts": ts})


def atr_m5():
    # exakt dieselbe TR-Logik wie v5.0
    if len(bars) < ATR_LEN + 1:
        return None
    b = list(bars)
    trs = [
        max(
            b[i]["h"] - b[i]["l"],
            abs(b[i]["h"] - b[i - 1]["c"]),
            abs(b[i]["l"] - b[i - 1]["c"]),
        )
        for i in range(1, len(b))
    ]
    return sum(trs[-ATR_LEN:]) / ATR_LEN


def momentum():
    # exakt wie v5.0 / Backtest
    if len(days) < 22:
        return None, None, False, False
    cp = days[-1]["c"]
    cn = days[-21]["c"]
    atr = sum(d["h"] - d["l"] for d in days[-14:]) / 14
    if atr <= 0:
        return None, None, False, False
    mom = abs(cp - cn) / atr
    up = cp > cn
    return mom, up, mom <= MOM_THRESH, mom > MOM_THRESH


def add_day(date, h, l, c):
    """Upsert nach Datum; chronologische Reihenfolge bleibt deterministisch."""
    global days
    row = {"date": str(date), "h": float(h), "l": float(l), "c": float(c)}
    by_date = {d["date"]: d for d in days}
    by_date[row["date"]] = row
    days = [by_date[k] for k in sorted(by_date.keys())][-50:]
    save_state()
    print(f"[DAILY] {date} H:{h} L:{l} C:{c} | Cache={len(days)}")


# ─── ZONE LOCK ─────────────────────────────────────────────
def zone_tick():
    global long_zones, short_zones
    long_zones = [(l, e) for l, e in long_zones if e > bar_num]
    short_zones = [(l, e) for l, e in short_zones if e > bar_num]


def zone_locked_long(level):
    return any(abs(l - level) <= LEVEL_TOL for l, _ in long_zones)


def zone_locked_short(level):
    return any(abs(l - level) <= LEVEL_TOL for l, _ in short_zones)


def zone_add_long(level):
    long_zones.append((level, bar_num + ZONE_BARS))


def zone_add_short(level):
    short_zones.append((level, bar_num + ZONE_BARS))


def zone_reset(reason=""):
    long_zones.clear()
    short_zones.clear()
    print(f"[ZONE] reset{': ' + reason if reason else ''}")


# ─── DAY / SESSION STATE ──────────────────────────────────
def check_new_day(ts):
    global current_date, sig_today, wins_today, losses_today, bars_today
    d = ct_date_str(ts)
    if current_date is None:
        current_date = d
        bars_today = 0
        return
    if d != current_date:
        print(f"[DAY] {current_date} -> {d}")
        current_date = d
        sig_today = []
        wins_today = 0
        losses_today = 0
        bars_today = 0
        zone_reset("new CT day")


def apply_session_reset(ts):
    """Exakt die validierte v5.0-Semantik: Reset beim Eintritt in neue Session."""
    global prev_session
    curr = session_code(ts)
    if curr is not None and curr != prev_session:
        old = prev_session
        zone_reset(f"session {old} -> {curr}")
        prev_session = curr


# ─── SIGNAL ENGINE: STRATEGIE 1:1 ─────────────────────────
def find_signals(in_session, s1, s2, up, atr):
    if atr is None or atr > ATR_MAX:
        return []
    b = list(bars)
    if len(b) < LOOKBACK + 3:
        return []

    close = b[-1]["c"]
    sigs = []

    def long_signal(system, crv):
        for k in range(2, LOOKBACK + 1):
            i_liq = -(k + 2)
            i_extr = -(k + 1)
            if abs(i_liq) > len(b):
                break
            liq = b[i_liq]["l"]
            extr = b[i_extr]["l"]
            if extr < liq and close >= liq + MM:
                en = liq
                st = extr - SB
                rk = en - st
                tk = round(rk / TICK_SIZE)  # ABSICHTLICH v5.0
                if 0 < rk <= MAX_RISK and tk <= MAX_TICKS:
                    if not zone_locked_long(en):
                        if in_session:
                            zone_add_long(en)
                            sigs.append({
                                "system": system,
                                "dir": "LONG",
                                "entry": round(en, 2),
                                "stop": round(st, 2),
                                "target": round(en + rk * crv, 2),
                                "ticks": tk,
                                "crv": crv,
                            })
                        break
                    else:
                        break

    def short_signal(system, crv):
        for k in range(2, LOOKBACK + 1):
            i_liq = -(k + 2)
            i_extr = -(k + 1)
            if abs(i_liq) > len(b):
                break
            liq = b[i_liq]["h"]
            extr = b[i_extr]["h"]
            if extr > liq and close <= liq - MM:
                en = liq
                st = extr + SB
                rk = st - en
                tk = round(rk / TICK_SIZE)  # ABSICHTLICH v5.0
                if 0 < rk <= MAX_RISK and tk <= MAX_TICKS:
                    if not zone_locked_short(en):
                        if in_session:
                            zone_add_short(en)
                            sigs.append({
                                "system": system,
                                "dir": "SHORT",
                                "entry": round(en, 2),
                                "stop": round(st, 2),
                                "target": round(en - rk * crv, 2),
                                "ticks": tk,
                                "crv": crv,
                            })
                        break
                    else:
                        break

    if s1:
        long_signal("S1", CRV_S1)
        short_signal("S1", CRV_S1)
    if s2:
        if up:
            long_signal("S2", CRV_S2)
        else:
            short_signal("S2", CRV_S2)

    return sigs


# ─── TELEGRAM ──────────────────────────────────────────────
def tg(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"[TG OFF] {msg[:100]}")
        return False
    try:
        body = json.dumps({
            "chat_id": TELEGRAM_CHAT_ID,
            "text": msg,
            "parse_mode": "HTML",
        }).encode("utf-8")
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"[TG ERR] {e}")
        return False


def signal_id(ts, sig):
    raw = f"{int(ts)}|{sig['system']}|{sig['dir']}|{sig['entry']:.2f}|{sig['stop']:.2f}|{sig['target']:.2f}"
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


def fmt(sig, mom, atr, sess, ts):
    local = dt.datetime.fromtimestamp(ts, tz=CET)
    em = "🟢" if sig["dir"] == "LONG" else "🔴"
    ar = "▲" if sig["dir"] == "LONG" else "▼"
    risk = sig["ticks"] * 10
    rew = round(sig["ticks"] * sig["crv"] * 10)
    rewt = round(sig["ticks"] * sig["crv"])
    name = "1 (Seitwärts)" if sig["system"] == "S1" else "2 (Trend)"
    sid = signal_id(ts, sig)
    return (
        f"{em} <b>System {name} | {sig['dir']} {ar}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📍 Entry:  <b>${sig['entry']:.2f}</b>\n"
        f"🛑 Stop:   <b>${sig['stop']:.2f}</b>  (-{sig['ticks']}T / -${risk})\n"
        f"🎯 Target: <b>${sig['target']:.2f}</b>  (+{rewt}T / +${rew})\n"
        f"📊 CRV 1:{sig['crv']} | ATR-Mom:{mom:.1f}× | ATR:${atr:.3f}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🕐 {local.strftime('%Y-%m-%d %H:%M %Z')} | {sess} | CL M5\n"
        f"ID: <code>{sid}</code>"
    )


# ─── REQUEST HELPERS ───────────────────────────────────────
def parse_json_body():
    raw = request.get_data(as_text=True)
    if not raw or not raw.strip():
        raise ValueError("empty body")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Kompatibilität zum alten TradingView-Format mit unquoted ISO-Zeit
        import re
        fixed = re.sub(
            r'"t":([0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:.+-]+Z?)',
            r'"t":"\1"',
            raw,
        )
        try:
            return json.loads(fixed)
        except json.JSONDecodeError as e:
            raise ValueError(f"json parse error: {e.msg}") from e


def get_price(d, short_key, long_key):
    if short_key in d:
        return float(d[short_key])
    if long_key in d:
        return float(d[long_key])
    raise ValueError(f"Feld '{short_key}'/'{long_key}' fehlt")


def validate_ohlc(o, h, l, c, v):
    vals = [o, h, l, c, v]
    if not all(math.isfinite(x) for x in vals):
        raise ValueError("OHLCV enthält NaN/Inf")
    if min(o, h, l, c) <= 0:
        raise ValueError("OHLC muss > 0 sein")
    if h < max(o, l, c) or l > min(o, h, c):
        raise ValueError("inkonsistente OHLC-Werte")
    if v < 0:
        raise ValueError("volume < 0")


# ─── ENDPOINTS ─────────────────────────────────────────────
@app.route("/webhook", methods=["POST"])
def webhook():
    global bar_num, bars_today, last_bar_ts

    with LOCK:
        try:
            d = parse_json_body()
            o = get_price(d, "o", "open")
            h = get_price(d, "h", "high")
            l = get_price(d, "l", "low")
            c = get_price(d, "c", "close")
            v = float(d.get("v", d.get("volume", 0)))
            ts = parse_timestamp(d.get("t"))
            validate_ohlc(o, h, l, c, v)

            ts_key = int(round(ts))
            if ts_key in recent_bar_ts:
                return jsonify({"status": "ok", "msg": "duplicate bar ignored", "ts": ts_key}), 200
            if last_bar_ts is not None and ts <= float(last_bar_ts):
                return jsonify({
                    "status": "ok",
                    "msg": "out-of-order bar ignored",
                    "ts": ts,
                    "last_bar_ts": last_bar_ts,
                }), 200

            if not weekday(ts):
                return jsonify({"status": "ok", "msg": "weekend"}), 200

            check_new_day(ts)

            # Exakt wie Backtest: jede akzeptierte M5-Kerze geht in den Buffer
            add_bar(o, h, l, c, v, ts)
            bar_num += 1
            bars_today += 1
            zone_tick()

            # Validierte Session-Reset-Regel
            apply_session_reset(ts)

            recent_bar_ts.append(ts_key)
            last_bar_ts = ts

            mom, up, s1, s2 = momentum()
            atr = atr_m5()
            sess = session_label(ts)
            in_session = in_any(ts)

            if mom is None:
                save_state()
                return jsonify({"status":"ok", "msg":f"warming up ({len(days)} days)"}), 200
            if atr is None:
                save_state()
                return jsonify({"status":"ok", "msg":"atr warming up"}), 200
            if not in_session:
                save_state()
                return jsonify({
                    "status":"ok",
                    "msg":"pre-session buffer only",
                    "mom_atr":round(mom,2),
                    "atr_m5":round(atr,3),
                }), 200

            signals = find_signals(True, s1, s2, up, atr)
            sent = []
            for sig in signals:
                sid = signal_id(ts, sig)
                tg_ok = tg(fmt(sig, mom, atr, sess, ts))
                record = {
                    "signal_id": sid,
                    "bar_ts": int(ts),
                    "time": dt.datetime.fromtimestamp(ts, tz=CET).isoformat(),
                    "system": sig["system"],
                    "dir": sig["dir"],
                    "entry": sig["entry"],
                    "stop": sig["stop"],
                    "target": sig["target"],
                    "ticks": sig["ticks"],
                    "session": sess,
                    "telegram_sent": tg_ok,
                }
                sig_today.append(record)
                sent.append(record)
                print(f"[SIG] {sid} | {sess} | {sig['system']} {sig['dir']} @{sig['entry']}")

            save_state()
            return jsonify({
                "status":"ok",
                "version":"5.1",
                "bar_ts":int(ts),
                "session":sess,
                "mom_atr":round(mom,2),
                "atr_m5":round(atr,3),
                "s1":s1,
                "s2":s2,
                "trend_up":up,
                "signals":sent,
                "zone_lock":{
                    "long":[round(lv,2) for lv,_ in long_zones],
                    "short":[round(lv,2) for lv,_ in short_zones],
                },
            }), 200

        except ValueError as e:
            return jsonify({"status":"error", "msg":str(e)}), 400
        except Exception as e:
            print(f"[ERR] {type(e).__name__}: {e}")
            return jsonify({"status":"error", "msg":str(e)}), 500


@app.route("/daily", methods=["POST"])
def daily_endpoint():
    with LOCK:
        try:
            d = parse_json_body()
            h = float(d["h"])
            l = float(d["l"])
            c = float(d["c"])
            if not all(math.isfinite(x) for x in (h, l, c)) or l <= 0 or h < l or c < l or c > h:
                raise ValueError("ungültige Daily H/L/C")
            date = d.get("date")
            if not date:
                raise ValueError("daily 'date' fehlt")
            # Formatprüfung
            dt.date.fromisoformat(str(date))

            add_day(str(date), h, l, c)
            mom, up, s1, s2 = momentum()
            if mom is not None:
                tg(
                    f"📅 <b>Tagesabschluss {date}</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"💰 Close: <b>${c:.2f}</b>\n"
                    f"📊 ATR-Mom: {mom:.2f}×\n"
                    f"{'✅ Morgen: System 1 (Seitwärts)' if s1 else '📈 Morgen: System 2 (Trend)'}\n"
                    f"Trend: {'📈 UP' if up else '📉 DOWN'}"
                )

            return jsonify({
                "status":"ok",
                "date":str(date),
                "mom_atr":round(mom,2) if mom is not None else None,
                "system":"S1" if s1 else "S2",
                "trend":"up" if up else "down",
                "days_cached":len(days),
            }), 200
        except (ValueError, KeyError) as e:
            return jsonify({"status":"error", "msg":str(e)}), 400
        except Exception as e:
            return jsonify({"status":"error", "msg":str(e)}), 500


@app.route("/outcome/<result>", methods=["POST"])
def outcome(result):
    global wins_today, losses_today
    with LOCK:
        if result not in {"win", "loss"}:
            return jsonify({"status":"error", "msg":"result must be win/loss"}), 400
        if result == "win":
            wins_today += 1
            em = "✅"
        else:
            losses_today += 1
            em = "❌"
        total = wins_today + losses_today
        tq = wins_today / total * 100 if total else 0
        now = dt.datetime.now(CET)
        tg(
            f"{em} <b>Trade {result.upper()}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 Heute: {wins_today}W / {losses_today}L ({tq:.0f}% TQ)\n"
            f"🕐 {now.strftime('%H:%M %Z')}"
        )
        save_state()
        return jsonify({"status":"ok", "tq":round(tq,1)}), 200


@app.route("/status", methods=["GET"])
def status():
    with LOCK:
        mom, up, s1, s2 = momentum()
        total = wins_today + losses_today
        tq = wins_today / total * 100 if total else 0
        now = dt.datetime.now(CET)
        return jsonify({
            "status":"online",
            "version":"5.1",
            "time_local":now.isoformat(),
            "trade_date_ct":current_date,
            "sessions_ct":{"eu":"02:00-08:30", "us":"08:30-14:00"},
            "zone_reset":"new CT day + every session transition",
            "daily_cache":{
                "days":len(days),
                "last_day":days[-1]["date"] if days else None,
                "last_close":days[-1]["c"] if days else None,
                "mom_atr":round(mom,2) if mom is not None else None,
                "s1":s1,
                "s2":s2,
                "trend_up":up,
            },
            "atr_filter":f"<= {ATR_MAX}$ (v5.0 semantics)",
            "bars_today":bars_today,
            "bars_buffer":len(bars),
            "last_bar_ts":last_bar_ts,
            "last_bar_utc":dt.datetime.fromtimestamp(last_bar_ts, tz=UTC).isoformat() if last_bar_ts else None,
            "zone_lock":{
                "long":[round(lv,2) for lv,_ in long_zones],
                "short":[round(lv,2) for lv,_ in short_zones],
            },
            "today":{
                "signals":len(sig_today),
                "wins":wins_today,
                "losses":losses_today,
                "tq_pct":round(tq,1),
            },
            "signals_today":sig_today[-10:],
            "state_file":str(STATE_FILE),
        }), 200


@app.route("/reset", methods=["GET", "POST"])
def reset_endpoint():
    global sig_today, wins_today, losses_today
    with LOCK:
        sig_today = []
        wins_today = 0
        losses_today = 0
        zone_reset("manual")
        save_state()
        return jsonify({"status":"ok", "msg":"day stats + zones reset"}), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status":"ok", "version":"5.1"}), 200


load_state()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)

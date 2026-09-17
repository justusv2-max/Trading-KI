from __future__ import annotations

"""
CL Futures M5 | System 1 + 2 | Server v7.0 FINAL
====================================================

ZWECK
-----
Live-Signalserver für die neue M1-validierte Strategie.

STRATEGIEPARAMETER
------------------
S1 (ATR-Momentum <= 2.5):
    LONG + SHORT
    MM=0.05, SB=0.05, CRV=0.60, LOOKBACK=20, MAX_TICKS=15
S2 (ATR-Momentum > 2.5):
    nur Trendrichtung
    MM=0.08, SB=0.07, CRV=0.70, LOOKBACK=30, MAX_TICKS=18

Gemeinsam:
    M5 ATR(14) <= 0.40
    MAX_RISK=1.00
    MOM_THRESH=2.5
    Daily Momentum: letzter abgeschlossener Daily-Close gegen 20 Daily-Zeilen zurück,
                    ATR = Mittelwert H-L der letzten 14 abgeschlossenen Dailys
    Zone-Lock: 96 akzeptierte M5-Bars, LEVEL_TOL=0.05
    Zone-Reset: neuer CT-Handelstag + Eintritt EU + Wechsel EU->US
    EU: 02:00 <= CT < 08:30
    US: 08:30 <= CT <= 14:00
    Entry/Stop/Target: Python round(..., 2), Target = Entry +/- raw_risk * CRV

WICHTIG ZUR BACKTEST-GLEICHHEIT
-------------------------------
Der historische Referenz-Backtest, der zuletzt verwendet wurde, berechnet den
Daily-ATR für einen Intraday-Tag aus der vollständigen H/L-Range dieses Tages.
Das enthält Zukunftsinformation und kann live nicht 1:1 bekannt sein.

Dieser Server verwendet deshalb ausschließlich ABGESCHLOSSENE Daily-Daten.
Alle übrigen Signalregeln sind so umgesetzt, wie sie in der Referenzlogik
definiert wurden. Vor Live-Einsatz muss der Backtest mit genau dieser kausalen
Daily-Berechnung erneut laufen. Erst danach darf diese Datei als endgültig
"1:1 backtest-identisch" bezeichnet werden.

M1 / EXECUTION
--------------
Der Server erzeugt M5-Setups/Signale. Die historische M1-Regel
"SL + TP in derselben M1-Kerze = LOSS" ist eine Backtest-Auswertungsregel und
kann im M5-Signalserver nicht die echte Tick-Reihenfolge ersetzen.
Der tatsächliche Order-Fill/SL/TP wird vom Ausführungs-Bridge/Broker bestimmt.

TECHNIK
-------
- genau EIN Gunicorn-Worker verwenden
- atomare persistente State-Datei
- Bars, Daily-Cache, aktive Daily-Kerze, Zonen, Session, Signalhistorie,
  Duplicate-Schutz werden persistiert
- strikte Timestamps, kein Serverzeit-Fallback
- Duplicate- und Out-of-order-Schutz
- optional WEBHOOK_SECRET über Header X-Webhook-Secret
- kann bei erstmaligem Start Daily-Historie aus einem alten State importieren:
      LEGACY_STATE_FILE=/data/cl_state_v6.json
- empfohlener Start:
      gunicorn cl_server_v7:app --workers 1 --threads 4 --timeout 30
"""

from flask import Flask, request, jsonify
from collections import deque
from pathlib import Path
from threading import RLock
from zoneinfo import ZoneInfo
import datetime as dt
import hashlib
import json
import math
import os
import re
import tempfile
import urllib.request

app = Flask(__name__)
LOCK = RLock()

# ─────────────────────────────────────────────────────────────
# ENV / TIMEZONES
# ─────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
STATE_FILE = Path(os.environ.get("STATE_FILE", "/data/cl_v7_state.json"))
LEGACY_STATE_FILE = Path(os.environ.get("LEGACY_STATE_FILE", "/data/cl_state_v6.json"))
LEGACY_STATE_CANDIDATES = [
    LEGACY_STATE_FILE,
    Path("/data/cl_v6_state.json"),
    Path("/data/cl_v5_1_state.json"),
    Path("/data/cl_v5_state.json"),
]

CET = ZoneInfo("Europe/Berlin")
CT = ZoneInfo("America/Chicago")
ET = ZoneInfo("America/New_York")
UTC = dt.timezone.utc

VERSION = "7.0"

# ─────────────────────────────────────────────────────────────
# FIXIERTE STRATEGIEPARAMETER
# ─────────────────────────────────────────────────────────────
S1 = {
    "MM": 0.05,
    "SB": 0.05,
    "CRV": 0.60,
    "LOOKBACK": 20,
    "MAX_TICKS": 15,
}
S2 = {
    "MM": 0.08,
    "SB": 0.07,
    "CRV": 0.70,
    "LOOKBACK": 30,
    "MAX_TICKS": 18,
}

MAX_RISK = 1.00
ATR_MAX = 0.40
ATR_LEN = 14
MOM_THRESH = 2.5
MOM_WINDOW = 20
ZONE_BARS = 96
LEVEL_TOL = 0.05
TICK = 0.01

EU_S = 2 * 60
EU_E = 8 * 60 + 30
US_S = 8 * 60 + 30
US_E = 14 * 60

MAX_LOOKBACK = max(S1["LOOKBACK"], S2["LOOKBACK"])

# ─────────────────────────────────────────────────────────────
# RUNTIME STATE
# ─────────────────────────────────────────────────────────────
bars = deque(maxlen=600)
days = []                     # nur ABGESCHLOSSENE Custom-Dailys
active_daily = None           # laufender Custom-Day
long_zones = []               # [(level, expire_bar_num), ...]
short_zones = []
bar_num = 0
bars_today = 0
prev_session = None
current_ct_date = None
last_bar_ts = None
recent_bar_ts = deque(maxlen=2000)
recent_bar_set = set()
signals_today = []
signal_history = deque(maxlen=1000)


# ─────────────────────────────────────────────────────────────
# GENERIC HELPERS
# ─────────────────────────────────────────────────────────────
def authorized():
    if not WEBHOOK_SECRET:
        return True
    return request.headers.get("X-Webhook-Secret", "") == WEBHOOK_SECRET


def r2(x):
    # Backtest-Semantik: Python round(..., 2)
    return round(float(x), 2)


def parse_json_body():
    raw = request.get_data(as_text=True)
    if not raw or not raw.strip():
        raise ValueError("empty body")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
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


def parse_timestamp(value):
    """Epoch sec/ms oder ISO-8601 mit Zeitzone. Kein Serverzeit-Fallback."""
    if value is None or value == "":
        raise ValueError("timestamp 't' fehlt")

    if isinstance(value, (int, float)):
        ts = float(value)
    else:
        s = str(value).strip()
        try:
            ts = float(s)
        except ValueError:
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            try:
                x = dt.datetime.fromisoformat(s)
            except ValueError as e:
                raise ValueError(f"ungültiger ISO timestamp: {value}") from e
            if x.tzinfo is None:
                raise ValueError("ISO timestamp benötigt Zeitzone/Z")
            ts = x.timestamp()

    if ts > 10_000_000_000:
        ts /= 1000.0
    if not math.isfinite(ts) or ts <= 0:
        raise ValueError("ungültiger timestamp")
    return ts


def validate_ohlcv(o, h, l, c, v):
    vals = (o, h, l, c, v)
    if not all(math.isfinite(x) for x in vals):
        raise ValueError("OHLCV enthält NaN/Inf")
    if min(o, h, l, c) <= 0:
        raise ValueError("OHLC muss > 0 sein")
    if h < max(o, l, c) or l > min(o, h, c):
        raise ValueError("inkonsistente OHLC-Werte")
    if v < 0:
        raise ValueError("volume < 0")


def remember_ts(ts):
    key = int(round(float(ts)))
    if key in recent_bar_set:
        return False
    if len(recent_bar_ts) == recent_bar_ts.maxlen:
        old = recent_bar_ts[0]
        recent_bar_set.discard(old)
    recent_bar_ts.append(key)
    recent_bar_set.add(key)
    return True


# ─────────────────────────────────────────────────────────────
# TIME / SESSION
# ─────────────────────────────────────────────────────────────
def ct_dt(ts):
    return dt.datetime.fromtimestamp(float(ts), tz=CT)


def ct_min(ts):
    x = ct_dt(ts)
    return x.hour * 60 + x.minute


def ct_date_str(ts):
    return ct_dt(ts).date().isoformat()


def weekday_ct(ts):
    return ct_dt(ts).weekday() < 5


def in_eu(ts):
    return EU_S <= ct_min(ts) < EU_E


def in_us(ts):
    # Referenz-Backtest: 14:00 eingeschlossen.
    return US_S <= ct_min(ts) <= US_E


def session_code(ts):
    if in_eu(ts):
        return "EU"
    if in_us(ts):
        return "US"
    return None


def session_label(ts):
    s = session_code(ts)
    return "EU Session" if s == "EU" else ("US Session" if s == "US" else "")


def in_any_session(ts):
    return session_code(ts) is not None


# ─────────────────────────────────────────────────────────────
# PERSISTENCE
# ─────────────────────────────────────────────────────────────
def state_dict():
    return {
        "version": VERSION,
        "bars": list(bars),
        "days": days[-80:],
        "active_daily": active_daily,
        "long_zones": long_zones,
        "short_zones": short_zones,
        "bar_num": bar_num,
        "bars_today": bars_today,
        "prev_session": prev_session,
        "current_ct_date": current_ct_date,
        "last_bar_ts": last_bar_ts,
        "recent_bar_ts": list(recent_bar_ts),
        "signals_today": signals_today[-200:],
        "signal_history": list(signal_history),
    }


def save_state():
    """Atomisches JSON-Replace."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(state_dict(), separators=(",", ":"), ensure_ascii=False)
    fd, tmp_name = tempfile.mkstemp(
        prefix=STATE_FILE.name + ".",
        dir=str(STATE_FILE.parent),
    )
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


def import_legacy_days():
    """Nur Daily-Historie migrieren; KEINE alten Zonen/Bars/Signale."""
    source = next((p for p in LEGACY_STATE_CANDIDATES if p.exists()), None)
    if source is None:
        return []
    try:
        s = json.loads(source.read_text(encoding="utf-8"))
        raw = s.get("days", [])
        clean = []
        for d in raw:
            date = str(d["date"])
            dt.date.fromisoformat(date)
            h, l, c = float(d["h"]), float(d["l"]), float(d["c"])
            if not all(math.isfinite(x) for x in (h, l, c)):
                continue
            if l <= 0 or h < l or not (l <= c <= h):
                continue
            clean.append({"date": date, "h": h, "l": l, "c": c})
        by_date = {d["date"]: d for d in clean}
        out = [by_date[k] for k in sorted(by_date.keys())][-80:]
        if out:
            print(f"[MIGRATION] {len(out)} Daily-Zeilen aus {source}")
        return out
    except Exception as e:
        print(f"[MIGRATION ERR] {e}")
        return []


def load_state():
    global days, active_daily, long_zones, short_zones
    global bar_num, bars_today, prev_session, current_ct_date
    global last_bar_ts, signals_today

    if not STATE_FILE.exists():
        days = import_legacy_days()
        save_state()
        print(f"[STATE] neu | days={len(days)}")
        return

    try:
        s = json.loads(STATE_FILE.read_text(encoding="utf-8"))

        bars.clear()
        bars.extend(s.get("bars", [])[-600:])

        raw_days = s.get("days", [])
        days = raw_days[-80:] if raw_days else import_legacy_days()
        active_daily = s.get("active_daily")

        long_zones = [tuple(x) for x in s.get("long_zones", [])]
        short_zones = [tuple(x) for x in s.get("short_zones", [])]

        bar_num = int(s.get("bar_num", 0))
        bars_today = int(s.get("bars_today", 0))
        prev_session = s.get("prev_session")
        current_ct_date = s.get("current_ct_date")
        last_bar_ts = s.get("last_bar_ts")
        signals_today = s.get("signals_today", [])[-200:]

        recent_bar_ts.clear()
        recent_bar_set.clear()
        for x in s.get("recent_bar_ts", [])[-2000:]:
            k = int(x)
            recent_bar_ts.append(k)
            recent_bar_set.add(k)

        signal_history.clear()
        signal_history.extend(s.get("signal_history", [])[-1000:])

        print(
            f"[STATE] geladen bars={len(bars)} days={len(days)} "
            f"zones={len(long_zones)}/{len(short_zones)} last_ts={last_bar_ts}"
        )
    except Exception as e:
        raise RuntimeError(f"State-Datei unlesbar: {STATE_FILE}: {e}") from e


# ─────────────────────────────────────────────────────────────
# DAILY DATA / MOMENTUM
# ─────────────────────────────────────────────────────────────
def backtest_daily_date(ts):
    """
    Custom-Day-Gruppierung aus dem bisherigen robusten Server:
    date(America/New_York timestamp - 1h).
    """
    x = dt.datetime.fromtimestamp(float(ts), tz=ET) - dt.timedelta(hours=1)
    return x.date().isoformat()


def upsert_closed_day(row):
    global days
    date = str(row["date"])
    clean = {
        "date": date,
        "h": float(row["h"]),
        "l": float(row["l"]),
        "c": float(row["c"]),
    }
    by_date = {d["date"]: d for d in days}
    by_date[date] = clean
    days = [by_date[k] for k in sorted(by_date.keys())][-80:]


def update_daily_from_m5(h, l, c, ts):
    """
    Baut den laufenden Custom-Day aus allen eingehenden M5-Bars.
    Erst beim Wechsel des Daily-Keys wird der vorherige Tag in `days`
    übernommen. Momentum nutzt damit nur abgeschlossene Tage.
    """
    global active_daily

    key = backtest_daily_date(ts)
    h, l, c, ts = float(h), float(l), float(c), float(ts)

    if active_daily is None:
        active_daily = {
            "date": key, "h": h, "l": l, "c": c, "last_ts": ts
        }
        return False

    cur = str(active_daily["date"])
    if key < cur:
        return False

    if key != cur:
        upsert_closed_day(active_daily)
        print(
            f"[DAILY] final {cur} "
            f"H:{active_daily['h']:.2f} L:{active_daily['l']:.2f} "
            f"C:{active_daily['c']:.2f}"
        )
        active_daily = {
            "date": key, "h": h, "l": l, "c": c, "last_ts": ts
        }
        return True

    active_daily["h"] = max(float(active_daily["h"]), h)
    active_daily["l"] = min(float(active_daily["l"]), l)
    if ts >= float(active_daily.get("last_ts", -1)):
        active_daily["c"] = c
        active_daily["last_ts"] = ts
    return False


def momentum():
    """
    Live-kausale Fassung:
    cp = letzter abgeschlossener Daily-Close
    cn = 20 Daily-Zeilen davor (days[-21])
    ATR = Mittel H-L der letzten 14 abgeschlossenen Dailys
    """
    if len(days) < 21:
        return None, None, False, False

    cp = float(days[-1]["c"])
    cn = float(days[-21]["c"])
    atr_d = sum(float(d["h"]) - float(d["l"]) for d in days[-14:]) / 14.0

    if atr_d <= 0:
        return None, None, False, False

    mom = abs(cp - cn) / atr_d
    up = cp > cn
    return mom, up, mom <= MOM_THRESH, mom > MOM_THRESH


# ─────────────────────────────────────────────────────────────
# M5 ATR
# ─────────────────────────────────────────────────────────────
def add_bar(o, h, l, c, v, ts):
    bars.append({
        "o": float(o), "h": float(h), "l": float(l),
        "c": float(c), "v": float(v), "ts": float(ts)
    })


def atr_m5():
    if len(bars) < ATR_LEN + 1:
        return None

    b = list(bars)
    trs = []
    for i in range(1, len(b)):
        trs.append(max(
            b[i]["h"] - b[i]["l"],
            abs(b[i]["h"] - b[i - 1]["c"]),
            abs(b[i]["l"] - b[i - 1]["c"]),
        ))
    return sum(trs[-ATR_LEN:]) / ATR_LEN


# ─────────────────────────────────────────────────────────────
# ZONE LOCK / SESSION RESET
# ─────────────────────────────────────────────────────────────
def zone_tick():
    global long_zones, short_zones
    long_zones = [(lv, ex) for lv, ex in long_zones if ex > bar_num]
    short_zones = [(lv, ex) for lv, ex in short_zones if ex > bar_num]


def zone_locked(zones, level):
    return any(abs(float(lv) - float(level)) <= LEVEL_TOL for lv, _ in zones)


def zone_add(zones, level):
    zones.append((float(level), bar_num + ZONE_BARS))


def zone_reset(reason=""):
    long_zones.clear()
    short_zones.clear()
    print(f"[ZONE] reset{': ' + reason if reason else ''}")


def check_new_ct_day(ts):
    global current_ct_date, bars_today, signals_today, prev_session

    d = ct_date_str(ts)
    if current_ct_date is None:
        current_ct_date = d
        bars_today = 0
        return

    if d != current_ct_date:
        print(f"[DAY] {current_ct_date} -> {d}")
        current_ct_date = d
        bars_today = 0
        signals_today = []
        zone_reset("new CT day")
        # Wichtig: Damit der erste Eintritt in EU des neuen Tages
        # sicher wieder als Sessionwechsel erkannt wird.
        prev_session = None


def apply_session_reset(ts):
    """
    Reset beim EINTRITT in EU und beim Wechsel EU -> US.
    Außerhalb einer Session bleibt prev_session unverändert.
    """
    global prev_session

    curr = session_code(ts)
    if curr is not None and curr != prev_session:
        old = prev_session
        zone_reset(f"session {old} -> {curr}")
        prev_session = curr


# ─────────────────────────────────────────────────────────────
# SIGNAL ENGINE
# ─────────────────────────────────────────────────────────────
def make_signal(system, direction, params, entry, stop):
    risk = (entry - stop) if direction == "LONG" else (stop - entry)
    ticks = round(risk / TICK)

    if not (0 < risk <= MAX_RISK and ticks <= params["MAX_TICKS"]):
        return None

    target = (
        entry + risk * params["CRV"]
        if direction == "LONG"
        else entry - risk * params["CRV"]
    )

    return {
        "system": system,
        "dir": direction,
        "entry": r2(entry),
        "stop": r2(stop),
        "target": r2(target),
        "raw_risk": float(risk),
        "ticks": int(ticks),
        "crv": float(params["CRV"]),
        "mm": float(params["MM"]),
        "sb": float(params["SB"]),
        "lookback": int(params["LOOKBACK"]),
        "max_ticks": int(params["MAX_TICKS"]),
    }


def scan_direction(system, direction, params, close):
    """
    Referenz-Semantik:
    - k = 2..LOOKBACK
    - erstes Sweep/Reclaim-Muster besitzt den Scan
    - sobald die Pattern-Bedingung erfüllt ist, wird IMMER abgebrochen,
      auch wenn Risk/MaxTicks ungültig oder das Level gesperrt ist.
    """
    b = list(bars)
    zones = long_zones if direction == "LONG" else short_zones

    for k in range(2, params["LOOKBACK"] + 1):
        i_liq = -(k + 2)
        i_extr = -(k + 1)

        if abs(i_liq) > len(b):
            break

        if direction == "LONG":
            liq = float(b[i_liq]["l"])
            extr = float(b[i_extr]["l"])
            pattern = extr < liq and close >= liq + params["MM"]
            stop = extr - params["SB"]
        else:
            liq = float(b[i_liq]["h"])
            extr = float(b[i_extr]["h"])
            pattern = extr > liq and close <= liq - params["MM"]
            stop = extr + params["SB"]

        if not pattern:
            continue

        sig = make_signal(system, direction, params, liq, stop)

        if sig is not None and not zone_locked(zones, liq):
            zone_add(zones, liq)
            return sig

        # Entscheidend: erstes qualifying Pattern beendet den Scan.
        break

    return None


def find_signals(s1_active, s2_active, trend_up, atr):
    if atr is None or atr > ATR_MAX:
        return []

    b = list(bars)
    if len(b) < MAX_LOOKBACK + 3:
        return []

    close = float(b[-1]["c"])
    out = []

    if s1_active:
        a = scan_direction("S1", "LONG", S1, close)
        b_sig = scan_direction("S1", "SHORT", S1, close)
        if a:
            out.append(a)
        if b_sig:
            out.append(b_sig)

    if s2_active:
        direction = "LONG" if trend_up else "SHORT"
        s = scan_direction("S2", direction, S2, close)
        if s:
            out.append(s)

    return out


# ─────────────────────────────────────────────────────────────
# TELEGRAM
# ─────────────────────────────────────────────────────────────
def tg(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"[TG OFF] {msg[:200]}")
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
    raw = (
        f"{int(ts)}|{sig['system']}|{sig['dir']}|"
        f"{sig['entry']:.2f}|{sig['stop']:.2f}|{sig['target']:.2f}"
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def format_signal(sig, mom, atr, sess, ts):
    local = dt.datetime.fromtimestamp(ts, tz=CET)
    em = "🟢" if sig["dir"] == "LONG" else "🔴"
    ar = "▲" if sig["dir"] == "LONG" else "▼"
    name = "1 (Seitwärts)" if sig["system"] == "S1" else "2 (Trend)"

    risk_dollars = sig["ticks"] * 10
    reward_ticks = abs(sig["target"] - sig["entry"]) / TICK
    reward_dollars = round(reward_ticks * 10)
    sid = signal_id(ts, sig)

    return (
        f"{em} <b>System {name} | {sig['dir']} {ar}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📍 Entry:  <b>${sig['entry']:.2f}</b>\n"
        f"🛑 Stop:   <b>${sig['stop']:.2f}</b>  "
        f"(-{sig['ticks']}T / -${risk_dollars})\n"
        f"🎯 Target: <b>${sig['target']:.2f}</b>  "
        f"(+{reward_ticks:.0f}T / +${reward_dollars})\n"
        f"📊 CRV 1:{sig['crv']:.1f} | ATR-Mom:{mom:.1f}× | ATR:${atr:.3f}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🕐 {local.strftime('%Y-%m-%d %H:%M %Z')} | {sess} | CL M5\n"
        f"ID: <code>{sid}</code>"
    )


# ─────────────────────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────────────────────
@app.route("/webhook", methods=["POST"])
def webhook():
    global bar_num, bars_today, last_bar_ts

    with LOCK:
        try:
            if not authorized():
                return jsonify({"status": "error", "msg": "unauthorized"}), 401

            d = parse_json_body()
            o = get_price(d, "o", "open")
            h = get_price(d, "h", "high")
            l = get_price(d, "l", "low")
            c = get_price(d, "c", "close")
            v = float(d.get("v", d.get("volume", 0)) or 0)
            ts = parse_timestamp(d.get("t", d.get("time")))

            validate_ohlcv(o, h, l, c, v)

            ts_key = int(round(ts))
            if ts_key in recent_bar_set:
                return jsonify({
                    "status": "ok",
                    "msg": "duplicate bar ignored",
                    "ts": ts_key,
                }), 200

            if last_bar_ts is not None and ts <= float(last_bar_ts):
                return jsonify({
                    "status": "ok",
                    "msg": "out-of-order bar ignored",
                    "ts": ts,
                    "last_bar_ts": last_bar_ts,
                }), 200

            # Daily-Aufbau bekommt ALLE M5-Bars, auch Weekend/Sonntag.
            update_daily_from_m5(h, l, c, ts)

            if not remember_ts(ts):
                return jsonify({
                    "status": "ok",
                    "msg": "duplicate bar ignored",
                    "ts": ts_key,
                }), 200

            last_bar_ts = ts

            # Signal-M5-Puffer wie bisher nur CT-Wochentage.
            if not weekday_ct(ts):
                save_state()
                return jsonify({
                    "status": "ok",
                    "msg": "weekend daily-only",
                    "daily_key": backtest_daily_date(ts),
                }), 200

            check_new_ct_day(ts)

            add_bar(o, h, l, c, v, ts)
            bar_num += 1
            bars_today += 1

            zone_tick()
            apply_session_reset(ts)

            mom, up, s1_active, s2_active = momentum()
            atr = atr_m5()
            sess = session_label(ts)

            if mom is None:
                save_state()
                return jsonify({
                    "status": "ok",
                    "msg": f"daily warming up ({len(days)} closed days)",
                }), 200

            if atr is None:
                save_state()
                return jsonify({
                    "status": "ok",
                    "msg": "M5 ATR warming up",
                }), 200

            if not in_any_session(ts):
                save_state()
                return jsonify({
                    "status": "ok",
                    "msg": "pre/post-session buffer only",
                    "mom_atr": round(mom, 4),
                    "atr_m5": round(atr, 4),
                }), 200

            signals = find_signals(s1_active, s2_active, up, atr)
            sent = []

            for sig in signals:
                sid = signal_id(ts, sig)
                telegram_ok = tg(format_signal(sig, mom, atr, sess, ts))

                record = {
                    "signal_id": sid,
                    "bar_ts": int(ts),
                    "time_berlin": dt.datetime.fromtimestamp(ts, tz=CET).isoformat(),
                    "time_ct": dt.datetime.fromtimestamp(ts, tz=CT).isoformat(),
                    "system": sig["system"],
                    "dir": sig["dir"],
                    "entry": sig["entry"],
                    "stop": sig["stop"],
                    "target": sig["target"],
                    "raw_risk": sig["raw_risk"],
                    "ticks": sig["ticks"],
                    "crv": sig["crv"],
                    "session": sess,
                    "mom_atr": mom,
                    "atr_m5": atr,
                    "telegram_sent": telegram_ok,
                }

                signals_today.append(record)
                signal_history.append(record)
                sent.append(record)

                print(
                    f"[SIG] {sid} | {sess} | "
                    f"{sig['system']} {sig['dir']} @{sig['entry']:.2f}"
                )

            save_state()

            return jsonify({
                "status": "ok",
                "version": VERSION,
                "bar_ts": int(ts),
                "session": sess,
                "mom_atr": round(mom, 4),
                "atr_m5": round(atr, 4),
                "system": "S1" if s1_active else "S2",
                "trend": "up" if up else "down",
                "signals": sent,
                "zone_lock": {
                    "long": [
                        {"level": round(lv, 2), "expire_bar": ex}
                        for lv, ex in long_zones
                    ],
                    "short": [
                        {"level": round(lv, 2), "expire_bar": ex}
                        for lv, ex in short_zones
                    ],
                },
            }), 200

        except ValueError as e:
            return jsonify({"status": "error", "msg": str(e)}), 400
        except Exception as e:
            print(f"[ERR] {type(e).__name__}: {e}")
            return jsonify({"status": "error", "msg": str(e)}), 500


@app.route("/daily", methods=["POST"])
def daily_disabled():
    # Daily wird aus M5 gebaut, damit die Gruppierung deterministisch bleibt.
    return jsonify({
        "status": "disabled",
        "msg": "Daily wird automatisch aus M5 aufgebaut; D1-Alarm deaktiviert lassen.",
    }), 409


@app.route("/status", methods=["GET"])
def status():
    with LOCK:
        mom, up, s1_active, s2_active = momentum()
        now = dt.datetime.now(CET)

        return jsonify({
            "status": "online",
            "version": VERSION,
            "time_berlin": now.isoformat(),
            "state_file": str(STATE_FILE),
            "legacy_state_file": str(LEGACY_STATE_FILE),
            "strategy": {
                "S1": S1,
                "S2": S2,
                "atr_max": ATR_MAX,
                "atr_len": ATR_LEN,
                "mom_thresh": MOM_THRESH,
                "mom_window": MOM_WINDOW,
                "zone_bars": ZONE_BARS,
                "level_tol": LEVEL_TOL,
                "sessions_ct": {
                    "eu": "02:00 <= t < 08:30",
                    "us": "08:30 <= t <= 14:00",
                },
                "zone_reset": "new CT day + EU entry + EU->US",
                "target_formula": "round(entry +/- raw_risk*crv, 2)",
                "daily_mode": "closed-days-only (live causal)",
            },
            "runtime": {
                "current_ct_date": current_ct_date,
                "bars_today": bars_today,
                "bars_buffer": len(bars),
                "bar_num": bar_num,
                "last_bar_ts": last_bar_ts,
                "last_bar_utc": (
                    dt.datetime.fromtimestamp(last_bar_ts, tz=UTC).isoformat()
                    if last_bar_ts else None
                ),
                "prev_session": prev_session,
            },
            "daily": {
                "closed_days": len(days),
                "last_closed_day": days[-1]["date"] if days else None,
                "active_day": active_daily,
                "mom_atr": round(mom, 4) if mom is not None else None,
                "system": (
                    "S1" if s1_active else ("S2" if s2_active else None)
                ),
                "trend": (
                    "up" if up is True else ("down" if up is False else None)
                ),
            },
            "zones": {
                "long": [
                    {"level": round(lv, 2), "expire_bar": ex}
                    for lv, ex in long_zones
                ],
                "short": [
                    {"level": round(lv, 2), "expire_bar": ex}
                    for lv, ex in short_zones
                ],
            },
            "signals_today": signals_today[-20:],
        }), 200


@app.route("/reset", methods=["POST"])
def reset():
    global signals_today, prev_session

    with LOCK:
        if not authorized():
            return jsonify({"status": "error", "msg": "unauthorized"}), 401

        signals_today = []
        zone_reset("manual")
        # Session-State bewusst nicht auf None setzen:
        # ein manueller Reset innerhalb der laufenden Session soll nicht
        # beim nächsten M5-Bar nochmals automatisch resetten.
        save_state()

        return jsonify({
            "status": "ok",
            "msg": "signal day stats + zones reset",
        }), 200


@app.route("/test", methods=["GET"])
def test():
    ok = tg(
        "🧪 <b>CL v7.0 FINAL</b> — Server online\n"
        "S1 0.6R | S2 0.7R | EU + US"
    )
    return jsonify({"status": "ok", "telegram": bool(ok)}), 200


@app.route("/health", methods=["GET"])
@app.route("/", methods=["GET"])
def health():
    return jsonify({
        "status": "online",
        "version": VERSION,
    }), 200


load_state()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)

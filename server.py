"""
System 1 + System 2 | CL Futures M5 | Railway Server v2
========================================================
TradingView sendet rohe M5 OHLCV Daten per Webhook.
Server berechnet alles selbst – exakt wie Python Backtest:
  - Daily Momentum (ATR-basiert, letzte 20 Handelstage)
  - ATR M5 Filter (< 0.30$)
  - Zone Lock (8h, ±0.05$ Toleranz)
  - Liq-Abgriff Erkennung (lookback 12 Kerzen)
  - System 1: Seitwärts (ATR-Mom ≤ 2.5×) | CRV 1.5R
  - System 2: Trend     (ATR-Mom > 2.5×)  | CRV 1.0R | Trend-Richtung

Deployment: Railway
Webhook URL: https://YOUR-RAILWAY-URL/webhook
"""

from flask import Flask, request, jsonify
import json, os, datetime, math
from collections import deque
from zoneinfo import ZoneInfo


# ══════════════════════════════════════════
# INITIALE DAILY DATEN (letzte 25 Handelstage)
# Wird beim Server-Start automatisch geladen!
# → Kein manuelles /init nötig!
# ══════════════════════════════════════════
INITIAL_DAYS = [
    {"date":"2026-07-29","h":85.57,"l":81.51,"c":84.05},
    {"date":"2026-07-30","h":85.94,"l":81.60,"c":81.66},
    {"date":"2026-07-31","h":86.87,"l":81.06,"c":86.80},
    {"date":"2026-08-02","h":81.30,"l":78.78,"c":79.52},
    {"date":"2026-08-03","h":81.30,"l":78.43,"c":81.23},
    {"date":"2026-08-04","h":82.33,"l":74.24,"c":75.15},
    {"date":"2026-08-05","h":76.70,"l":74.45,"c":74.81},
    {"date":"2026-08-06","h":78.77,"l":74.57,"c":78.32},
    {"date":"2026-08-07","h":78.50,"l":76.53,"c":77.08},
    {"date":"2026-08-09","h":79.43,"l":78.18,"c":78.45},
    {"date":"2026-08-10","h":82.52,"l":77.79,"c":82.24},
    {"date":"2026-08-11","h":84.61,"l":81.27,"c":83.70},
    {"date":"2026-08-12","h":84.10,"l":81.90,"c":83.00},
    {"date":"2026-08-13","h":83.30,"l":80.09,"c":81.38},
    {"date":"2026-08-14","h":82.99,"l":80.76,"c":82.40},
    {"date":"2026-08-16","h":83.04,"l":81.72,"c":82.15},
    {"date":"2026-08-17","h":85.04,"l":81.50,"c":84.34},
    {"date":"2026-08-18","h":85.14,"l":83.78,"c":84.61},
    {"date":"2026-08-19","h":85.84,"l":83.45,"c":84.47},
    {"date":"2026-08-20","h":87.69,"l":84.33,"c":86.24},
    {"date":"2026-08-21","h":87.51,"l":85.80,"c":86.64},
    {"date":"2026-08-23","h":86.57,"l":84.84,"c":85.61},
    {"date":"2026-08-24","h":86.24,"l":84.36,"c":85.08},
    {"date":"2026-08-25","h":85.09,"l":80.08,"c":80.61},
    {"date":"2026-08-26","h":80.94,"l":80.28,"c":80.60},
]

app = Flask(__name__)

# ══════════════════════════════════════════
# KONFIGURATION
# ══════════════════════════════════════════
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
CET = ZoneInfo("Europe/Berlin")

# ══════════════════════════════════════════
# SYSTEM PARAMETER (identisch mit Backtest!)
# ══════════════════════════════════════════
MM          = 0.08   # Min Momentum Entry ($)
SB          = 0.05   # Stop Buffer ($)
MR          = 1.00   # Max Risk ($)
MAX_TICKS   = 15     # Max Stop Ticks
CRV_S1      = 1.5    # CRV System 1 (Seitwärts)
CRV_S2      = 1.0    # CRV System 2 (Trend)
LOOKBACK    = 12     # Lookback Kerzen
ATR_MAX     = 0.30   # Max ATR M5 ($)
ATR_LEN     = 14     # ATR Periode
MOM_THRESH  = 2.5    # ATR-Momentum Schwelle
MOM_DAYS    = 20     # Momentum Fenster (Handelstage)
ZONE_LOCK_H = 8      # Zone Lock Stunden
ZONE_LOCK_B = ZONE_LOCK_H * 12  # In M5 Bars (12 × 5min = 60min)
LEVEL_TOL   = 0.05   # Level Toleranz ($)
COMM        = 7.80   # Kommission pro Trade ($)

# US Session CT Zeit
SESSION_START = 8 * 60 + 30   # 08:30 CT = 15:30 MEZ
SESSION_END   = 14 * 60 + 0   # 14:00 CT = 21:00 MEZ

# ══════════════════════════════════════════
# ROLLING BUFFER FÜR M5 KERZEN
# ══════════════════════════════════════════
MAX_BARS = 500  # Genug für ATR(14) + Lookback(12) + Puffer

class BarBuffer:
    """Hält die letzten N M5 Kerzen im Speicher"""
    def __init__(self, maxlen=MAX_BARS):
        self.bars = deque(maxlen=maxlen)  # [{'o','h','l','c','v','ts'}]

    def add(self, o, h, l, c, v, ts):
        self.bars.append({'o':o,'h':h,'l':l,'c':c,'v':v,'ts':ts})

    def get_array(self, field):
        """Gibt Array eines Feldes zurück (neueste zuletzt)"""
        return [b[field] for b in self.bars]

    def size(self):
        return len(self.bars)

bar_buffer = BarBuffer()

# ══════════════════════════════════════════
# DAILY CACHE FÜR MOMENTUM
# Speichert Tages-Schlusskurse + ATR
# ══════════════════════════════════════════
class DailyCache:
    """
    Hält tägliche OHLC Daten für Momentum Berechnung.
    Momentum = |Close_gestern - Close_vor21T| / ATR_Daily_14
    → Exakt wie Python Backtest mit close[1] (gestrig!)
    """
    def __init__(self):
        self.days = []  # [{'date','h','l','c'}] sortiert nach Datum
        self.current_day = None
        self.current_h = -999
        self.current_l = 999
        self.current_c = None

    def update(self, ts, h, l, c):
        """Update mit neuer M5 Kerze"""
        dt = datetime.datetime.fromtimestamp(ts, tz=CET)
        day = dt.date().isoformat()

        if self.current_day is None:
            self.current_day = day

        if day != self.current_day:
            # Neuer Tag → gestern abschließen
            if self.current_c is not None:
                self.days.append({
                    'date': self.current_day,
                    'h': self.current_h,
                    'l': self.current_l,
                    'c': self.current_c
                })
                # Nur letzte 50 Tage behalten
                if len(self.days) > 50:
                    self.days = self.days[-50:]
            self.current_day = day
            self.current_h = h
            self.current_l = l
            self.current_c = c
        else:
            self.current_h = max(self.current_h, h)
            self.current_l = min(self.current_l, l)
            self.current_c = c

    def get_momentum(self):
        """
        Berechnet ATR-Momentum für HEUTE (basierend auf gestern!)
        → Identisch mit Backtest: close[1] / ATR_Daily[1]
        → Konstant für ganzen Tag (keine Intraday Schwankung)

        Returns: (mom_atr, trend_up, sideway_ok, s2_ok)
        """
        # Brauche mindestens MOM_DAYS + 1 abgeschlossene Tage
        if len(self.days) < MOM_DAYS + 1:
            return None, None, False, False

        # close[1] = gestriger Close (letzter abgeschlossener Tag)
        close_prev = self.days[-1]['c']

        # close[MOM_DAYS+1] = vor 21 abgeschlossenen Tagen
        if len(self.days) < MOM_DAYS + 1:
            return None, None, False, False
        close_n_ago = self.days[-(MOM_DAYS + 1)]['c']

        # ATR Daily (14 Tage) – gestriger Wert
        atr_days = self.days[-(ATR_LEN):]
        if len(atr_days) < ATR_LEN:
            return None, None, False, False
        atr_daily = sum(d['h'] - d['l'] for d in atr_days) / ATR_LEN

        if atr_daily <= 0:
            return None, None, False, False

        # ATR-Momentum
        mom_atr = abs(close_prev - close_n_ago) / atr_daily

        # Trend-Richtung: Close gestern > Close vor 21 Tagen
        trend_up = close_prev > close_n_ago

        # System 1: Seitwärts (≤ 2.5×ATR)
        sideway_ok = mom_atr <= MOM_THRESH

        # System 2: Trend (> 2.5×ATR)
        s2_ok = mom_atr > MOM_THRESH

        return mom_atr, trend_up, sideway_ok, s2_ok

daily_cache = DailyCache()

# ══════════════════════════════════════════
# PERSISTENTER SPEICHER FÜR DAILY CACHE
# Speichert täglich in JSON Datei
# Bei Neustart: Datei laden → sofort bereit!
# ══════════════════════════════════════════
CACHE_FILE = "daily_cache.json"

def save_cache():
    """Speichert Daily Cache in JSON Datei"""
    try:
        with open(CACHE_FILE, 'w') as f:
            json.dump(daily_cache.days, f)
        print(f"[CACHE] Gespeichert: {len(daily_cache.days)} Tage")
    except Exception as e:
        print(f"[CACHE] Fehler beim Speichern: {e}")

def load_cache():
    """Lädt Daily Cache aus JSON Datei beim Start"""
    try:
        with open(CACHE_FILE, 'r') as f:
            days = json.load(f)
        daily_cache.days = days[-50:]  # Max 50 Tage
        print(f"[CACHE] Geladen: {len(daily_cache.days)} Tage aus Datei")
        return True
    except FileNotFoundError:
        print("[CACHE] Keine Cache Datei gefunden → verwende Initial-Daten")
        return False
    except Exception as e:
        print(f"[CACHE] Fehler beim Laden: {e}")
        return False

def auto_init():
    """
    Beim Server-Start:
    1. Versuche Cache aus Datei zu laden
    2. Falls keine Datei: nutze Initial-Daten
    3. Berechne Momentum und logge Status
    """
    loaded = load_cache()

    if not loaded or len(daily_cache.days) < MOM_DAYS + 1:
        # Keine oder zu wenige Daten → Initial-Daten verwenden
        print("[CACHE] Lade Initial-Daten...")
        daily_cache.days = []
        for d in INITIAL_DAYS:
            daily_cache.days.append({
                'date': d['date'],
                'h': d['h'],
                'l': d['l'],
                'c': d['c']
            })
        save_cache()  # Sofort speichern
        print(f"[CACHE] Initial-Daten geladen: {len(daily_cache.days)} Tage")

    # Momentum berechnen und loggen
    mom_atr, trend_up, sideway_ok, s2_ok = daily_cache.get_momentum()
    if mom_atr:
        system = "S1 Seitwärts" if sideway_ok else "S2 Trend"
        direction = "UP" if trend_up else "DOWN"
        print(f"[AUTO-INIT] ATR-Mom: {mom_atr:.2f}x | {system} | Trend {direction}")
        print(f"[AUTO-INIT] Letzter Tag: {daily_cache.days[-1]['date']} | Close: {daily_cache.days[-1]['c']}")
    else:
        print("[AUTO-INIT] Warnung: Nicht genug Daten für Momentum!")

# Sofort beim Start ausführen
auto_init()

# ══════════════════════════════════════════
# ATR M5 BERECHNUNG
# ══════════════════════════════════════════
def calc_atr_m5(bars_h, bars_l, bars_c, period=ATR_LEN):
    """
    Berechnet ATR auf M5 Basis
    True Range = max(H-L, |H-C_prev|, |L-C_prev|)
    """
    if len(bars_h) < period + 1:
        return None

    trs = []
    for i in range(1, len(bars_h)):
        hl = bars_h[i] - bars_l[i]
        hc = abs(bars_h[i] - bars_c[i-1])
        lc = abs(bars_l[i] - bars_c[i-1])
        trs.append(max(hl, hc, lc))

    if len(trs) < period:
        return None

    return sum(trs[-period:]) / period

# ══════════════════════════════════════════
# ZONE LOCK
# ══════════════════════════════════════════
class ZoneLock:
    """
    Verhindert Duplikat-Trades auf gleichen Levels.
    Sperrt Level für ZONE_LOCK_B Bars (8h × 12 Bars/h = 96 Bars).
    """
    def __init__(self):
        self.long_levels  = []  # [(level, expire_bar)]
        self.short_levels = []

    def _clean(self, current_bar):
        """Entfernt abgelaufene Locks"""
        self.long_levels  = [(l,e) for l,e in self.long_levels  if e > current_bar]
        self.short_levels = [(l,e) for l,e in self.short_levels if e > current_bar]

    def is_locked_long(self, level):
        return any(abs(l - level) <= LEVEL_TOL for l,_ in self.long_levels)

    def is_locked_short(self, level):
        return any(abs(l - level) <= LEVEL_TOL for l,_ in self.short_levels)

    def register_long(self, level, current_bar):
        self.long_levels.append((level, current_bar + ZONE_LOCK_B))

    def register_short(self, level, current_bar):
        self.short_levels.append((level, current_bar + ZONE_LOCK_B))

    def update(self, current_bar):
        self._clean(current_bar)

    def status(self):
        return {
            'long_count':  len(self.long_levels),
            'short_count': len(self.short_levels),
            'long_levels':  [round(l,2) for l,_ in self.long_levels],
            'short_levels': [round(l,2) for l,_ in self.short_levels]
        }

zone_lock = ZoneLock()

# ══════════════════════════════════════════
# SESSION CHECK
# ══════════════════════════════════════════
def in_session(ts):
    """Prüft ob Timestamp in US Session (08:30-14:00 CT = 15:30-21:00 MEZ)"""
    # CT = MEZ - 7h (Sommerzeit) / MEZ - 6h (Winterzeit)
    dt_cet = datetime.datetime.fromtimestamp(ts, tz=CET)
    # Einfach: CT = UTC - 5h (Sommerzeit CDT)
    dt_ct = datetime.datetime.fromtimestamp(ts, tz=ZoneInfo("America/Chicago"))
    ct_minutes = dt_ct.hour * 60 + dt_ct.minute
    return SESSION_START <= ct_minutes <= SESSION_END

# ══════════════════════════════════════════
# SIGNAL ERKENNUNG
# Exakt identisch mit Python Backtest!
# ══════════════════════════════════════════
def detect_signal(bars_h, bars_l, bars_c, current_bar,
                  sideway_ok, s2_ok, trend_up, atr_m5):
    """
    Sucht Liq-Abgriff Signal in den letzten LOOKBACK Kerzen.

    LONG:  low[k+1] > low[k] (Abgriff unter Level)
           close >= low[k+1] + MM (Momentum zurück)

    SHORT: high[k+1] < high[k] (Abgriff über Level)
           close <= high[k+1] - MM (Momentum zurück)

    Gibt Liste von Signalen zurück:
    [{'system','dir','entry','stop','target','risk_ticks','crv'}]
    """
    if len(bars_h) < LOOKBACK + 3:
        return []
    if atr_m5 is None or atr_m5 > ATR_MAX:
        return []

    signals = []
    close = bars_c[-1]  # Aktuelle Kerze

    # Zone Lock updaten
    zone_lock.update(current_bar)

    # System 1: Seitwärts
    if sideway_ok:
        # LONG
        for k in range(2, LOOKBACK + 1):
            idx_level = -(k + 2)  # low[k+1]
            idx_extr  = -(k + 1)  # low[k]
            if abs(idx_level) > len(bars_l) or abs(idx_extr) > len(bars_l):
                break
            liq_level = bars_l[idx_level]
            extr_low  = bars_l[idx_extr]
            if extr_low < liq_level and close >= liq_level + MM:
                en = liq_level
                st = extr_low - SB
                rk = en - st
                sl_ticks = round(rk / 0.01)
                if 0 < rk <= MR and sl_ticks <= MAX_TICKS:
                    if not zone_lock.is_locked_long(en):
                        signals.append({
                            'system': 'S1',
                            'dir': 'LONG',
                            'entry': round(en, 2),
                            'stop':  round(st, 2),
                            'target': round(en + rk * CRV_S1, 2),
                            'risk_ticks': sl_ticks,
                            'crv': CRV_S1
                        })
                        zone_lock.register_long(en, current_bar)
                        break  # Nur erstes valides Signal

        # SHORT
        for k in range(2, LOOKBACK + 1):
            idx_level = -(k + 2)
            idx_extr  = -(k + 1)
            if abs(idx_level) > len(bars_h) or abs(idx_extr) > len(bars_h):
                break
            liq_level = bars_h[idx_level]
            extr_high = bars_h[idx_extr]
            if extr_high > liq_level and close <= liq_level - MM:
                en = liq_level
                st = extr_high + SB
                rk = st - en
                sl_ticks = round(rk / 0.01)
                if 0 < rk <= MR and sl_ticks <= MAX_TICKS:
                    if not zone_lock.is_locked_short(en):
                        signals.append({
                            'system': 'S1',
                            'dir': 'SHORT',
                            'entry': round(en, 2),
                            'stop':  round(st, 2),
                            'target': round(en - rk * CRV_S1, 2),
                            'risk_ticks': sl_ticks,
                            'crv': CRV_S1
                        })
                        zone_lock.register_short(en, current_bar)
                        break

    # System 2: Trend (nur in Trend-Richtung)
    if s2_ok:
        # LONG (nur wenn Aufwärtstrend)
        if trend_up:
            for k in range(2, LOOKBACK + 1):
                idx_level = -(k + 2)
                idx_extr  = -(k + 1)
                if abs(idx_level) > len(bars_l) or abs(idx_extr) > len(bars_l):
                    break
                liq_level = bars_l[idx_level]
                extr_low  = bars_l[idx_extr]
                if extr_low < liq_level and close >= liq_level + MM:
                    en = liq_level
                    st = extr_low - SB
                    rk = en - st
                    sl_ticks = round(rk / 0.01)
                    if 0 < rk <= MR and sl_ticks <= MAX_TICKS:
                        if not zone_lock.is_locked_long(en):
                            signals.append({
                                'system': 'S2',
                                'dir': 'LONG',
                                'entry': round(en, 2),
                                'stop':  round(st, 2),
                                'target': round(en + rk * CRV_S2, 2),
                                'risk_ticks': sl_ticks,
                                'crv': CRV_S2
                            })
                            zone_lock.register_long(en, current_bar)
                            break

        # SHORT (nur wenn Abwärtstrend)
        if not trend_up:
            for k in range(2, LOOKBACK + 1):
                idx_level = -(k + 2)
                idx_extr  = -(k + 1)
                if abs(idx_level) > len(bars_h) or abs(idx_extr) > len(bars_h):
                    break
                liq_level = bars_h[idx_level]
                extr_high = bars_h[idx_extr]
                if extr_high > liq_level and close <= liq_level - MM:
                    en = liq_level
                    st = extr_high + SB
                    rk = st - en
                    sl_ticks = round(rk / 0.01)
                    if 0 < rk <= MR and sl_ticks <= MAX_TICKS:
                        if not zone_lock.is_locked_short(en):
                            signals.append({
                                'system': 'S2',
                                'dir': 'SHORT',
                                'entry': round(en, 2),
                                'stop':  round(st, 2),
                                'target': round(en - rk * CRV_S2, 2),
                                'risk_ticks': sl_ticks,
                                'crv': CRV_S2
                            })
                            zone_lock.register_short(en, current_bar)
                            break

    return signals

# ══════════════════════════════════════════
# TELEGRAM
# ══════════════════════════════════════════
def send_telegram(message: str) -> bool:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"[TELEGRAM] {message}")
        return False
    import urllib.request
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = json.dumps({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=data,
                                      headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status == 200
    except Exception as e:
        print(f"[TELEGRAM] Fehler: {e}")
        return False

def format_signal(sig: dict, mom_atr: float, atr_m5: float) -> str:
    now = datetime.datetime.now(CET).strftime("%H:%M")
    d = sig['dir']
    s = sig['system']
    emoji = "🟢" if d == "LONG" else "🔴"
    arrow = "▲" if d == "LONG" else "▼"
    risk_usd  = sig['risk_ticks'] * 10
    reward_usd = round(sig['risk_ticks'] * sig['crv'] * 10)
    reward_ticks = round(sig['risk_ticks'] * sig['crv'])
    sys_label = f"System {'1 (Seitwärts)' if s == 'S1' else '2 (Trend)'}"

    return (
        f"{emoji} <b>{sys_label} | {d} {arrow}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📍 Entry:  <b>${sig['entry']:.2f}</b>\n"
        f"🛑 Stop:   <b>${sig['stop']:.2f}</b>  "
        f"(-{sig['risk_ticks']}T / -${risk_usd})\n"
        f"🎯 Target: <b>${sig['target']:.2f}</b>  "
        f"(+{reward_ticks}T / +${reward_usd})\n"
        f"📊 CRV: 1:{sig['crv']} | "
        f"ATR-Mom: {mom_atr:.1f}× | ATR M5: ${atr_m5:.3f}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🕐 {now} MEZ | CL Futures M5"
    )

# ══════════════════════════════════════════
# STATS
# ══════════════════════════════════════════
stats = {
    'bar_count': 0,
    'signals_today': [],
    'wins': 0,
    'losses': 0,
    'last_bar': None,
    'server_start': datetime.datetime.now(CET).isoformat()
}

# ══════════════════════════════════════════
# WEBHOOK – HAUPTENDPUNKT
# TradingView sendet jede M5 Kerze:
# {"o":82.10,"h":82.25,"l":82.05,"c":82.20,"v":450,"t":1234567890}
# ══════════════════════════════════════════
@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        raw = request.get_data(as_text=True)
        data = json.loads(raw)

        # Pflichtfelder
        o = float(data['o'])
        h = float(data['h'])
        l = float(data['l'])
        c = float(data['c'])
        v = float(data.get('v', 0))
        # Timestamp optional - Server nutzt eigene Zeit
        import time as time_module
        ts = float(data.get('t', time_module.time()))

        # Session Check
        if not in_session(ts):
            return jsonify({"status": "ok", "message": "Outside session"}), 200

        # Bars Buffer updaten
        bar_buffer.add(o, h, l, c, v, ts)
        stats['bar_count'] += 1
        stats['last_bar'] = {
            'o':o,'h':h,'l':l,'c':c,
            'ts': datetime.datetime.fromtimestamp(ts, tz=CET).strftime("%H:%M MEZ")
        }

        # Daily Cache updaten
        daily_cache.update(ts, h, l, c)

        # Momentum berechnen (aus abgeschlossenen Tages-Daten)
        mom_atr, trend_up, sideway_ok, s2_ok = daily_cache.get_momentum()

        if mom_atr is None:
            return jsonify({
                "status": "ok",
                "message": f"Warming up... ({len(daily_cache.days)} Tage)"
            }), 200

        # ATR M5 berechnen
        bars_h = bar_buffer.get_array('h')
        bars_l = bar_buffer.get_array('l')
        bars_c = bar_buffer.get_array('c')
        atr_m5 = calc_atr_m5(bars_h, bars_l, bars_c)

        if atr_m5 is None:
            return jsonify({
                "status": "ok",
                "message": "ATR warming up..."
            }), 200

        # Signale suchen
        current_bar = stats['bar_count']
        signals = detect_signal(
            bars_h, bars_l, bars_c, current_bar,
            sideway_ok, s2_ok, trend_up, atr_m5
        )

        # Signale senden
        sent = []
        for sig in signals:
            msg = format_signal(sig, mom_atr, atr_m5)
            send_telegram(msg)
            stats['signals_today'].append({
                'time': datetime.datetime.fromtimestamp(ts, tz=CET).strftime("%H:%M"),
                'system': sig['system'],
                'dir': sig['dir'],
                'entry': sig['entry'],
                'stop': sig['stop'],
                'target': sig['target']
            })
            sent.append(f"{sig['system']} {sig['dir']} {sig['entry']}")
            print(f"[SIGNAL] {sig['system']} {sig['dir']} Entry:{sig['entry']}")

        return jsonify({
            "status": "ok",
            "bar": stats['last_bar'],
            "mom_atr": round(mom_atr, 2),
            "atr_m5": round(atr_m5, 3),
            "sideway": sideway_ok,
            "trend": s2_ok,
            "trend_up": trend_up,
            "signals": sent,
            "zone_lock": zone_lock.status()
        }), 200

    except KeyError as e:
        return jsonify({"status": "error", "message": f"Missing field: {e}"}), 400
    except Exception as e:
        print(f"[WEBHOOK] Exception: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# ══════════════════════════════════════════
# TRADE OUTCOME (manuell)
# ══════════════════════════════════════════
@app.route("/outcome/<result>", methods=["POST"])
def outcome(result):
    """
    Manuell Trade Ergebnis eintragen
    POST /outcome/win  oder  POST /outcome/loss
    """
    if result not in ["win", "loss"]:
        return jsonify({"status": "error"}), 400

    if result == "win":
        stats['wins'] += 1
        emoji = "✅"
    else:
        stats['losses'] += 1
        emoji = "❌"

    total = stats['wins'] + stats['losses']
    tq = stats['wins'] / total * 100 if total > 0 else 0
    now = datetime.datetime.now(CET).strftime("%H:%M")

    msg = (
        f"{emoji} <b>Trade {result.upper()}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 Heute: {stats['wins']}W / {stats['losses']}L "
        f"({tq:.0f}% TQ)\n"
        f"🕐 {now} MEZ"
    )
    send_telegram(msg)
    return jsonify({"status": "ok", "wins": stats['wins'], "losses": stats['losses'], "tq": round(tq,1)}), 200

# ══════════════════════════════════════════
# STATUS
# ══════════════════════════════════════════
@app.route("/status", methods=["GET"])
def status():
    now = datetime.datetime.now(CET)
    total = stats['wins'] + stats['losses']
    tq = stats['wins'] / total * 100 if total > 0 else 0
    mom_atr, trend_up, sideway_ok, s2_ok = daily_cache.get_momentum()

    return jsonify({
        "status": "online",
        "system": "System 1+2 CL Futures M5",
        "version": "2.0",
        "time_cet": now.strftime("%H:%M MEZ"),
        "daily_cache": {
            "days": len(daily_cache.days),
            "ready": mom_atr is not None,
            "mom_atr": round(mom_atr, 2) if mom_atr else None,
            "sideway": sideway_ok,
            "trend": s2_ok,
            "trend_up": trend_up
        },
        "atr_filter": f"< {ATR_MAX}$",
        "zone_lock": zone_lock.status(),
        "bars_received": stats['bar_count'],
        "last_bar": stats['last_bar'],
        "today": {
            "signals": len(stats['signals_today']),
            "wins": stats['wins'],
            "losses": stats['losses'],
            "tq_pct": round(tq, 1)
        },
        "signals_today": stats['signals_today'][-10:]
    }), 200

# ══════════════════════════════════════════
# RESET
# ══════════════════════════════════════════
@app.route("/reset", methods=["POST"])
def reset():
    """Tages-Reset (täglich um Mitternacht oder manuell)"""
    stats['signals_today'] = []
    stats['wins'] = 0
    stats['losses'] = 0
    send_telegram("🔄 <b>System 1+2 CL</b> – Tages-Reset")
    return jsonify({"status": "ok"}), 200

# ══════════════════════════════════════════
# TEST
# ══════════════════════════════════════════
@app.route("/test", methods=["GET", "POST"])
def test():
    now = datetime.datetime.now(CET).strftime("%H:%M")
    msg = (
        f"🧪 <b>System 1+2 CL Test</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ Server Online\n"
        f"✅ Telegram Verbindung OK\n"
        f"📊 Daily Cache: {len(daily_cache.days)} Tage\n"
        f"🕐 {now} MEZ\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Bereit für CL Futures M5!"
    )
    success = send_telegram(msg)
    return jsonify({"status": "ok", "telegram": "ok" if success else "error"}), 200

# ══════════════════════════════════════════
# HEALTH
# ══════════════════════════════════════════
@app.route("/", methods=["GET"])
def health():
    return jsonify({
        "status": "online",
        "system": "System 1+2 CL Futures M5",
        "version": "2.0"
    }), 200


# ══════════════════════════════════════════
# INIT – Daily Cache befüllen beim Start
# Schicke letzte 25 Daily Closes als JSON:
# POST /init
# {"days": [
#   {"date":"2026-08-01","h":83.5,"l":81.2,"c":82.1},
#   {"date":"2026-08-04","h":84.1,"l":82.8,"c":83.5},
#   ...
# ]}
# ══════════════════════════════════════════
@app.route("/init", methods=["POST"])
def init():
    """Befüllt Daily Cache mit historischen Daten"""
    try:
        data = json.loads(request.get_data(as_text=True))
        days = data.get("days", [])

        if len(days) < MOM_DAYS + 1:
            return jsonify({
                "status": "error",
                "message": f"Brauche mindestens {MOM_DAYS+1} Tage, erhalten: {len(days)}"
            }), 400

        # Cache befüllen
        daily_cache.days = []
        for d in days:
            daily_cache.days.append({
                'date': d['date'],
                'h': float(d['h']),
                'l': float(d['l']),
                'c': float(d['c'])
            })

        # Momentum berechnen
        mom_atr, trend_up, sideway_ok, s2_ok = daily_cache.get_momentum()

        msg = (
            f"✅ <b>Daily Cache initialisiert</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 {len(days)} Tage geladen\n"
            f"📈 ATR-Mom: {mom_atr:.2f}×\n"
            f"{'✅ Seitwärts (S1 aktiv)' if sideway_ok else '✅ Trend (S2 aktiv)'}\n"
            f"{'📈 Aufwärtstrend' if trend_up else '📉 Abwärtstrend'}\n"
            f"🕐 {datetime.datetime.now(CET).strftime('%H:%M MEZ')}"
        )
        send_telegram(msg)

        return jsonify({
            "status": "ok",
            "days_loaded": len(days),
            "mom_atr": round(mom_atr, 2) if mom_atr else None,
            "sideway": sideway_ok,
            "trend": s2_ok,
            "trend_up": trend_up
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ══════════════════════════════════════════
# DAILY UPDATE – Tagesabschluss
# TradingView Daily Alert sendet:
# {"date":"2026-08-26","h":83.5,"l":81.2,"c":82.1}
# ══════════════════════════════════════════
@app.route("/daily", methods=["POST"])
def daily_update():
    """Empfängt täglichen Abschlusskurs von TradingView"""
    try:
        data = json.loads(request.get_data(as_text=True))
        h = float(data['h'])
        l = float(data['l'])
        c = float(data['c'])
        date = data.get('date', datetime.datetime.now(CET).date().isoformat())

        # Zum Cache hinzufügen
        daily_cache.days.append({'date': date, 'h': h, 'l': l, 'c': c})
        if len(daily_cache.days) > 50:
            daily_cache.days = daily_cache.days[-50:]

        # Neues Momentum berechnen
        mom_atr, trend_up, sideway_ok, s2_ok = daily_cache.get_momentum()

        print(f"[DAILY] {date} | H:{h} L:{l} C:{c} | ATR-Mom:{mom_atr:.2f}×")

        if mom_atr:
            msg = (
                f"📅 <b>Tagesabschluss {date}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"💰 Close: ${c:.2f}\n"
                f"📊 ATR-Mom: {mom_atr:.2f}×ATR\n"
                f"{'✅ Morgen: System 1 (Seitwärts)' if sideway_ok else '✅ Morgen: System 2 (Trend)'}\n"
                f"{'📈 Trend UP' if trend_up else '📉 Trend DOWN'}"
            )
            send_telegram(msg)

        return jsonify({
            "status": "ok",
            "date": date,
            "close": c,
            "mom_atr": round(mom_atr, 2) if mom_atr else None,
            "tomorrow_system": "S1" if sideway_ok else "S2"
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ══════════════════════════════════════════
# START
# ══════════════════════════════════════════
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"System 1+2 CL Futures M5 Server v2.0 | Port {port}")
    print(f"Port: {port}")
    print(f"Telegram: {'✅' if TELEGRAM_TOKEN else '❌ nicht konfiguriert'}")
    print(f"Parameter:")
    print(f"  ATR-Mom Schwelle: {MOM_THRESH}×")
    print(f"  ATR Max M5:       ${ATR_MAX}")
    print(f"  Zone Lock:        {ZONE_LOCK_H}h ({ZONE_LOCK_B} Bars)")
    print(f"  CRV S1/S2:        {CRV_S1}R / {CRV_S2}R")
    app.run(host="0.0.0.0", port=port, debug=False)

from flask import Flask, request, jsonify
import requests, os, json
from datetime import datetime, timezone
import pytz
from collections import deque

app = Flask(__name__)
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
WEBHOOK_SECRET   = os.environ.get("WEBHOOK_SECRET", "trading123")
CET = pytz.timezone("Europe/Berlin")
try:
    os.makedirs("/data", exist_ok=True)
    CACHE_FILE = "/data/bar_cache.json"
except:
    CACHE_FILE = "/tmp/bar_cache.json"
print("Cache Pfad:", CACHE_FILE)

PARAMS = {
    "CL_H1": {
        "crv": 2.0, "atr_max": 1.00, "mom_threshold": 15.0,
        "momentum_min": 0.50, "stop_buffer": 0.10, "max_risk": 5.00,
        "vol_ma_len": 20, "max_pb_bars": 72,
        "sessions": ["Europa", "US"], "excl_hours": [15],
    },
    "CL_M30": {
        "crv": 2.0, "atr_max": 1.00, "mom_threshold": 15.0,
        "momentum_min": 0.50, "stop_buffer": 0.10, "max_risk": 5.00,
        "vol_ma_len": 20, "max_pb_bars": 144,
        "sessions": ["Europa", "US"], "excl_hours": [15, 19],
    },
}

DEFAULT_BARS = {
    "CL_H1":  [{'timestamp': 1784710800, 'open': 88.261, 'high': 89.241, 'low': 87.971, 'close': 89.081, 'volume': 6529.0}, {'timestamp': 1784714400, 'open': 89.091, 'high': 89.091, 'low': 87.561, 'close': 87.801, 'volume': 6995.0}, {'timestamp': 1784718000, 'open': 87.811, 'high': 88.481, 'low': 87.651, 'close': 87.981, 'volume': 5412.0}, {'timestamp': 1784721600, 'open': 87.981, 'high': 88.311, 'low': 87.181, 'close': 87.861, 'volume': 5945.0}, {'timestamp': 1784725200, 'open': 87.871, 'high': 88.011, 'low': 86.791, 'close': 87.581, 'volume': 7692.0}, {'timestamp': 1784728800, 'open': 87.601, 'high': 87.791, 'low': 87.061, 'close': 87.341, 'volume': 6070.0}, {'timestamp': 1784732400, 'open': 87.351, 'high': 87.951, 'low': 86.421, 'close': 86.651, 'volume': 6492.0}, {'timestamp': 1784736000, 'open': 86.661, 'high': 87.181, 'low': 86.551, 'close': 86.951, 'volume': 3808.0}, {'timestamp': 1784739600, 'open': 86.961, 'high': 87.571, 'low': 86.961, 'close': 87.451, 'volume': 3344.0}, {'timestamp': 1784743200, 'open': 87.461, 'high': 87.731, 'low': 87.281, 'close': 87.691, 'volume': 3744.0}, {'timestamp': 1784746800, 'open': 87.711, 'high': 87.791, 'low': 87.101, 'close': 87.151, 'volume': 1792.0}, {'timestamp': 1784750400, 'open': 87.161, 'high': 87.301, 'low': 86.871, 'close': 87.061, 'volume': 2242.0}, {'timestamp': 1784757600, 'open': 88.208, 'high': 88.958, 'low': 87.938, 'close': 88.558, 'volume': 2500.0}, {'timestamp': 1784761200, 'open': 88.538, 'high': 88.608, 'low': 88.348, 'close': 88.418, 'volume': 868.0}, {'timestamp': 1784764800, 'open': 88.428, 'high': 88.998, 'low': 87.968, 'close': 88.588, 'volume': 3004.0}, {'timestamp': 1784768400, 'open': 88.578, 'high': 89.238, 'low': 88.448, 'close': 88.708, 'volume': 5284.0}, {'timestamp': 1784772000, 'open': 88.718, 'high': 89.088, 'low': 88.648, 'close': 88.858, 'volume': 2817.0}, {'timestamp': 1784775600, 'open': 88.868, 'high': 89.278, 'low': 88.818, 'close': 89.018, 'volume': 2217.0}, {'timestamp': 1784779200, 'open': 89.028, 'high': 89.078, 'low': 88.538, 'close': 88.738, 'volume': 1542.0}, {'timestamp': 1784782800, 'open': 88.728, 'high': 89.018, 'low': 88.268, 'close': 88.898, 'volume': 3155.0}, {'timestamp': 1784786400, 'open': 88.888, 'high': 89.398, 'low': 88.548, 'close': 89.248, 'volume': 4170.0}, {'timestamp': 1784790000, 'open': 89.208, 'high': 90.458, 'low': 89.208, 'close': 89.918, 'volume': 6528.0}, {'timestamp': 1784793600, 'open': 89.888, 'high': 90.338, 'low': 89.538, 'close': 90.118, 'volume': 6733.0}, {'timestamp': 1784797200, 'open': 90.128, 'high': 90.968, 'low': 89.858, 'close': 90.828, 'volume': 6136.0}, {'timestamp': 1784800800, 'open': 90.838, 'high': 91.328, 'low': 90.478, 'close': 90.738, 'volume': 5130.0}, {'timestamp': 1784804400, 'open': 90.758, 'high': 91.788, 'low': 90.718, 'close': 91.298, 'volume': 5108.0}, {'timestamp': 1784808000, 'open': 91.268, 'high': 91.978, 'low': 91.128, 'close': 91.438, 'volume': 7147.0}, {'timestamp': 1784811600, 'open': 91.498, 'high': 92.498, 'low': 91.298, 'close': 92.348, 'volume': 8986.0}, {'timestamp': 1784815200, 'open': 92.338, 'high': 92.758, 'low': 91.598, 'close': 92.508, 'volume': 7985.0}, {'timestamp': 1784818800, 'open': 92.458, 'high': 93.388, 'low': 92.348, 'close': 92.468, 'volume': 8990.0}, {'timestamp': 1784822400, 'open': 92.448, 'high': 93.188, 'low': 92.198, 'close': 92.938, 'volume': 5853.0}, {'timestamp': 1784826000, 'open': 92.948, 'high': 93.888, 'low': 92.928, 'close': 93.848, 'volume': 5476.0}, {'timestamp': 1784829600, 'open': 93.838, 'high': 94.108, 'low': 92.548, 'close': 92.648, 'volume': 6676.0}, {'timestamp': 1784833200, 'open': 92.638, 'high': 92.638, 'low': 91.738, 'close': 92.208, 'volume': 4104.0}, {'timestamp': 1784836800, 'open': 92.218, 'high': 93.018, 'low': 92.038, 'close': 92.998, 'volume': 2451.0}, {'timestamp': 1784844000, 'open': 93.066, 'high': 93.206, 'low': 92.646, 'close': 92.676, 'volume': 1178.0}, {'timestamp': 1784847600, 'open': 92.676, 'high': 93.106, 'low': 92.646, 'close': 92.856, 'volume': 955.0}, {'timestamp': 1784851200, 'open': 92.866, 'high': 93.406, 'low': 92.486, 'close': 92.496, 'volume': 2942.0}, {'timestamp': 1784854800, 'open': 92.456, 'high': 92.456, 'low': 91.756, 'close': 92.236, 'volume': 6044.0}, {'timestamp': 1784858400, 'open': 92.246, 'high': 92.636, 'low': 92.196, 'close': 92.496, 'volume': 2974.0}, {'timestamp': 1784862000, 'open': 92.506, 'high': 92.986, 'low': 92.456, 'close': 92.496, 'volume': 3116.0}, {'timestamp': 1784865600, 'open': 92.476, 'high': 92.576, 'low': 92.126, 'close': 92.246, 'volume': 1433.0}, {'timestamp': 1784869200, 'open': 92.226, 'high': 92.436, 'low': 91.766, 'close': 92.086, 'volume': 3012.0}, {'timestamp': 1784872800, 'open': 92.096, 'high': 92.236, 'low': 91.106, 'close': 91.156, 'volume': 5386.0}, {'timestamp': 1784876400, 'open': 91.156, 'high': 91.336, 'low': 90.746, 'close': 91.046, 'volume': 5866.0}, {'timestamp': 1784880000, 'open': 91.036, 'high': 91.386, 'low': 90.026, 'close': 90.186, 'volume': 7602.0}, {'timestamp': 1784883600, 'open': 90.176, 'high': 90.216, 'low': 89.336, 'close': 89.616, 'volume': 7098.0}, {'timestamp': 1784887200, 'open': 89.626, 'high': 90.746, 'low': 89.436, 'close': 90.496, 'volume': 5250.0}, {'timestamp': 1784890800, 'open': 90.516, 'high': 90.706, 'low': 89.536, 'close': 89.996, 'volume': 4671.0}, {'timestamp': 1784894400, 'open': 89.966, 'high': 90.606, 'low': 89.556, 'close': 89.716, 'volume': 4671.0}],
    "CL_M30": [{'timestamp': 1784804400, 'open': 90.758, 'high': 91.488, 'low': 90.718, 'close': 91.318, 'volume': 2380.0}, {'timestamp': 1784806200, 'open': 91.348, 'high': 91.788, 'low': 90.898, 'close': 91.298, 'volume': 2728.0}, {'timestamp': 1784808000, 'open': 91.268, 'high': 91.978, 'low': 91.158, 'close': 91.448, 'volume': 3321.0}, {'timestamp': 1784809800, 'open': 91.498, 'high': 91.838, 'low': 91.128, 'close': 91.438, 'volume': 3826.0}, {'timestamp': 1784811600, 'open': 91.498, 'high': 92.198, 'low': 91.298, 'close': 91.568, 'volume': 4753.0}, {'timestamp': 1784813400, 'open': 91.578, 'high': 92.498, 'low': 91.348, 'close': 92.348, 'volume': 4233.0}, {'timestamp': 1784815200, 'open': 92.338, 'high': 92.568, 'low': 91.598, 'close': 92.358, 'volume': 4107.0}, {'timestamp': 1784817000, 'open': 92.378, 'high': 92.758, 'low': 91.928, 'close': 92.508, 'volume': 3878.0}, {'timestamp': 1784818800, 'open': 92.458, 'high': 93.378, 'low': 92.348, 'close': 93.098, 'volume': 4670.0}, {'timestamp': 1784820600, 'open': 93.088, 'high': 93.388, 'low': 92.398, 'close': 92.468, 'volume': 4320.0}, {'timestamp': 1784822400, 'open': 92.448, 'high': 92.978, 'low': 92.198, 'close': 92.498, 'volume': 3309.0}, {'timestamp': 1784824200, 'open': 92.478, 'high': 93.188, 'low': 92.478, 'close': 92.938, 'volume': 2544.0}, {'timestamp': 1784826000, 'open': 92.948, 'high': 93.398, 'low': 92.928, 'close': 93.188, 'volume': 2690.0}, {'timestamp': 1784827800, 'open': 93.188, 'high': 93.888, 'low': 93.168, 'close': 93.848, 'volume': 2786.0}, {'timestamp': 1784829600, 'open': 93.838, 'high': 94.108, 'low': 92.628, 'close': 92.708, 'volume': 4206.0}, {'timestamp': 1784831400, 'open': 92.718, 'high': 92.958, 'low': 92.548, 'close': 92.648, 'volume': 2470.0}, {'timestamp': 1784833200, 'open': 92.638, 'high': 92.638, 'low': 92.168, 'close': 92.228, 'volume': 1963.0}, {'timestamp': 1784835000, 'open': 92.218, 'high': 92.468, 'low': 91.738, 'close': 92.208, 'volume': 2141.0}, {'timestamp': 1784836800, 'open': 92.218, 'high': 92.688, 'low': 92.038, 'close': 92.528, 'volume': 1345.0}, {'timestamp': 1784838600, 'open': 92.518, 'high': 93.018, 'low': 92.408, 'close': 92.998, 'volume': 1106.0}, {'timestamp': 1784844000, 'open': 93.066, 'high': 93.206, 'low': 92.716, 'close': 92.766, 'volume': 829.0}, {'timestamp': 1784845800, 'open': 92.756, 'high': 92.796, 'low': 92.646, 'close': 92.676, 'volume': 349.0}, {'timestamp': 1784847600, 'open': 92.676, 'high': 92.796, 'low': 92.676, 'close': 92.726, 'volume': 238.0}, {'timestamp': 1784849400, 'open': 92.736, 'high': 93.106, 'low': 92.646, 'close': 92.856, 'volume': 717.0}, {'timestamp': 1784851200, 'open': 92.866, 'high': 93.406, 'low': 92.766, 'close': 92.826, 'volume': 1915.0}, {'timestamp': 1784853000, 'open': 92.836, 'high': 92.936, 'low': 92.486, 'close': 92.496, 'volume': 1027.0}, {'timestamp': 1784854800, 'open': 92.456, 'high': 92.456, 'low': 91.966, 'close': 92.116, 'volume': 3466.0}, {'timestamp': 1784856600, 'open': 92.126, 'high': 92.276, 'low': 91.756, 'close': 92.236, 'volume': 2578.0}, {'timestamp': 1784858400, 'open': 92.246, 'high': 92.476, 'low': 92.196, 'close': 92.426, 'volume': 1328.0}, {'timestamp': 1784860200, 'open': 92.436, 'high': 92.636, 'low': 92.266, 'close': 92.496, 'volume': 1646.0}, {'timestamp': 1784862000, 'open': 92.506, 'high': 92.926, 'low': 92.456, 'close': 92.806, 'volume': 2170.0}, {'timestamp': 1784863800, 'open': 92.816, 'high': 92.986, 'low': 92.496, 'close': 92.496, 'volume': 946.0}, {'timestamp': 1784865600, 'open': 92.476, 'high': 92.576, 'low': 92.236, 'close': 92.266, 'volume': 752.0}, {'timestamp': 1784867400, 'open': 92.256, 'high': 92.336, 'low': 92.126, 'close': 92.246, 'volume': 681.0}, {'timestamp': 1784869200, 'open': 92.226, 'high': 92.436, 'low': 92.176, 'close': 92.316, 'volume': 708.0}, {'timestamp': 1784871000, 'open': 92.306, 'high': 92.386, 'low': 91.766, 'close': 92.086, 'volume': 2304.0}, {'timestamp': 1784872800, 'open': 92.096, 'high': 92.236, 'low': 91.696, 'close': 91.906, 'volume': 2441.0}, {'timestamp': 1784874600, 'open': 91.896, 'high': 91.946, 'low': 91.106, 'close': 91.156, 'volume': 2945.0}, {'timestamp': 1784876400, 'open': 91.156, 'high': 91.336, 'low': 90.886, 'close': 90.906, 'volume': 3009.0}, {'timestamp': 1784878200, 'open': 90.916, 'high': 91.296, 'low': 90.746, 'close': 91.046, 'volume': 2857.0}, {'timestamp': 1784880000, 'open': 91.036, 'high': 91.386, 'low': 90.646, 'close': 90.656, 'volume': 3752.0}, {'timestamp': 1784881800, 'open': 90.716, 'high': 90.846, 'low': 90.026, 'close': 90.186, 'volume': 3850.0}, {'timestamp': 1784883600, 'open': 90.176, 'high': 90.216, 'low': 89.356, 'close': 89.656, 'volume': 3939.0}, {'timestamp': 1784885400, 'open': 89.626, 'high': 89.846, 'low': 89.336, 'close': 89.616, 'volume': 3159.0}, {'timestamp': 1784887200, 'open': 89.626, 'high': 90.376, 'low': 89.436, 'close': 90.226, 'volume': 2882.0}, {'timestamp': 1784889000, 'open': 90.236, 'high': 90.746, 'low': 90.216, 'close': 90.496, 'volume': 2368.0}, {'timestamp': 1784890800, 'open': 90.516, 'high': 90.606, 'low': 90.286, 'close': 90.436, 'volume': 1842.0}, {'timestamp': 1784892600, 'open': 90.436, 'high': 90.706, 'low': 89.536, 'close': 89.996, 'volume': 2829.0}, {'timestamp': 1784894400, 'open': 89.966, 'high': 90.606, 'low': 89.816, 'close': 90.076, 'volume': 3303.0}, {'timestamp': 1784896200, 'open': 90.066, 'high': 90.186, 'low': 89.556, 'close': 89.716, 'volume': 1574.0}],
}

# Warmup Daily Closes - 25 echte Tages-Closes
WARMUP_CLOSES = [74.853, 73.816, 70.578, 72.151, 70.954, 71.022, 70.625, 68.608, 68.951, 69.243, 69.002, 72.554, 74.947, 72.13, 71.773, 78.131, 80.054, 80.386, 79.689, 82.492, 83.1, 85.193, 87.061, 92.998, 89.716]

# ============================================================
# CACHE FUNKTIONEN
# ============================================================

def load_cache():
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE) as f: return json.load(f)
    except: pass
    return None

def save_cache():
    try:
        parent = os.path.dirname(CACHE_FILE)
        if parent: os.makedirs(parent, exist_ok=True)
        with open(CACHE_FILE, "w") as f:
            json.dump({
                "buffers": {k: list(v) for k,v in BUFFERS.items()},
                "shared_daily": list(SHARED_DAILY)
            }, f)
    except Exception as e: print("Cache Fehler:", e)

# ============================================================
# INITIALISIERUNG
# ============================================================

cache = load_cache()
if cache:
    print("Cache geladen!")
    BUFFERS = {k: deque(cache["buffers"].get(k, DEFAULT_BARS[k]), maxlen=300) for k in PARAMS}
    # Bei Neustart: letzte 25 Closes aus Cache - korrekte Momentum Berechnung
    if "shared_daily" in cache and len(cache["shared_daily"]) >= 21:
        SHARED_DAILY = deque(cache["shared_daily"][-25:], maxlen=30)
        print(f"Daily Closes aus Cache: {len(SHARED_DAILY)}")
    else:
        SHARED_DAILY = deque(WARMUP_CLOSES, maxlen=30)
        print(f"Daily Closes: Warmup ({len(SHARED_DAILY)})")
else:
    print("Erster Start - Warmup geladen!")
    BUFFERS = {k: deque(DEFAULT_BARS[k], maxlen=300) for k in PARAMS}
    SHARED_DAILY = deque(WARMUP_CLOSES, maxlen=30)

mom_init = (list(SHARED_DAILY)[-1] - list(SHARED_DAILY)[-21]) / list(SHARED_DAILY)[-21] * 100 if len(SHARED_DAILY) >= 21 else None
print(f"Momentum beim Start: {mom_init:.1f}%" if mom_init else "Momentum: Nicht berechenbar")

# Offene Trades - mehrere gleichzeitig wie im Backtest
OPEN_TRADES = {"CL_H1": [], "CL_M30": []}

# ============================================================
# HILFSFUNKTIONEN
# ============================================================

def get_session(h):
    if 9 <= h < 15: return "Europa"
    elif 15 <= h < 22: return "US"
    return "Off"

def calc_vol_ma(buf, n=20):
    v = [b["volume"] for b in buf]
    return sum(v[-n:]) / n if len(v) >= n else None

def calc_atr(buf, n=14):
    if len(buf) < n+1: return None
    bars = list(buf)
    trs = [max(bars[i]["high"]-bars[i]["low"],
               abs(bars[i]["high"]-bars[i-1]["close"]),
               abs(bars[i]["low"]-bars[i-1]["close"])) for i in range(1, len(bars))]
    return sum(trs[-n:]) / n

def calc_mom():
    c = list(SHARED_DAILY)
    return (c[-1]-c[-21])/c[-21]*100 if len(c) >= 21 else None

def send_telegram(msg):
    url = "https://api.telegram.org/bot" + TELEGRAM_TOKEN + "/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=10)
        return r.status_code == 200
    except Exception as e:
        print(str(e)); return False

# ============================================================
# TRADE VERWALTUNG
# ============================================================

def update_open_trades(inst, bar):
    names = {"CL_H1": "CL H1", "CL_M30": "CL M30"}
    crv = PARAMS[inst]["crv"]
    zeit = datetime.now(CET).strftime("%d.%m.%Y %H:%M")
    remaining = []
    for trade in OPEN_TRADES[inst]:
        trade["bars_since"] += 1
        closed = False

        if not trade["entry_filled"]:
            # Warte auf Entry Fuellung
            if trade["direction"] == "LONG" and bar["low"] <= trade["entry"]:
                trade["entry_filled"] = True
            elif trade["direction"] == "SHORT" and bar["high"] >= trade["entry"]:
                trade["entry_filled"] = True
            # Limit abgelaufen
            if not trade["entry_filled"] and trade["bars_since"] >= PARAMS[inst]["max_pb_bars"]:
                send_telegram("\u23f1 <b>" + names[inst] + " LIMIT ABGELAUFEN</b>\nEntry " + str(trade["entry"]) + " nicht erreicht\nOrder loeschen! | " + zeit)
                closed = True

        # Entry gefuellt - Stop/Target in gleicher Kerze pruefen
        if trade["entry_filled"] and not closed:
            if trade["direction"] == "SHORT":
                if bar["high"] >= trade["stop"]:
                    send_telegram("\U0001f534 <b>" + names[inst] + " STOP LOSS</b>\nEntry: " + str(trade["entry"]) + " | Stop: " + str(trade["stop"]) + "\nVerlust: -1R | " + zeit)
                    closed = True
                elif bar["low"] <= trade["target"]:
                    send_telegram("\u2705 <b>" + names[inst] + " TARGET ERREICHT</b>\nEntry: " + str(trade["entry"]) + " | Target: " + str(trade["target"]) + "\nGewinn: +" + str(crv) + "R | " + zeit)
                    closed = True
            elif trade["direction"] == "LONG":
                if bar["low"] <= trade["stop"]:
                    send_telegram("\U0001f534 <b>" + names[inst] + " STOP LOSS</b>\nEntry: " + str(trade["entry"]) + " | Stop: " + str(trade["stop"]) + "\nVerlust: -1R | " + zeit)
                    closed = True
                elif bar["high"] >= trade["target"]:
                    send_telegram("\u2705 <b>" + names[inst] + " TARGET ERREICHT</b>\nEntry: " + str(trade["entry"]) + " | Target: " + str(trade["target"]) + "\nGewinn: +" + str(crv) + "R | " + zeit)
                    closed = True

        if not closed:
            remaining.append(trade)
    OPEN_TRADES[inst] = remaining

def check_signal(inst, bar):
    buf = BUFFERS[inst]; p = PARAMS[inst]
    if len(buf) < 15: return None
    mom = calc_mom()
    if mom is not None and abs(mom) > p["mom_threshold"]: return None
    bars = list(buf); c = bars[-1]
    ts = datetime.fromtimestamp(c["timestamp"], tz=timezone.utc).astimezone(CET)
    h = ts.hour
    if get_session(h) not in p["sessions"]: return None
    if h in p["excl_hours"]: return None
    vm = calc_vol_ma(buf, p["vol_ma_len"]); atr = calc_atr(buf)
    if vm is None or atr is None: return None
    if c["volume"] <= vm: return None
    if atr > p["atr_max"]: return None
    mm = p["momentum_min"]; sb = p["stop_buffer"]; mr = p["max_risk"]; crv = p["crv"]
    p_bar = bars[-2]
    # LONG
    if c["low"] < p_bar["low"] and c["close"] >= p_bar["low"] + mm:
        en = p_bar["low"]; st = c["low"] - sb; rk = en - st
        if 0 < rk <= mr:
            return {"direction": "LONG", "entry": round(en,2), "stop": round(st,2), "target": round(en+rk*crv,2)}
    # SHORT
    if c["high"] > p_bar["high"] and c["close"] <= p_bar["high"] - mm:
        en = p_bar["high"]; st = c["high"] + sb; rk = st - en
        if 0 < rk <= mr:
            return {"direction": "SHORT", "entry": round(en,2), "stop": round(st,2), "target": round(en-rk*crv,2)}
    return None

# ============================================================
# ENDPOINTS
# ============================================================

@app.route("/webhook/<instrument>", methods=["POST"])
def webhook(instrument):
    inst_map = {"cl_h1": "CL_H1", "cl_m30": "CL_M30"}
    inst = inst_map.get(instrument.lower())
    if not inst: return jsonify({"error": "Unbekannt"}), 400
    try:
        data = request.get_json(force=True)
        if not data: return jsonify({"error": "Keine Daten"}), 400
        if data.get("secret") != WEBHOOK_SECRET: return jsonify({"error": "Fehler"}), 401
        bar = {
            "timestamp": int(data.get("timestamp", datetime.now().timestamp())),
            "open": float(data["open"]), "high": float(data["high"]),
            "low": float(data["low"]), "close": float(data["close"]),
            "volume": float(data["volume"])}
        # Nur Tages-Schlusskerze als Daily Close speichern (21:30 M30 oder 21:00 H1)
        if data.get("daily_close"):
            bar_time = datetime.fromtimestamp(bar["timestamp"], tz=timezone.utc).astimezone(CET)
            if (bar_time.hour == 21 and bar_time.minute == 30) or (bar_time.hour == 21 and bar_time.minute == 0):
                close_val = float(data["daily_close"])
                if len(SHARED_DAILY) == 0 or SHARED_DAILY[-1] != close_val:
                    SHARED_DAILY.append(close_val)
                    print(f"Daily Close gespeichert: {close_val}")
    except Exception as e: return jsonify({"error": str(e)}), 400
    BUFFERS[inst].append(bar)
    update_open_trades(inst, bar)
    save_cache()
    sig = check_signal(inst, bar)
    if sig:
        names = {"CL_H1": "CL H1", "CL_M30": "CL M30"}
        crv = PARAMS[inst]["crv"]
        d = sig["direction"]
        em = "\U0001f7e2" if d == "LONG" else "\U0001f534"
        zeit = datetime.now(CET).strftime("%d.%m.%Y %H:%M")
        OPEN_TRADES[inst].append({
            "direction": d, "entry": sig["entry"],
            "stop": sig["stop"], "target": sig["target"],
            "bars_since": 0, "entry_filled": False
        })
        msg = (em + " <b>" + names[inst] + " - " + d + " SIGNAL</b>\n\n"
               + "<b>Limit Order setzen:</b>\n"
               + "Entry:  <code>" + str(sig["entry"]) + "</code>\n"
               + "Stop:   <code>" + str(sig["stop"]) + "</code>\n"
               + "Target " + str(crv) + "R: <code>" + str(sig["target"]) + "</code>\n"
               + "Risiko: <code>" + str(round(abs(sig["entry"]-sig["stop"]),2)) + "</code>\n\n"
               + "<b>Pepperstone SpotCrude oeffnen!</b>\n"
               + "Zeit: " + zeit + " MEZ")
        send_telegram(msg)
        return jsonify({"status": "signal", "signal": sig})
    return jsonify({"status": "ok", "bars": len(BUFFERS[inst])})

@app.route("/status", methods=["GET"])
def status():
    mom = calc_mom()
    res = {}
    for inst in PARAMS:
        last_close = list(BUFFERS[inst])[-1]["close"] if BUFFERS[inst] else None
        res[inst] = {
            "bars": len(BUFFERS[inst]),
            "last_close": last_close,
            "offene_trades": len(OPEN_TRADES[inst]),
            "trades_detail": OPEN_TRADES[inst],
            "crv": PARAMS[inst]["crv"],
            "momentum_20d": round(mom, 2) if mom else None,
            "mom_ok": abs(mom) <= PARAMS[inst]["mom_threshold"] if mom else True,
            "fully_ready": calc_vol_ma(BUFFERS[inst]) is not None,
            "cache_aktiv": os.path.exists(CACHE_FILE),
            "daily_closes": len(SHARED_DAILY),
        }
    return jsonify(res)

@app.route("/test", methods=["GET"])
def test():
    mom = calc_mom()
    last_h1 = list(BUFFERS["CL_H1"])[-1]["close"] if BUFFERS["CL_H1"] else "?"
    cache_ok = os.path.exists(CACHE_FILE)
    msg = ("Trading Signal Server laeuft!\n\n"
           "Instrumente:\n"
           "CL H1:  2R | Kein 15 Uhr\n"
           "CL M30: 2R | Kein 15+19 Uhr\n\n"
           "Cache: " + ("AKTIV" if cache_ok else "DEFAULTS") + "\n"
           "Letzter Close: " + str(last_h1) + "$\n"
           "Momentum (20d): " + (str(round(mom,1))+"%%" if mom else "?") + "\n"
           "Mom Filter: " + ("OK - handelbar!" if (mom and abs(mom)<=15) else "GESPERRT") + "\n"
           "Offene H1 Trades: " + str(len(OPEN_TRADES["CL_H1"])) + "\n"
           "Offene M30 Trades: " + str(len(OPEN_TRADES["CL_M30"])))
    return jsonify({"sent": send_telegram(msg), "cache": cache_ok})

@app.route("/reset/<instrument>", methods=["GET", "POST"])
def reset(instrument):
    inst_map = {"cl_h1": "CL_H1", "cl_m30": "CL_M30"}
    inst = inst_map.get(instrument.lower())
    if not inst: return jsonify({"error": "Unbekannt"}), 400
    OPEN_TRADES[inst] = []
    names = {"CL_H1": "CL H1", "CL_M30": "CL M30"}
    send_telegram("\U0001f504 <b>" + names[inst] + " - RESET</b>\nBereit fuer neue Signale!")
    return jsonify({"reset": inst, "status": "Bereit!"})

@app.route("/reset_all", methods=["GET", "POST"])
def reset_all():
    OPEN_TRADES["CL_H1"] = []
    OPEN_TRADES["CL_M30"] = []
    send_telegram("\U0001f504 <b>ALLE TRADES RESETTET</b>\nH1 + M30 bereit fuer neue Signale!")
    return jsonify({"reset": "all", "status": "Alle offenen Trades geloescht!"})

@app.route("/", methods=["GET"])
def home():
    mom = calc_mom()
    return jsonify({
        "status": "running",
        "system": "CL H1 (2R) + CL M30 (2R) | SpotCrude CFD",
        "momentum_20d": round(mom,2) if mom else None,
        "mom_ok": abs(mom) <= 15 if mom else True,
        "cache": os.path.exists(CACHE_FILE),
        "offene_trades": {k: len(v) for k,v in OPEN_TRADES.items()},
        "endpoints": {
            "/webhook/cl_h1": "POST - CL H1 Signal",
            "/webhook/cl_m30": "POST - CL M30 Signal",
            "/status": "GET - System Status",
            "/test": "GET - Telegram Test",
            "/reset/cl_h1": "GET - H1 Reset",
            "/reset/cl_m30": "GET - M30 Reset",
            "/reset_all": "GET - Alle Trades loeschen"
        }
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

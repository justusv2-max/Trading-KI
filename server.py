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
    "CL_H1":  [{'timestamp': 1785128400, 'open': 85.379, 'high': 85.489, 'low': 84.889, 'close': 85.079, 'volume': 3613.0}, {'timestamp': 1785132000, 'open': 85.119, 'high': 85.149, 'low': 83.939, 'close': 83.989, 'volume': 7004.0}, {'timestamp': 1785135600, 'open': 83.999, 'high': 85.119, 'low': 83.869, 'close': 85.109, 'volume': 6791.0}, {'timestamp': 1785139200, 'open': 85.149, 'high': 85.369, 'low': 83.409, 'close': 83.469, 'volume': 9214.0}, {'timestamp': 1785142800, 'open': 83.469, 'high': 83.799, 'low': 82.669, 'close': 82.859, 'volume': 6771.0}, {'timestamp': 1785146400, 'open': 82.869, 'high': 84.079, 'low': 82.849, 'close': 83.789, 'volume': 5791.0}, {'timestamp': 1785150000, 'open': 83.779, 'high': 84.449, 'low': 83.549, 'close': 83.879, 'volume': 5342.0}, {'timestamp': 1785153600, 'open': 83.899, 'high': 84.859, 'low': 83.889, 'close': 84.539, 'volume': 7494.0}, {'timestamp': 1785157200, 'open': 84.529, 'high': 85.069, 'low': 84.219, 'close': 84.749, 'volume': 8182.0}, {'timestamp': 1785160800, 'open': 84.739, 'high': 84.789, 'low': 83.979, 'close': 84.089, 'volume': 6553.0}, {'timestamp': 1785164400, 'open': 84.109, 'high': 84.359, 'low': 83.509, 'close': 83.919, 'volume': 7515.0}, {'timestamp': 1785168000, 'open': 83.909, 'high': 84.299, 'low': 82.859, 'close': 83.369, 'volume': 7312.0}, {'timestamp': 1785171600, 'open': 83.379, 'high': 83.529, 'low': 83.039, 'close': 83.139, 'volume': 4888.0}, {'timestamp': 1785175200, 'open': 83.149, 'high': 83.469, 'low': 82.519, 'close': 82.659, 'volume': 5449.0}, {'timestamp': 1785178800, 'open': 82.659, 'high': 82.969, 'low': 82.429, 'close': 82.449, 'volume': 2533.0}, {'timestamp': 1785182400, 'open': 82.459, 'high': 82.599, 'low': 82.149, 'close': 82.409, 'volume': 2138.0}, {'timestamp': 1785189600, 'open': 82.337, 'high': 82.677, 'low': 82.237, 'close': 82.617, 'volume': 769.0}, {'timestamp': 1785193200, 'open': 82.627, 'high': 82.707, 'low': 82.517, 'close': 82.547, 'volume': 478.0}, {'timestamp': 1785196800, 'open': 82.507, 'high': 82.697, 'low': 81.927, 'close': 82.617, 'volume': 2611.0}, {'timestamp': 1785200400, 'open': 82.617, 'high': 82.727, 'low': 81.957, 'close': 82.127, 'volume': 4774.0}, {'timestamp': 1785204000, 'open': 82.137, 'high': 82.287, 'low': 81.207, 'close': 81.327, 'volume': 3956.0}, {'timestamp': 1785207600, 'open': 81.337, 'high': 82.077, 'low': 81.107, 'close': 82.067, 'volume': 2584.0}, {'timestamp': 1785211200, 'open': 82.077, 'high': 82.427, 'low': 82.037, 'close': 82.127, 'volume': 1290.0}, {'timestamp': 1785214800, 'open': 82.137, 'high': 82.917, 'low': 81.967, 'close': 82.627, 'volume': 3565.0}, {'timestamp': 1785218400, 'open': 82.627, 'high': 82.827, 'low': 81.127, 'close': 81.307, 'volume': 5638.0}, {'timestamp': 1785222000, 'open': 81.317, 'high': 82.037, 'low': 81.047, 'close': 81.277, 'volume': 5891.0}, {'timestamp': 1785225600, 'open': 81.317, 'high': 81.347, 'low': 80.307, 'close': 80.697, 'volume': 7568.0}, {'timestamp': 1785229200, 'open': 80.737, 'high': 81.727, 'low': 80.737, 'close': 81.117, 'volume': 4979.0}, {'timestamp': 1785232800, 'open': 81.167, 'high': 81.987, 'low': 81.077, 'close': 81.677, 'volume': 3949.0}, {'timestamp': 1785236400, 'open': 81.647, 'high': 82.407, 'low': 81.197, 'close': 82.217, 'volume': 4739.0}, {'timestamp': 1785240000, 'open': 82.237, 'high': 82.237, 'low': 81.127, 'close': 81.297, 'volume': 4775.0}, {'timestamp': 1785243600, 'open': 81.327, 'high': 82.147, 'low': 81.237, 'close': 81.947, 'volume': 6243.0}, {'timestamp': 1785247200, 'open': 81.937, 'high': 82.307, 'low': 81.407, 'close': 81.947, 'volume': 5976.0}, {'timestamp': 1785250800, 'open': 81.927, 'high': 82.067, 'low': 78.777, 'close': 78.857, 'volume': 12222.0}, {'timestamp': 1785254400, 'open': 78.887, 'high': 79.337, 'low': 78.287, 'close': 79.167, 'volume': 8706.0}, {'timestamp': 1785258000, 'open': 79.177, 'high': 80.107, 'low': 78.847, 'close': 79.927, 'volume': 7418.0}, {'timestamp': 1785261600, 'open': 79.937, 'high': 79.997, 'low': 79.317, 'close': 79.707, 'volume': 5611.0}, {'timestamp': 1785265200, 'open': 79.717, 'high': 79.737, 'low': 79.387, 'close': 79.617, 'volume': 2186.0}, {'timestamp': 1785268800, 'open': 79.637, 'high': 79.767, 'low': 79.367, 'close': 79.607, 'volume': 2059.0}, {'timestamp': 1785276000, 'open': 80.694, 'high': 83.684, 'low': 80.634, 'close': 83.114, 'volume': 4389.0}, {'timestamp': 1785279600, 'open': 83.104, 'high': 83.754, 'low': 82.294, 'close': 82.344, 'volume': 2864.0}, {'timestamp': 1785283200, 'open': 82.354, 'high': 83.064, 'low': 82.124, 'close': 82.934, 'volume': 4926.0}, {'timestamp': 1785286800, 'open': 82.934, 'high': 83.524, 'low': 82.794, 'close': 83.224, 'volume': 6426.0}, {'timestamp': 1785290400, 'open': 83.224, 'high': 83.304, 'low': 82.534, 'close': 82.784, 'volume': 2950.0}, {'timestamp': 1785294000, 'open': 82.794, 'high': 83.234, 'low': 82.774, 'close': 83.174, 'volume': 2204.0}, {'timestamp': 1785297600, 'open': 83.174, 'high': 83.174, 'low': 82.364, 'close': 82.524, 'volume': 2086.0}, {'timestamp': 1785301200, 'open': 82.514, 'high': 82.744, 'low': 82.284, 'close': 82.704, 'volume': 3501.0}, {'timestamp': 1785304800, 'open': 82.724, 'high': 82.904, 'low': 82.274, 'close': 82.574, 'volume': 4109.0}, {'timestamp': 1785308400, 'open': 82.584, 'high': 82.844, 'low': 82.184, 'close': 82.504, 'volume': 4725.0}, {'timestamp': 1785312000, 'open': 82.524, 'high': 82.754, 'low': 82.334, 'close': 82.354, 'volume': 1616.0}],
    "CL_M30": [{'timestamp': 1784804400, 'open': 90.758, 'high': 91.488, 'low': 90.718, 'close': 91.318, 'volume': 2380.0}, {'timestamp': 1784806200, 'open': 91.348, 'high': 91.788, 'low': 90.898, 'close': 91.298, 'volume': 2728.0}, {'timestamp': 1784808000, 'open': 91.268, 'high': 91.978, 'low': 91.158, 'close': 91.448, 'volume': 3321.0}, {'timestamp': 1784809800, 'open': 91.498, 'high': 91.838, 'low': 91.128, 'close': 91.438, 'volume': 3826.0}, {'timestamp': 1784811600, 'open': 91.498, 'high': 92.198, 'low': 91.298, 'close': 91.568, 'volume': 4753.0}, {'timestamp': 1784813400, 'open': 91.578, 'high': 92.498, 'low': 91.348, 'close': 92.348, 'volume': 4233.0}, {'timestamp': 1784815200, 'open': 92.338, 'high': 92.568, 'low': 91.598, 'close': 92.358, 'volume': 4107.0}, {'timestamp': 1784817000, 'open': 92.378, 'high': 92.758, 'low': 91.928, 'close': 92.508, 'volume': 3878.0}, {'timestamp': 1784818800, 'open': 92.458, 'high': 93.378, 'low': 92.348, 'close': 93.098, 'volume': 4670.0}, {'timestamp': 1784820600, 'open': 93.088, 'high': 93.388, 'low': 92.398, 'close': 92.468, 'volume': 4320.0}, {'timestamp': 1784822400, 'open': 92.448, 'high': 92.978, 'low': 92.198, 'close': 92.498, 'volume': 3309.0}, {'timestamp': 1784824200, 'open': 92.478, 'high': 93.188, 'low': 92.478, 'close': 92.938, 'volume': 2544.0}, {'timestamp': 1784826000, 'open': 92.948, 'high': 93.398, 'low': 92.928, 'close': 93.188, 'volume': 2690.0}, {'timestamp': 1784827800, 'open': 93.188, 'high': 93.888, 'low': 93.168, 'close': 93.848, 'volume': 2786.0}, {'timestamp': 1784829600, 'open': 93.838, 'high': 94.108, 'low': 92.628, 'close': 92.708, 'volume': 4206.0}, {'timestamp': 1784831400, 'open': 92.718, 'high': 92.958, 'low': 92.548, 'close': 92.648, 'volume': 2470.0}, {'timestamp': 1784833200, 'open': 92.638, 'high': 92.638, 'low': 92.168, 'close': 92.228, 'volume': 1963.0}, {'timestamp': 1784835000, 'open': 92.218, 'high': 92.468, 'low': 91.738, 'close': 92.208, 'volume': 2141.0}, {'timestamp': 1784836800, 'open': 92.218, 'high': 92.688, 'low': 92.038, 'close': 92.528, 'volume': 1345.0}, {'timestamp': 1784838600, 'open': 92.518, 'high': 93.018, 'low': 92.408, 'close': 92.998, 'volume': 1106.0}, {'timestamp': 1784844000, 'open': 93.066, 'high': 93.206, 'low': 92.716, 'close': 92.766, 'volume': 829.0}, {'timestamp': 1784845800, 'open': 92.756, 'high': 92.796, 'low': 92.646, 'close': 92.676, 'volume': 349.0}, {'timestamp': 1784847600, 'open': 92.676, 'high': 92.796, 'low': 92.676, 'close': 92.726, 'volume': 238.0}, {'timestamp': 1784849400, 'open': 92.736, 'high': 93.106, 'low': 92.646, 'close': 92.856, 'volume': 717.0}, {'timestamp': 1784851200, 'open': 92.866, 'high': 93.406, 'low': 92.766, 'close': 92.826, 'volume': 1915.0}, {'timestamp': 1784853000, 'open': 92.836, 'high': 92.936, 'low': 92.486, 'close': 92.496, 'volume': 1027.0}, {'timestamp': 1784854800, 'open': 92.456, 'high': 92.456, 'low': 91.966, 'close': 92.116, 'volume': 3466.0}, {'timestamp': 1784856600, 'open': 92.126, 'high': 92.276, 'low': 91.756, 'close': 92.236, 'volume': 2578.0}, {'timestamp': 1784858400, 'open': 92.246, 'high': 92.476, 'low': 92.196, 'close': 92.426, 'volume': 1328.0}, {'timestamp': 1784860200, 'open': 92.436, 'high': 92.636, 'low': 92.266, 'close': 92.496, 'volume': 1646.0}, {'timestamp': 1784862000, 'open': 92.506, 'high': 92.926, 'low': 92.456, 'close': 92.806, 'volume': 2170.0}, {'timestamp': 1784863800, 'open': 92.816, 'high': 92.986, 'low': 92.496, 'close': 92.496, 'volume': 946.0}, {'timestamp': 1784865600, 'open': 92.476, 'high': 92.576, 'low': 92.236, 'close': 92.266, 'volume': 752.0}, {'timestamp': 1784867400, 'open': 92.256, 'high': 92.336, 'low': 92.126, 'close': 92.246, 'volume': 681.0}, {'timestamp': 1784869200, 'open': 92.226, 'high': 92.436, 'low': 92.176, 'close': 92.316, 'volume': 708.0}, {'timestamp': 1784871000, 'open': 92.306, 'high': 92.386, 'low': 91.766, 'close': 92.086, 'volume': 2304.0}, {'timestamp': 1784872800, 'open': 92.096, 'high': 92.236, 'low': 91.696, 'close': 91.906, 'volume': 2441.0}, {'timestamp': 1784874600, 'open': 91.896, 'high': 91.946, 'low': 91.106, 'close': 91.156, 'volume': 2945.0}, {'timestamp': 1784876400, 'open': 91.156, 'high': 91.336, 'low': 90.886, 'close': 90.906, 'volume': 3009.0}, {'timestamp': 1784878200, 'open': 90.916, 'high': 91.296, 'low': 90.746, 'close': 91.046, 'volume': 2857.0}, {'timestamp': 1784880000, 'open': 91.036, 'high': 91.386, 'low': 90.646, 'close': 90.656, 'volume': 3752.0}, {'timestamp': 1784881800, 'open': 90.716, 'high': 90.846, 'low': 90.026, 'close': 90.186, 'volume': 3850.0}, {'timestamp': 1784883600, 'open': 90.176, 'high': 90.216, 'low': 89.356, 'close': 89.656, 'volume': 3939.0}, {'timestamp': 1784885400, 'open': 89.626, 'high': 89.846, 'low': 89.336, 'close': 89.616, 'volume': 3159.0}, {'timestamp': 1784887200, 'open': 89.626, 'high': 90.376, 'low': 89.436, 'close': 90.226, 'volume': 2882.0}, {'timestamp': 1784889000, 'open': 90.236, 'high': 90.746, 'low': 90.216, 'close': 90.496, 'volume': 2368.0}, {'timestamp': 1784890800, 'open': 90.516, 'high': 90.606, 'low': 90.286, 'close': 90.436, 'volume': 1842.0}, {'timestamp': 1784892600, 'open': 90.436, 'high': 90.706, 'low': 89.536, 'close': 89.996, 'volume': 2829.0}, {'timestamp': 1784894400, 'open': 89.966, 'high': 90.606, 'low': 89.816, 'close': 90.076, 'volume': 3303.0}, {'timestamp': 1784896200, 'open': 90.066, 'high': 90.186, 'low': 89.556, 'close': 89.716, 'volume': 1574.0}],
}

# Warmup Daily Closes - 25 echte Tages-Closes
WARMUP_CLOSES = [68.491, 68.863, 69.243, 68.642, 69.114, 72.757, 74.77, 72.203, 71.773, 73.981, 79.144, 79.996, 80.289, 79.782, 82.492, 84.53, 83.133, 85.421, 88.418, 92.856, 91.106, 85.139, 82.547, 82.344, 82.354]

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

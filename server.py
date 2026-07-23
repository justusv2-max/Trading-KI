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
    "CL_H1":  [{'timestamp': 1784545200, 'open': 82.3, 'high': 82.41, 'low': 80.28, 'close': 80.95, 'volume': 7774.0}, {'timestamp': 1784548800, 'open': 80.94, 'high': 82.81, 'low': 80.93, 'close': 82.55, 'volume': 8153.0}, {'timestamp': 1784552400, 'open': 82.6, 'high': 82.67, 'low': 81.78, 'close': 82.39, 'volume': 8108.0}, {'timestamp': 1784556000, 'open': 82.4, 'high': 82.74, 'low': 81.97, 'close': 82.66, 'volume': 6560.0}, {'timestamp': 1784559600, 'open': 82.68, 'high': 82.77, 'low': 81.8, 'close': 82.24, 'volume': 6954.0}, {'timestamp': 1784563200, 'open': 82.26, 'high': 83.08, 'low': 81.87, 'close': 82.58, 'volume': 5123.0}, {'timestamp': 1784566800, 'open': 82.6, 'high': 82.97, 'low': 82.35, 'close': 82.85, 'volume': 4649.0}, {'timestamp': 1784570400, 'open': 82.86, 'high': 83.83, 'low': 82.51, 'close': 83.54, 'volume': 4941.0}, {'timestamp': 1784574000, 'open': 83.55, 'high': 83.67, 'low': 82.86, 'close': 83.11, 'volume': 3428.0}, {'timestamp': 1784577600, 'open': 83.12, 'high': 83.23, 'low': 83.04, 'close': 83.1, 'volume': 1868.0}, {'timestamp': 1784584800, 'open': 83.063, 'high': 83.353, 'low': 83.063, 'close': 83.293, 'volume': 813.0}, {'timestamp': 1784588400, 'open': 83.313, 'high': 83.383, 'low': 83.093, 'close': 83.133, 'volume': 508.0}, {'timestamp': 1784592000, 'open': 83.153, 'high': 83.203, 'low': 82.973, 'close': 83.153, 'volume': 1159.0}, {'timestamp': 1784595600, 'open': 83.183, 'high': 83.193, 'low': 82.603, 'close': 83.073, 'volume': 3635.0}, {'timestamp': 1784599200, 'open': 83.083, 'high': 83.193, 'low': 82.783, 'close': 82.803, 'volume': 1922.0}, {'timestamp': 1784602800, 'open': 82.813, 'high': 83.053, 'low': 82.763, 'close': 82.833, 'volume': 1714.0}, {'timestamp': 1784606400, 'open': 82.833, 'high': 82.903, 'low': 82.573, 'close': 82.783, 'volume': 818.0}, {'timestamp': 1784610000, 'open': 82.803, 'high': 83.063, 'low': 82.473, 'close': 82.703, 'volume': 2271.0}, {'timestamp': 1784613600, 'open': 82.733, 'high': 82.973, 'low': 82.563, 'close': 82.973, 'volume': 3809.0}, {'timestamp': 1784617200, 'open': 82.963, 'high': 83.693, 'low': 82.553, 'close': 82.563, 'volume': 4720.0}, {'timestamp': 1784620800, 'open': 82.583, 'high': 83.103, 'low': 82.053, 'close': 82.893, 'volume': 5830.0}, {'timestamp': 1784624400, 'open': 82.903, 'high': 84.023, 'low': 82.603, 'close': 83.913, 'volume': 4632.0}, {'timestamp': 1784628000, 'open': 83.923, 'high': 84.023, 'low': 82.963, 'close': 83.913, 'volume': 6440.0}, {'timestamp': 1784631600, 'open': 83.933, 'high': 84.653, 'low': 83.863, 'close': 84.533, 'volume': 4502.0}, {'timestamp': 1784635200, 'open': 84.503, 'high': 85.073, 'low': 83.983, 'close': 84.783, 'volume': 6240.0}, {'timestamp': 1784638800, 'open': 84.793, 'high': 85.593, 'low': 84.733, 'close': 85.033, 'volume': 7340.0}, {'timestamp': 1784642400, 'open': 85.043, 'high': 85.673, 'low': 84.733, 'close': 85.373, 'volume': 6609.0}, {'timestamp': 1784646000, 'open': 85.383, 'high': 85.503, 'low': 84.353, 'close': 85.163, 'volume': 6888.0}, {'timestamp': 1784649600, 'open': 85.153, 'high': 85.223, 'low': 84.753, 'close': 85.043, 'volume': 3948.0}, {'timestamp': 1784653200, 'open': 85.053, 'high': 85.153, 'low': 84.693, 'close': 85.013, 'volume': 3020.0}, {'timestamp': 1784656800, 'open': 85.023, 'high': 85.223, 'low': 84.623, 'close': 85.173, 'volume': 4315.0}, {'timestamp': 1784660400, 'open': 85.183, 'high': 85.413, 'low': 85.103, 'close': 85.313, 'volume': 1861.0}, {'timestamp': 1784664000, 'open': 85.313, 'high': 85.393, 'low': 84.973, 'close': 85.193, 'volume': 1342.0}, {'timestamp': 1784671200, 'open': 85.281, 'high': 85.421, 'low': 85.221, 'close': 85.341, 'volume': 405.0}, {'timestamp': 1784674800, 'open': 85.341, 'high': 85.541, 'low': 85.271, 'close': 85.421, 'volume': 400.0}, {'timestamp': 1784678400, 'open': 85.371, 'high': 85.451, 'low': 85.101, 'close': 85.281, 'volume': 1443.0}, {'timestamp': 1784682000, 'open': 85.271, 'high': 86.381, 'low': 85.211, 'close': 86.231, 'volume': 4923.0}, {'timestamp': 1784685600, 'open': 86.231, 'high': 86.281, 'low': 85.551, 'close': 85.691, 'volume': 3512.0}, {'timestamp': 1784689200, 'open': 85.711, 'high': 85.981, 'low': 85.671, 'close': 85.981, 'volume': 1795.0}, {'timestamp': 1784692800, 'open': 85.991, 'high': 86.091, 'low': 85.851, 'close': 86.061, 'volume': 1271.0}, {'timestamp': 1784696400, 'open': 86.041, 'high': 86.191, 'low': 85.661, 'close': 85.781, 'volume': 2562.0}, {'timestamp': 1784700000, 'open': 85.801, 'high': 87.011, 'low': 85.681, 'close': 86.771, 'volume': 5081.0}, {'timestamp': 1784703600, 'open': 86.761, 'high': 88.491, 'low': 86.761, 'close': 88.331, 'volume': 6521.0}, {'timestamp': 1784707200, 'open': 88.311, 'high': 88.431, 'low': 87.781, 'close': 88.251, 'volume': 6678.0}, {'timestamp': 1784710800, 'open': 88.261, 'high': 89.241, 'low': 87.971, 'close': 89.081, 'volume': 6529.0}, {'timestamp': 1784714400, 'open': 89.091, 'high': 89.091, 'low': 87.561, 'close': 87.801, 'volume': 6995.0}, {'timestamp': 1784718000, 'open': 87.811, 'high': 88.481, 'low': 87.651, 'close': 87.981, 'volume': 5412.0}, {'timestamp': 1784721600, 'open': 87.981, 'high': 88.311, 'low': 87.181, 'close': 87.861, 'volume': 5945.0}, {'timestamp': 1784725200, 'open': 87.871, 'high': 88.011, 'low': 86.791, 'close': 87.581, 'volume': 7692.0}, {'timestamp': 1784728800, 'open': 87.601, 'high': 87.791, 'low': 87.061, 'close': 87.381, 'volume': 5921.0}],
    "CL_M30": [{'timestamp': 1784743200, 'open': 87.461, 'high': 87.701, 'low': 87.281, 'close': 87.481, 'volume': 2560.0}, {'timestamp': 1784745000, 'open': 87.491, 'high': 87.731, 'low': 87.481, 'close': 87.691, 'volume': 1184.0}, {'timestamp': 1784746800, 'open': 87.711, 'high': 87.791, 'low': 87.511, 'close': 87.521, 'volume': 793.0}, {'timestamp': 1784748600, 'open': 87.511, 'high': 87.541, 'low': 87.101, 'close': 87.151, 'volume': 999.0}, {'timestamp': 1784750400, 'open': 87.161, 'high': 87.161, 'low': 86.871, 'close': 87.031, 'volume': 1254.0}, {'timestamp': 1784752200, 'open': 87.041, 'high': 87.301, 'low': 87.001, 'close': 87.061, 'volume': 988.0}, {'timestamp': 1784757600, 'open': 88.208, 'high': 88.928, 'low': 87.938, 'close': 88.778, 'volume': 1613.0}, {'timestamp': 1784759400, 'open': 88.788, 'high': 88.958, 'low': 88.418, 'close': 88.558, 'volume': 887.0}, {'timestamp': 1784761200, 'open': 88.538, 'high': 88.608, 'low': 88.388, 'close': 88.388, 'volume': 466.0}, {'timestamp': 1784763000, 'open': 88.388, 'high': 88.568, 'low': 88.348, 'close': 88.418, 'volume': 402.0}, {'timestamp': 1784764800, 'open': 88.428, 'high': 88.998, 'low': 87.968, 'close': 88.648, 'volume': 1926.0}, {'timestamp': 1784766600, 'open': 88.658, 'high': 88.888, 'low': 88.428, 'close': 88.588, 'volume': 1078.0}, {'timestamp': 1784768400, 'open': 88.578, 'high': 89.148, 'low': 88.448, 'close': 89.088, 'volume': 2901.0}, {'timestamp': 1784770200, 'open': 89.078, 'high': 89.238, 'low': 88.548, 'close': 88.708, 'volume': 2383.0}, {'timestamp': 1784772000, 'open': 88.718, 'high': 88.848, 'low': 88.648, 'close': 88.818, 'volume': 1290.0}, {'timestamp': 1784773800, 'open': 88.828, 'high': 89.088, 'low': 88.658, 'close': 88.858, 'volume': 1527.0}, {'timestamp': 1784775600, 'open': 88.868, 'high': 89.278, 'low': 88.818, 'close': 89.098, 'volume': 1530.0}, {'timestamp': 1784777400, 'open': 89.098, 'high': 89.148, 'low': 88.928, 'close': 89.018, 'volume': 687.0}, {'timestamp': 1784779200, 'open': 89.028, 'high': 89.078, 'low': 88.718, 'close': 88.748, 'volume': 747.0}, {'timestamp': 1784781000, 'open': 88.738, 'high': 88.888, 'low': 88.538, 'close': 88.738, 'volume': 795.0}, {'timestamp': 1784782800, 'open': 88.728, 'high': 89.018, 'low': 88.608, 'close': 88.608, 'volume': 763.0}, {'timestamp': 1784784600, 'open': 88.598, 'high': 88.988, 'low': 88.268, 'close': 88.898, 'volume': 2392.0}, {'timestamp': 1784786400, 'open': 88.888, 'high': 88.918, 'low': 88.548, 'close': 88.868, 'volume': 2034.0}, {'timestamp': 1784788200, 'open': 88.858, 'high': 89.398, 'low': 88.828, 'close': 89.248, 'volume': 2136.0}, {'timestamp': 1784790000, 'open': 89.208, 'high': 90.218, 'low': 89.208, 'close': 89.838, 'volume': 3246.0}, {'timestamp': 1784791800, 'open': 89.848, 'high': 90.458, 'low': 89.728, 'close': 89.918, 'volume': 3282.0}, {'timestamp': 1784793600, 'open': 89.888, 'high': 90.138, 'low': 89.538, 'close': 89.818, 'volume': 3704.0}, {'timestamp': 1784795400, 'open': 89.878, 'high': 90.338, 'low': 89.838, 'close': 90.118, 'volume': 3029.0}, {'timestamp': 1784797200, 'open': 90.128, 'high': 90.968, 'low': 89.858, 'close': 90.768, 'volume': 3009.0}, {'timestamp': 1784799000, 'open': 90.788, 'high': 90.948, 'low': 90.438, 'close': 90.828, 'volume': 3127.0}, {'timestamp': 1784800800, 'open': 90.838, 'high': 91.198, 'low': 90.478, 'close': 91.168, 'volume': 2580.0}, {'timestamp': 1784802600, 'open': 91.168, 'high': 91.328, 'low': 90.728, 'close': 90.738, 'volume': 2550.0}, {'timestamp': 1784804400, 'open': 90.758, 'high': 91.488, 'low': 90.718, 'close': 91.318, 'volume': 2380.0}, {'timestamp': 1784806200, 'open': 91.348, 'high': 91.788, 'low': 90.898, 'close': 91.298, 'volume': 2728.0}, {'timestamp': 1784808000, 'open': 91.268, 'high': 91.978, 'low': 91.158, 'close': 91.448, 'volume': 3321.0}, {'timestamp': 1784809800, 'open': 91.498, 'high': 91.838, 'low': 91.128, 'close': 91.438, 'volume': 3826.0}, {'timestamp': 1784811600, 'open': 91.498, 'high': 92.198, 'low': 91.298, 'close': 91.568, 'volume': 4753.0}, {'timestamp': 1784813400, 'open': 91.578, 'high': 92.498, 'low': 91.348, 'close': 92.348, 'volume': 4233.0}, {'timestamp': 1784815200, 'open': 92.338, 'high': 92.568, 'low': 91.598, 'close': 92.358, 'volume': 4107.0}, {'timestamp': 1784817000, 'open': 92.378, 'high': 92.758, 'low': 91.928, 'close': 92.508, 'volume': 3878.0}, {'timestamp': 1784818800, 'open': 92.458, 'high': 93.378, 'low': 92.348, 'close': 93.098, 'volume': 4670.0}, {'timestamp': 1784820600, 'open': 93.088, 'high': 93.388, 'low': 92.398, 'close': 92.468, 'volume': 4320.0}, {'timestamp': 1784822400, 'open': 92.448, 'high': 92.978, 'low': 92.198, 'close': 92.498, 'volume': 3309.0}, {'timestamp': 1784824200, 'open': 92.478, 'high': 93.188, 'low': 92.478, 'close': 92.938, 'volume': 2544.0}, {'timestamp': 1784826000, 'open': 92.948, 'high': 93.398, 'low': 92.928, 'close': 93.188, 'volume': 2690.0}, {'timestamp': 1784827800, 'open': 93.188, 'high': 93.888, 'low': 93.168, 'close': 93.848, 'volume': 2786.0}, {'timestamp': 1784829600, 'open': 93.838, 'high': 94.108, 'low': 92.628, 'close': 92.708, 'volume': 4206.0}, {'timestamp': 1784831400, 'open': 92.718, 'high': 92.958, 'low': 92.548, 'close': 92.648, 'volume': 2470.0}, {'timestamp': 1784833200, 'open': 92.638, 'high': 92.638, 'low': 92.168, 'close': 92.228, 'volume': 1963.0}, {'timestamp': 1784835000, 'open': 92.218, 'high': 92.398, 'low': 91.738, 'close': 92.298, 'volume': 1161.0}],
}
# Gemeinsame Daily Closes - verhindert unterschiedliche Momentum Werte
SHARED_DAILY = deque([77.687, 74.853, 73.816, 70.578, 72.151, 70.954, 71.022, 70.625, 68.608, 68.951, 69.243, 69.002, 72.554, 74.947, 72.13, 71.773, 78.131, 80.054, 80.386, 79.689, 82.492, 83.1, 85.193, 87.061, 92.298], maxlen=30)

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
            # Speichere NUR Kerzen - Daily Closes kommen aus Warmup
            json.dump({
                "buffers": {k: list(v) for k,v in BUFFERS.items()}
            }, f)
    except Exception as e: print("Cache Fehler:", e)

cache = load_cache()
if cache:
    print("Cache geladen - echte Preise aktiv!")
    BUFFERS = {k: deque(cache["buffers"].get(k, DEFAULT_BARS[k]), maxlen=300) for k in PARAMS}
    if "shared_daily" in cache: SHARED_DAILY = deque([76.782, 77.687, 74.853, 73.816, 70.578, 72.151, 70.954, 71.022, 70.625, 68.608, 68.951, 69.243, 69.002, 72.554, 74.947, 72.13, 71.773, 78.131, 80.054, 80.386, 79.689, 82.492, 83.1, 85.193, 87.491], maxlen=30)
else:
    print("Defaults geladen - SpotCrude ~82$")
    BUFFERS = {k: deque(DEFAULT_BARS[k], maxlen=300) for k in PARAMS}

# Offene Trades Liste - mehrere gleichzeitig moeglich wie im Backtest
OPEN_TRADES = {"CL_H1": [], "CL_M30": []}

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

def update_open_trades(inst, bar):
    """Aktualisiert offene Trades - exakt wie Backtest Logik"""
    names = {"CL_H1": "CL H1", "CL_M30": "CL M30"}
    crv = PARAMS[inst]["crv"]
    zeit = datetime.now(CET).strftime("%d.%m.%Y %H:%M")
    remaining = []
    for trade in OPEN_TRADES[inst]:
        trade["bars_since"] += 1
        closed = False

        if not trade["entry_filled"]:
            # Warte bis Limit Order gefuellt - exakt wie Backtest
            if trade["direction"] == "LONG" and bar["low"] <= trade["entry"]:
                trade["entry_filled"] = True
            elif trade["direction"] == "SHORT" and bar["high"] >= trade["entry"]:
                trade["entry_filled"] = True
            # Limit abgelaufen ohne Fuellung
            if not trade["entry_filled"] and trade["bars_since"] >= PARAMS[inst]["max_pb_bars"]:
                send_telegram("⏱ <b>" + names[inst] + " LIMIT ABGELAUFEN</b>\nEntry " + str(trade["entry"]) + " nicht erreicht\nOrder loeschen! | " + zeit)
                closed = True

        # Entry gefuellt - Stop/Target in GLEICHER Kerze pruefen (1 zu 1 Backtest)
        if trade["entry_filled"] and not closed:
            if trade["direction"] == "SHORT":
                if bar["high"] >= trade["stop"]:
                    send_telegram("🔴 <b>" + names[inst] + " STOP LOSS</b>\nEntry: " + str(trade["entry"]) + " | Stop: " + str(trade["stop"]) + "\nVerlust: -1R | " + zeit)
                    closed = True
                elif bar["low"] <= trade["target"]:
                    send_telegram("✅ <b>" + names[inst] + " TARGET ERREICHT</b>\nEntry: " + str(trade["entry"]) + " | Target: " + str(trade["target"]) + "\nGewinn: +" + str(crv) + "R | " + zeit)
                    closed = True
            elif trade["direction"] == "LONG":
                if bar["low"] <= trade["stop"]:
                    send_telegram("🔴 <b>" + names[inst] + " STOP LOSS</b>\nEntry: " + str(trade["entry"]) + " | Stop: " + str(trade["stop"]) + "\nVerlust: -1R | " + zeit)
                    closed = True
                elif bar["high"] >= trade["target"]:
                    send_telegram("✅ <b>" + names[inst] + " TARGET ERREICHT</b>\nEntry: " + str(trade["entry"]) + " | Target: " + str(trade["target"]) + "\nGewinn: +" + str(crv) + "R | " + zeit)
                    closed = True

        if not closed:
            remaining.append(trade)
    OPEN_TRADES[inst] = remaining

def check_signal(inst, bar):
    """Exakt wie Backtest - kein Lock, immer weitersuchen"""
    buf = BUFFERS[inst]; p = PARAMS[inst]
    if len(buf) < 15: return None
    # Gemeinsamer Momentum Filter
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
    # LONG - exakt wie Backtest
    if c["low"] < p_bar["low"] and c["close"] >= p_bar["low"] + mm:
        en = p_bar["low"]; st = c["low"] - sb; rk = en - st
        if 0 < rk <= mr:
            return {"direction": "LONG", "entry": round(en,2), "stop": round(st,2), "target": round(en+rk*crv,2)}
    # SHORT - exakt wie Backtest
    if c["high"] > p_bar["high"] and c["close"] <= p_bar["high"] - mm:
        en = p_bar["high"]; st = c["high"] + sb; rk = st - en
        if 0 < rk <= mr:
            return {"direction": "SHORT", "entry": round(en,2), "stop": round(st,2), "target": round(en-rk*crv,2)}
    return None

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
        if data.get("daily_close"):
            SHARED_DAILY.append(float(data["daily_close"]))
    except Exception as e: return jsonify({"error": str(e)}), 400
    BUFFERS[inst].append(bar)
    # Offene Trades aktualisieren
    update_open_trades(inst, bar)
    save_cache()
    # Signal suchen - KEIN LOCK wie im Backtest
    sig = check_signal(inst, bar)
    if sig:
        names = {"CL_H1": "CL H1", "CL_M30": "CL M30"}
        crv = PARAMS[inst]["crv"]
        d = sig["direction"]
        em = "\U0001f7e2" if d == "LONG" else "\U0001f534"
        zeit = datetime.now(CET).strftime("%d.%m.%Y %H:%M")
        # Trade zur offenen Liste hinzufuegen
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
           "Momentum (gemeinsam): " + (str(round(mom,1))+"%%" if mom else "?") + "\n"
           "Mom Filter: " + ("OK - handelbar!" if (mom and abs(mom)<=15) else "GESPERRT") + "\n"
           "Offene H1 Trades: " + str(len(OPEN_TRADES["CL_H1"])) + "\n"
           "Offene M30 Trades: " + str(len(OPEN_TRADES["CL_M30"])))
    return jsonify({"sent": send_telegram(msg), "cache": cache_ok})

# GET und POST Reset - einfach im Browser aufrufbar
@app.route("/reset/<instrument>", methods=["GET", "POST"])
def reset(instrument):
    inst_map = {"cl_h1": "CL_H1", "cl_m30": "CL_M30"}
    inst = inst_map.get(instrument.lower())
    if not inst: return jsonify({"error": "Unbekannt"}), 400
    OPEN_TRADES[inst] = []
    names = {"CL_H1": "CL H1", "CL_M30": "CL M30"}
    send_telegram("🔄 <b>" + names[inst] + " - ALLE TRADES RESETTET</b>\nBereit fuer neue Signale!")
    return jsonify({"reset": inst, "status": "Alle offenen Trades geloescht!"})

@app.route("/reset_all", methods=["GET", "POST"])
def reset_all():
    OPEN_TRADES["CL_H1"] = []
    OPEN_TRADES["CL_M30"] = []
    send_telegram("🔄 <b>ALLE TRADES RESETTET</b>\nH1 + M30 bereit fuer neue Signale!")
    return jsonify({"reset": "all", "status": "Alle offenen Trades geloescht!"})

@app.route("/", methods=["GET"])
def home():
    mom = calc_mom()
    return jsonify({
        "status": "running",
        "system": "CL H1 (2R) + CL M30 (2R) | SpotCrude CFD | 1 zu 1 Backtest Logik",
        "momentum_gemeinsam": round(mom,2) if mom else None,
        "cache": os.path.exists(CACHE_FILE),
        "offene_trades": {k: len(v) for k,v in OPEN_TRADES.items()},
        "endpoints": {
            "/webhook/cl_h1": "POST - CL H1 Signal",
            "/webhook/cl_m30": "POST - CL M30 Signal",
            "/status": "GET - System Status",
            "/test": "GET - Telegram Test",
            "/reset/cl_h1": "GET - H1 Trades loeschen",
            "/reset/cl_m30": "GET - M30 Trades loeschen",
            "/reset_all": "GET - Alle Trades loeschen"
        }
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

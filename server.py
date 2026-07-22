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
    "CL_M30": [{'timestamp': 1784638800, 'open': 84.793, 'high': 85.313, 'low': 84.733, 'close': 85.263, 'volume': 3718.0}, {'timestamp': 1784640600, 'open': 85.283, 'high': 85.593, 'low': 84.943, 'close': 85.033, 'volume': 3622.0}, {'timestamp': 1784642400, 'open': 85.043, 'high': 85.333, 'low': 84.853, 'close': 85.273, 'volume': 3143.0}, {'timestamp': 1784644200, 'open': 85.293, 'high': 85.673, 'low': 84.733, 'close': 85.373, 'volume': 3466.0}, {'timestamp': 1784646000, 'open': 85.383, 'high': 85.503, 'low': 84.353, 'close': 85.213, 'volume': 4101.0}, {'timestamp': 1784647800, 'open': 85.253, 'high': 85.443, 'low': 85.003, 'close': 85.163, 'volume': 2787.0}, {'timestamp': 1784649600, 'open': 85.153, 'high': 85.203, 'low': 84.753, 'close': 84.983, 'volume': 2261.0}, {'timestamp': 1784651400, 'open': 84.973, 'high': 85.223, 'low': 84.843, 'close': 85.043, 'volume': 1687.0}, {'timestamp': 1784653200, 'open': 85.053, 'high': 85.153, 'low': 84.693, 'close': 84.853, 'volume': 1476.0}, {'timestamp': 1784655000, 'open': 84.853, 'high': 85.153, 'low': 84.843, 'close': 85.013, 'volume': 1544.0}, {'timestamp': 1784656800, 'open': 85.023, 'high': 85.053, 'low': 84.623, 'close': 85.033, 'volume': 2901.0}, {'timestamp': 1784658600, 'open': 85.043, 'high': 85.223, 'low': 84.773, 'close': 85.173, 'volume': 1414.0}, {'timestamp': 1784660400, 'open': 85.183, 'high': 85.343, 'low': 85.103, 'close': 85.293, 'volume': 1002.0}, {'timestamp': 1784662200, 'open': 85.283, 'high': 85.413, 'low': 85.183, 'close': 85.313, 'volume': 859.0}, {'timestamp': 1784664000, 'open': 85.313, 'high': 85.393, 'low': 85.133, 'close': 85.163, 'volume': 650.0}, {'timestamp': 1784665800, 'open': 85.153, 'high': 85.213, 'low': 84.973, 'close': 85.193, 'volume': 692.0}, {'timestamp': 1784671200, 'open': 85.281, 'high': 85.311, 'low': 85.221, 'close': 85.281, 'volume': 225.0}, {'timestamp': 1784673000, 'open': 85.291, 'high': 85.421, 'low': 85.281, 'close': 85.341, 'volume': 180.0}, {'timestamp': 1784674800, 'open': 85.341, 'high': 85.351, 'low': 85.271, 'close': 85.321, 'volume': 107.0}, {'timestamp': 1784676600, 'open': 85.311, 'high': 85.541, 'low': 85.291, 'close': 85.421, 'volume': 293.0}, {'timestamp': 1784678400, 'open': 85.371, 'high': 85.391, 'low': 85.181, 'close': 85.351, 'volume': 769.0}, {'timestamp': 1784680200, 'open': 85.331, 'high': 85.451, 'low': 85.101, 'close': 85.281, 'volume': 674.0}, {'timestamp': 1784682000, 'open': 85.271, 'high': 86.381, 'low': 85.211, 'close': 86.111, 'volume': 2911.0}, {'timestamp': 1784683800, 'open': 86.101, 'high': 86.371, 'low': 86.071, 'close': 86.231, 'volume': 2012.0}, {'timestamp': 1784685600, 'open': 86.231, 'high': 86.281, 'low': 85.801, 'close': 85.921, 'volume': 1540.0}, {'timestamp': 1784687400, 'open': 85.911, 'high': 85.921, 'low': 85.551, 'close': 85.691, 'volume': 1972.0}, {'timestamp': 1784689200, 'open': 85.711, 'high': 85.941, 'low': 85.671, 'close': 85.801, 'volume': 1238.0}, {'timestamp': 1784691000, 'open': 85.811, 'high': 85.981, 'low': 85.771, 'close': 85.981, 'volume': 557.0}, {'timestamp': 1784692800, 'open': 85.991, 'high': 86.051, 'low': 85.851, 'close': 85.901, 'volume': 635.0}, {'timestamp': 1784694600, 'open': 85.891, 'high': 86.091, 'low': 85.881, 'close': 86.061, 'volume': 636.0}, {'timestamp': 1784696400, 'open': 86.041, 'high': 86.191, 'low': 85.981, 'close': 86.021, 'volume': 599.0}, {'timestamp': 1784698200, 'open': 86.031, 'high': 86.091, 'low': 85.661, 'close': 85.781, 'volume': 1963.0}, {'timestamp': 1784700000, 'open': 85.801, 'high': 86.771, 'low': 85.681, 'close': 86.661, 'volume': 2675.0}, {'timestamp': 1784701800, 'open': 86.661, 'high': 87.011, 'low': 86.531, 'close': 86.771, 'volume': 2406.0}, {'timestamp': 1784703600, 'open': 86.761, 'high': 87.431, 'low': 86.761, 'close': 87.381, 'volume': 2470.0}, {'timestamp': 1784705400, 'open': 87.401, 'high': 88.491, 'low': 87.321, 'close': 88.331, 'volume': 4051.0}, {'timestamp': 1784707200, 'open': 88.311, 'high': 88.351, 'low': 87.781, 'close': 88.011, 'volume': 3733.0}, {'timestamp': 1784709000, 'open': 88.001, 'high': 88.431, 'low': 87.781, 'close': 88.251, 'volume': 2945.0}, {'timestamp': 1784710800, 'open': 88.261, 'high': 88.721, 'low': 87.971, 'close': 88.641, 'volume': 3213.0}, {'timestamp': 1784712600, 'open': 88.691, 'high': 89.241, 'low': 88.431, 'close': 89.081, 'volume': 3316.0}, {'timestamp': 1784714400, 'open': 89.091, 'high': 89.091, 'low': 87.561, 'close': 87.631, 'volume': 3708.0}, {'timestamp': 1784716200, 'open': 87.621, 'high': 88.071, 'low': 87.561, 'close': 87.801, 'volume': 3287.0}, {'timestamp': 1784718000, 'open': 87.811, 'high': 88.131, 'low': 87.811, 'close': 88.041, 'volume': 2134.0}, {'timestamp': 1784719800, 'open': 88.041, 'high': 88.481, 'low': 87.651, 'close': 87.981, 'volume': 3278.0}, {'timestamp': 1784721600, 'open': 87.981, 'high': 88.191, 'low': 87.381, 'close': 87.411, 'volume': 2741.0}, {'timestamp': 1784723400, 'open': 87.421, 'high': 88.311, 'low': 87.181, 'close': 87.861, 'volume': 3204.0}, {'timestamp': 1784725200, 'open': 87.871, 'high': 88.011, 'low': 86.791, 'close': 86.981, 'volume': 4164.0}, {'timestamp': 1784727000, 'open': 86.968, 'high': 87.631, 'low': 86.811, 'close': 87.581, 'volume': 3528.0}, {'timestamp': 1784728800, 'open': 87.601, 'high': 87.791, 'low': 87.361, 'close': 87.731, 'volume': 2777.0}, {'timestamp': 1784730600, 'open': 87.641, 'high': 87.781, 'low': 87.061, 'close': 87.471, 'volume': 2790.0}],
}
# Gemeinsame Daily Closes - verhindert unterschiedliche Momentum Werte
SHARED_DAILY = deque([76.782, 77.687, 74.853, 73.816, 70.578, 72.151, 70.954, 71.022, 70.625, 68.608, 68.951, 69.243, 69.002, 72.554, 74.947, 72.13, 71.773, 78.131, 80.054, 80.386, 79.689, 82.492, 83.1, 85.193, 87.381], maxlen=30)

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
    """Aktualisiert offene Trades - sendet Telegram bei Stop/Target"""
    names = {"CL_H1": "CL H1", "CL_M30": "CL M30"}
    crv = PARAMS[inst]["crv"]
    zeit = datetime.now(CET).strftime("%d.%m.%Y %H:%M")
    remaining = []
    for trade in OPEN_TRADES[inst]:
        trade["bars_since"] += 1
        closed = False
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
        # Auto-close nach max_pb_bars (Limit nicht gefuellt)
        if not closed and trade["bars_since"] >= PARAMS[inst]["max_pb_bars"]:
            send_telegram("⏱ <b>" + names[inst] + " LIMIT ABGELAUFEN</b>\nEntry " + str(trade["entry"]) + " nicht erreicht - Order loeschen!")
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
            "bars_since": 0
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

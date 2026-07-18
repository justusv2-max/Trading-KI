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
CACHE_FILE = "/data/bar_cache.json"

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
    "CL_H1":  [{'timestamp': 1783926000, 'open': 74.06, 'high': 74.23, 'low': 73.66, 'close': 73.99, 'volume': 2882.0}, {'timestamp': 1783929600, 'open': 74.01, 'high': 74.04, 'low': 72.75, 'close': 73.05, 'volume': 6110.0}, {'timestamp': 1783933200, 'open': 73.07, 'high': 73.2, 'low': 72.61, 'close': 73.13, 'volume': 4026.0}, {'timestamp': 1783936800, 'open': 73.11, 'high': 73.95, 'low': 73.1, 'close': 73.8, 'volume': 4160.0}, {'timestamp': 1783940400, 'open': 73.83, 'high': 74.06, 'low': 73.59, 'close': 73.81, 'volume': 4414.0}, {'timestamp': 1783944000, 'open': 73.83, 'high': 74.47, 'low': 73.62, 'close': 73.77, 'volume': 5912.0}, {'timestamp': 1783947600, 'open': 73.79, 'high': 74.12, 'low': 73.43, 'close': 73.74, 'volume': 6388.0}, {'timestamp': 1783951200, 'open': 73.75, 'high': 75.21, 'low': 73.5, 'close': 74.49, 'volume': 16028.0}, {'timestamp': 1783954800, 'open': 74.51, 'high': 74.99, 'low': 74.4, 'close': 74.84, 'volume': 6444.0}, {'timestamp': 1783958400, 'open': 74.86, 'high': 75.96, 'low': 74.78, 'close': 75.73, 'volume': 7444.0}, {'timestamp': 1783962000, 'open': 75.75, 'high': 77.7, 'low': 75.39, 'close': 77.59, 'volume': 10378.0}, {'timestamp': 1783965600, 'open': 77.61, 'high': 78.45, 'low': 77.36, 'close': 77.65, 'volume': 14876.0}, {'timestamp': 1783969200, 'open': 77.66, 'high': 77.98, 'low': 77.47, 'close': 77.65, 'volume': 3816.0}, {'timestamp': 1783972800, 'open': 77.69, 'high': 78.58, 'low': 77.64, 'close': 77.99, 'volume': 4218.0}, {'timestamp': 1783980000, 'open': 78.04, 'high': 79.09, 'low': 77.86, 'close': 79.03, 'volume': 2426.0}, {'timestamp': 1783983600, 'open': 79.05, 'high': 79.58, 'low': 78.58, 'close': 78.94, 'volume': 2938.0}, {'timestamp': 1783987200, 'open': 78.96, 'high': 80.42, 'low': 78.57, 'close': 79.87, 'volume': 7746.0}, {'timestamp': 1783990800, 'open': 79.85, 'high': 79.96, 'low': 79.07, 'close': 79.51, 'volume': 6406.0}, {'timestamp': 1783994400, 'open': 79.55, 'high': 79.62, 'low': 78.92, 'close': 79.54, 'volume': 2814.0}, {'timestamp': 1783998000, 'open': 79.55, 'high': 80.07, 'low': 79.42, 'close': 79.62, 'volume': 3420.0}, {'timestamp': 1784001600, 'open': 79.61, 'high': 79.92, 'low': 79.42, 'close': 79.77, 'volume': 1690.0}, {'timestamp': 1784005200, 'open': 79.79, 'high': 79.91, 'low': 78.82, 'close': 79.36, 'volume': 3576.0}, {'timestamp': 1784008800, 'open': 79.4, 'high': 80.58, 'low': 79.32, 'close': 80.43, 'volume': 4526.0}, {'timestamp': 1784012400, 'open': 80.44, 'high': 80.93, 'low': 79.96, 'close': 80.37, 'volume': 7308.0}, {'timestamp': 1784016000, 'open': 80.4, 'high': 81.13, 'low': 79.96, 'close': 81.02, 'volume': 8918.0}, {'timestamp': 1784019600, 'open': 81.05, 'high': 81.25, 'low': 80.04, 'close': 80.57, 'volume': 6766.0}, {'timestamp': 1784023200, 'open': 80.6, 'high': 81.27, 'low': 80.31, 'close': 80.91, 'volume': 5672.0}, {'timestamp': 1784026800, 'open': 80.93, 'high': 81.06, 'low': 79.48, 'close': 79.53, 'volume': 7860.0}, {'timestamp': 1784030400, 'open': 79.55, 'high': 80.89, 'low': 79.49, 'close': 80.7, 'volume': 8480.0}, {'timestamp': 1784034000, 'open': 80.71, 'high': 80.97, 'low': 79.58, 'close': 79.92, 'volume': 14338.0}, {'timestamp': 1784037600, 'open': 79.95, 'high': 80.01, 'low': 78.11, 'close': 78.83, 'volume': 16198.0}, {'timestamp': 1784041200, 'open': 78.85, 'high': 79.8, 'low': 77.84, 'close': 79.47, 'volume': 19108.0}, {'timestamp': 1784044800, 'open': 79.49, 'high': 79.64, 'low': 78.78, 'close': 79.21, 'volume': 7448.0}, {'timestamp': 1784048400, 'open': 79.2, 'high': 79.32, 'low': 78.48, 'close': 78.72, 'volume': 6540.0}, {'timestamp': 1784052000, 'open': 78.73, 'high': 79.86, 'low': 78.71, 'close': 79.64, 'volume': 7888.0}, {'timestamp': 1784055600, 'open': 79.65, 'high': 79.97, 'low': 79.48, 'close': 79.69, 'volume': 3536.0}, {'timestamp': 1784059200, 'open': 79.67, 'high': 80.27, 'low': 79.66, 'close': 79.82, 'volume': 1672.0}, {'timestamp': 1784066400, 'open': 79.74, 'high': 80.24, 'low': 79.59, 'close': 79.89, 'volume': 1180.0}, {'timestamp': 1784070000, 'open': 79.93, 'high': 79.97, 'low': 79.67, 'close': 79.88, 'volume': 630.0}, {'timestamp': 1784073600, 'open': 79.85, 'high': 80.59, 'low': 79.6, 'close': 80.21, 'volume': 2360.0}, {'timestamp': 1784077200, 'open': 80.2, 'high': 80.26, 'low': 79.77, 'close': 80.22, 'volume': 2238.0}, {'timestamp': 1784080800, 'open': 80.24, 'high': 80.44, 'low': 80.03, 'close': 80.31, 'volume': 1244.0}, {'timestamp': 1784084400, 'open': 80.3, 'high': 80.32, 'low': 79.82, 'close': 79.92, 'volume': 1576.0}, {'timestamp': 1784088000, 'open': 79.96, 'high': 80.08, 'low': 79.65, 'close': 79.79, 'volume': 1046.0}, {'timestamp': 1784091600, 'open': 79.81, 'high': 80.0, 'low': 79.48, 'close': 79.72, 'volume': 1874.0}, {'timestamp': 1784095200, 'open': 79.73, 'high': 80.04, 'low': 79.49, 'close': 79.97, 'volume': 1894.0}, {'timestamp': 1784098800, 'open': 80.0, 'high': 80.63, 'low': 80.0, 'close': 80.51, 'volume': 3506.0}, {'timestamp': 1784102400, 'open': 80.56, 'high': 80.93, 'low': 79.34, 'close': 79.39, 'volume': 6876.0}, {'timestamp': 1784106000, 'open': 79.41, 'high': 80.18, 'low': 79.3, 'close': 80.12, 'volume': 3530.0}, {'timestamp': 1784109600, 'open': 80.14, 'high': 80.35, 'low': 79.92, 'close': 80.02, 'volume': 2728.0}],
    "CL_M30": [{'timestamp': 1784021400, 'open': 80.69, 'high': 80.69, 'low': 80.15, 'close': 80.57, 'volume': 2460.0}, {'timestamp': 1784023200, 'open': 80.6, 'high': 81.08, 'low': 80.5, 'close': 80.85, 'volume': 2368.0}, {'timestamp': 1784025000, 'open': 80.89, 'high': 81.27, 'low': 80.31, 'close': 80.91, 'volume': 3304.0}, {'timestamp': 1784026800, 'open': 80.93, 'high': 81.06, 'low': 79.93, 'close': 79.97, 'volume': 3362.0}, {'timestamp': 1784028600, 'open': 79.98, 'high': 79.98, 'low': 79.48, 'close': 79.53, 'volume': 4498.0}, {'timestamp': 1784030400, 'open': 79.55, 'high': 80.16, 'low': 79.49, 'close': 80.05, 'volume': 3306.0}, {'timestamp': 1784032200, 'open': 80.08, 'high': 80.89, 'low': 79.72, 'close': 80.7, 'volume': 5174.0}, {'timestamp': 1784034000, 'open': 80.71, 'high': 80.97, 'low': 79.83, 'close': 80.03, 'volume': 7070.0}, {'timestamp': 1784035800, 'open': 80.05, 'high': 80.53, 'low': 79.58, 'close': 79.92, 'volume': 7268.0}, {'timestamp': 1784037600, 'open': 79.95, 'high': 80.01, 'low': 79.31, 'close': 79.43, 'volume': 6338.0}, {'timestamp': 1784039400, 'open': 79.42, 'high': 79.52, 'low': 78.11, 'close': 78.83, 'volume': 9860.0}, {'timestamp': 1784041200, 'open': 78.85, 'high': 79.04, 'low': 77.84, 'close': 78.54, 'volume': 12048.0}, {'timestamp': 1784043000, 'open': 78.57, 'high': 79.8, 'low': 78.57, 'close': 79.47, 'volume': 7060.0}, {'timestamp': 1784044800, 'open': 79.49, 'high': 79.64, 'low': 78.78, 'close': 79.36, 'volume': 4914.0}, {'timestamp': 1784046600, 'open': 79.35, 'high': 79.39, 'low': 78.96, 'close': 79.21, 'volume': 2534.0}, {'timestamp': 1784048400, 'open': 79.2, 'high': 79.32, 'low': 78.81, 'close': 79.07, 'volume': 3124.0}, {'timestamp': 1784050200, 'open': 79.06, 'high': 79.17, 'low': 78.48, 'close': 78.72, 'volume': 3416.0}, {'timestamp': 1784052000, 'open': 78.73, 'high': 79.41, 'low': 78.71, 'close': 79.39, 'volume': 4540.0}, {'timestamp': 1784053800, 'open': 79.42, 'high': 79.86, 'low': 79.31, 'close': 79.64, 'volume': 3348.0}, {'timestamp': 1784055600, 'open': 79.65, 'high': 79.81, 'low': 79.48, 'close': 79.6, 'volume': 1884.0}, {'timestamp': 1784057400, 'open': 79.61, 'high': 79.97, 'low': 79.57, 'close': 79.69, 'volume': 1652.0}, {'timestamp': 1784059200, 'open': 79.67, 'high': 80.0, 'low': 79.66, 'close': 79.94, 'volume': 626.0}, {'timestamp': 1784061000, 'open': 79.96, 'high': 80.27, 'low': 79.79, 'close': 79.82, 'volume': 1046.0}, {'timestamp': 1784066400, 'open': 79.74, 'high': 80.24, 'low': 79.59, 'close': 79.85, 'volume': 936.0}, {'timestamp': 1784068200, 'open': 79.87, 'high': 80.01, 'low': 79.82, 'close': 79.89, 'volume': 244.0}, {'timestamp': 1784070000, 'open': 79.93, 'high': 79.97, 'low': 79.67, 'close': 79.77, 'volume': 274.0}, {'timestamp': 1784071800, 'open': 79.76, 'high': 79.93, 'low': 79.74, 'close': 79.88, 'volume': 356.0}, {'timestamp': 1784073600, 'open': 79.85, 'high': 80.33, 'low': 79.6, 'close': 80.25, 'volume': 1312.0}, {'timestamp': 1784075400, 'open': 80.3, 'high': 80.59, 'low': 80.19, 'close': 80.21, 'volume': 1048.0}, {'timestamp': 1784077200, 'open': 80.2, 'high': 80.22, 'low': 79.77, 'close': 80.09, 'volume': 1602.0}, {'timestamp': 1784079000, 'open': 80.1, 'high': 80.26, 'low': 79.9, 'close': 80.22, 'volume': 636.0}, {'timestamp': 1784080800, 'open': 80.24, 'high': 80.38, 'low': 80.03, 'close': 80.19, 'volume': 572.0}, {'timestamp': 1784082600, 'open': 80.2, 'high': 80.44, 'low': 80.14, 'close': 80.31, 'volume': 672.0}, {'timestamp': 1784084400, 'open': 80.3, 'high': 80.32, 'low': 80.06, 'close': 80.08, 'volume': 522.0}, {'timestamp': 1784086200, 'open': 80.11, 'high': 80.24, 'low': 79.82, 'close': 79.92, 'volume': 1054.0}, {'timestamp': 1784088000, 'open': 79.96, 'high': 80.08, 'low': 79.74, 'close': 79.84, 'volume': 624.0}, {'timestamp': 1784089800, 'open': 79.85, 'high': 79.9, 'low': 79.65, 'close': 79.79, 'volume': 422.0}, {'timestamp': 1784091600, 'open': 79.81, 'high': 80.0, 'low': 79.72, 'close': 79.88, 'volume': 610.0}, {'timestamp': 1784093400, 'open': 79.89, 'high': 79.91, 'low': 79.48, 'close': 79.72, 'volume': 1264.0}, {'timestamp': 1784095200, 'open': 79.73, 'high': 79.87, 'low': 79.49, 'close': 79.73, 'volume': 962.0}, {'timestamp': 1784097000, 'open': 79.69, 'high': 80.04, 'low': 79.56, 'close': 79.97, 'volume': 932.0}, {'timestamp': 1784098800, 'open': 80.0, 'high': 80.5, 'low': 80.0, 'close': 80.33, 'volume': 1818.0}, {'timestamp': 1784100600, 'open': 80.37, 'high': 80.63, 'low': 80.13, 'close': 80.51, 'volume': 1688.0}, {'timestamp': 1784102400, 'open': 80.56, 'high': 80.93, 'low': 79.81, 'close': 79.84, 'volume': 3772.0}, {'timestamp': 1784104200, 'open': 79.85, 'high': 80.02, 'low': 79.34, 'close': 79.39, 'volume': 3104.0}, {'timestamp': 1784106000, 'open': 79.41, 'high': 79.99, 'low': 79.3, 'close': 79.93, 'volume': 2064.0}, {'timestamp': 1784107800, 'open': 79.96, 'high': 80.18, 'low': 79.71, 'close': 80.12, 'volume': 1466.0}, {'timestamp': 1784109600, 'open': 80.14, 'high': 80.35, 'low': 79.94, 'close': 80.27, 'volume': 1658.0}, {'timestamp': 1784111400, 'open': 80.28, 'high': 80.31, 'low': 79.85, 'close': 79.88, 'volume': 1260.0}, {'timestamp': 1784113200, 'open': 79.86, 'high': 79.98, 'low': 79.74, 'close': 79.94, 'volume': 470.0}],
}
DEFAULT_DAILY = {
    "CL_H1":  [86.43, 84.28, 81.17, 76.61, 75.0, 75.51, 76.55, 74.07, 73.04, 69.86, 71.46, 70.25, 70.41, 70.02, 68.08, 68.45, 68.77, 68.61, 72.19, 74.77, 71.8, 71.5, 77.99, 79.82, 80.02],
    "CL_M30": [86.43, 84.28, 81.17, 76.61, 75.0, 75.51, 76.55, 74.07, 73.04, 69.86, 71.46, 70.25, 70.41, 70.02, 68.08, 68.45, 68.77, 68.61, 72.19, 74.77, 71.8, 71.5, 77.99, 79.82, 80.02],
}

def load_cache():
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE) as f: return json.load(f)
    except: pass
    return None

def save_cache():
    try:
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        with open(CACHE_FILE, "w") as f:
            json.dump({"buffers":{k:list(v) for k,v in BUFFERS.items()},
                       "daily":{k:list(v) for k,v in DAILY_CLOSES.items()}}, f)
    except Exception as e: print("Cache Fehler:", e)

cache = load_cache()
if cache:
    print("Cache geladen - echte Preise aktiv!")
    BUFFERS      = {k: deque(cache["buffers"].get(k, DEFAULT_BARS[k]),  maxlen=300) for k in PARAMS}
    DAILY_CLOSES = {k: deque(cache["daily"].get(k,   DEFAULT_DAILY[k]), maxlen=30)  for k in PARAMS}
else:
    print("Defaults geladen - USOIL CFD ~80$")
    BUFFERS      = {k: deque(DEFAULT_BARS[k],  maxlen=300) for k in PARAMS}
    DAILY_CLOSES = {k: deque(DEFAULT_DAILY[k], maxlen=30)  for k in PARAMS}

TRADE_STATUS = {inst: {"in_trade": False, "bars_since": 0} for inst in PARAMS}

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

def calc_mom(dc):
    c = list(dc)
    return (c[-1]-c[-21])/c[-21]*100 if len(c) >= 21 else None

def send_telegram(msg):
    url = "https://api.telegram.org/bot" + TELEGRAM_TOKEN + "/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=10)
        return r.status_code == 200
    except Exception as e:
        print(str(e)); return False

def check_signal(inst, bar):
    buf = BUFFERS[inst]; p = PARAMS[inst]; s = TRADE_STATUS[inst]
    if len(buf) < 15: return None
    if s["in_trade"]:
        s["bars_since"] += 1
        if s["bars_since"] >= p["max_pb_bars"]: s["in_trade"] = False; s["bars_since"] = 0
        else: return None
    bars = list(buf); c = bars[-1]
    ts = datetime.fromtimestamp(c["timestamp"], tz=timezone.utc).astimezone(CET)
    h = ts.hour
    if get_session(h) not in p["sessions"]: return None
    if h in p["excl_hours"]: return None
    vm = calc_vol_ma(buf, p["vol_ma_len"]); atr = calc_atr(buf)
    if vm is None or atr is None: return None
    if c["volume"] <= vm: return None
    if atr > p["atr_max"]: return None
    mom = calc_mom(DAILY_CLOSES[inst])
    if mom is not None and abs(mom) > p["mom_threshold"]: return None
    mm = p["momentum_min"]; sb = p["stop_buffer"]; mr = p["max_risk"]; crv = p["crv"]
    # LONG: Vorkerze Tief = Liquiditaetslevel
    p_bar = bars[-2]
    if c["low"] < p_bar["low"] and c["close"] >= p_bar["low"] + mm:
        en = p_bar["low"]; st = c["low"] - sb; rk = en - st
        if 0 < rk <= mr:
            s["in_trade"] = True; s["bars_since"] = 0
            return {"direction": "LONG", "entry": en, "stop": st, "target": en+rk*crv}
    # SHORT: Vorkerze Hoch = Liquiditaetslevel
    if c["high"] > p_bar["high"] and c["close"] <= p_bar["high"] - mm:
        en = p_bar["high"]; st = c["high"] + sb; rk = st - en
        if 0 < rk <= mr:
            s["in_trade"] = True; s["bars_since"] = 0
            return {"direction": "SHORT", "entry": en, "stop": st, "target": en-rk*crv}
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
        if data.get("daily_close"): DAILY_CLOSES[inst].append(float(data["daily_close"]))
    except Exception as e: return jsonify({"error": str(e)}), 400
    BUFFERS[inst].append(bar)
    save_cache()
    sig = check_signal(inst, bar)
    if sig:
        names = {"CL_H1": "CL H1", "CL_M30": "CL M30"}
        crv = PARAMS[inst]["crv"]
        d = sig["direction"]
        em = "\U0001f7e2" if d == "LONG" else "\U0001f534"
        zeit = datetime.now(CET).strftime("%d.%m.%Y %H:%M")
        msg = (em + " <b>" + names[inst] + " - " + d + " SIGNAL</b>\n\n"
               + "<b>Limit Order setzen:</b>\n"
               + "Entry:  <code>" + str(round(sig["entry"], 2)) + "</code>\n"
               + "Stop:   <code>" + str(round(sig["stop"], 2)) + "</code>\n"
               + "Target " + str(crv) + "R: <code>" + str(round(sig["target"], 2)) + "</code>\n"
               + "Risiko: <code>" + str(round(abs(sig["entry"]-sig["stop"]), 2)) + "</code>\n\n"
               + "<b>Pepperstone USOIL oeffnen!</b>\n"
               + "Zeit: " + zeit + " MEZ")
        send_telegram(msg)
        return jsonify({"status": "signal", "signal": sig})
    return jsonify({"status": "ok", "bars": len(BUFFERS[inst])})

@app.route("/status", methods=["GET"])
def status():
    res = {}
    for inst in PARAMS:
        mom = calc_mom(DAILY_CLOSES[inst])
        last_close = list(BUFFERS[inst])[-1]["close"] if BUFFERS[inst] else None
        res[inst] = {
            "bars": len(BUFFERS[inst]),
            "last_close": last_close,
            "in_trade": TRADE_STATUS[inst]["in_trade"],
            "crv": PARAMS[inst]["crv"],
            "momentum_20d": round(mom, 2) if mom else None,
            "mom_ok": abs(mom) <= PARAMS[inst]["mom_threshold"] if mom else True,
            "fully_ready": calc_vol_ma(BUFFERS[inst]) is not None,
            "cache_aktiv": os.path.exists(CACHE_FILE),
        }
    return jsonify(res)

@app.route("/test", methods=["GET"])
def test():
    cache_ok = os.path.exists(CACHE_FILE)
    last_h1 = list(BUFFERS["CL_H1"])[-1]["close"] if BUFFERS["CL_H1"] else "?"
    mom_h1 = calc_mom(DAILY_CLOSES["CL_H1"])
    msg = ("Trading Signal Server laeuft!\n\n"
           "Instrumente:\n"
           "CL H1:  2R | Kein 15 Uhr\n"
           "CL M30: 2R | Kein 15+19 Uhr\n\n"
           "Cache: " + ("AKTIV - echte Preise!" if cache_ok else "DEFAULTS ~80$") + "\n"
           "Letzter CL H1 Close: " + str(last_h1) + "$\n"
           "Momentum 20d: " + (str(round(mom_h1,1))+"%%" if mom_h1 else "?") + "\n"
           "Mom Filter: " + ("OK" if (mom_h1 and abs(mom_h1)<=15) else "GESPERRT"))
    return jsonify({"sent": send_telegram(msg), "cache": cache_ok})

@app.route("/reset/<instrument>", methods=["POST"])
def reset(instrument):
    inst_map = {"cl_h1": "CL_H1", "cl_m30": "CL_M30"}
    inst = inst_map.get(instrument.lower())
    if not inst: return jsonify({"error": "Unbekannt"}), 400
    TRADE_STATUS[inst]["in_trade"] = False; TRADE_STATUS[inst]["bars_since"] = 0
    return jsonify({"reset": inst, "status": "bereit"})

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "running",
        "system": "CL H1 (2R) + CL M30 (2R) | USOIL CFD",
        "cache": os.path.exists(CACHE_FILE),
        "endpoints": {
            "/webhook/cl_h1": "POST - CL H1 Signal",
            "/webhook/cl_m30": "POST - CL M30 Signal",
            "/status": "GET - System Status",
            "/test": "GET - Telegram Test",
            "/reset/cl_h1": "POST - Trade Reset H1",
            "/reset/cl_m30": "POST - Trade Reset M30"
        }
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

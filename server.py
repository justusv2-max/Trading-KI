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
# Versuche /data zu erstellen (Railway Volume)
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
    "CL_H1":  [{'timestamp': 1784134800, 'open': 79.626, 'high': 79.626, 'low': 78.946, 'close': 79.126, 'volume': 5094.0}, {'timestamp': 1784138400, 'open': 79.116, 'high': 80.046, 'low': 78.976, 'close': 79.896, 'volume': 4290.0}, {'timestamp': 1784142000, 'open': 79.906, 'high': 80.826, 'low': 79.706, 'close': 80.456, 'volume': 3666.0}, {'timestamp': 1784145600, 'open': 80.466, 'high': 80.626, 'low': 80.326, 'close': 80.386, 'volume': 1710.0}, {'timestamp': 1784152800, 'open': 80.119, 'high': 80.689, 'low': 80.029, 'close': 80.419, 'volume': 1164.0}, {'timestamp': 1784156400, 'open': 80.399, 'high': 80.479, 'low': 80.239, 'close': 80.289, 'volume': 533.0}, {'timestamp': 1784160000, 'open': 80.289, 'high': 80.339, 'low': 79.999, 'close': 80.249, 'volume': 1359.0}, {'timestamp': 1784163600, 'open': 80.229, 'high': 80.489, 'low': 80.069, 'close': 80.179, 'volume': 3157.0}, {'timestamp': 1784167200, 'open': 80.169, 'high': 80.399, 'low': 80.119, 'close': 80.149, 'volume': 2009.0}, {'timestamp': 1784170800, 'open': 80.139, 'high': 80.209, 'low': 79.399, 'close': 79.669, 'volume': 2594.0}, {'timestamp': 1784174400, 'open': 79.669, 'high': 79.739, 'low': 79.379, 'close': 79.499, 'volume': 1381.0}, {'timestamp': 1784178000, 'open': 79.489, 'high': 79.609, 'low': 79.269, 'close': 79.529, 'volume': 2559.0}, {'timestamp': 1784181600, 'open': 79.549, 'high': 79.809, 'low': 79.379, 'close': 79.539, 'volume': 3870.0}, {'timestamp': 1784185200, 'open': 79.529, 'high': 79.899, 'low': 79.339, 'close': 79.669, 'volume': 4096.0}, {'timestamp': 1784188800, 'open': 79.679, 'high': 79.799, 'low': 79.389, 'close': 79.439, 'volume': 5001.0}, {'timestamp': 1784192400, 'open': 79.439, 'high': 79.769, 'low': 79.019, 'close': 79.679, 'volume': 4556.0}, {'timestamp': 1784196000, 'open': 79.689, 'high': 79.809, 'low': 79.519, 'close': 79.739, 'volume': 2741.0}, {'timestamp': 1784199600, 'open': 79.749, 'high': 80.389, 'low': 79.449, 'close': 79.799, 'volume': 4410.0}, {'timestamp': 1784203200, 'open': 79.759, 'high': 80.839, 'low': 79.739, 'close': 80.619, 'volume': 6467.0}, {'timestamp': 1784206800, 'open': 80.609, 'high': 80.989, 'low': 79.999, 'close': 80.199, 'volume': 6985.0}, {'timestamp': 1784210400, 'open': 80.209, 'high': 80.429, 'low': 79.579, 'close': 79.709, 'volume': 6314.0}, {'timestamp': 1784214000, 'open': 79.709, 'high': 79.889, 'low': 79.299, 'close': 79.469, 'volume': 6056.0}, {'timestamp': 1784217600, 'open': 79.469, 'high': 80.189, 'low': 78.949, 'close': 79.099, 'volume': 6490.0}, {'timestamp': 1784221200, 'open': 79.109, 'high': 79.369, 'low': 78.829, 'close': 78.889, 'volume': 4759.0}, {'timestamp': 1784224800, 'open': 78.899, 'high': 79.199, 'low': 78.709, 'close': 79.129, 'volume': 3487.0}, {'timestamp': 1784228400, 'open': 79.139, 'high': 79.289, 'low': 79.069, 'close': 79.179, 'volume': 1334.0}, {'timestamp': 1784232000, 'open': 79.189, 'high': 79.799, 'low': 78.989, 'close': 79.689, 'volume': 1561.0}, {'timestamp': 1784239200, 'open': 79.662, 'high': 79.822, 'low': 79.572, 'close': 79.682, 'volume': 655.0}, {'timestamp': 1784242800, 'open': 79.692, 'high': 79.792, 'low': 79.672, 'close': 79.782, 'volume': 302.0}, {'timestamp': 1784246400, 'open': 79.762, 'high': 79.912, 'low': 79.552, 'close': 79.882, 'volume': 1370.0}, {'timestamp': 1784250000, 'open': 79.852, 'high': 80.332, 'low': 79.772, 'close': 79.922, 'volume': 2810.0}, {'timestamp': 1784253600, 'open': 79.932, 'high': 80.012, 'low': 79.532, 'close': 79.772, 'volume': 2057.0}, {'timestamp': 1784257200, 'open': 79.772, 'high': 79.932, 'low': 79.642, 'close': 79.922, 'volume': 1275.0}, {'timestamp': 1784260800, 'open': 79.922, 'high': 80.042, 'low': 79.842, 'close': 79.942, 'volume': 695.0}, {'timestamp': 1784264400, 'open': 79.952, 'high': 79.972, 'low': 78.912, 'close': 79.182, 'volume': 3474.0}, {'timestamp': 1784268000, 'open': 79.212, 'high': 79.652, 'low': 78.702, 'close': 79.402, 'volume': 4659.0}, {'timestamp': 1784271600, 'open': 79.419, 'high': 79.892, 'low': 79.419, 'close': 79.532, 'volume': 3490.0}, {'timestamp': 1784275200, 'open': 79.542, 'high': 80.082, 'low': 79.292, 'close': 80.072, 'volume': 4730.0}, {'timestamp': 1784278800, 'open': 80.082, 'high': 80.682, 'low': 80.052, 'close': 80.532, 'volume': 4227.0}, {'timestamp': 1784282400, 'open': 80.522, 'high': 80.852, 'low': 80.332, 'close': 80.762, 'volume': 2813.0}, {'timestamp': 1784286000, 'open': 80.732, 'high': 81.072, 'low': 80.682, 'close': 80.952, 'volume': 2853.0}, {'timestamp': 1784289600, 'open': 80.962, 'high': 81.212, 'low': 80.822, 'close': 81.112, 'volume': 3134.0}, {'timestamp': 1784293200, 'open': 81.102, 'high': 81.962, 'low': 81.072, 'close': 81.912, 'volume': 5773.0}, {'timestamp': 1784296800, 'open': 81.902, 'high': 82.012, 'low': 80.962, 'close': 80.982, 'volume': 4704.0}, {'timestamp': 1784300400, 'open': 80.982, 'high': 81.612, 'low': 80.582, 'close': 81.452, 'volume': 5991.0}, {'timestamp': 1784304000, 'open': 81.442, 'high': 82.312, 'low': 81.392, 'close': 82.232, 'volume': 4679.0}, {'timestamp': 1784307600, 'open': 82.232, 'high': 82.632, 'low': 82.042, 'close': 82.532, 'volume': 3459.0}, {'timestamp': 1784311200, 'open': 82.542, 'high': 82.822, 'low': 82.122, 'close': 82.172, 'volume': 3996.0}, {'timestamp': 1784314800, 'open': 82.182, 'high': 82.232, 'low': 81.872, 'close': 82.202, 'volume': 2361.0}, {'timestamp': 1784318400, 'open': 82.202, 'high': 82.622, 'low': 82.092, 'close': 82.492, 'volume': 1499.0}],
    "CL_M30": [{'timestamp': 1784228400, 'open': 79.139, 'high': 79.219, 'low': 79.069, 'close': 79.109, 'volume': 666.0}, {'timestamp': 1784230200, 'open': 79.119, 'high': 79.289, 'low': 79.119, 'close': 79.179, 'volume': 668.0}, {'timestamp': 1784232000, 'open': 79.189, 'high': 79.279, 'low': 78.989, 'close': 79.229, 'volume': 641.0}, {'timestamp': 1784233800, 'open': 79.239, 'high': 79.799, 'low': 79.239, 'close': 79.689, 'volume': 920.0}, {'timestamp': 1784239200, 'open': 79.662, 'high': 79.822, 'low': 79.572, 'close': 79.722, 'volume': 441.0}, {'timestamp': 1784241000, 'open': 79.682, 'high': 79.782, 'low': 79.682, 'close': 79.682, 'volume': 214.0}, {'timestamp': 1784242800, 'open': 79.692, 'high': 79.782, 'low': 79.672, 'close': 79.762, 'volume': 174.0}, {'timestamp': 1784244600, 'open': 79.772, 'high': 79.792, 'low': 79.712, 'close': 79.782, 'volume': 128.0}, {'timestamp': 1784246400, 'open': 79.762, 'high': 79.802, 'low': 79.552, 'close': 79.762, 'volume': 779.0}, {'timestamp': 1784248200, 'open': 79.752, 'high': 79.912, 'low': 79.592, 'close': 79.882, 'volume': 591.0}, {'timestamp': 1784250000, 'open': 79.852, 'high': 80.292, 'low': 79.772, 'close': 80.292, 'volume': 1616.0}, {'timestamp': 1784251800, 'open': 80.292, 'high': 80.332, 'low': 79.872, 'close': 79.922, 'volume': 1194.0}, {'timestamp': 1784253600, 'open': 79.932, 'high': 80.012, 'low': 79.832, 'close': 79.842, 'volume': 646.0}, {'timestamp': 1784255400, 'open': 79.832, 'high': 79.842, 'low': 79.532, 'close': 79.772, 'volume': 1411.0}, {'timestamp': 1784257200, 'open': 79.772, 'high': 79.872, 'low': 79.642, 'close': 79.822, 'volume': 831.0}, {'timestamp': 1784259000, 'open': 79.832, 'high': 79.932, 'low': 79.702, 'close': 79.922, 'volume': 444.0}, {'timestamp': 1784260800, 'open': 79.922, 'high': 80.042, 'low': 79.842, 'close': 80.012, 'volume': 421.0}, {'timestamp': 1784262600, 'open': 80.012, 'high': 80.042, 'low': 79.872, 'close': 79.942, 'volume': 274.0}, {'timestamp': 1784264400, 'open': 79.952, 'high': 79.972, 'low': 79.702, 'close': 79.742, 'volume': 337.0}, {'timestamp': 1784266200, 'open': 79.752, 'high': 79.872, 'low': 78.912, 'close': 79.182, 'volume': 3137.0}, {'timestamp': 1784268000, 'open': 79.212, 'high': 79.232, 'low': 78.702, 'close': 79.202, 'volume': 2655.0}, {'timestamp': 1784269800, 'open': 79.222, 'high': 79.652, 'low': 79.132, 'close': 79.402, 'volume': 2004.0}, {'timestamp': 1784271600, 'open': 79.419, 'high': 79.892, 'low': 79.419, 'close': 79.772, 'volume': 1732.0}, {'timestamp': 1784273400, 'open': 79.772, 'high': 79.822, 'low': 79.502, 'close': 79.532, 'volume': 1758.0}, {'timestamp': 1784275200, 'open': 79.542, 'high': 79.872, 'low': 79.292, 'close': 79.852, 'volume': 2820.0}, {'timestamp': 1784277000, 'open': 79.812, 'high': 80.082, 'low': 79.562, 'close': 80.072, 'volume': 1910.0}, {'timestamp': 1784278800, 'open': 80.082, 'high': 80.582, 'low': 80.052, 'close': 80.532, 'volume': 2299.0}, {'timestamp': 1784280600, 'open': 80.542, 'high': 80.682, 'low': 80.422, 'close': 80.532, 'volume': 1928.0}, {'timestamp': 1784282400, 'open': 80.522, 'high': 80.852, 'low': 80.332, 'close': 80.602, 'volume': 1658.0}, {'timestamp': 1784284200, 'open': 80.622, 'high': 80.812, 'low': 80.512, 'close': 80.762, 'volume': 1155.0}, {'timestamp': 1784286000, 'open': 80.732, 'high': 81.072, 'low': 80.692, 'close': 80.832, 'volume': 1416.0}, {'timestamp': 1784287800, 'open': 80.842, 'high': 80.972, 'low': 80.682, 'close': 80.952, 'volume': 1437.0}, {'timestamp': 1784289600, 'open': 80.962, 'high': 81.072, 'low': 80.822, 'close': 81.002, 'volume': 1366.0}, {'timestamp': 1784291400, 'open': 81.012, 'high': 81.212, 'low': 80.862, 'close': 81.112, 'volume': 1768.0}, {'timestamp': 1784293200, 'open': 81.102, 'high': 81.772, 'low': 81.072, 'close': 81.712, 'volume': 3079.0}, {'timestamp': 1784295000, 'open': 81.732, 'high': 81.962, 'low': 81.352, 'close': 81.912, 'volume': 2694.0}, {'timestamp': 1784296800, 'open': 81.902, 'high': 82.012, 'low': 81.602, 'close': 81.672, 'volume': 2362.0}, {'timestamp': 1784298600, 'open': 81.662, 'high': 81.662, 'low': 80.962, 'close': 80.982, 'volume': 2342.0}, {'timestamp': 1784300400, 'open': 80.982, 'high': 81.332, 'low': 80.582, 'close': 81.182, 'volume': 3497.0}, {'timestamp': 1784302200, 'open': 81.172, 'high': 81.612, 'low': 81.082, 'close': 81.452, 'volume': 2494.0}, {'timestamp': 1784304000, 'open': 81.442, 'high': 82.272, 'low': 81.392, 'close': 82.162, 'volume': 3061.0}, {'timestamp': 1784305800, 'open': 82.152, 'high': 82.312, 'low': 81.972, 'close': 82.232, 'volume': 1618.0}, {'timestamp': 1784307600, 'open': 82.232, 'high': 82.482, 'low': 82.042, 'close': 82.402, 'volume': 1512.0}, {'timestamp': 1784309400, 'open': 82.402, 'high': 82.632, 'low': 82.272, 'close': 82.532, 'volume': 1947.0}, {'timestamp': 1784311200, 'open': 82.542, 'high': 82.822, 'low': 82.382, 'close': 82.442, 'volume': 2568.0}, {'timestamp': 1784313000, 'open': 82.412, 'high': 82.452, 'low': 82.122, 'close': 82.172, 'volume': 1428.0}, {'timestamp': 1784314800, 'open': 82.182, 'high': 82.232, 'low': 82.082, 'close': 82.132, 'volume': 973.0}, {'timestamp': 1784316600, 'open': 82.132, 'high': 82.222, 'low': 81.872, 'close': 82.202, 'volume': 1388.0}, {'timestamp': 1784318400, 'open': 82.202, 'high': 82.512, 'low': 82.092, 'close': 82.492, 'volume': 727.0}, {'timestamp': 1784320200, 'open': 82.492, 'high': 82.622, 'low': 82.372, 'close': 82.492, 'volume': 772.0}],
}
DEFAULT_DAILY = {
    "CL_H1":  [81.996, 77.371, 76.387, 76.782, 77.687, 74.853, 73.816, 70.578, 72.151, 70.954, 71.022, 70.625, 68.608, 68.951, 69.243, 69.002, 72.554, 74.947, 72.13, 71.773, 78.131, 80.054, 80.386, 79.689, 82.492],
    "CL_M30": [81.996, 77.371, 76.387, 76.782, 77.687, 74.853, 73.816, 70.578, 72.151, 70.954, 71.022, 70.625, 68.608, 68.951, 69.243, 69.002, 72.554, 74.947, 72.13, 71.773, 78.131, 80.054, 80.386, 79.689, 82.492],
}

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
        "system": "CL H1 (2R) + CL M30 (2R) | SpotCrude CFD",
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

from flask import Flask, request, jsonify
import requests
import json
import os
from datetime import datetime, timezone
import pytz
from collections import deque

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "trading123")

BUFFERS = {
    "CL_H1": deque(maxlen=300),
    "ES_H1": deque(maxlen=300),
    "ES_M30": deque(maxlen=300),
    "EURUSD_H1": deque(maxlen=300),
}

TRADE_STATUS = {
    "CL_H1":     {"in_trade": False, "bars": 0},
    "ES_H1":     {"in_trade": False, "bars": 0},
    "ES_M30":    {"in_trade": False, "bars": 0},
    "EURUSD_H1": {"in_trade": False, "bars": 0},
}

DAILY_CLOSES = {
    "CL_H1":     deque(maxlen=30),
    "ES_H1":     deque(maxlen=30),
    "ES_M30":    deque(maxlen=30),
    "EURUSD_H1": deque(maxlen=30),
}

CET = pytz.timezone("Europe/Berlin")
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=payload, timeout=10)
        return r.status_code == 200
    except Exception as e:
        print(f"Telegram Fehler: {e}")
        return False

def calc_vol_ma(buffer, period=20):
    vols = [b["volume"] for b in buffer]
    if len(vols) < period: return None
    return sum(vols[-period:]) / period

def calc_atr(buffer, period=14):
    if len(buffer) < period + 1: return None
    trs = []
    bars = list(buffer)
    for i in range(1, len(bars)):
        hl = bars[i]["high"] - bars[i]["low"]
        hc = abs(bars[i]["high"] - bars[i-1]["close"])
        lc = abs(bars[i]["low"] - bars[i-1]["close"])
        trs.append(max(hl, hc, lc))
    return sum(trs[-period:]) / period

def calc_momentum(daily_closes):
    closes = list(daily_closes)
    if len(closes) < 21: return None
    return (closes[-1] - closes[-21]) / closes[-21] * 100

def get_session_cl_es(hour_cet):
    if 9 <= hour_cet < 15: return "Europa"
    elif 15 <= hour_cet < 22: return "US"
    else: return "Off"

def get_session_eurusd(hour_cet):
    if 13 <= hour_cet < 16: return "Overlap"
    elif 8 <= hour_cet < 13: return "London"
    elif 16 <= hour_cet < 22: return "NewYork"
    elif 0 <= hour_cet < 8: return "Asia"
    else: return "Off"
      def check_signal(inst, bar):
    buffer = BUFFERS[inst]
    status = TRADE_STATUS[inst]

    if status["in_trade"]:
        status["bars"] += 1
        max_pb = 144 if inst == "ES_M30" else 72
        if status["bars"] >= max_pb:
            status["in_trade"] = False
            status["bars"] = 0
        else:
            return None

    ts = datetime.fromtimestamp(bar["timestamp"], tz=timezone.utc).astimezone(CET)
    hour_cet = ts.hour

    if inst == "EURUSD_H1":
        session = get_session_eurusd(hour_cet)
        if session != "Overlap": return None
    else:
        session = get_session_cl_es(hour_cet)
        if session == "Off": return None
        if hour_cet == 15: return None

    vol_ma = calc_vol_ma(buffer)
    atr14  = calc_atr(buffer)
    if vol_ma is None or atr14 is None: return None
    if bar["volume"] <= vol_ma: return None

    bars = list(buffer)
    price_ref = sum(b["close"] for b in bars[-20:]) / min(20, len(bars))

    if inst == "CL_H1":
        if atr14 > 1.0: return None
        mom = calc_momentum(DAILY_CLOSES[inst])
        if mom and abs(mom) > 15: return None
        mm = 0.50; sb = 0.10; mr = 5.0; crv = 2.0
    elif inst in ["ES_H1", "ES_M30"]:
        if atr14 > price_ref * 0.0143: return None
        mom = calc_momentum(DAILY_CLOSES[inst])
        if mom and abs(mom) > 10: return None
        mm = price_ref * 0.0071
        sb = price_ref * 0.0014
        mr = price_ref * 0.071
        crv = 2.0
    else:
        sb = price_ref * 0.0014
        mr = price_ref * 0.071
        crv = 1.5
        mm = 0

    for i in range(2, min(12, len(bars))):
        liq  = bars[-i-1]["low"]
        extr = bars[-i]["low"]
        if extr < liq and bar["close"] >= liq + mm:
            en = liq; st = extr - sb; rk = en - st
            if 0 < rk <= mr:
                status["in_trade"] = True; status["bars"] = 0
                return {"direction": "LONG", "entry": en, "stop": st,
                        "target": en + rk * crv, "risk": rk, "inst": inst}

    for i in range(2, min(12, len(bars))):
        liq  = bars[-i-1]["high"]
        extr = bars[-i]["high"]
        if extr > liq and bar["close"] <= liq - mm:
            en = liq; st = extr + sb; rk = st - en
            if 0 < rk <= mr:
                status["in_trade"] = True; status["bars"] = 0
                return {"direction": "SHORT", "entry": en, "stop": st,
                        "target": en - rk * crv, "risk": rk, "inst": inst}
    return None

@app.route("/webhook/<instrument>", methods=["POST"])
def webhook(instrument):
    inst_map = {"cl": "CL_H1", "es_h1": "ES_H1", "es_m30": "ES_M30", "eurusd": "EURUSD_H1"}
    inst = inst_map.get(instrument.lower())
    if not inst: return jsonify({"error": "Unbekannt"}), 400
    try:
        data = request.get_json()
        if data.get("secret") != WEBHOOK_SECRET:
            return jsonify({"error": "Ungültiger Secret"}), 401
        bar = {
            "timestamp": data.get("timestamp", datetime.now().timestamp()),
            "open": float(data["open"]), "high": float(data["high"]),
            "low": float(data["low"]), "close": float(data["close"]),
            "volume": float(data["volume"]),
        }
        if data.get("daily_close"):
            DAILY_CLOSES[inst].append(float(data["daily_close"]))
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    BUFFERS[inst].append(bar)
    signal = check_signal(inst, bar)

    if signal:
        names = {"CL_H1": "CL H1", "ES_H1": "ES H1", "ES_M30": "ES M30", "EURUSD_H1": "EUR/USD H1"}
        emoji = "🟢" if signal["direction"] == "LONG" else "🔴"
        fmt = "#.####" if "USD" in inst else "#.##"
        msg = f"""{emoji} <b>{names[inst]} – {signal['direction']}</b>

<b>Limit Order setzen:</b>
Entry:  <code>{signal['entry']:.4f if 'USD' in inst else f"{signal['entry']:.2f}"}</code>
Stop:   <code>{signal['stop']:.4f if 'USD' in inst else f"{signal['stop']:.2f}"}</code>
Target: <code>{signal['target']:.4f if 'USD' in inst else f"{signal['target']:.2f}"}</code>
Risiko: <code>{signal['risk']:.4f if 'USD' in inst else f"{signal['risk']:.2f}"}</code>

<b>Pepperstone öffnen und Limit Order platzieren!</b>
Zeit: {datetime.now(CET).strftime('%d.%m.%Y %H:%M')} MEZ"""
        send_telegram(msg)
        return jsonify({"status": "signal", "signal": signal})

    return jsonify({"status": "ok", "bars": len(BUFFERS[inst])})

@app.route("/status", methods=["GET"])
def status():
    return jsonify({inst: {"bars": len(BUFFERS[inst]), "in_trade": TRADE_STATUS[inst]["in_trade"]} for inst in BUFFERS})

@app.route("/test", methods=["GET"])
def test():
    sent = send_telegram("✅ Trading Signal Server läuft!\nAlle Systeme aktiv.")
    return jsonify({"sent": sent})

@app.route("/reset/<instrument>", methods=["POST"])
def reset(instrument):
    inst_map = {"cl": "CL_H1", "es_h1": "ES_H1", "es_m30": "ES_M30", "eurusd": "EURUSD_H1"}
    inst = inst_map.get(instrument.lower())
    if not inst: return jsonify({"error": "Unbekannt"}), 400
    TRADE_STATUS[inst]["in_trade"] = False
    TRADE_STATUS[inst]["bars"] = 0
    return jsonify({"reset": inst})

@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "running", "message": "Trading Signal Server aktiv!"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

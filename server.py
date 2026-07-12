from flask import Flask, request, jsonify
import requests
import os
from datetime import datetime, timezone
import pytz
from collections import deque

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "trading123")

PARAMS = {
    "CL_H1": {
        "momentum_min_abs": 0.50,
        "stop_buffer": 0.10,
        "max_risk": 5.00,
        "crv": 2.0,
        "atr_max": 1.00,
        "atr_pct": False,
        "vol_ma_len": 20,
        "mom_threshold": 15.0,
        "max_pb_bars": 72,
        "sessions": ["Europa", "US"],
        "excl_hours": [15],
    },
    "ES_H1": {
        "momentum_min_pct": 0.0071,
        "stop_buffer_pct": 0.0014,
        "max_risk_pct": 0.071,
        "crv": 1.0,
        "atr_max_pct": 0.0143,
        "atr_pct": True,
        "vol_ma_len": 20,
        "mom_threshold": 10.0,
        "max_pb_bars": 72,
        "sessions": ["Europa", "US"],
        "excl_hours": [15],
    },
    "ES_M30": {
        "momentum_min_pct": 0.0071,
        "stop_buffer_pct": 0.0014,
        "max_risk_pct": 0.071,
        "crv": 1.0,
        "atr_max_pct": 0.0143,
        "atr_pct": True,
        "vol_ma_len": 20,
        "mom_threshold": 10.0,
        "max_pb_bars": 144,
        "sessions": ["Europa", "US"],
        "excl_hours": [15],
    },
    "EURUSD_H1": {
        "stop_buffer_pct": 0.0014,
        "max_risk_pct": 0.071,
        "crv": 1.5,
        "atr_pct": False,
        "vol_ma_len": 20,
        "mom_threshold": None,
        "max_pb_bars": 72,
        "sessions": ["Overlap"],
        "excl_hours": [],
        "swing_bars": 3,
    },
}

BUFFERS = {inst: deque(maxlen=300) for inst in PARAMS}
TRADE_STATUS = {inst: {"in_trade": False, "bars_since": 0} for inst in PARAMS}

# Startwerte: letzte 25 Tages-Closes aus Backtest Daten
DAILY_CLOSES = {
    "CL_H1": deque([92.78, 88.62, 87.74, 86.97, 91.68, 92.6, 95.41, 92.12, 89.46, 90.49,
                    87.91, 91.06, 85.63, 83.5, 80.37, 75.83, 75.01, 75.52, 76.54, 74.08,
                    73.05, 69.87, 71.47, 70.24, 70.84], maxlen=30),
    "ES_H1": deque([7595.0, 7616.5, 7650.0, 7653.0, 7670.75, 7690.5, 7609.75, 7650.0, 7430.25, 7474.5,
                    7452.25, 7329.25, 7460.5, 7498.5, 7624.25, 7583.0, 7511.0, 7574.75, 7556.25, 7540.75,
                    7445.5, 7477.5, 7433.75, 7397.25, 7462.75], maxlen=30),
    "ES_M30": deque([7595.0, 7616.5, 7650.0, 7653.0, 7670.75, 7690.5, 7609.75, 7650.0, 7430.25, 7474.5,
                     7452.25, 7329.25, 7460.5, 7498.5, 7624.25, 7583.0, 7511.0, 7574.75, 7556.25, 7540.75,
                     7445.5, 7477.5, 7433.75, 7397.25, 7462.75], maxlen=30),
    "EURUSD_H1": deque([1.15989, 1.1614, 1.15226, 1.15115, 1.15372, 1.15394, 1.15358, 1.15774, 1.15669, 1.1606,
                        1.15904, 1.16091, 1.15038, 1.14623, 1.14712, 1.14622, 1.14284, 1.13837, 1.13586, 1.13732,
                        1.1385, 1.13838, 1.1426, 1.14224, 1.14078], maxlen=30),
}

CET = pytz.timezone("Europe/Berlin")


def get_session(hour_cet, inst):
    if inst == "EURUSD_H1":
        if 13 <= hour_cet < 16:
            return "Overlap"
        elif 8 <= hour_cet < 13:
            return "London"
        elif 16 <= hour_cet < 22:
            return "NewYork"
        elif 0 <= hour_cet < 8:
            return "Asia"
        else:
            return "Off"
    else:
        if 9 <= hour_cet < 15:
            return "Europa"
        elif 15 <= hour_cet < 22:
            return "US"
        else:
            return "Off"


def calc_vol_ma(buffer, period=20):
    vols = [b["volume"] for b in buffer]
    if len(vols) < period:
        return None
    return sum(vols[-period:]) / period


def calc_atr(buffer, period=14):
    if len(buffer) < period + 1:
        return None
    trs = []
    bars = list(buffer)
    for i in range(1, len(bars)):
        hl = bars[i]["high"] - bars[i]["low"]
        hc = abs(bars[i]["high"] - bars[i-1]["close"])
        lc = abs(bars[i]["low"] - bars[i-1]["close"])
        trs.append(max(hl, hc, lc))
    return sum(trs[-period:]) / period


def calc_momentum_20d(daily_closes):
    closes = list(daily_closes)
    if len(closes) < 21:
        return None
    return (closes[-1] - closes[-21]) / closes[-21] * 100


def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=payload, timeout=10)
        return r.status_code == 200
    except Exception as e:
        print(f"Telegram Fehler: {e}")
        return False


def check_signal(inst, bar):
    buffer = BUFFERS[inst]
    p = PARAMS[inst]
    status = TRADE_STATUS[inst]

    if len(buffer) < 15:
        return None

    if status["in_trade"]:
        status["bars_since"] += 1
        if status["bars_since"] >= p["max_pb_bars"]:
            status["in_trade"] = False
            status["bars_since"] = 0
        else:
            return None

    bars = list(buffer)
    c = bars[-1]
    ts = datetime.fromtimestamp(c["timestamp"], tz=timezone.utc).astimezone(CET)
    hour_cet = ts.hour
    session = get_session(hour_cet, inst)

    if session not in p["sessions"]:
        return None
    if hour_cet in p["excl_hours"]:
        return None

    vol_ma = calc_vol_ma(buffer, p["vol_ma_len"])
    atr14 = calc_atr(buffer)
    if vol_ma is None or atr14 is None:
        return None
    if c["volume"] <= vol_ma:
        return None

    price_ref = sum(b["close"] for b in bars[-20:]) / min(20, len(bars))

    if p["atr_pct"]:
        if atr14 > price_ref * p["atr_max_pct"]:
            return None
        mm = price_ref * p["momentum_min_pct"]
        sb = price_ref * p["stop_buffer_pct"]
        mr = price_ref * p["max_risk_pct"]
    else:
        if "atr_max" in p and atr14 > p["atr_max"]:
            return None
        mm = p.get("momentum_min_abs", 0)
        sb = p.get("stop_buffer", price_ref * p.get("stop_buffer_pct", 0.0014))
        mr = p.get("max_risk", price_ref * p.get("max_risk_pct", 0.071))

    if p["mom_threshold"]:
        mom = calc_momentum_20d(DAILY_CLOSES[inst])
        if mom is not None and abs(mom) > p["mom_threshold"]:
            return None

    if inst == "EURUSD_H1":
        swing_bars = p["swing_bars"]
        n = len(bars)
        for idx in range(swing_bars, n - swing_bars - 1):
            sl = bars[idx]["low"]
            if all(bars[idx-j]["low"] > sl and bars[idx+j]["low"] > sl for j in range(1, swing_bars+1)):
                if c["low"] < sl and c["close"] > sl:
                    en = sl
                    st = c["low"] - sb
                    rk = en - st
                    if 0 < rk <= mr:
                        status["in_trade"] = True
                        status["bars_since"] = 0
                        return {"direction": "LONG", "entry": en, "stop": st,
                                "target": en + rk * p["crv"], "inst": inst}
        for idx in range(swing_bars, n - swing_bars - 1):
            sh = bars[idx]["high"]
            if all(bars[idx-j]["high"] < sh and bars[idx+j]["high"] < sh for j in range(1, swing_bars+1)):
                if c["high"] > sh and c["close"] < sh:
                    en = sh
                    st = c["high"] + sb
                    rk = st - en
                    if 0 < rk <= mr:
                        status["in_trade"] = True
                        status["bars_since"] = 0
                        return {"direction": "SHORT", "entry": en, "stop": st,
                                "target": en - rk * p["crv"], "inst": inst}
    else:
        for i in range(2, min(12, len(bars))):
            liq = bars[-i-1]["low"]
            extr = bars[-i]["low"]
            if extr < liq and c["close"] >= liq + mm:
                en = liq
                st = extr - sb
                rk = en - st
                if 0 < rk <= mr:
                    status["in_trade"] = True
                    status["bars_since"] = 0
                    return {"direction": "LONG", "entry": en, "stop": st,
                            "target": en + rk * p["crv"], "inst": inst}
        for i in range(2, min(12, len(bars))):
            liq = bars[-i-1]["high"]
            extr = bars[-i]["high"]
            if extr > liq and c["close"] <= liq - mm:
                en = liq
                st = extr + sb
                rk = st - en
                if 0 < rk <= mr:
                    status["in_trade"] = True
                    status["bars_since"] = 0
                    return {"direction": "SHORT", "entry": en, "stop": st,
                            "target": en - rk * p["crv"], "inst": inst}

    return None


@app.route("/webhook/<instrument>", methods=["POST"])
def webhook(instrument):
    inst_map = {"cl": "CL_H1", "es_h1": "ES_H1", "es_m30": "ES_M30", "eurusd": "EURUSD_H1"}
    inst = inst_map.get(instrument.lower())
    if not inst:
        return jsonify({"error": "Unbekannt"}), 400
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Keine Daten"}), 400
        if data.get("secret") != WEBHOOK_SECRET:
            return jsonify({"error": "Ungültiger Secret"}), 401
        bar = {
            "timestamp": data.get("timestamp", datetime.now().timestamp()),
            "open": float(data["open"]),
            "high": float(data["high"]),
            "low": float(data["low"]),
            "close": float(data["close"]),
            "volume": float(data["volume"]),
        }
        if data.get("daily_close"):
            DAILY_CLOSES[inst].append(float(data["daily_close"]))
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    BUFFERS[inst].append(bar)
    signal = check_signal(inst, bar)

    if signal:
        inst_names = {
            "CL_H1": "CL H1",
            "ES_H1": "ES H1",
            "ES_M30": "ES M30",
            "EURUSD_H1": "EUR/USD H1"
        }
        crv = PARAMS[inst]["crv"]
        emoji = "🟢" if signal["direction"] == "LONG" else "🔴"
        is_forex = "USD" in inst
        fmt = ".4f" if is_forex else ".2f"
        msg = (
            f"{emoji} <b>{inst_names[inst]} – {signal['direction']} SIGNAL</b>\n\n"
            f"<b>Limit Order setzen:</b>\n"
            f"Entry:  <code>{signal['entry']:{fmt}}</code>\n"
            f"Stop:   <code>{signal['stop']:{fmt}}</code>\n"
            f"Target {crv}R: <code>{signal['target']:{fmt}}</code>\n\n"
            f"<b>Pepperstone öffnen!</b>\n"
            f"Zeit: {datetime.now(CET).strftime('%d.%m.%Y %H:%M')} MEZ"
        )
        send_telegram(msg)
        return jsonify({"status": "signal", "signal": signal})

    return jsonify({"status": "ok", "bars": len(BUFFERS[inst])})


@app.route("/status", methods=["GET"])
def status():
    result = {}
    for inst in PARAMS:
        mom = calc_momentum_20d(DAILY_CLOSES[inst])
        result[inst] = {
            "bars": len(BUFFERS[inst]),
            "in_trade": TRADE_STATUS[inst]["in_trade"],
            "crv": PARAMS[inst]["crv"],
            "momentum_20d": round(mom, 2) if mom else None,
            "daily_closes": len(DAILY_CLOSES[inst]),
        }
    return jsonify(result)


@app.route("/test", methods=["GET"])
def test():
    sent = send_telegram(
        "✅ Trading Signal Server läuft!\n\n"
        "CRV Einstellungen:\n"
        "• CL H1: 2R\n"
        "• ES H1: 1R\n"
        "• ES M30: 1R\n"
        "• EUR/USD H1: 1.5R"
    )
    return jsonify({"sent": sent})


@app.route("/reset/<instrument>", methods=["POST"])
def reset(instrument):
    inst_map = {"cl": "CL_H1", "es_h1": "ES_H1", "es_m30": "ES_M30", "eurusd": "EURUSD_H1"}
    inst = inst_map.get(instrument.lower())
    if not inst:
        return jsonify({"error": "Unbekannt"}), 400
    TRADE_STATUS[inst]["in_trade"] = False
    TRADE_STATUS[inst]["bars_since"] = 0
    return jsonify({"reset": inst})


@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "running",
        "message": "Trading Signal Server aktiv!",
        "crv": {"CL": "2R", "ES_H1": "1R", "ES_M30": "1R", "EURUSD": "1.5R"}
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

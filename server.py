from flask import Flask, request, jsonify
import requests
import os
from datetime import datetime, timezone
import pytz
from collections import deque


app = Flask(__name__)


# ---------------------------------------------------------
# RAILWAY-VARIABLEN
# ---------------------------------------------------------

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "trading123")


# ---------------------------------------------------------
# STRATEGIE-PARAMETER
# ---------------------------------------------------------

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

    "CL_M30": {
        "momentum_min_abs": 0.50,
        "stop_buffer": 0.10,
        "max_risk": 5.00,
        "crv": 2.0,
        "atr_max": 1.00,
        "atr_pct": False,
        "vol_ma_len": 20,
        "mom_threshold": 15.0,
        "max_pb_bars": 144,
        "sessions": ["Europa", "US"],
        "excl_hours": [15, 19],
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
}


# ---------------------------------------------------------
# SPEICHER
# ---------------------------------------------------------

# Keine alten Warmup-Kerzen mehr.
# Der Server sammelt ausschließlich echte TradingView-Kerzen.
BUFFERS = {
    "CL_H1": deque(maxlen=300),
    "CL_M30": deque(maxlen=300),
    "ES_M30": deque(maxlen=300),
}

# Nach 20 echten Kerzen funktionieren Volumen-MA und ATR.
MIN_LIVE_BARS = 20

LIVE_BARS = {
    "CL_H1": 0,
    "CL_M30": 0,
    "ES_M30": 0,
}

TRADE_STATUS = {
    instrument: {
        "in_trade": False,
        "bars_since": 0,
    }
    for instrument in PARAMS
}


# Tages-Schlusskurse für den Momentumfilter.
DAILY_CLOSES = {
    "CL_H1": deque(
        [
            91.28, 88.70, 91.85, 86.42, 84.29,
            81.16, 76.62, 75.01, 75.52, 76.54,
            74.08, 73.05, 69.87, 71.47, 70.24,
            70.42, 70.03, 68.09, 68.46, 68.78,
            68.60, 72.20, 74.76, 71.81, 71.51,
        ],
        maxlen=30,
    ),

    "CL_M30": deque(
        [
            91.28, 88.70, 91.85, 86.42, 84.29,
            81.16, 76.62, 75.01, 75.52, 76.54,
            74.08, 73.05, 69.87, 71.47, 70.24,
            70.42, 70.03, 68.09, 68.46, 68.78,
            68.60, 72.20, 74.76, 71.81, 71.51,
        ],
        maxlen=30,
    ),

    "ES_M30": deque(
        [
            7412.25, 7390.00, 7267.00, 7398.25, 7436.25,
            7624.25, 7583.00, 7511.00, 7574.75, 7556.25,
            7540.75, 7445.50, 7477.50, 7433.75, 7397.25,
            7493.50, 7542.00, 7532.75, 7523.00, 7557.00,
            7596.75, 7551.75, 7515.50, 7586.25, 7626.00,
        ],
        maxlen=30,
    ),
}


CET = pytz.timezone("Europe/Berlin")


# ---------------------------------------------------------
# HILFSFUNKTIONEN
# ---------------------------------------------------------

def get_session(hour):
    if 9 <= hour < 15:
        return "Europa"

    if 15 <= hour < 22:
        return "US"

    return "Off"


def calc_vol_ma(buffer, length=20):
    volumes = [bar["volume"] for bar in buffer]

    if len(volumes) < length:
        return None

    return sum(volumes[-length:]) / length


def calc_atr(buffer, length=14):
    if len(buffer) < length + 1:
        return None

    bars = list(buffer)
    true_ranges = []

    for index in range(1, len(bars)):
        current = bars[index]
        previous = bars[index - 1]

        true_range = max(
            current["high"] - current["low"],
            abs(current["high"] - previous["close"]),
            abs(current["low"] - previous["close"]),
        )

        true_ranges.append(true_range)

    return sum(true_ranges[-length:]) / length


def calc_momentum(daily_closes):
    closes = list(daily_closes)

    if len(closes) < 21:
        return None

    return (
        (closes[-1] - closes[-21])
        / closes[-21]
        * 100
    )


def send_telegram(message):
    if not TELEGRAM_TOKEN:
        print("Telegram-Fehler: TELEGRAM_TOKEN fehlt")
        return False

    if not TELEGRAM_CHAT_ID:
        print("Telegram-Fehler: TELEGRAM_CHAT_ID fehlt")
        return False

    url = (
        "https://api.telegram.org/bot"
        + TELEGRAM_TOKEN
        + "/sendMessage"
    )

    try:
        response = requests.post(
            url,
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "HTML",
            },
            timeout=10,
        )

        print(
            "Telegram Status:",
            response.status_code,
            response.text,
        )

        return response.status_code == 200

    except Exception as error:
        print("Telegram Ausnahme:", str(error))
        return False


# ---------------------------------------------------------
# SIGNALBERECHNUNG
# ---------------------------------------------------------

def check_signal(instrument):
    buffer = BUFFERS[instrument]
    parameters = PARAMS[instrument]
    trade_status = TRADE_STATUS[instrument]

    if len(buffer) < MIN_LIVE_BARS:
        return None

    if trade_status["in_trade"]:
        trade_status["bars_since"] += 1

        if (
            trade_status["bars_since"]
            >= parameters["max_pb_bars"]
        ):
            trade_status["in_trade"] = False
            trade_status["bars_since"] = 0
        else:
            return None

    bars = list(buffer)
    current_bar = bars[-1]

    timestamp = datetime.fromtimestamp(
        current_bar["timestamp"],
        tz=timezone.utc,
    ).astimezone(CET)

    hour = timestamp.hour
    session = get_session(hour)

    if session not in parameters["sessions"]:
        print(instrument, "Kein Signal: außerhalb Session")
        return None

    if hour in parameters["excl_hours"]:
        print(instrument, "Kein Signal: ausgeschlossene Stunde")
        return None

    volume_ma = calc_vol_ma(
        buffer,
        parameters["vol_ma_len"],
    )

    atr = calc_atr(buffer)

    if volume_ma is None or atr is None:
        print(instrument, "Kein Signal: Indikatoren nicht bereit")
        return None

    if current_bar["volume"] <= volume_ma:
        print(instrument, "Kein Signal: Volumenfilter")
        return None

    average_price = (
        sum(bar["close"] for bar in bars[-20:])
        / 20
    )

    if parameters["atr_pct"]:
        atr_limit = (
            average_price
            * parameters["atr_max_pct"]
        )

        if atr > atr_limit:
            print(instrument, "Kein Signal: ATR-Filter")
            return None

        minimum_momentum = (
            average_price
            * parameters["momentum_min_pct"]
        )

        stop_buffer = (
            average_price
            * parameters["stop_buffer_pct"]
        )

        max_risk = (
            average_price
            * parameters["max_risk_pct"]
        )

    else:
        if atr > parameters["atr_max"]:
            print(instrument, "Kein Signal: ATR-Filter")
            return None

        minimum_momentum = parameters["momentum_min_abs"]
        stop_buffer = parameters["stop_buffer"]
        max_risk = parameters["max_risk"]

    momentum = calc_momentum(
        DAILY_CLOSES[instrument]
    )

    if (
        momentum is not None
        and parameters["mom_threshold"]
        and abs(momentum)
        > parameters["mom_threshold"]
    ):
        print(instrument, "Kein Signal: Momentumfilter")
        return None

    # LONG
    for index in range(2, min(12, len(bars))):
        liquidity_level = bars[-index - 1]["low"]
        extreme = bars[-index]["low"]

        if (
            extreme < liquidity_level
            and current_bar["close"]
            >= liquidity_level + minimum_momentum
        ):
            entry = liquidity_level
            stop = extreme - stop_buffer
            risk = entry - stop

            if 0 < risk <= max_risk:
                trade_status["in_trade"] = True
                trade_status["bars_since"] = 0

                return {
                    "direction": "LONG",
                    "entry": entry,
                    "stop": stop,
                    "target": (
                        entry
                        + risk * parameters["crv"]
                    ),
                }

    # SHORT
    for index in range(2, min(12, len(bars))):
        liquidity_level = bars[-index - 1]["high"]
        extreme = bars[-index]["high"]

        if (
            extreme > liquidity_level
            and current_bar["close"]
            <= liquidity_level - minimum_momentum
        ):
            entry = liquidity_level
            stop = extreme + stop_buffer
            risk = stop - entry

            if 0 < risk <= max_risk:
                trade_status["in_trade"] = True
                trade_status["bars_since"] = 0

                return {
                    "direction": "SHORT",
                    "entry": entry,
                    "stop": stop,
                    "target": (
                        entry
                        - risk * parameters["crv"]
                    ),
                }

    print(instrument, "Kein Signal: kein gültiges Setup")
    return None


# ---------------------------------------------------------
# TRADINGVIEW-WEBHOOK
# ---------------------------------------------------------

@app.route("/webhook/<instrument>", methods=["POST"])
def webhook(instrument):
    instrument_map = {
        "cl_h1": "CL_H1",
        "cl_m30": "CL_M30",
        "es_m30": "ES_M30",
    }

    instrument_name = instrument_map.get(
        instrument.lower()
    )

    if not instrument_name:
        return jsonify({
            "error": "Unbekanntes Instrument"
        }), 400

    try:
        data = request.get_json(silent=True)

        if not data:
            return jsonify({
                "error": "Keine JSON-Daten"
            }), 400

        if data.get("secret") != WEBHOOK_SECRET:
            return jsonify({
                "error": "Falsches Webhook-Secret"
            }), 401

        bar = {
            "timestamp": float(
                data.get(
                    "timestamp",
                    datetime.now(
                        timezone.utc
                    ).timestamp(),
                )
            ),
            "open": float(data["open"]),
            "high": float(data["high"]),
            "low": float(data["low"]),
            "close": float(data["close"]),
            "volume": float(data["volume"]),
        }

        if data.get("daily_close") is not None:
            DAILY_CLOSES[instrument_name].append(
                float(data["daily_close"])
            )

    except (
        KeyError,
        TypeError,
        ValueError,
    ) as error:
        return jsonify({
            "error": str(error)
        }), 400

    BUFFERS[instrument_name].append(bar)
    LIVE_BARS[instrument_name] += 1

    live_bars = LIVE_BARS[instrument_name]

    print(
        instrument_name,
        "Kerze empfangen",
        "Live-Bars:",
        live_bars,
        "Close:",
        bar["close"],
    )

    if live_bars < MIN_LIVE_BARS:
        remaining = MIN_LIVE_BARS - live_bars

        return jsonify({
            "status": "warming_up",
            "instrument": instrument_name,
            "live_bars": live_bars,
            "required_live_bars": MIN_LIVE_BARS,
            "bars_until_ready": remaining,
            "signal_ready": False,
            "close": bar["close"],
        })

    signal = check_signal(instrument_name)

    if not signal:
        return jsonify({
            "status": "ok",
            "result": "no_signal",
            "instrument": instrument_name,
            "live_bars": live_bars,
            "signal_ready": True,
            "close": bar["close"],
        })

    display_names = {
        "CL_H1": "CL H1",
        "CL_M30": "CL M30",
        "ES_M30": "ES M30",
    }

    direction = signal["direction"]
    emoji = "🟢" if direction == "LONG" else "🔴"

    current_time = datetime.now(
        CET
    ).strftime("%d.%m.%Y %H:%M")

    message = (
        f"{emoji} "
        f"<b>{display_names[instrument_name]} "
        f"- {direction} SIGNAL</b>\n\n"

        f"<b>Limit Order setzen:</b>\n"
        f"Entry:  <code>"
        f"{round(signal['entry'], 2)}</code>\n"

        f"Stop:   <code>"
        f"{round(signal['stop'], 2)}</code>\n"

        f"Target {PARAMS[instrument_name]['crv']}R: "
        f"<code>{round(signal['target'], 2)}</code>\n"

        f"Risiko: <code>"
        f"{round(abs(signal['entry'] - signal['stop']), 2)}"
        f"</code>\n\n"

        f"<b>Pepperstone öffnen!</b>\n"
        f"Zeit: {current_time} MEZ"
    )

    telegram_sent = send_telegram(message)

    return jsonify({
        "status": "signal",
        "instrument": instrument_name,
        "signal": signal,
        "telegram_sent": telegram_sent,
        "live_bars": live_bars,
        "signal_ready": True,
    })


# ---------------------------------------------------------
# STATUSSEITE
# ---------------------------------------------------------

@app.route("/status", methods=["GET"])
def status():
    result = {}

    for instrument in PARAMS:
        momentum = calc_momentum(
            DAILY_CLOSES[instrument]
        )

        live_bars = LIVE_BARS[instrument]

        result[instrument] = {
            "bars": len(BUFFERS[instrument]),
            "live_bars": live_bars,
            "required_live_bars": MIN_LIVE_BARS,
            "bars_until_ready": max(
                0,
                MIN_LIVE_BARS - live_bars,
            ),
            "signal_ready": (
                live_bars >= MIN_LIVE_BARS
            ),
            "in_trade": TRADE_STATUS[
                instrument
            ]["in_trade"],
            "crv": PARAMS[instrument]["crv"],
            "momentum_20d": (
                round(momentum, 2)
                if momentum is not None
                else None
            ),
            "mom_ok": (
                abs(momentum)
                <= PARAMS[instrument]["mom_threshold"]
                if momentum is not None
                else True
            ),
            "volume_ma_ready": (
                calc_vol_ma(
                    BUFFERS[instrument],
                    PARAMS[instrument]["vol_ma_len"],
                )
                is not None
            ),
            "atr_ready": (
                calc_atr(
                    BUFFERS[instrument]
                )
                is not None
            ),
            "last_close": (
                BUFFERS[instrument][-1]["close"]
                if BUFFERS[instrument]
                else None
            ),
            "daily_closes": len(
                DAILY_CLOSES[instrument]
            ),
        }

    return jsonify(result)


# ---------------------------------------------------------
# TELEGRAM-TEST
# ---------------------------------------------------------

@app.route("/test", methods=["GET"])
def test():
    message = (
        "Trading Signal Server läuft!\n\n"
        "Aktive Instrumente:\n"
        "CL H1: 2R\n"
        "CL M30: 2R\n"
        "ES M30: 1R\n\n"
        "Signale erst nach 20 echten Live-Kerzen."
    )

    return jsonify({
        "sent": send_telegram(message)
    })


# ---------------------------------------------------------
# TRADE-STATUS ZURÜCKSETZEN
# ---------------------------------------------------------

@app.route(
    "/reset/<instrument>",
    methods=["GET", "POST"],
)
def reset(instrument):
    instrument_map = {
        "cl_h1": "CL_H1",
        "cl_m30": "CL_M30",
        "es_m30": "ES_M30",
    }

    instrument_name = instrument_map.get(
        instrument.lower()
    )

    if not instrument_name:
        return jsonify({
            "error": "Unbekanntes Instrument"
        }), 400

    TRADE_STATUS[instrument_name][
        "in_trade"
    ] = False

    TRADE_STATUS[instrument_name][
        "bars_since"
    ] = 0

    return jsonify({
        "reset": instrument_name
    })


# ---------------------------------------------------------
# STARTSEITE
# ---------------------------------------------------------

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "running",
        "system": (
            "CL H1 + CL M30 + ES M30"
        ),
        "warmup": (
            "20 echte TradingView-Kerzen "
            "pro Instrument erforderlich"
        ),
    })


# ---------------------------------------------------------
# SERVERSTART
# ---------------------------------------------------------

if __name__ == "__main__":
    port = int(
        os.environ.get("PORT", 5000)
    )

    app.run(
        host="0.0.0.0",
        port=port,
    )

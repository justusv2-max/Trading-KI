from pathlib import Path

src = Path("/mnt/data/server(1).txt")
dst = Path("/mnt/data/server.py")

text = src.read_text(encoding="utf-8")

# 1) Mark warmup bars and add live tracking after BUFFERS
old = '''BUFFERS = {
    "CL_H1":  deque(CL_H1_WARMUP,  maxlen=300),
    "CL_M30": deque(CL_M30_WARMUP, maxlen=300),
    "ES_M30": deque(ES_M30_WARMUP, maxlen=300),
}
TRADE_STATUS = {inst: {"in_trade": False, "bars_since": 0} for inst in PARAMS}
'''
new = '''BUFFERS = {
    "CL_H1":  deque(CL_H1_WARMUP,  maxlen=300),
    "CL_M30": deque(CL_M30_WARMUP, maxlen=300),
    "ES_M30": deque(ES_M30_WARMUP, maxlen=300),
}

# Alte Warmup-Kerzen dürfen nur die Indikatoren vorbereiten.
# Sie dürfen keine neuen Live-Signale auslösen.
for buffer in BUFFERS.values():
    for warmup_bar in buffer:
        warmup_bar["is_live"] = False

SIGNAL_LOOKBACK_BARS = 20
LIVE_BARS = {inst: 0 for inst in PARAMS}

TRADE_STATUS = {inst: {"in_trade": False, "bars_since": 0} for inst in PARAMS}
'''
if old not in text:
    raise RuntimeError("BUFFERS-Block nicht gefunden")
text = text.replace(old, new, 1)

# 2) Replace bar creation with is_live marker
old = '''        bar = {"timestamp": data.get("timestamp", datetime.now().timestamp()),
               "open": float(data["open"]), "high": float(data["high"]),
               "low": float(data["low"]), "close": float(data["close"]),
               "volume": float(data["volume"])}
'''
new = '''        bar = {
            "timestamp": data.get("timestamp", datetime.now().timestamp()),
            "open": float(data["open"]),
            "high": float(data["high"]),
            "low": float(data["low"]),
            "close": float(data["close"]),
            "volume": float(data["volume"]),
            "is_live": True,
        }
'''
if old not in text:
    raise RuntimeError("Bar-Erstellung nicht gefunden")
text = text.replace(old, new, 1)

# 3) Replace webhook processing section
old = '''    BUFFERS[inst].append(bar)
    sig = check_signal(inst, bar)
    if sig:
'''
new = '''    BUFFERS[inst].append(bar)
    LIVE_BARS[inst] += 1

    recent_bars = list(BUFFERS[inst])[-SIGNAL_LOOKBACK_BARS:]
    live_bars_in_window = sum(
        1 for recent_bar in recent_bars
        if recent_bar.get("is_live", False)
    )

    signal_ready = (
        len(recent_bars) == SIGNAL_LOOKBACK_BARS
        and live_bars_in_window == SIGNAL_LOOKBACK_BARS
    )

    if not signal_ready:
        remaining = SIGNAL_LOOKBACK_BARS - live_bars_in_window

        print(
            f"{inst}: Live-Warmup "
            f"{live_bars_in_window}/{SIGNAL_LOOKBACK_BARS}; "
            f"noch {remaining} Kerzen bis Signalfreigabe"
        )

        return jsonify({
            "status": "warming_up_live",
            "instrument": inst,
            "live_bars_total": LIVE_BARS[inst],
            "live_bars_in_signal_window": live_bars_in_window,
            "required_live_bars": SIGNAL_LOOKBACK_BARS,
            "bars_until_signal_ready": remaining,
            "signal_ready": False,
            "total_bars": len(BUFFERS[inst]),
        })

    print(
        f"{inst}: Live-Kerze verarbeitet | "
        f"Close={bar['close']} | Gesamt-Bars={len(BUFFERS[inst])}"
    )

    sig = check_signal(inst, bar)
    if sig:
'''
if old not in text:
    raise RuntimeError("Webhook-Signalblock nicht gefunden")
text = text.replace(old, new, 1)

# 4) Replace telegram return block
old = '''        send_telegram(msg)
        return jsonify({"status": "signal", "signal": sig})
    return jsonify({"status": "ok", "bars": len(BUFFERS[inst])})
'''
new = '''        telegram_sent = send_telegram(msg)

        print(
            f"{inst}: {d}-Signal | "
            f"Telegram gesendet={telegram_sent}"
        )

        return jsonify({
            "status": "signal",
            "signal": sig,
            "telegram_sent": telegram_sent,
            "signal_ready": True,
            "live_bars_total": LIVE_BARS[inst],
            "total_bars": len(BUFFERS[inst]),
        })

    print(f"{inst}: Kein Signal")

    return jsonify({
        "status": "ok",
        "result": "no_signal",
        "signal_ready": True,
        "live_bars_total": LIVE_BARS[inst],
        "total_bars": len(BUFFERS[inst]),
    })
'''
if old not in text:
    raise RuntimeError("Telegram-Returnblock nicht gefunden")
text = text.replace(old, new, 1)

# 5) Replace status endpoint
start = text.index('@app.route("/status", methods=["GET"])')
end = text.index('\n\n@app.route("/test", methods=["GET"])', start)

new_status = '''@app.route("/status", methods=["GET"])
def status():
    res = {}

    for inst in PARAMS:
        mom = calc_mom(DAILY_CLOSES[inst])

        recent_bars = list(BUFFERS[inst])[-SIGNAL_LOOKBACK_BARS:]
        live_bars_in_window = sum(
            1 for recent_bar in recent_bars
            if recent_bar.get("is_live", False)
        )

        signal_ready = (
            len(recent_bars) == SIGNAL_LOOKBACK_BARS
            and live_bars_in_window == SIGNAL_LOOKBACK_BARS
        )

        res[inst] = {
            "bars": len(BUFFERS[inst]),
            "live_bars_total": LIVE_BARS[inst],
            "live_bars_in_signal_window": live_bars_in_window,
            "required_live_bars": SIGNAL_LOOKBACK_BARS,
            "bars_until_signal_ready": max(
                0,
                SIGNAL_LOOKBACK_BARS - live_bars_in_window
            ),
            "signal_ready": signal_ready,
            "in_trade": TRADE_STATUS[inst]["in_trade"],
            "crv": PARAMS[inst]["crv"],
            "momentum_20d": round(mom, 2) if mom is not None else None,
            "mom_ok": (
                abs(mom) <= PARAMS[inst]["mom_threshold"]
                if mom is not None else True
            ),
            "fully_ready": calc_vol_ma(BUFFERS[inst]) is not None,
            "daily_closes": len(DAILY_CLOSES[inst]),
        }

    return jsonify(res)
'''

text = text[:start] + new_status + text[end:]

# 6) Update test text so it doesn't claim immediate readiness
text = text.replace(
    '"50 Warmup Kerzen vorgeladen - sofort einsatzbereit!")',
    '"Warmup-Kerzen vorgeladen. Signale erst nach 20 echten Live-Kerzen!")'
)

# Validate syntax
compile(text, str(dst), "exec")

dst.write_text(text, encoding="utf-8")
print(f"Fertig: {dst}")

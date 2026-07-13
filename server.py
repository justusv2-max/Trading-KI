from flask import Flask, request, jsonify
import requests
import os
from datetime import datetime, timezone
import pytz
from collections import deque

app = Flask(__name__)

TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
WEBHOOK_SECRET   = os.environ.get("WEBHOOK_SECRET", "trading123")

# ── Instrument Parameter ──────────────────────────────────
PARAMS = {
    "CL_H1": {
        "momentum_min_abs": 0.50,
        "stop_buffer":      0.10,
        "max_risk":         5.00,
        "crv":              2.0,
        "atr_max":          1.00,
        "atr_pct":          False,
        "vol_ma_len":       20,
        "mom_threshold":    15.0,
        "max_pb_bars":      72,
        "sessions":         ["Europa", "US"],
        "excl_hours":       [15],
    },
    "CL_M30": {
        "momentum_min_abs": 0.50,
        "stop_buffer":      0.10,
        "max_risk":         5.00,
        "crv":              2.0,
        "atr_max":          1.00,
        "atr_pct":          False,
        "vol_ma_len":       20,
        "mom_threshold":    15.0,
        "max_pb_bars":      144,
        "sessions":         ["Europa", "US"],
        "excl_hours":       [15, 19],
    },
    "ES_M30": {
        "momentum_min_pct":  0.0071,
        "stop_buffer_pct":   0.0014,
        "max_risk_pct":      0.071,
        "crv":               1.0,
        "atr_max_pct":       0.0143,
        "atr_pct":           True,
        "vol_ma_len":        20,
        "mom_threshold":     10.0,
        "max_pb_bars":       144,
        "sessions":          ["Europa", "US"],
        "excl_hours":        [15],
    },
}

# ── Warmup Daten (letzte 50 Kerzen aus Backtest) ──────────
CL_H1_WARMUP  = [{'timestamp': 1783530000, 'open': 74.58, 'high': 74.63, 'low': 73.54, 'close': 73.78, 'volume': 13184.0}, {'timestamp': 1783533600, 'open': 73.77, 'high': 73.85, 'low': 73.35, 'close': 73.59, 'volume': 14105.0}, {'timestamp': 1783537200, 'open': 73.61, 'high': 74.31, 'low': 73.5, 'close': 74.07, 'volume': 5502.0}, {'timestamp': 1783540800, 'open': 74.06, 'high': 75.06, 'low': 74.05, 'close': 74.76, 'volume': 6735.0}, {'timestamp': 1783548000, 'open': 74.95, 'high': 75.13, 'low': 74.22, 'close': 74.53, 'volume': 1882.0}, {'timestamp': 1783551600, 'open': 74.52, 'high': 74.57, 'low': 74.4, 'close': 74.46, 'volume': 567.0}, {'timestamp': 1783555200, 'open': 74.45, 'high': 74.52, 'low': 74.0, 'close': 74.02, 'volume': 2403.0}, {'timestamp': 1783558800, 'open': 74.02, 'high': 74.62, 'low': 73.88, 'close': 74.12, 'volume': 3325.0}, {'timestamp': 1783562400, 'open': 74.12, 'high': 74.67, 'low': 73.97, 'close': 74.51, 'volume': 2189.0}, {'timestamp': 1783566000, 'open': 74.53, 'high': 74.6, 'low': 74.16, 'close': 74.27, 'volume': 1794.0}, {'timestamp': 1783569600, 'open': 74.27, 'high': 74.41, 'low': 74.25, 'close': 74.35, 'volume': 904.0}, {'timestamp': 1783573200, 'open': 74.34, 'high': 74.54, 'low': 73.0, 'close': 73.06, 'volume': 7509.0}, {'timestamp': 1783576800, 'open': 73.08, 'high': 73.53, 'low': 73.01, 'close': 73.31, 'volume': 4455.0}, {'timestamp': 1783580400, 'open': 73.32, 'high': 73.74, 'low': 72.54, 'close': 72.76, 'volume': 7526.0}, {'timestamp': 1783584000, 'open': 72.76, 'high': 73.05, 'low': 72.37, 'close': 73.02, 'volume': 6559.0}, {'timestamp': 1783587600, 'open': 73.04, 'high': 73.67, 'low': 72.97, 'close': 73.51, 'volume': 4888.0}, {'timestamp': 1783591200, 'open': 73.51, 'high': 74.62, 'low': 73.42, 'close': 74.25, 'volume': 7281.0}, {'timestamp': 1783594800, 'open': 74.25, 'high': 74.29, 'low': 73.83, 'close': 73.96, 'volume': 6815.0}, {'timestamp': 1783598400, 'open': 73.95, 'high': 74.13, 'low': 73.63, 'close': 73.93, 'volume': 6477.0}, {'timestamp': 1783602000, 'open': 73.92, 'high': 74.01, 'low': 72.62, 'close': 72.66, 'volume': 16564.0}, {'timestamp': 1783605600, 'open': 72.66, 'high': 73.08, 'low': 72.16, 'close': 72.31, 'volume': 15562.0}, {'timestamp': 1783609200, 'open': 72.31, 'high': 72.53, 'low': 71.81, 'close': 72.12, 'volume': 12941.0}, {'timestamp': 1783612800, 'open': 72.14, 'high': 72.27, 'low': 71.64, 'close': 71.94, 'volume': 9671.0}, {'timestamp': 1783616400, 'open': 71.94, 'high': 72.12, 'low': 71.43, 'close': 71.53, 'volume': 9845.0}, {'timestamp': 1783620000, 'open': 71.52, 'high': 72.2, 'low': 71.42, 'close': 71.61, 'volume': 17809.0}, {'timestamp': 1783623600, 'open': 71.6, 'high': 71.89, 'low': 71.43, 'close': 71.88, 'volume': 3379.0}, {'timestamp': 1783627200, 'open': 71.88, 'high': 71.93, 'low': 71.63, 'close': 71.81, 'volume': 2020.0}, {'timestamp': 1783634400, 'open': 71.86, 'high': 71.87, 'low': 71.22, 'close': 71.83, 'volume': 1241.0}, {'timestamp': 1783638000, 'open': 71.82, 'high': 71.95, 'low': 71.74, 'close': 71.92, 'volume': 576.0}, {'timestamp': 1783641600, 'open': 71.92, 'high': 72.01, 'low': 71.78, 'close': 71.97, 'volume': 1160.0}, {'timestamp': 1783645200, 'open': 71.97, 'high': 72.18, 'low': 71.77, 'close': 72.14, 'volume': 1644.0}, {'timestamp': 1783648800, 'open': 72.15, 'high': 72.42, 'low': 72.08, 'close': 72.36, 'volume': 1432.0}, {'timestamp': 1783652400, 'open': 72.36, 'high': 72.41, 'low': 72.17, 'close': 72.39, 'volume': 1012.0}, {'timestamp': 1783656000, 'open': 72.42, 'high': 72.56, 'low': 72.18, 'close': 72.29, 'volume': 1351.0}, {'timestamp': 1783659600, 'open': 72.31, 'high': 72.43, 'low': 71.97, 'close': 72.16, 'volume': 1454.0}, {'timestamp': 1783663200, 'open': 72.18, 'high': 72.26, 'low': 71.75, 'close': 72.04, 'volume': 2261.0}, {'timestamp': 1783666800, 'open': 72.04, 'high': 72.09, 'low': 71.31, 'close': 71.57, 'volume': 4991.0}, {'timestamp': 1783670400, 'open': 71.55, 'high': 72.19, 'low': 71.16, 'close': 71.89, 'volume': 6333.0}, {'timestamp': 1783674000, 'open': 71.89, 'high': 72.05, 'low': 71.51, 'close': 71.85, 'volume': 2806.0}, {'timestamp': 1783677600, 'open': 71.86, 'high': 72.3, 'low': 71.81, 'close': 72.24, 'volume': 3340.0}, {'timestamp': 1783681200, 'open': 72.25, 'high': 72.84, 'low': 72.14, 'close': 72.73, 'volume': 6152.0}, {'timestamp': 1783684800, 'open': 72.73, 'high': 72.85, 'low': 71.47, 'close': 71.95, 'volume': 10678.0}, {'timestamp': 1783688400, 'open': 71.96, 'high': 72.39, 'low': 71.5, 'close': 71.59, 'volume': 10103.0}, {'timestamp': 1783692000, 'open': 71.6, 'high': 73.16, 'low': 71.25, 'close': 71.93, 'volume': 17845.0}, {'timestamp': 1783695600, 'open': 71.93, 'high': 71.93, 'low': 70.77, 'close': 71.01, 'volume': 14139.0}, {'timestamp': 1783699200, 'open': 71.01, 'high': 71.49, 'low': 71.01, 'close': 71.09, 'volume': 7798.0}, {'timestamp': 1783702800, 'open': 71.1, 'high': 71.4, 'low': 71.03, 'close': 71.29, 'volume': 5690.0}, {'timestamp': 1783706400, 'open': 71.28, 'high': 71.61, 'low': 71.08, 'close': 71.59, 'volume': 13272.0}, {'timestamp': 1783710000, 'open': 71.6, 'high': 71.7, 'low': 71.45, 'close': 71.57, 'volume': 4174.0}, {'timestamp': 1783713600, 'open': 71.56, 'high': 71.65, 'low': 71.47, 'close': 71.51, 'volume': 1574.0}]
CL_M30_WARMUP = [{'timestamp': 1783668600, 'open': 71.58, 'high': 71.66, 'low': 71.31, 'close': 71.57, 'volume': 2098.0}, {'timestamp': 1783670400, 'open': 71.55, 'high': 71.65, 'low': 71.16, 'close': 71.64, 'volume': 3160.0}, {'timestamp': 1783672200, 'open': 71.63, 'high': 72.19, 'low': 71.63, 'close': 71.89, 'volume': 3173.0}, {'timestamp': 1783674000, 'open': 71.89, 'high': 72.05, 'low': 71.51, 'close': 71.65, 'volume': 1585.0}, {'timestamp': 1783675800, 'open': 71.64, 'high': 71.95, 'low': 71.55, 'close': 71.85, 'volume': 1221.0}, {'timestamp': 1783677600, 'open': 71.86, 'high': 72.07, 'low': 71.81, 'close': 71.97, 'volume': 1577.0}, {'timestamp': 1783679400, 'open': 71.98, 'high': 72.3, 'low': 71.89, 'close': 72.24, 'volume': 1763.0}, {'timestamp': 1783681200, 'open': 72.25, 'high': 72.53, 'low': 72.14, 'close': 72.49, 'volume': 2739.0}, {'timestamp': 1783683000, 'open': 72.49, 'high': 72.84, 'low': 72.45, 'close': 72.73, 'volume': 3413.0}, {'timestamp': 1783684800, 'open': 72.73, 'high': 72.85, 'low': 71.47, 'close': 72.05, 'volume': 7961.0}, {'timestamp': 1783686600, 'open': 72.06, 'high': 72.34, 'low': 71.92, 'close': 71.95, 'volume': 2717.0}, {'timestamp': 1783688400, 'open': 71.96, 'high': 72.39, 'low': 71.87, 'close': 72.11, 'volume': 3607.0}, {'timestamp': 1783690200, 'open': 72.1, 'high': 72.19, 'low': 71.5, 'close': 71.59, 'volume': 6496.0}, {'timestamp': 1783692000, 'open': 71.6, 'high': 71.86, 'low': 71.53, 'close': 71.73, 'volume': 4189.0}, {'timestamp': 1783693800, 'open': 71.73, 'high': 73.16, 'low': 71.25, 'close': 71.93, 'volume': 13656.0}, {'timestamp': 1783695600, 'open': 71.93, 'high': 71.93, 'low': 71.14, 'close': 71.33, 'volume': 7658.0}, {'timestamp': 1783697400, 'open': 71.33, 'high': 71.42, 'low': 70.77, 'close': 71.01, 'volume': 6481.0}, {'timestamp': 1783699200, 'open': 71.01, 'high': 71.49, 'low': 71.01, 'close': 71.24, 'volume': 4749.0}, {'timestamp': 1783701000, 'open': 71.25, 'high': 71.31, 'low': 71.01, 'close': 71.09, 'volume': 3049.0}, {'timestamp': 1783702800, 'open': 71.1, 'high': 71.4, 'low': 71.03, 'close': 71.25, 'volume': 2892.0}, {'timestamp': 1783704600, 'open': 71.25, 'high': 71.4, 'low': 71.13, 'close': 71.29, 'volume': 2798.0}, {'timestamp': 1783706400, 'open': 71.28, 'high': 71.51, 'low': 71.08, 'close': 71.41, 'volume': 10542.0}, {'timestamp': 1783708200, 'open': 71.42, 'high': 71.61, 'low': 71.36, 'close': 71.59, 'volume': 2730.0}, {'timestamp': 1783710000, 'open': 71.6, 'high': 71.7, 'low': 71.5, 'close': 71.62, 'volume': 2166.0}, {'timestamp': 1783711800, 'open': 71.61, 'high': 71.69, 'low': 71.45, 'close': 71.57, 'volume': 2008.0}, {'timestamp': 1783713600, 'open': 71.56, 'high': 71.6, 'low': 71.5, 'close': 71.57, 'volume': 428.0}, {'timestamp': 1783715400, 'open': 71.56, 'high': 71.65, 'low': 71.47, 'close': 71.51, 'volume': 1146.0}, {'timestamp': 1783893600, 'open': 73.69, 'high': 74.2, 'low': 73.18, 'close': 73.68, 'volume': 6499.0}, {'timestamp': 1783895400, 'open': 73.68, 'high': 73.77, 'low': 73.56, 'close': 73.69, 'volume': 872.0}, {'timestamp': 1783897200, 'open': 73.7, 'high': 73.75, 'low': 73.62, 'close': 73.73, 'volume': 669.0}, {'timestamp': 1783899000, 'open': 73.73, 'high': 73.88, 'low': 73.66, 'close': 73.77, 'volume': 905.0}, {'timestamp': 1783900800, 'open': 73.76, 'high': 74.17, 'low': 73.73, 'close': 73.91, 'volume': 1421.0}, {'timestamp': 1783902600, 'open': 73.92, 'high': 74.5, 'low': 73.9, 'close': 74.27, 'volume': 2896.0}, {'timestamp': 1783904400, 'open': 74.25, 'high': 74.59, 'low': 74.17, 'close': 74.31, 'volume': 3009.0}, {'timestamp': 1783906200, 'open': 74.32, 'high': 74.66, 'low': 74.32, 'close': 74.39, 'volume': 1715.0}, {'timestamp': 1783908000, 'open': 74.39, 'high': 74.59, 'low': 74.26, 'close': 74.5, 'volume': 1655.0}, {'timestamp': 1783909800, 'open': 74.47, 'high': 74.53, 'low': 74.11, 'close': 74.25, 'volume': 1455.0}, {'timestamp': 1783911600, 'open': 74.24, 'high': 74.45, 'low': 74.24, 'close': 74.31, 'volume': 990.0}, {'timestamp': 1783913400, 'open': 74.3, 'high': 74.38, 'low': 74.12, 'close': 74.29, 'volume': 1411.0}, {'timestamp': 1783915200, 'open': 74.3, 'high': 74.4, 'low': 74.28, 'close': 74.34, 'volume': 675.0}, {'timestamp': 1783917000, 'open': 74.34, 'high': 74.55, 'low': 74.31, 'close': 74.53, 'volume': 808.0}, {'timestamp': 1783918800, 'open': 74.52, 'high': 74.7, 'low': 74.47, 'close': 74.69, 'volume': 1156.0}, {'timestamp': 1783920600, 'open': 74.68, 'high': 75.08, 'low': 74.62, 'close': 74.7, 'volume': 2690.0}, {'timestamp': 1783922400, 'open': 74.69, 'high': 74.71, 'low': 74.25, 'close': 74.33, 'volume': 1924.0}, {'timestamp': 1783924200, 'open': 74.33, 'high': 74.37, 'low': 73.99, 'close': 74.06, 'volume': 2108.0}, {'timestamp': 1783926000, 'open': 74.05, 'high': 74.22, 'low': 73.93, 'close': 74.1, 'volume': 1670.0}, {'timestamp': 1783927800, 'open': 74.09, 'high': 74.23, 'low': 73.67, 'close': 74.0, 'volume': 2063.0}, {'timestamp': 1783929600, 'open': 74.0, 'high': 74.05, 'low': 73.09, 'close': 73.24, 'volume': 5939.0}, {'timestamp': 1783931400, 'open': 73.23, 'high': 73.53, 'low': 72.75, 'close': 73.06, 'volume': 3249.0}, {'timestamp': 1783933200, 'open': 73.06, 'high': 73.16, 'low': 73.05, 'close': 73.1, 'volume': 260.0}]
ES_M30_WARMUP = [{'timestamp': 1783623600, 'open': 7585.25, 'high': 7588.5, 'low': 7581.0, 'close': 7585.0, 'volume': 35696.0}, {'timestamp': 1783625400, 'open': 7585.0, 'high': 7591.0, 'low': 7582.5, 'close': 7590.75, 'volume': 93812.0}, {'timestamp': 1783627200, 'open': 7590.25, 'high': 7592.0, 'low': 7585.75, 'close': 7587.0, 'volume': 28630.0}, {'timestamp': 1783629000, 'open': 7586.75, 'high': 7590.0, 'low': 7584.75, 'close': 7586.25, 'volume': 7920.0}, {'timestamp': 1783634400, 'open': 7587.25, 'high': 7589.0, 'low': 7583.75, 'close': 7584.75, 'volume': 2800.0}, {'timestamp': 1783636200, 'open': 7584.5, 'high': 7587.25, 'low': 7584.0, 'close': 7586.75, 'volume': 1011.0}, {'timestamp': 1783638000, 'open': 7586.75, 'high': 7591.75, 'low': 7585.0, 'close': 7591.25, 'volume': 2080.0}, {'timestamp': 1783639800, 'open': 7591.5, 'high': 7591.75, 'low': 7586.75, 'close': 7588.5, 'volume': 1928.0}, {'timestamp': 1783641600, 'open': 7588.5, 'high': 7589.5, 'low': 7577.5, 'close': 7579.5, 'volume': 6562.0}, {'timestamp': 1783643400, 'open': 7579.75, 'high': 7580.75, 'low': 7574.5, 'close': 7580.75, 'volume': 6170.0}, {'timestamp': 1783645200, 'open': 7580.75, 'high': 7581.25, 'low': 7576.0, 'close': 7579.5, 'volume': 4577.0}, {'timestamp': 1783647000, 'open': 7579.25, 'high': 7583.75, 'low': 7577.5, 'close': 7580.25, 'volume': 4584.0}, {'timestamp': 1783648800, 'open': 7580.25, 'high': 7582.25, 'low': 7577.0, 'close': 7579.25, 'volume': 3756.0}, {'timestamp': 1783650600, 'open': 7579.5, 'high': 7586.5, 'low': 7578.0, 'close': 7586.25, 'volume': 4484.0}, {'timestamp': 1783652400, 'open': 7586.25, 'high': 7588.5, 'low': 7583.25, 'close': 7583.5, 'volume': 3333.0}, {'timestamp': 1783654200, 'open': 7583.5, 'high': 7584.0, 'low': 7581.75, 'close': 7583.25, 'volume': 2624.0}, {'timestamp': 1783656000, 'open': 7583.25, 'high': 7584.25, 'low': 7580.5, 'close': 7581.25, 'volume': 2305.0}, {'timestamp': 1783657800, 'open': 7581.25, 'high': 7581.5, 'low': 7577.25, 'close': 7577.5, 'volume': 2918.0}, {'timestamp': 1783659600, 'open': 7577.75, 'high': 7579.75, 'low': 7576.25, 'close': 7578.25, 'volume': 4103.0}, {'timestamp': 1783661400, 'open': 7578.25, 'high': 7579.0, 'low': 7575.75, 'close': 7576.5, 'volume': 3576.0}, {'timestamp': 1783663200, 'open': 7576.5, 'high': 7579.5, 'low': 7570.5, 'close': 7571.75, 'volume': 7449.0}, {'timestamp': 1783665000, 'open': 7571.75, 'high': 7576.75, 'low': 7570.5, 'close': 7574.0, 'volume': 6210.0}, {'timestamp': 1783666800, 'open': 7574.0, 'high': 7579.5, 'low': 7572.0, 'close': 7578.75, 'volume': 6100.0}, {'timestamp': 1783668600, 'open': 7578.75, 'high': 7578.75, 'low': 7569.5, 'close': 7572.25, 'volume': 6216.0}, {'timestamp': 1783670400, 'open': 7572.0, 'high': 7579.25, 'low': 7569.75, 'close': 7575.5, 'volume': 9492.0}, {'timestamp': 1783672200, 'open': 7575.25, 'high': 7577.25, 'low': 7573.0, 'close': 7574.25, 'volume': 4470.0}, {'timestamp': 1783674000, 'open': 7574.25, 'high': 7582.25, 'low': 7568.5, 'close': 7581.0, 'volume': 6603.0}, {'timestamp': 1783675800, 'open': 7580.75, 'high': 7582.5, 'low': 7579.5, 'close': 7581.0, 'volume': 3664.0}, {'timestamp': 1783677600, 'open': 7581.0, 'high': 7586.75, 'low': 7581.0, 'close': 7586.25, 'volume': 5508.0}, {'timestamp': 1783679400, 'open': 7586.25, 'high': 7590.75, 'low': 7586.25, 'close': 7590.5, 'volume': 5077.0}, {'timestamp': 1783681200, 'open': 7590.25, 'high': 7592.25, 'low': 7586.5, 'close': 7586.75, 'volume': 6094.0}, {'timestamp': 1783683000, 'open': 7586.75, 'high': 7586.75, 'low': 7580.75, 'close': 7583.25, 'volume': 7693.0}, {'timestamp': 1783684800, 'open': 7583.5, 'high': 7595.5, 'low': 7577.25, 'close': 7587.75, 'volume': 19276.0}, {'timestamp': 1783686600, 'open': 7587.75, 'high': 7592.5, 'low': 7584.25, 'close': 7588.0, 'volume': 11477.0}, {'timestamp': 1783688400, 'open': 7588.25, 'high': 7594.0, 'low': 7586.75, 'close': 7592.25, 'volume': 14576.0}, {'timestamp': 1783690200, 'open': 7592.25, 'high': 7604.5, 'low': 7590.0, 'close': 7601.5, 'volume': 98721.0}, {'timestamp': 1783692000, 'open': 7601.5, 'high': 7605.75, 'low': 7593.0, 'close': 7598.0, 'volume': 75420.0}, {'timestamp': 1783693800, 'open': 7597.75, 'high': 7602.75, 'low': 7552.75, 'close': 7584.25, 'volume': 137200.0}, {'timestamp': 1783695600, 'open': 7584.25, 'high': 7606.75, 'low': 7578.5, 'close': 7605.25, 'volume': 78678.0}, {'timestamp': 1783697400, 'open': 7605.25, 'high': 7606.5, 'low': 7586.0, 'close': 7600.25, 'volume': 68292.0}, {'timestamp': 1783699200, 'open': 7600.25, 'high': 7609.25, 'low': 7600.0, 'close': 7604.25, 'volume': 43206.0}, {'timestamp': 1783701000, 'open': 7604.0, 'high': 7614.0, 'low': 7601.5, 'close': 7612.75, 'volume': 35474.0}, {'timestamp': 1783702800, 'open': 7612.5, 'high': 7613.25, 'low': 7607.25, 'close': 7613.0, 'volume': 25208.0}, {'timestamp': 1783704600, 'open': 7613.0, 'high': 7617.0, 'low': 7611.5, 'close': 7612.75, 'volume': 27603.0}, {'timestamp': 1783706400, 'open': 7612.75, 'high': 7620.0, 'low': 7612.0, 'close': 7617.25, 'volume': 33148.0}, {'timestamp': 1783708200, 'open': 7617.5, 'high': 7620.25, 'low': 7616.25, 'close': 7618.5, 'volume': 21662.0}, {'timestamp': 1783710000, 'open': 7618.5, 'high': 7625.5, 'low': 7618.25, 'close': 7622.75, 'volume': 41023.0}, {'timestamp': 1783711800, 'open': 7622.75, 'high': 7627.25, 'low': 7617.75, 'close': 7620.75, 'volume': 98334.0}, {'timestamp': 1783713600, 'open': 7621.0, 'high': 7625.25, 'low': 7618.0, 'close': 7624.75, 'volume': 32867.0}, {'timestamp': 1783715400, 'open': 7624.75, 'high': 7628.75, 'low': 7624.0, 'close': 7626.0, 'volume': 8919.0}]

# ── Buffer vorbelegen ─────────────────────────────────────
BUFFERS = {
    "CL_H1":  deque(CL_H1_WARMUP,  maxlen=300),
    "CL_M30": deque(CL_M30_WARMUP, maxlen=300),
    "ES_M30": deque(ES_M30_WARMUP, maxlen=300),
}

TRADE_STATUS = {inst: {"in_trade": False, "bars_since": 0} for inst in PARAMS}

# ── Tages Closes vorgeladen ───────────────────────────────
DAILY_CLOSES = {
    "CL_H1":  deque([91.28, 88.7, 91.85, 86.42, 84.29, 81.16, 76.62, 75.01, 75.52, 76.54, 74.08, 73.05, 69.87, 71.47, 70.24, 70.42, 70.03, 68.09, 68.46, 68.78, 68.6, 72.2, 74.76, 71.81, 71.51], maxlen=30),
    "CL_M30": deque([91.28, 88.7, 91.85, 86.42, 84.29, 81.16, 76.62, 75.01, 75.52, 76.54, 74.08, 73.05, 69.87, 71.47, 70.24, 70.42, 70.03, 68.09, 68.46, 68.78, 68.6, 72.2, 74.76, 71.81, 71.51], maxlen=30),
    "ES_M30": deque([7412.25, 7390.0, 7267.0, 7398.25, 7436.25, 7624.25, 7583.0, 7511.0, 7574.75, 7556.25, 7540.75, 7445.5, 7477.5, 7433.75, 7397.25, 7493.5, 7542.0, 7532.75, 7523.0, 7557.0, 7596.75, 7551.75, 7515.5, 7586.25, 7626.0], maxlen=30),
}

CET = pytz.timezone("Europe/Berlin")


def get_session(hour_cet):
    if 9 <= hour_cet < 15:  return "Europa"
    elif 15 <= hour_cet < 22: return "US"
    else: return "Off"


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
        lc = abs(bars[i]["low"]  - bars[i-1]["close"])
        trs.append(max(hl, hc, lc))
    return sum(trs[-period:]) / period


def calc_momentum(daily_closes):
    closes = list(daily_closes)
    if len(closes) < 21: return None
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

    if len(buffer) < 15: return None

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
    session = get_session(hour_cet)

    if session not in p["sessions"]: return None
    if hour_cet in p["excl_hours"]: return None

    vol_ma = calc_vol_ma(buffer, p["vol_ma_len"])
    atr14  = calc_atr(buffer)
    if vol_ma is None or atr14 is None: return None
    if c["volume"] <= vol_ma: return None

    price_ref = sum(b["close"] for b in bars[-20:]) / min(20, len(bars))

    if p["atr_pct"]:
        if atr14 > price_ref * p["atr_max_pct"]: return None
        mm = price_ref * p["momentum_min_pct"]
        sb = price_ref * p["stop_buffer_pct"]
        mr = price_ref * p["max_risk_pct"]
    else:
        if atr14 > p["atr_max"]: return None
        mm = p["momentum_min_abs"]
        sb = p["stop_buffer"]
        mr = p["max_risk"]

    if p["mom_threshold"]:
        mom = calc_momentum(DAILY_CLOSES[inst])
        if mom is not None and abs(mom) > p["mom_threshold"]: return None

    for i in range(2, min(12, len(bars))):
        liq  = bars[-i-1]["low"]
        extr = bars[-i]["low"]
        if extr < liq and c["close"] >= liq + mm:
            en = liq; st = extr - sb; rk = en - st
            if 0 < rk <= mr:
                status["in_trade"] = True
                status["bars_since"] = 0
                return {"direction": "LONG", "entry": en, "stop": st,
                        "target": en + rk * p["crv"], "inst": inst}

    for i in range(2, min(12, len(bars))):
        liq  = bars[-i-1]["high"]
        extr = bars[-i]["high"]
        if extr > liq and c["close"] <= liq - mm:
            en = liq; st = extr + sb; rk = st - en
            if 0 < rk <= mr:
                status["in_trade"] = True
                status["bars_since"] = 0
                return {"direction": "SHORT", "entry": en, "stop": st,
                        "target": en - rk * p["crv"], "inst": inst}

    return None


@app.route("/webhook/<instrument>", methods=["POST"])
def webhook(instrument):
    inst_map = {
        "cl_h1":  "CL_H1",
        "cl_m30": "CL_M30",
        "es_m30": "ES_M30",
    }
    inst = inst_map.get(instrument.lower())
    if not inst: return jsonify({"error": "Unbekannt"}), 400

    try:
        data = request.get_json()
        if not data: return jsonify({"error": "Keine Daten"}), 400
        if data.get("secret") != WEBHOOK_SECRET:
            return jsonify({"error": "Ungültiger Secret"}), 401
        bar = {
            "timestamp": data.get("timestamp", datetime.now().timestamp()),
            "open":   float(data["open"]),
            "high":   float(data["high"]),
            "low":    float(data["low"]),
            "close":  float(data["close"]),
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
            "CL_H1":  "CL H1",
            "CL_M30": "CL M30",
            "ES_M30": "ES M30",
        }
        crv = PARAMS[inst]["crv"]
        emoji = "🟢" if signal["direction"] == "LONG" else "🔴"
        is_es = "ES" in inst
        fmt = ".2f"
        risk = abs(signal["entry"] - signal["stop"])
        msg = (
            f"{emoji} <b>{inst_names[inst]} - {signal['direction']} SIGNAL</b>

"
            f"<b>Limit Order setzen:</b>
"
            f"Entry:  <code>{signal['entry']:{fmt}}</code>
"
            f"Stop:   <code>{signal['stop']:{fmt}}</code>
"
            f"Target {crv}R: <code>{signal['target']:{fmt}}</code>
"
            f"Risiko: <code>{risk:{fmt}}</code>

"
            f"<b>Pepperstone oeffnen!</b>
"
            f"Zeit: {datetime.now(CET).strftime('%d.%m.%Y %H:%M')} MEZ"
        )
        send_telegram(msg)
        return jsonify({"status": "signal", "signal": signal})

    return jsonify({"status": "ok", "bars": len(BUFFERS[inst])})


@app.route("/status", methods=["GET"])
def status():
    result = {}
    for inst in PARAMS:
        mom = calc_momentum(DAILY_CLOSES[inst])
        vol_ma = calc_vol_ma(BUFFERS[inst])
        atr14  = calc_atr(BUFFERS[inst])
        result[inst] = {
            "bars":         len(BUFFERS[inst]),
            "in_trade":     TRADE_STATUS[inst]["in_trade"],
            "crv":          PARAMS[inst]["crv"],
            "momentum_20d": round(mom, 2) if mom else None,
            "mom_ok":       abs(mom) <= PARAMS[inst]["mom_threshold"] if mom else True,
            "vol_ma_ready": vol_ma is not None,
            "atr_ready":    atr14 is not None,
            "fully_ready":  vol_ma is not None and atr14 is not None,
            "daily_closes": len(DAILY_CLOSES[inst]),
        }
    return jsonify(result)


@app.route("/test", methods=["GET"])
def test():
    sent = send_telegram(
        "Trading Signal Server laeuft!

"
        "Aktive Instrumente:
"
        "CL H1:  2R | Kein 15+00
"
        "CL M30: 2R | Kein 15+19 Uhr
"
        "ES M30: 1R | Kein 15+00

"
        "50 Warmup Kerzen vorgeladen
"
        "Momentum Filter sofort aktiv!"
    )
    return jsonify({"sent": sent})


@app.route("/reset/<instrument>", methods=["POST"])
def reset(instrument):
    inst_map = {"cl_h1": "CL_H1", "cl_m30": "CL_M30", "es_m30": "ES_M30"}
    inst = inst_map.get(instrument.lower())
    if not inst: return jsonify({"error": "Unbekannt"}), 400
    TRADE_STATUS[inst]["in_trade"] = False
    TRADE_STATUS[inst]["bars_since"] = 0
    return jsonify({"reset": inst})


@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status":  "running",
        "system":  "CL H1 (2R) + CL M30 (2R) + ES M30 (1R)",
        "warmup":  "50 Kerzen vorgeladen - sofort einsatzbereit",
        "endpoints": {
            "/webhook/cl_h1":  "POST - CL H1 Webhook",
            "/webhook/cl_m30": "POST - CL M30 Webhook",
            "/webhook/es_m30": "POST - ES M30 Webhook",
            "/status":         "GET  - Status aller Instrumente",
            "/test":           "GET  - Test Telegram",
            "/reset/<inst>":   "POST - Trade Reset",
        }
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

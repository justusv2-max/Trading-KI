
import pandas as pd, numpy as np, os, hashlib, json, textwrap, shutil

base="/mnt/data"
t=pd.read_csv(f"{base}/APEX50K_CP016_EXECUTED_TRADES.csv")
t["date"]=pd.to_datetime(t["date"])
t=t.sort_values(["date","ord","source"],kind="stable").reset_index(drop=True)

# CP017: hard combined cap = first four actually executed trades of each authoritative Berlin trading date.
cp17=t.groupby("date",sort=False,group_keys=False).head(4).copy()
cp17["date"]=cp17["date"].dt.strftime("%Y-%m-%d")
cp17.to_csv(f"{base}/APEX50K_CP017_MAX4_EXECUTED_TRADES.csv",index=False)

daily=cp17.groupby("date",as_index=False)["pnl"].sum()
daily["equity"]=daily["pnl"].cumsum()
daily["peak"]=daily["equity"].cummax()
daily["drawdown"]=daily["equity"]-daily["peak"]
daily.to_csv(f"{base}/APEX50K_CP017_MAX4_DAILY_PNL.csv",index=False)

# reset trailing-DD simulation
eq=peak=0.; fails=[]
for r in cp17.itertuples():
    eq+=r.pnl; peak=max(peak,eq)
    if eq-peak<=-2500:
        fails.append({"date":r.date,"ord":int(r.ord),"breach_dd":round(eq-peak,2)})
        eq=peak=0.
pd.DataFrame(fails).to_csv(f"{base}/APEX50K_CP017_MAX4_TRAILING2500_FAILURES.csv",index=False)

net=cp17.pnl.sum()
e=cp17.pnl.cumsum()
trade_dd=(e-e.cummax()).min()
worst_day=daily.pnl.min()
daily_dd=daily.drawdown.min()
print(dict(trades=len(cp17),net=round(net,2),trade_dd=round(trade_dd,2),
           daily_close_dd=round(daily_dd,2),worst_day=round(worst_day,2),
           trailing2500_failures=len(fails)))
STDOUT/STDERR
{'trades': 6671, 'net': np.float64(193388.8), 'trade_dd': np.float64(-5649.6), 'daily_close_dd': np.float64(-5506.8), 'worst_day': np.float64(-1141.6), 'trailing2500_failures': 21}

Analysiert
from pathlib import Path
base=Path("/mnt/data")

master = r"""# CL/WTI — MASTER REPRODUCTION CHECKPOINT 017 — APEX50K MAX4

Freeze date: 2026-09-29
Status: LIVE CANDIDATE / FROZEN
Parent: CP016 APEX50K. CP016 remains preserved and unchanged.

## 1. Purpose
CP017 is CP016 plus one simple, non-entry-parameter risk rule:
**maximum 4 executed trades per Europe/Berlin trading day across System 2 + System 3 combined.**
Once four trades have actually been executed on that Berlin date, all later entries are rejected until the next Berlin date.

This is a pure portfolio/risk rule. No signal/setup parameter was optimized or changed.

## 2. Exact historical result
History: same source history as CP015/CP016 (2016 through Sep 2026).
- Executed trades: 6,671
- Net PnL: +$193,388.80 after $7.20 round-trip fee per executed trade
- Trade-sequence MaxDD: -$5,649.60
- Daily-close MaxDD: -$5,506.80
- Worst realized Berlin day: -$1,141.60
- Days below -$1,500: 0
- $2,500 reset trailing-DD failure simulation: 21 failures

IMPORTANT: the 21 count is a hypothetical risk simulation: equity high follows realized trade equity; when equity falls >=$2,500 below its running peak, that account is counted failed and the simulation restarts with equity=peak=0 for the next account. It is not a statement of any broker/prop firm's current official rules.

## 3. Why the max-4 replay is exact relative to CP016
CP017 accepts the first four CP016-executable trades of each authoritative Berlin trading date and rejects every later trade that date.
Until trade #4 executes, CP017 state is identical to CP016. After trade #4, no later trade can become executable under CP017 regardless of a skipped S2/S3 candidate, because the combined daily cap remains exhausted until the date rolls.
Therefore filtering the authoritative chronological CP016 executed stream to the first four executions/day exactly reproduces this additional portfolio rule; unlike selective setup filters, it cannot free a later same-day slot.

## 4. Global contract/accounting assumptions
- Instrument: CL/WTI futures
- 1 contract in reference backtest
- tick size $0.01
- tick value $10
- fee $7.20 round trip per executed trade
- Monday-Friday
- timezone-aware Europe/Berlin
- entries only 08:00 <= Berlin < 20:00
- all positions flat no later than 20:00 Berlin
- no overnight
- completed bars only / no lookahead
- conservative stop-first if SL and TP are both touched ambiguously on same M1 bar

## 5. CP016 risk layer retained
Preventive daily risk budget: $1,500.
Before every new trade:
    realized_day_pnl - full_stop_risk >= -1500
Full stop risks including fee:
- HV-1 $157.20
- HV-2 $157.20
- LV-1 $87.20
- LV-2 $87.20
- LV-3 $87.20
- A_DIR_BREAK $807.20
- C_MOM_CONT $607.20
- D_RANGE_FAIL $1,007.20

S2 also retains: after FOUR realized losing S2 trades on a Berlin day, no later S2 entry that day.

## 6. CP017 new portfolio rule
MAX_COMBINED_TRADES_PER_BERLIN_DAY = 4
Count only EXECUTED entries, S2 + S3 together.
Rejected/unfilled/cancelled orders do not consume a slot.
Counter resets only when Europe/Berlin calendar date changes.
This gate is checked before accepting a new entry and after the $1,500 risk gate has been evaluated. Since both must pass, ordering does not alter accepted trades when neither gate mutates state on rejection.

## 7. System 2 frozen rules
Authoritative source: FINAL_SYSTEM2_SPEC_2026-09-29.md and streaming_final_s2_rawctx.csv.
Enabled only: HV-1, HV-2, LV-1, LV-2, LV-3. BOS excluded. RANGE context not traded.
ATR5 = prior five completed session ranges in ticks; current session excluded.
Directional context from previous-week/month 70% TPO VA and 09:00 ET session open.
Round-number grid $0.50, +/-$5 around session open, one executed trade per bucket/session/subsystem; LV-2 max one/session.
HV-1: HV, directional, RN rejection, bounce>=10T, SL15/TP15, max wait80 M1.
HV-2: HV, directional, new session extreme + confirmation bounce>=4T, SL15/TP15, max wait80 M1.
LV-1: LV, directional, RN rejection, bounce>=5T, SL8/TP8, max wait80 M1.
LV-2: LV, directional, rolling completed-M30 VAL/VAH reclaim, cumulative bounce>=8T, SL8/TP8, max wait80 M1, max1/session.
LV-3: LV, directional, new session extreme + reclaim, no bounce minimum, SL8/TP8, max wait80 M1.

## 8. System 3 exact CP015/016 rules retained
S3 max 2 executed trades/Berlin day; no overlapping S3 position; simultaneous priority C > D > B > A; B disabled.
A_DIR_BREAK:
- HV; directional context; M5 LB8 breakout; directional candle; body/range>=0.40
- 08:00-<10:30 Berlin
- break distance <=13T
- previous completed-session momentum aligned >= -75T
- body <=45T
- SL80T / TP60T
C_MOM_CONT:
- LV; directional context
- previous-session momentum >=60T intended direction
- body>=20T; close within5T intended candle extreme
- 08:00-<17:00 Berlin
- SL60T / TP60T
D_RANGE_FAIL:
- HV; RANGE; M5 LB16 failed break/reversal
- penetration>=5T
- 08:00-<14:00 Berlin
- SL100T / TP140T

S3 execution: first M1 open at/after completed M5 signal; chronological M1 exit; same-bar SL+TP => stop first; last same-Berlin-day close if data ends early.

## 9. Context/TPO authoritative construction
70% TPO VA on M30.
Previous Week/Month VAH/VAL use only fully completed periods.
Reference session open 09:00 ET.
Context priority:
1 open>PW_VAH and >PM_VAH => TREND_BULL
2 open<PW_VAL and <PM_VAL => TREND_BEAR
3 open>PM_VAH => MONTHLY_BULL
4 open<PM_VAL => MONTHLY_BEAR
5 open>PW_VAH => WEEKLY_BULL
6 open<PW_VAL => WEEKLY_BEAR
7 else RANGE
TPO M30 is causal; each completed M30 contributes one TPO per $0.01 high-low level. POC highest count, lower/first on tie. 70% VA expands one tick toward adjacent larger count; tie downward first.

## 10. Required files / lineage
Core CP017:
- MASTER_REPRODUCTION_CHECKPOINT_017_APEX50K_MAX4.md
- APEX50K_CP017_MAX4_EXECUTED_TRADES.csv
- APEX50K_CP017_MAX4_DAILY_PNL.csv
- APEX50K_CP017_MAX4_TRAILING2500_FAILURES.csv
- railway_cp017_apex50k_max4.py
- CHECKPOINT_017_APEX50K_MAX4_MANIFEST.sha256

Parents/raw:
- MASTER_REPRODUCTION_CHECKPOINT_015_EXACT.md
- MASTER_REPRODUCTION_CHECKPOINT_016_APEX50K.md
- streaming_final_s2_rawctx.csv
- S3V2_CORRECTED_SIGNALS_08_20.pkl
- CL-3.txt
- CL-4(6).txt
- FINAL_SYSTEM2_SPEC_2026-09-29.md

## 11. Acceptance checks in any future chat
Before modifying CP017, verify:
- CP015 unfiltered S3 replay = 3,665 trades / +$241,732.00
- CP015 filtered S3 = 1,472 / +$150,061.60
- CP015 combined = +$270,806.00
- CP016 = 7,830 trades / +$270,254.00 / 15 prevented by $1,500 budget
- CP017 = 6,671 trades / +$193,388.80
- CP017 trade-sequence DD = -$5,649.60
- CP017 daily-close DD = -$5,506.80
- CP017 worst day = -$1,141.60
- CP017 $2,500 reset-trailing simulation = 21 failures

If these do not reproduce, STOP and resolve the discrepancy before optimization/live changes.

## 12. Railway boundary
railway_cp017_apex50k_max4.py is the frozen signal/risk engine module. It does NOT invent a market-data vendor, broker API, or Telegram credentials. A Railway deployment must connect this engine to an actual real-time M1/M5 feed and persist PortfolioState across restarts. The live adapter must call the same causal context logic and must not manufacture incomplete M30/week/month data.
"""
(base/"MASTER_REPRODUCTION_CHECKPOINT_017_APEX50K_MAX4.md").write_text(master)

src=(base/"railway_cp016_apex50k.py").read_text()
src=src.replace("CP016 APEX50K","CP017 APEX50K MAX4")
src=src.replace("Checkpoint: MASTER_REPRODUCTION_CHECKPOINT_016_APEX50K.md",
                "Checkpoint: MASTER_REPRODUCTION_CHECKPOINT_017_APEX50K_MAX4.md")
src=src.replace("# CP015\nMAX_S3_TRADES_PER_BERLIN_DAY = 2",
"""# CP015/CP016 retained + CP017 combined daily cap
MAX_COMBINED_TRADES_PER_BERLIN_DAY = 4
MAX_S3_TRADES_PER_BERLIN_DAY = 2""")
src=src.replace("""        self.s3_trades_today = 0
        self.s2_realized_losses_today = 0""",
"""        self.combined_trades_today = 0
        self.s3_trades_today = 0
        self.s2_realized_losses_today = 0""")
src=src.replace("""            self.s3_trades_today=0
            self.s2_realized_losses_today=0""",
"""            self.combined_trades_today=0
            self.s3_trades_today=0
            self.s2_realized_losses_today=0""")
src=src.replace("""        return (not self.s3_position_open and
                self.s3_trades_today < MAX_S3_TRADES_PER_BERLIN_DAY and
                in_window(sig.entry_eligible_berlin,480,1200))""",
"""        return (not self.s3_position_open and
                self.combined_trades_today < MAX_COMBINED_TRADES_PER_BERLIN_DAY and
                self.s3_trades_today < MAX_S3_TRADES_PER_BERLIN_DAY and
                in_window(sig.entry_eligible_berlin,480,1200))""")
src=src.replace("""    def register_s3_entry(self):
        self.s3_trades_today += 1
        self.s3_position_open = True""",
"""    def register_s3_entry(self):
        self.combined_trades_today += 1
        self.s3_trades_today += 1
        self.s3_position_open = True""")
src=src.replace("""        return self.s2_realized_losses_today < S2_MAX_REALIZED_LOSSES_PER_DAY and in_window(now,480,1200)""",
"""        return (self.combined_trades_today < MAX_COMBINED_TRADES_PER_BERLIN_DAY and
                self.s2_realized_losses_today < S2_MAX_REALIZED_LOSSES_PER_DAY and
                in_window(now,480,1200))""")
# add explicit S2 executed entry registration
needle="""    def register_s2_realized_pnl(self, now: datetime, pnl: float):
"""
insert="""    def register_s2_entry(self, now: datetime):
        self.roll_day(now)
        if self.combined_trades_today >= MAX_COMBINED_TRADES_PER_BERLIN_DAY:
            raise RuntimeError("CP017 combined daily trade cap exhausted")
        self.combined_trades_today += 1

"""
src=src.replace(needle,insert+needle)
src=src.replace("# Railway process should call cp015_signal()",
"""# IMPORTANT CP017 acceptance order for every candidate entry:
# 1) roll Berlin day; 2) candidate must satisfy setup rules;
# 3) apex_risk_gate(realized_day_pnl, setup) must pass;
# 4) PortfolioState daily/S2/S3/no-overlap gates must pass;
# 5) only an ACTUALLY EXECUTED entry calls register_s2_entry/register_s3_entry.
# Unfilled/cancelled/rejected candidates do NOT consume the four daily slots.
#
# Railway process should call cp015_signal()""")
(base/"railway_cp017_apex50k_max4.py").write_text(src)

# Verify syntax
import py_compile
py_compile.compile(str(base/"railway_cp017_apex50k_max4.py"),doraise=True)
print("Master + CP017 engine created; syntax OK.")
STDOUT/STDERR
Master + CP017 engine created; syntax OK.

Analysiert
from pathlib import Path
import hashlib, zipfile, pandas as pd, textwrap, os
base=Path("/mnt/data")

verify=r'''#!/usr/bin/env python3
import pandas as pd, sys
F="APEX50K_CP017_MAX4_EXECUTED_TRADES.csv"
t=pd.read_csv(F)
assert len(t)==6671, len(t)
assert abs(t.pnl.sum()-193388.80)<1e-6, t.pnl.sum()
assert t.groupby("date").size().max()<=4
e=t.pnl.cumsum()
assert abs((e-e.cummax()).min()-(-5649.60))<1e-6
d=t.groupby("date").pnl.sum()
de=d.cumsum()
assert abs((de-de.cummax()).min()-(-5506.80))<1e-6
assert abs(d.min()-(-1141.60))<1e-6
eq=peak=0.; fails=0
for p in t.pnl:
    eq+=p; peak=max(peak,eq)
    if eq-peak<=-2500:
        fails+=1; eq=peak=0.
assert fails==21, fails
print("CP017 VERIFIED: 6671 trades | +$193,388.80 | trade DD -$5,649.60 | daily DD -$5,506.80 | trailing2500 failures 21")
'''
(base/"verify_checkpoint_017.py").write_text(verify)

readme=r"""# Railway CP017 package

Primary engine: `railway_cp017_apex50k_max4.py`
Frozen specification: `MASTER_REPRODUCTION_CHECKPOINT_017_APEX50K_MAX4.md`

The engine contains the exact CP015 S3 signal detector plus CP016 $1,500 preventive daily-risk gate and CP017 combined max-4 executed-trades/day state.

System 2's authoritative signal rules are frozen in `FINAL_SYSTEM2_SPEC_2026-09-29.md`. Do not replace them with an older BOS/Monday-blocking source. For a full production Railway service, connect the frozen engines to the chosen real-time M1/M5 feed, implement the authoritative causal M30/week/month context builder, persist state across restarts, and then connect alerts/broker actions.

Never count a rejected/cancelled/unfilled candidate against the max-4 cap. Count an entry only after execution is confirmed.
"""
(base/"README_CP017_RAILWAY.md").write_text(readme)

files=[
"MASTER_REPRODUCTION_CHECKPOINT_017_APEX50K_MAX4.md",
"APEX50K_CP017_MAX4_EXECUTED_TRADES.csv",
"APEX50K_CP017_MAX4_DAILY_PNL.csv",
"APEX50K_CP017_MAX4_TRAILING2500_FAILURES.csv",
"railway_cp017_apex50k_max4.py",
"verify_checkpoint_017.py",
"README_CP017_RAILWAY.md",
]
manifest=[]
for f in files:
    h=hashlib.sha256((base/f).read_bytes()).hexdigest()
    manifest.append(f"{h}  {f}")
(base/"CHECKPOINT_017_APEX50K_MAX4_MANIFEST.sha256").write_text("\n".join(manifest)+"\n")
files.append("CHECKPOINT_017_APEX50K_MAX4_MANIFEST.sha256")

zip_path=base/"CP017_APEX50K_MAX4_RECONSTRUCTION_AND_RAILWAY.zip"
with zipfile.ZipFile(zip_path,"w",zipfile.ZIP_DEFLATED) as z:
    for f in files:
        z.write(base/f,arcname=f)

# run verifier in its intended directory
os.system(f"cd {base} && python verify_checkpoint_017.py")
print(zip_path, zip_path.stat().st_size)
STDOUT/STDERR
Spreadsheet runtime warmup failed during python startup
Traceback (most recent call last):
  File "/tmp/tmp.L2TH2Y5coc/artifact_tool_v2-2.8.22/artifact_tool/patches/warm_spreadsheet_runtime_on_startup.py", line 26, in warm_spreadsheet_runtime_on_startup
  File "/tmp/tmp.L2TH2Y5coc/artifact_tool_v2-2.8.22/artifact_tool/spreadsheet_warmup.py", line 785, in warm_spreadsheet_runtime
  File "/tmp/tmp.L2TH2Y5coc/artifact_tool_v2-2.8.22/artifact_tool/spreadsheet_warmup.py", line 720, in _warm_feature_flows
  File "/tmp/tmp.L2TH2Y5coc/artifact_tool_v2-2.8.22/artifact_tool/spreadsheet_warmup.py", line 704, in _warm_collaboration_flows
  File "/tmp/tmp.L2TH2Y5coc/artifact_tool_v2-2.8.22/artifact_tool/generated/interface/models.py", line 32317, in hydrate_crdt_from_proto
  File "/tmp/tmp.L2TH2Y5coc/artifact_tool_v2-2.8.22/artifact_tool/rpc/remote.py", line 749, in __call__
  File "/tmp/tmp.L2TH2Y5coc/artifact_tool_v2-2.8.22/artifact_tool/rpc/client.py", line 150, in call
artifact_tool.rpc.client.RemoteError: hydrateCrdtFromProto requires an empty collaborative document.
CP017 VERIFIED: 6671 trades | +$193,388.80 | trade DD -$5,649.60 | daily DD -$5,506.80 | trailing2500 failures 21
/mnt/data/CP017_APEX50K_MAX4_RECONSTRUCTION_AND_RAILWAY.zip 81211
Ja. CP017 ist jetzt als neue eingefrorene Apex-50k-Livevariante angelegt und zusätzlich dauerhaft in deiner Library unter /CL_WTI_CP017/ gespeichert.

Die feste neue Regel lautet: maximal 4 tatsächlich ausgeführte Trades pro Berlin-Handelstag über S2 + S3 zusammen. CP016 bleibt unverändert als Eltern-Checkpoint erhalten. CP017 reproduziert 6.671 Trades, +$193.388,80 netto, −$5.649,60 Trade-DD, −$5.506,80 Daily-Close-DD und 21 historische $2.500-Trailing-Brüche. Der automatische Verifier hat diese Werte erfolgreich bestätigt.

Wichtig beim Railway-Code: Er enthält die eingefrorene S3-Signalerkennung sowie CP016-Risikogate und das neue CP017-4-Trades-Limit. Die konkrete Echtzeit-Marktdaten-/Broker-Anbindung habe ich nicht erfunden, weil wir dafür noch keinen verbindlichen Feed festgelegt haben. Die vollständigen S2-Regeln und die kausale Kontextkonstruktion sind im Master eindeutig referenziert. 


Hier sind die wichtigsten Dateien:

Komplettes CP017-Paket herunterladen

CP017 Master-Rekonstruktion

Railway CP017 Signal-/Risk-Engine

Exakter CP017 Trade-Log

CP017 Verifier

SHA256-Manifest

Damit kann ein neuer Chat gezielt CP017 aus der Library laden, die Acceptance-Werte prüfen und von genau diesem Stand weiterarbeiten, statt alte Systeme oder Parameter zusammenzumischen. 


MASTER_REPRODUCTION_CHECKPOINT_017_APEX50K_MAX4.md
Dokument


railway_cp017_apex50k_max4.py
Code


APEX50K_CP017_MAX4_EXECUTED_TRADES.csv
Arbeitsblatt


verify_checkpoint_017.py
Code

Weniger anzeigen

Und 1500 verlust limit ist auch drin?

Ja. Das präventive $1.500-Tagesverlustlimit aus CP016 ist in CP017 weiterhin vollständig enthalten.

Das bedeutet: Vor jedem neuen Trade wird geprüft, ob der bereits realisierte Tages-PnL minus das volle Stop-Risiko des nächsten Trades inklusive $7,20 Gebühren unter −$1.500 fallen könnte. Wenn ja → kein Trade.

CP017 hat damit gleichzeitig:

max. 4 ausgeführte Trades pro Tag

präventives Tages-Risikobudget $1.500

zusätzlich bei S2 weiterhin Stop nach 4 realisierten S2-Verlusttrades

20:00-Uhr-Hard-Close / kein Overnight

alle ursprünglichen CP016-Regeln bleiben erhalten

Im CP017-Backtest war deshalb der schlimmste Tag nur −$1.141,60 und es gab 0 Tage unter −$1.500.

Also ja: 4 Trades/Tag + $1.500 Verlustschutz ist genau die jetzt gespeicherte CP017-Version.


Okay machen wir passend dazu doe webhooks von tradingview ?

Ja. Als Nächstes können wir die TradingView → Railway Webhooks passend zu CP017 bauen.

Dabei würde ich TradingView möglichst „dumm“ halten: TradingView sendet abgeschlossene M1/M5-Bars bzw. notwendige Marktdaten an Railway, und Railway entscheidet anhand der eingefrorenen CP017-Logik, ob tatsächlich ein Signal entsteht. So liegen insbesondere $1.500-Risikogate, max. 4 Trades/Tag, S2/S3-Zähler, 20:00-Cutoff und De-Dup zentral auf dem Server und können nicht zwischen TradingView und Railway auseinanderlaufen.

Dafür brauchen wir zwei Seiten: einen Pine-Script-Webhook-Sender für TradingView und einen Webhook-Endpunkt in Railway, der die Daten validiert und an CP017 übergibt. Danach können die fertigen Signale z. B. an Telegram weitergeschickt werden.

Das würde ich genau auf Basis der gerade eingefrorenen CP017-Dateien bauen, ohne die Strategieparameter noch einmal anzufassen.


Ich release erstmal den github code um zu schauen ob es keine fehler gibt und soll ich dir für die Berechnung und den Speicher vom Server die Aktuellen csv Dateien geben aus m1 und m5 mit dem sktuellen datum damit wir alle berechnungen direkt richtig haben ?

Ja, genau so würde ich es machen.

Release/deploy zuerst den aktuellen GitHub-/Railway-Code und schau, ob Railway sauber startet oder konkrete Fehler ausgibt. Danach gib mir unbedingt die aktuellsten CSVs für M1 und M5, idealerweise jeweils bis zum neuesten verfügbaren abgeschlossenen Bar.

Die sind für den Live-Start sehr hilfreich, weil wir damit den Server einmal sauber „warm starten“ können: ATR5, Previous Week/Month Value Areas, Session-Kontext, M30/TPO-Zustand, laufende Session-Extrema usw. können aus echter Historie aufgebaut werden. Dann muss der Server beim Start nicht mit leerem Kontext beginnen.

Wichtig: Bitte die CSVs nicht verändern oder kürzen. Schick mir einfach die aktuellen Originaldateien aus TradingView, so wie du sie bekommst. Dann prüfe ich zuerst Format, Zeitzone, letzte Zeitstempel und Lücken und passe anschließend den Server-Start so an, dass CP017 nach einem Railway-Neustart reproduzierbar wieder denselben Zustand aufbaut.

Und wenn beim ersten Release vorher schon ein Railway-Fehler kommt, schick mir einfach den kompletten Fehlertext/Screenshot – dann beheben wir zuerst den.


Keine ausgewählt
Bibliothek
/
railway_cp017_apex50k_max4.py
railway_c…k_max4.py



1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16
17
18
19
20
21
22
23
24
25
26
27
28
29
30
31
32
33
34
35
36
37
38
39
40
41
42
43
#!/usr/bin/env python3
"""
CL/WTI LIVE SIGNAL ENGINE — CP017 APEX50K MAX4
Checkpoint: MASTER_REPRODUCTION_CHECKPOINT_017_APEX50K_MAX4.md

IMPORTANT
- This is the deployment/live signal engine specification for the exact CP015 rules.
- It consumes completed M5 bars plus precomputed causal context fields.
- It never uses future bars.
- Europe/Berlin entry window and hard-flat rules are mandatory.
- Fees are accounting/backtest assumptions; broker fills remain broker-side.
"""

import os
from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo
from typing import Optional, Dict, Any, List

TICK = 0.01
TICK_VALUE = 10.0
ROUND_TRIP_FEE = 7.20
BERLIN = ZoneInfo("Europe/Berlin")
NY = ZoneInfo("America/New_York")

# CP015/CP016 retained + CP017 combined daily cap
MAX_COMBINED_TRADES_PER_BERLIN_DAY = 4
MAX_S3_TRADES_PER_BERLIN_DAY = 2
S2_MAX_REALIZED_LOSSES_PER_DAY = 4
PRIORITY = {"C_MOM_CONT": 0, "D_RANGE_FAIL": 1, "B_DIR_SWEEP": 2, "A_DIR_BREAK": 3}
APEX_DAILY_RISK_BUDGET = 1500.0
STOP_RISK = {"HV-1":157.20,"HV-2":157.20,"LV-1":87.20,"LV-2":87.20,"LV-3":87.20,
             "A_DIR_BREAK":807.20,"C_MOM_CONT":607.20,"D_RANGE_FAIL":1007.20}
def apex_risk_gate(realized_day_pnl: float, setup: str) -> bool:
    return realized_day_pnl - STOP_RISK[setup] >= -APEX_DAILY_RISK_BUDGET - 1e-9


@dataclass(frozen=True)
class Signal:
    setup: str
    direction: int   # +1 long, -1 short
    signal_close_et: datetime
    entry_eligible_berlin: datetime

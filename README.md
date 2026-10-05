# Railway V3 EOD – SQLite/WAL Fix – 2026-10-05

Dieses Paket ist für den bestehenden CL-Master **S2 + S3 A/B/C/D** bestimmt.
Die Strategieparameter wurden nicht verändert.

## Was geändert wurde

- SQLite-Initialisierung nur noch einmal beim Serverstart.
- `PRAGMA journal_mode=WAL`.
- `PRAGMA busy_timeout=30000` plus 30-Sekunden-Connection-Timeout.
- Serverseitiger DB-Lock für konkurrierende Bridge-/TV-Schreibzugriffe.
- Normale `/bridge/status`-Polls sind soweit möglich read-only.
- Abgelaufene Reservations werden bei der Risikoberechnung ignoriert, ohne bei jedem Poll ein DELETE auszuführen.
- Stale/duplizierte M1-Bars liefern HTTP 200 `STALE_OR_DUPLICATE` statt 400.
- Wenn das persistierte Engine-State älter als `seed_state.pkl` ist, wird das neuere Seed verwendet. Ein neueres Railway-State bleibt erhalten.
- ATAS-V3-Quellcode: Standard-Polling 1500 ms; Fehlermeldung heißt jetzt `Bridge V3 Polling`.

## Frischer Seed

Daten:
- M1: 21.950 Bars, 2026-09-13 18:00 ET bis 2026-10-05 15:51 ET
- M5: 21.113 Bars, 2026-06-18 18:00 ET bis 2026-10-05 15:50 ET
- Seed `last_bar`: `2026-10-05T15:51:00-04:00`
- `completed_sessions`: 20
- Tageskontext 2026-10-05: `RANGE`
- Keine offene Paper-Position im Seed

Der Replay reproduziert das heutige S3-D-Ereignis:
- Signal: 2026-10-05 11:55 ET, SHORT
- Paper Entry: 11:56 ET bei 90.07
- SL 91.47 / Target 89.62
- Flat um 14:00 ET / 20:00 Berlin, Paper-PnL +$62.80

## GitHub / Railway

Die Dateien gehören in das Root-Verzeichnis des Railway-Repositories:
`server.py`, `engine.py`, `seed_state.pkl`, `requirements.txt`, `Procfile`.

Die beiden CSVs und `build_seed.py` sind zur Reproduzierbarkeit enthalten; Railway benötigt sie zur Laufzeit nicht.

Bestehende Railway-Variablen beibehalten, insbesondere:
- `TRADING_MODE=APEX`
- `WEBHOOK_SECRET`
- Telegram-Variablen
- `STATE_DB=/data/master.sqlite3` falls bereits so verwendet

Nach dem Deploy `/health` prüfen. Erwartet:
- `ok: true`
- `ready: true`
- `execution: ATAS_BRIDGE_V3_ACCOUNT_AWARE`
- `last_bar` mindestens `2026-10-05T15:51:00-04:00`

Danach je Apex-Konto `/bridge/status` prüfen.

## ATAS

Die bereits installierte V3-Bridge kann weiterverwendet werden, wenn `Polling (ms)=1500` gesetzt ist.
Der Quellcode im Paket hat 1500 ms bereits als Default.

`ApexRailwayBridge.csproj` erwartet die ATAS-DLLs unter:
`C:\Program Files (x86)\ATAS Platform\`

## Wichtiger 50K-Risk-Hinweis

Das 50K-EOD-Eval-Profil hat im aktuellen Server `DLL=$1.000`.
S3-D hat 140 Ticks nominales Stop-Risiko = $1.400 plus $7,20 Fee und wird daher bei Tages-PnL $0 vom kontospezifischen Apex-DLL-Gate blockiert. Das ist unverändert und beabsichtigt.

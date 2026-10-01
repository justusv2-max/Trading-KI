from datetime import datetime
from zoneinfo import ZoneInfo
from engine import session_id,berlin_entry_ok,value_area,classify
NY=ZoneInfo('America/New_York')
def test_session_roll():
 assert session_id(datetime(2026,9,30,19,tzinfo=NY))=='2026-09-30'
 assert session_id(datetime(2026,9,30,10,tzinfo=NY))=='2026-09-29'
def test_va_and_context():
 v=value_area([(1000,1010),(1005,1015)]);assert v['val']<=v['poc']<=v['vah']
 assert classify(20,{'vah':19,'val':18},{'vah':19.5,'val':17})=='TREND_BULL'

from engine import Engine

def test_apex_blocks_a_and_caps_trade_count():
    e=Engine();e.set_mode('APEX');e._risk_roll_day('2026-09-30')
    ok,reason=e._risk_allow('S3-A');assert not ok and reason=='APEX_PREVENTIVE_RISK_GATE'
    assert e._risk_allow('S3-B')[0]
    e.risk_day_trades=9;assert not e._risk_allow('HV-1')[0]

def test_ek_bypasses_apex_gate():
    e=Engine();e.set_mode('EK');e._risk_roll_day('2026-09-30');e.risk_day_trades=99;e.risk_day_realized=-9999
    assert e._risk_allow('S3-A')[0]

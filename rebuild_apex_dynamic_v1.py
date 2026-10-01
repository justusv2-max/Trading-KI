import pandas as pd, json
from pathlib import Path
HERE=Path(__file__).resolve().parent
SRC=(HERE/'../ek/S2_S3_ABCD_COMBINED_TRADES_CHRONO.csv').resolve()
RISK={'S2_HV-1':157.2,'S2_HV-2':157.2,'S2_LV-1':87.2,'S2_LV-2':87.2,'S2_LV-3':87.2,'S3_A':1827.2,'S3_B':807.2,'S3_C':1007.2,'S3_D':1407.2}
df=pd.read_csv(SRC);df['entry_time_ny']=pd.to_datetime(df.entry_time_ny);df=df.sort_values('entry_time_ny').reset_index(drop=True)
ids=[];blocked=[];equity=0.;peak=0.
for d,g in df.groupby('date',sort=True):
    realized=0.;n=0;startdd=equity-peak
    base=1200.-(200. if startdd<=-1000 else 0.)-(450. if startdd<=-1800 else 0.)
    for idx,row in g.iterrows():
        eff=min(base+.60*max(realized,0.),1400.)
        reason='MAX_9_TRADES' if n>=9 else ('PREVENTIVE_RISK_GATE' if realized-RISK[row.setup] < -eff else None)
        if reason:
            z=row.to_dict();z.update(realized_before=realized,effective_budget=eff,reserved_risk=RISK[row.setup],start_day_dd=startdd,reason=reason);blocked.append(z);continue
        ids.append(idx);realized+=row.pnl_net;n+=1
    equity+=realized;peak=max(peak,equity)
x=df.loc[ids].copy();x.to_csv(HERE/'REBUILT_APEX_DYNAMIC_V1_GOLDEN_EXECUTED.csv',index=False)
pd.DataFrame(blocked).to_csv(HERE/'REBUILT_APEX_DYNAMIC_V1_BLOCKED_TRADES.csv',index=False)
d=x.groupby('date',as_index=False).pnl_net.sum();d['equity']=d.pnl_net.cumsum();d['peak']=d.equity.cummax();d['drawdown']=d.equity-d.peak
y=x.groupby(x.entry_time_ny.dt.year).agg(trades=('pnl_net','size'),net=('pnl_net','sum')).reset_index(names='year')
mo=x.groupby(x.entry_time_ny.dt.to_period('M')).agg(trades=('pnl_net','size'),net=('pnl_net','sum')).reset_index(names='month');mo.month=mo.month.astype(str)
d.to_csv(HERE/'REBUILT_APEX_DYNAMIC_V1_DAILY_EQUITY.csv',index=False);y.to_csv(HERE/'REBUILT_APEX_DYNAMIC_V1_YEARLY.csv',index=False);mo.to_csv(HERE/'REBUILT_APEX_DYNAMIC_V1_MONTHLY.csv',index=False)
print({'trades':len(x),'net':float(x.pnl_net.sum()),'daily_close_maxdd':float(d.drawdown.min()),'worst_day':float(d.pnl_net.min()),'days_below_minus_1400':int((d.pnl_net<-1400).sum()),'positive_years':int((y.net>0).sum())})

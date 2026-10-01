import pandas as pd, numpy as np, json, hashlib, os
R='/mnt/data'
s2=pd.read_csv(R+'/streaming_final_s2_rawctx.csv')
s2['entry_time_ny']=pd.to_datetime(s2['date'])+pd.Timedelta(hours=9)+pd.to_timedelta(s2['entry_idx'],unit='m')
s2['pnl_net']=s2['pnl']; s2['source']='S2'; s2['setup']='S2_'+s2['system'].astype(str)
s3=[]
for fn,setup in [('S3_MASTER_A_LV_CONT_GOLDEN_TRADES.csv','S3_A'),('S3_B_QUALITY_GOLDEN_TRADES.csv','S3_B'),('S3_MASTER_C_HV200_FADE_GOLDEN_TRADES.csv','S3_C'),('S3_D_EXTREME_HV_GOLDEN_TRADES.csv','S3_D')]:
 d=pd.read_csv(R+'/'+fn); d['entry_time_ny']=pd.to_datetime(d['entry_time_ny']); d['source']='S3'; d['setup']=setup; s3.append(d[['entry_time_ny','pnl_net','source','setup']])
s3=pd.concat(s3,ignore_index=True)
s2x=s2[['entry_time_ny','pnl_net','source','setup']]
alltr=pd.concat([s2x,s3],ignore_index=True).sort_values(['entry_time_ny','source','setup']).reset_index(drop=True)
alltr['date']=alltr.entry_time_ny.dt.date; alltr['year']=alltr.entry_time_ny.dt.year; alltr['month']=alltr.entry_time_ny.dt.to_period('M').astype(str)
# daily is authoritative capacity-unconstrained portfolio realization metric
piv=alltr.pivot_table(index='date',columns='source',values='pnl_net',aggfunc='sum',fill_value=0).sort_index()
for c in ['S2','S3']:
 if c not in piv:piv[c]=0
piv['total']=piv.S2+piv.S3;piv['equity']=piv.total.cumsum();piv['peak']=piv.equity.cummax().clip(lower=0);piv['dd']=piv.equity-piv.peak
# chronological entry-ordered diagnostic only (not realized-exit sequence)
eq=alltr.pnl_net.cumsum(); pk=eq.cummax().clip(lower=0); entry_order_dd=float((eq-pk).min())
# stats
p=alltr.pnl_net.to_numpy(); gp=p[p>0].sum(); gl=-p[p<0].sum()
y=alltr.groupby('year').pnl_net.sum(); m=alltr.groupby('month').pnl_net.sum()
active_s2=set(s2x.entry_time_ny.dt.date); active_s3=set(s3.entry_time_ny.dt.date)
metrics={'status':'FINAL_COMBINED_RESEARCH_REPLAY_SIMULTANEOUS_SUBSYSTEM_POSITIONS_ALLOWED','trades':len(alltr),'s2_trades':len(s2x),'s3_trades':len(s3),'net':float(p.sum()),'pf_trade_aggregate':float(gp/gl),'daily_close_maxdd':float(piv.dd.min()),'worst_day':float(piv.total.min()),'best_day':float(piv.total.max()),'positive_years':int((y>0).sum()),'years_total':len(y),'positive_months':int((m>0).sum()),'months_total':len(m),'s2_s3_daily_corr':float(piv[['S2','S3']].corr().iloc[0,1]),'s2_active_days':len(active_s2),'s3_active_days':len(active_s3),'both_active_days':len(active_s2&active_s3),'entry_order_dd_diagnostic_not_exit_order':entry_order_dd,'yearly':{str(k):float(v) for k,v in y.items()}}
alltr.to_csv(R+'/S2_S3_ABCD_COMBINED_TRADES_CHRONO.csv',index=False); piv.reset_index().to_csv(R+'/S2_S3_ABCD_COMBINED_DAILY_EQUITY.csv',index=False); pd.DataFrame({'year':y.index,'pnl_net':y.values}).to_csv(R+'/S2_S3_ABCD_COMBINED_YEARLY.csv',index=False); pd.DataFrame({'month':m.index,'pnl_net':m.values}).to_csv(R+'/S2_S3_ABCD_COMBINED_MONTHLY.csv',index=False)
open(R+'/S2_S3_ABCD_COMBINED_METRICS.json','w').write(json.dumps(metrics,indent=2))
# checkpoint
text=f'''# S2 + S3 A+B+C+D — COMBINED MASTER CHECKPOINT — 2026-09-30\n\nStatus: authoritative combined research replay with simultaneous subsystem positions allowed. No portfolio-wide single-position restriction has been invented.\n\n## Frozen inputs\nS2: streaming_final_s2_rawctx.csv, 6,542 trades, frozen System 2.\nS3 A: S3_MASTER_A_LV_CONT_GOLDEN_TRADES.csv\nS3 B: S3_B_QUALITY_GOLDEN_TRADES.csv\nS3 C: S3_MASTER_C_HV200_FADE_GOLDEN_TRADES.csv\nS3 D: S3_D_EXTREME_HV_GOLDEN_TRADES.csv\nRaw reconstruction source: CL-3.txt and CL-4(6).txt.\n\n## Common execution assumptions\n1 CL per subsystem trade. Each subsystem retains its own no-overlap/execution rules. Different subsystems may hold positions simultaneously. $7.20 round-trip commission is already included in every golden-log PnL. No new entries >=20:00 Europe/Berlin and forced flat by 20:00 are inherited from the frozen subsystem definitions. S2 authoritative session indices are 09:00-15:00 ET M1: entry_time_ny = date 09:00 ET + entry_idx minutes.\n\n## Combined verified metrics\nTrades: {metrics['trades']} = {metrics['s2_trades']} S2 + {metrics['s3_trades']} S3.\nNet: ${metrics['net']:.2f}. Aggregate trade PF: {metrics['pf_trade_aggregate']:.6f}. Daily-close MaxDD: ${metrics['daily_close_maxdd']:.2f}. Worst day: ${metrics['worst_day']:.2f}. Positive years: {metrics['positive_years']}/{metrics['years_total']}. Positive months: {metrics['positive_months']}/{metrics['months_total']}. S2/S3 daily correlation: {metrics['s2_s3_daily_corr']:.6f}. Both active on {metrics['both_active_days']} days.\n\n## Important scope\nDaily-close equity/DD is the authoritative combined metric in this checkpoint because the frozen S2 golden log does not contain exit timestamps. `entry_order_dd_diagnostic_not_exit_order` is only a diagnostic and MUST NOT be called true intraday/trade-sequence DD. A portfolio-wide one-position-only or realized-PnL daily-stop replay requires exact S2 exit timestamps or a fully reconstructed S2 execution log; do not fabricate them.\n\n## Reproduction\nRun build_final_combined.py in the same directory as the five golden logs. It creates combined trades, daily equity, yearly/monthly tables and metrics. For full raw regeneration of S3 A/C use rebuild_s3_ac_master.py; B/D use the checkpoint optimization/replay scripts. S2 is governed by FINAL_SYSTEM2_SPEC_2026-09-29.md and streaming_final_s2_rawctx.csv.\n'''
open(R+'/S2_S3_ABCD_COMBINED_MASTER_CHECKPOINT.md','w').write(text)
# hashes
files=['CL-3.txt','CL-4(6).txt','streaming_final_s2_rawctx.csv','FINAL_SYSTEM2_SPEC_2026-09-29.md','S3_MASTER_A_LV_CONT_GOLDEN_TRADES.csv','S3_B_QUALITY_GOLDEN_TRADES.csv','S3_MASTER_C_HV200_FADE_GOLDEN_TRADES.csv','S3_D_EXTREME_HV_GOLDEN_TRADES.csv','build_final_combined.py','S2_S3_ABCD_COMBINED_TRADES_CHRONO.csv','S2_S3_ABCD_COMBINED_DAILY_EQUITY.csv','S2_S3_ABCD_COMBINED_METRICS.json','S2_S3_ABCD_COMBINED_MASTER_CHECKPOINT.md']
with open(R+'/S2_S3_ABCD_COMBINED_SHA256SUMS.txt','w') as f:
 for fn in files:
  path=R+'/'+fn
  if os.path.exists(path): f.write(hashlib.sha256(open(path,'rb').read()).hexdigest()+'  '+fn+'\n')
print(json.dumps(metrics,indent=2))

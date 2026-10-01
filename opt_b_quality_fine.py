exec(open('/mnt/data/compare_b_portfolio.py').read().split("Bs=[")[0])
base=pd.concat([A,C,Dd]); base_daily=base.assign(date=base.entry_time_ny.dt.date).groupby('date').pnl_net.sum()
rows=[]
for lb in [5,6,7,8]:
 for thr in [10,12,14]:
  for br in [.4,.5,.6]:
   mx=(pd.Series(c).shift(1)-pd.Series(c).shift(1+lb)).to_numpy()*100
   sig=np.where((mx>=thr)&(c>o)&(body>=br),1,np.where((mx<=-thr)&(c<o)&(body>=br),-1,0))
   for weak in [20,30,40]:
    mm=np.abs(pmom)<weak; ix=np.flatnonzero(nt&(atr>150)&(atr<=200)&mm&(bh>=10)&(bh<20)&(sig!=0)).astype(np.int64);di=sig[ix].astype(np.int64)
    for sl,tp in [(60,20),(80,25),(80,30),(100,30)]:
     p,en=run(o,h,l,bh,bd,ix,di,sl,tp)
     if len(p)<250:continue
     B=pd.DataFrame({'entry_time_ny':pd.to_datetime(ts[en],unit='m'),'pnl_net':p}); m=metrics(B); pm=metrics(pd.concat([base,B])); y=B.assign(year=B.entry_time_ny.dt.year).groupby('year').pnl_net.sum();
     rows.append([lb,thr,br,weak,sl,tp,m['n'],m['net'],m['pf'],m['daily_dd'],m['worst_day'],m['pos_years'],pm['net'],pm['pf'],pm['daily_dd'],pm['worst_day'],pm['pos_years']])
R=pd.DataFrame(rows,columns=['lb','thr','body','weak','sl','tp','n','net','pf','dd','worstday','posy','port_net','port_pf','port_dd','port_worstday','port_posy'])
R['score']=R.port_net/30000 + R.port_pf*2 - abs(R.port_dd)/3000 + R.posy*.08
R=R.sort_values('score',ascending=False);R.to_csv('/mnt/data/S3_B_QUALITY_FINE_RESULTS.csv',index=False);print('rows',len(R));print(R.head(30).to_string(index=False))

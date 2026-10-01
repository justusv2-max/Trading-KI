import numpy as np,pandas as pd, hashlib, json
from numba import njit
D=np.load('/mnt/data/S3_FEATURE_CACHE.npz');o,h,l,c,atr,pmom,bh,bd,yr,nt,body,ts=[D[k] for k in ['o','h','l','c','atr','pmom','bh','bd','year','nontrend','body','ts']]
@njit
def run(o,h,l,bh,bd,ix,di,sl,tp):
 p=np.empty(len(ix)); en=np.empty(len(ix),np.int64); n=0; last=-1
 for z in range(len(ix)):
  e=ix[z]+1
  if e>=len(o) or e<=last or bh[e]>=20: continue
  ep=o[e];st=ep-di[z]*sl*.01;tg=ep+di[z]*tp*.01
  for j in range(e,len(o)):
   if bd[j]!=bd[e] or bh[j]>=20:xp=o[j]
   elif (di[z]==1 and l[j]<=st) or (di[z]==-1 and h[j]>=st):xp=st
   elif (di[z]==1 and h[j]>=tg) or (di[z]==-1 and l[j]<=tg):xp=tg
   else:continue
   p[n]=di[z]*(xp-ep)*1000-7.2;en[n]=e;n+=1;last=j;break
 return p[:n],en[:n]
def mk(lb,thr,br,lo,hi,mode,sl,tp,name):
 mx=(pd.Series(c).shift(1)-pd.Series(c).shift(1+lb)).to_numpy()*100
 sig=np.where((mx>=thr)&(c>o)&(body>=br),1,np.where((mx<=-thr)&(c<o)&(body>=br),-1,0))
 mm=np.ones(len(o),bool) if mode=='ANY' else np.abs(pmom)<30
 ix=np.flatnonzero(nt&(atr>lo)&(atr<=hi)&mm&(bh>=10)&(bh<20)&(sig!=0)).astype(np.int64);di=sig[ix].astype(np.int64)
 p,en=run(o,h,l,bh,bd,ix,di,sl,tp); t=pd.to_datetime(ts[en],unit='m');return pd.DataFrame({'entry_time_ny':t,'pnl_net':p,'setup':name})
def mkD():
 mx=(pd.Series(c).shift(1)-pd.Series(c).shift(5)).to_numpy()*100; sig=np.where((mx>=20)&(c>o)&(body>=.8),1,np.where((mx<=-20)&(c<o)&(body>=.8),-1,0));mm=((sig==1)&(pmom>=60))|((sig==-1)&(pmom<=-60));ix=np.flatnonzero(nt&(atr>400)&mm&(bh>=10)&(bh<20)&(sig!=0)).astype(np.int64);di=sig[ix].astype(np.int64);p,en=run(o,h,l,bh,bd,ix,di,140,45);return pd.DataFrame({'entry_time_ny':pd.to_datetime(ts[en],unit='m'),'pnl_net':p,'setup':'D'})
def load(path,name):
 q=pd.read_csv(path);q['entry_time_ny']=pd.to_datetime(q.entry_time_ny);return q[['entry_time_ny','pnl_net']].assign(setup=name)
def metrics(df):
 d=df.assign(date=df.entry_time_ny.dt.date).groupby('date').pnl_net.sum().sort_index();eq=d.cumsum();dd=(eq-eq.cummax().clip(lower=0)).min(); y=df.assign(year=df.entry_time_ny.dt.year).groupby('year').pnl_net.sum();gp=df.loc[df.pnl_net>0,'pnl_net'].sum();gl=-df.loc[df.pnl_net<0,'pnl_net'].sum();return {'n':len(df),'net':df.pnl_net.sum(),'pf':gp/gl,'daily_dd':dd,'worst_day':d.min(),'pos_years':int((y>0).sum()),'years':len(y)}
A=load('/mnt/data/S3_MASTER_A_LV_CONT_GOLDEN_TRADES.csv','A');C=load('/mnt/data/S3_MASTER_C_HV200_FADE_GOLDEN_TRADES.csv','C');Dd=mkD();
Bs=[mk(8,10,.3,150,200,'ANY',100,30,'B_FREQ'),mk(6,12,.5,150,200,'WEAK',80,25,'B_QUAL'),mk(8,12,.4,150,200,'ANY',100,30,'B_OLD')]
base=pd.concat([A,C,Dd]);out=[]
for B in Bs:
 print(B.setup.iloc[0],metrics(B));print('PORT',metrics(pd.concat([base,B])));out.append(B)
Dd.to_csv('/mnt/data/S3_D_EXTREME_HV_GOLDEN_TRADES.csv',index=False)
for B in out:B.to_csv('/mnt/data/'+B.setup.iloc[0]+'_TRADES.csv',index=False)
print('BASE ACD',metrics(base))

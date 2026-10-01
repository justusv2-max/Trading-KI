# Rebuild S3 A+C-only master from raw CL-3.txt + CL-4(6).txt.
# Source algorithms frozen from s3_nontrend_discovery.py / candidate freeze scripts.
import pandas as pd, numpy as np, hashlib, json
from numba import njit
ROOT='/mnt/data'; M1=ROOT+'/CL-3.txt'; M5=ROOT+'/CL-4(6).txt'; FEE=7.20
# --- completed PW/PM 70% TPO VA from 09:00-15:00 ET M30 buckets ---
x=pd.read_csv(M5,header=None,names=['d','t','o','h','l','c','v']); dt=pd.to_datetime(x.d+' '+x.t,format='%m/%d/%Y %H:%M'); m=(dt>='2015-01-01')&(dt<'2027-01-01'); x=x[m].reset_index(drop=True); dt=dt[m].reset_index(drop=True); ny5=pd.DatetimeIndex(dt)
z=x.copy(); z['dt']=ny5; z['hour']=ny5.hour; z=z[(z.hour>=9)&(z.hour<15)].copy(); z['bucket']=z.dt.dt.floor('30min'); m30=z.groupby('bucket').agg(h=('h','max'),l=('l','min')).reset_index(); m30['week']=m30.bucket.dt.to_period('W-SUN'); m30['month']=m30.bucket.dt.to_period('M')
def va(g):
 lo=int(np.floor(g.l.min()*100+1e-6)); hi=int(np.ceil(g.h.max()*100-1e-6)); diff=np.zeros(hi-lo+2,dtype=np.int32)
 for a,b in zip(g.l,g.h):
  ia=int(round(a*100))-lo; ib=int(round(b*100))-lo; diff[ia]+=1; diff[ib+1]-=1
 cnt=np.cumsum(diff[:-1]); poc=int(np.argmax(cnt)); target=.70*cnt.sum(); s=cnt[poc]; L=R=poc
 while s<target and (L>0 or R<len(cnt)-1):
  lv=cnt[L-1] if L>0 else -1; rv=cnt[R+1] if R<len(cnt)-1 else -1
  if rv>lv: R+=1; s+=cnt[R]
  else: L-=1; s+=cnt[L]
 return pd.Series({'val':(lo+L)/100,'vah':(lo+R)/100})
wva=m30.groupby('week').apply(va,include_groups=False); mva=m30.groupby('month').apply(va,include_groups=False)
D5=pd.DataFrame({'dt':ny5,'o':x.o}); D5['date']=D5.dt.dt.date; D5['hour']=D5.dt.dt.hour; op=D5[D5.hour==9].groupby('date').first().o
rows=[]
for d,oo in op.items():
 ts=pd.Timestamp(d); wk=ts.to_period('W-SUN')-1; mo=ts.to_period('M')-1
 if wk not in wva.index or mo not in mva.index: continue
 W=wva.loc[wk]; M=mva.loc[mo]; ctx='R'
 if oo>W.vah and oo>M.vah: ctx='TB'
 elif oo<W.val and oo<M.val: ctx='TS'
 elif oo>M.vah: ctx='MB'
 elif oo<M.val: ctx='MS'
 elif oo>W.vah: ctx='WB'
 elif oo<W.val: ctx='WS'
 rows.append((d,ctx,oo,W.val,W.vah,M.val,M.vah))
ctxdf=pd.DataFrame(rows,columns=['nydate','ctx','open9','pwval','pwvah','pmval','pmvah']); ctxdf.to_csv(ROOT+'/S3_ABC_MASTER_CONTEXT.csv',index=False)
# --- M1 causal features ---
q=pd.read_csv(M1,header=None,names=['d','t','o','h','l','c','v']); t=pd.to_datetime(q.d+' '+q.t,format='%m/%d/%Y %H:%M'); m=(t>='2016-01-01')&(t<'2027-01-01'); q=q[m].reset_index(drop=True); t=t[m].reset_index(drop=True); ny=pd.DatetimeIndex(t); ber=ny.tz_localize('America/New_York',ambiguous='infer',nonexistent='shift_forward').tz_convert('Europe/Berlin')
o,h,l,c=[q[k].to_numpy(float) for k in ['o','h','l','c']]; bh=ber.hour.to_numpy(); bd=np.array([v.toordinal() for v in ber.date]); sid=(ny-pd.to_timedelta((ny.hour<18).astype(int),unit='D')).date
tmp=pd.DataFrame({'sid':sid,'o':o,'h':h,'l':l,'c':c}).groupby('sid').agg(O=('o','first'),H=('h','max'),L=('l','min'),C=('c','last')); tmp['rng']=(tmp.H-tmp.L)*100; tmp['atr']=tmp.rng.shift(1).rolling(5).mean(); tmp['pmom']=(tmp.C-tmp.O).shift(1)*100
atr=pd.Series(sid).map(tmp.atr).to_numpy(); pmom=pd.Series(sid).map(tmp.pmom).to_numpy(); cm=dict(zip(pd.to_datetime(ctxdf.nydate).dt.date,ctxdf.ctx)); C=np.array([cm.get(d,'NA') for d in ny.date]); nontrend=np.isin(C,['MB','MS','WB','WS','R']) & (ny.hour.to_numpy()>=9); body=np.abs(c-o)/np.maximum(h-l,1e-9)
@njit
def replay(o,h,l,bh,bd,ix,di,SL,TP):
 pn=[]; ents=[]; sigs=[]; last=-1
 for k in range(len(ix)):
  s=ix[k]; e=s+1; d=di[k]
  if e>=len(o) or e<=last or bh[e]>=20: continue
  ep=o[e]; st=ep-d*SL*.01; tg=ep+d*TP*.01
  for j in range(e,len(o)):
   if bd[j]!=bd[e] or bh[j]>=20: xp=o[j]
   elif (d==1 and l[j]<=st) or (d==-1 and h[j]>=st): xp=st
   elif (d==1 and h[j]>=tg) or (d==-1 and l[j]<=tg): xp=tg
   else: continue
   pn.append(d*(xp-ep)*1000-FEE); ents.append(e); sigs.append(s); last=j; break
 return np.array(pn),np.array(ents),np.array(sigs)
def make(name,sig,mask,SL,TP,extra=None):
 ix=np.flatnonzero(mask & (sig!=0)).astype(np.int64); di=sig[ix].astype(np.int64); p,en,si=replay(o,h,l,bh,bd,ix,di,SL,TP)
 out=pd.DataFrame({'signal_time_ny':ny[si],'entry_time_ny':ny[en],'direction':sig[si],'entry':o[en],'pnl_net':p,'year':ny[en].year,'atr5':atr[si],'prev_session_mom':pmom[si]})
 if extra:
  for k,v in extra.items(): out[k]=v[si]
 path=f'{ROOT}/S3_MASTER_{name}_GOLDEN_TRADES.csv'; out.to_csv(path,index=False); return out,path
# A: BO LB6, body>=.8, ATR5 (100,150], both session sides of 09:30 ET.
ph6=pd.Series(h).shift(1).rolling(6).max().to_numpy(); pl6=pd.Series(l).shift(1).rolling(6).min().to_numpy(); sigA=np.where((c>ph6)&(c>o)&(body>=.8),1,np.where((c<pl6)&(c<o)&(body>=.8),-1,0)); base=(nontrend&(atr>100)&(atr<=150)&(bh>=10)&(bh<20)); A,pa=make('A_LV_CONT',sigA,base,140,60)
# B REMOVED: not part of this master. Do not generate or trade it.
# C: HV>200 failed 24-bar break, both session sides of 09:30.
ph24=pd.Series(h).shift(1).rolling(24).max().to_numpy(); pl24=pd.Series(l).shift(1).rolling(24).min().to_numpy(); sigC=np.where((l<=pl24-.05)&(c>pl24)&(c>o),1,np.where((h>=ph24+.05)&(c<ph24)&(c<o),-1,0)); mm=((sigC==1)&(pmom<=-30))|((sigC==-1)&(pmom>=30)); baseC=nontrend&(atr>200)&mm&(bh>=10)&(bh<20)&(body>=.2); Cc,pc=make('C_HV200_FADE',sigC,baseC,100,45)
def stats(d):
 p=d.pnl_net.to_numpy(); eq=np.cumsum(p); peak=np.maximum.accumulate(np.r_[0,eq])[1:]; dd=(eq-peak).min() if len(p) else 0; gp=p[p>0].sum(); gl=-p[p<0].sum(); return {'trades':len(p),'net':float(p.sum()),'pf':float(gp/gl),'wr':float((p>0).mean()),'trade_seq_dd':float(dd),'years':{str(k):float(v) for k,v in d.groupby('year').pnl_net.sum().items()}}
# additive daily A+C research portfolio; each setup has its own no-overlap replay.
ss={}
for nm,d in [('A',A),('C',Cc)]:
 dd=d.copy(); dd['date']=pd.to_datetime(dd.entry_time_ny).dt.date; ss[nm]=dd.groupby('date').pnl_net.sum()
X=pd.concat(ss,axis=1).fillna(0).sort_index(); total=X.sum(axis=1); eq=total.cumsum(); dailydd=float((eq-eq.cummax()).min())
metrics={'master':'S3_AC_ONLY','B_status':'REMOVED_NOT_ACTIVE_SUPERSEDED','A':stats(A),'C':stats(Cc),'portfolio_additive':{'trades_sum':len(A)+len(Cc),'net':float(total.sum()),'daily_close_dd':dailydd,'worst_day':float(total.min()),'active_days':len(total),'correlation':X.corr().to_dict()}}
for path in [pa,pc]: metrics.setdefault('sha256',{})[path.split('/')[-1]]=hashlib.sha256(open(path,'rb').read()).hexdigest()
open(ROOT+'/S3_AC_MASTER_METRICS.json','w').write(json.dumps(metrics,indent=2)); print(json.dumps(metrics,indent=2))

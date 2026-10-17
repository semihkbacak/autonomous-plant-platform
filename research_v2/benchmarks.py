"""Offline chronological calibration screening; never assert OEM calibration."""
from __future__ import annotations
from math import sqrt,isfinite

def chronological_holdout(predicted:list[float], measured:list[float],train_fraction:float=.75)->dict:
    if len(predicted)!=len(measured) or not 8<=len(predicted)<=100000:
        raise ValueError('Need 8..100000 aligned samples')
    if not isinstance(train_fraction,(float,int)) or not .5<=train_fraction<=.9:
        raise ValueError('train_fraction out of range')
    pairs=list(zip(predicted,measured))
    if any(isinstance(v,bool) or not isinstance(v,(float,int)) or not isfinite(v) or v<0 for pair in pairs for v in pair):
        raise ValueError('Nonnegative, finite inputs required')
    split=int(len(pairs)*train_fraction)
    train,test=pairs[:split],pairs[split:]
    denom=sum(p*p for p,m in train)
    scale=sum(p*m for p,m in train)/denom if denom>0 else 0.0
    residuals=[scale*p-m for p,m in test]
    mae=sum(abs(x) for x in residuals)/len(residuals)
    rmse=sqrt(sum(x*x for x in residuals)/len(residuals))
    mean_m=sum(m for _,m in test)/len(test)
    baseline=sum(abs(p-m) for p,m in test)/len(test)
    return {'train_n':len(train),'test_n':len(test),'train_fraction':train_fraction,
            'scale':round(scale,9),'mae_kw':round(mae,9),'rmse_kw':round(rmse,9),
            'bias_kw':round(sum(residuals)/len(residuals),9),
            'baseline_mae_kw':round(baseline,9),
            'nmae_pct':round(100*mae/mean_m,6) if mean_m>0 else None,
            'site_validated':False,'oem_approved':False,'field_control_authorized':False,
            'note':'Chronological holdout on supplied values; provenance not established'}

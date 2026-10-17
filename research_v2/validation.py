"""Measured-vs-modeled quality metrics; measurement provenance remains UNVERIFIED."""
from __future__ import annotations
from math import sqrt, isfinite

def evaluate_pairs(pairs):
    pairs=list(pairs)
    if not pairs: return {'count':0,'status':'INSUFFICIENT_DATA','site_validated':False,'real_control_ready':False}
    for model, measured in pairs:
        if not all(isinstance(v,(float,int)) and not isinstance(v,bool) and isfinite(v) and v>=0 for v in (model,measured)):
            raise ValueError('Invalid modeled or measured power')
    diff=[a-b for a,b in pairs]
    mae=sum(abs(x) for x in diff)/len(diff)
    rmse=sqrt(sum(x*x for x in diff)/len(diff))
    bias=sum(diff)/len(diff)
    observed_mean=sum(x[1] for x in pairs)/len(pairs)
    return {'count':len(pairs),'mae_kw':mae,'rmse_kw':rmse,'bias_kw':bias,
            'normalized_mae':mae/observed_mean if observed_mean>0 else None,
            'status':'METRICS_ONLY_SOURCE_UNVERIFIED',
            'site_validated':False,'real_control_ready':False}

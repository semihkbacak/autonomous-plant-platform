"""Chronological holdout and physical sanity checks, explicitly NO site acceptance."""
from __future__ import annotations
from math import sqrt,isfinite
from statistics import mean


def metrics(predicted,observed):
    if len(predicted)!=len(observed) or not predicted:raise ValueError('Nonempty matched arrays required')
    if any(not isfinite(float(x)) or x<0 for x in [*predicted,*observed]):
        raise ValueError('Invalid measured/model values')
    errors=[p-o for p,o in zip(predicted,observed)]
    return {'count':len(errors),'mae_kw':round(mean(abs(x) for x in errors),6),
            'rmse_kw':round(sqrt(mean(x*x for x in errors)),6),
            'signed_bias_kw':round(mean(errors),6)}


def chronological_holdout(rows,observations,*,plant,source_label):
    """Offline comparison; all metadata are USER DECLARATIONS, not attested."""
    if plant not in ('HES','GES','RES'):raise ValueError('Unknown plant')
    if not isinstance(source_label,str) or len(source_label)<3 or len(source_label)>80:
        raise ValueError('Source label required for transparent provenance')
    expected={x['utc_end']:x['rows'][plant]['power_kw'] for x in rows}
    if len(observations)<10:raise ValueError('At least ten chronological observations required')
    times=[x.get('utc_end') for x in observations]
    if any(not isinstance(t,str) or t not in expected for t in times) or len(set(times))!=len(times) or times!=sorted(times):
        raise ValueError('Chronological unique UTC timestamps must match simulator output')
    if any(x.get('unit')!='kW' or x.get('quality')!='GOOD' for x in observations):
        raise ValueError('Use qualified kW observations only; quality does not prove authenticity')
    actual=[]
    for x in observations:
        v=x.get('power_kw')
        if isinstance(v,bool) or not isinstance(v,(float,int)) or not isfinite(v) or v<0:
            raise ValueError('Invalid observation')
        actual.append(v)
    estimates=[expected[t] for t in times]
    split=int(len(times)*.7)
    if split<5 or len(times)-split<3:raise ValueError('Holdout too short')
    base=sum(estimates[:split] or [1])
    if base<=0:
        scale=1.0
    else:
        scale=max(0.5,min(1.5,sum(actual[:split])/base))
    score=metrics([v*scale for v in estimates[split:]],actual[split:])
    baseline=metrics(estimates[split:],actual[split:])
    return {'scope':'OFFLINE_RESEARCH_NOT_FIELD_VALIDATION',
            'provenance':'UNVERIFIED_USER_SUPPLIED_LABEL','source_label':source_label,'plant':plant,
            'training_count':split,'test_count':len(times)-split,'split':'CHRONOLOGICAL_70_30_NO_TEST_LEAKAGE',
            'calibration_scale':round(scale,5),'holdout_calibrated':score,'holdout_uncalibrated':baseline,
            'site_validated':False,'real_control_authorized':False}


def forecast(history,horizon:int=8):
    """Persistence + exponentially-decaying trend, bounded uncertainty proxy."""
    if type(horizon) is not int or not 1<=horizon<=96:raise ValueError('Invalid forecast horizon')
    if len(history)<4:raise ValueError('Need four historical points')
    result={}
    for plant in ('HES','GES','RES'):
        powers=[row['rows'][plant]['power_kw'] for row in history[-12:]]
        current=powers[-1]
        trend=(powers[-1]-powers[-4])/3
        predictions=[]
        for i in range(1,horizon+1):
            pred=max(0,current+trend*i*.7**i)
            # Deliberately heuristic ± band, NOT statistical prediction interval.
            band=max(0.1,pred*.25+i*.02*max(1,current))
            predictions.append({'offset_slots':i,'estimated_kw':round(pred,4),
                                'lower_heuristic_kw':round(max(0,pred-band),4),
                                'upper_heuristic_kw':round(pred+band,4)})
        result[plant]=predictions
    return {'scope':'SYNTHETIC_DEMO_FORECAST_NOT_MEASURED','method':'DAMPED_TREND_HEURISTIC',
            'uncertainty_type':'HEURISTIC_BAND_NOT_CALIBRATED','forecasts':result}


def scenario_comparison(base_config, alternatives, steps=4):
    """Compare independent deterministic what-if scenarios; no permanent writes."""
    from advanced_v2.engine import ResearchConfig,AdvancedEngine
    if type(steps) is not int or not 1<=steps<=96:raise ValueError('Invalid step limit')
    if not alternatives or len(alternatives)>5:raise ValueError('Expected 1..5 alternatives')
    base=base_config.__dict__
    results=[]
    for alternative in [{'label':'baseline','changes':{}},*alternatives]:
        label=alternative['label']
        changes=alternative['changes']
        if not isinstance(changes,dict):raise ValueError('Invalid scenario overrides')
        allowed={'mppt','weather_mode','shade_profile','solar_fault','wind_fault','hydro_fault','demand_kw','pv_blocks'}
        if not set(changes).issubset(allowed):raise ValueError('Unsafe/unknown scenario field')
        if not isinstance(label,str) or not 1<=len(label)<=48:raise ValueError('Invalid label')
        cfg=ResearchConfig(**{**base,**changes})
        e=AdvancedEngine(cfg)
        served=0.0;shortfall=0.0;curtailment=0.0
        for _ in range(min(steps,cfg.max_steps)):
            row=e.advance()
            served+=row['dispatch']['served_kw']/4
            shortfall+=row['dispatch']['shortfall_kw']/4
            curtailment+=row['dispatch']['curtailment_kw']/4
        results.append({'label':label,'site_label':cfg.site_label,'steps':e.index,
                        'energy_kwh':dict(e.totals),'served_kwh':round(served,4),
                        'shortfall_kwh':round(shortfall,4),'curtailment_kwh':round(curtailment,4)})
    baseline=results[0]['served_kwh']
    for row in results:
        row['delta_served_kwh']=round(row['served_kwh']-baseline,4)
    return {'scope':'SYNTHETIC_SCENARIO_RESEARCH','method':'DETERMINISTIC_COMPARE_SAME_UTC',
            'results':results,'site_validated':False}

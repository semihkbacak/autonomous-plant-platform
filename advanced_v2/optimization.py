"""Exact greedy solution to a bounded linear water-budget allocation model.

The horizon model maximizes weighted served energy with no inter-temporal
ramping/flow/storage constraints except one finite water budget and per-slot
power cap. This is NOT a hydro scheduling tool for actual site operation.
"""
from __future__ import annotations
from math import isfinite


def optimize_water_budget(demand_kw,variable_kw,*,available_water_m3,
                          net_head_m=130.0,turbine_efficiency=0.83,
                          max_hydro_kw=12000,slot_hours=.25,criticality=None):
    n=len(demand_kw)
    if not n or n>96 or len(variable_kw)!=n or (criticality is not None and len(criticality)!=n):
        raise ValueError('Expected matched horizon 1..96 slots')
    if criticality is None:criticality=[1.0]*n
    args=[available_water_m3,net_head_m,turbine_efficiency,max_hydro_kw,slot_hours,
          *demand_kw,*variable_kw,*criticality]
    if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not isfinite(v) for v in args):
        raise ValueError('Non-finite optimization input')
    if (available_water_m3<0 or net_head_m<=0 or not 0<turbine_efficiency<=1 or
        max_hydro_kw<0 or slot_hours<=0 or any(v<0 for v in [*demand_kw,*variable_kw]) or
        any(not 1<=v<=100 for v in criticality)):
        raise ValueError('Unsafe/inconsistent optimization bound')
    # rho*g*h*eta*water / 3.6e6 => kWh
    budget_kwh = 1000*9.81*net_head_m*turbine_efficiency*available_water_m3/3_600_000
    left=budget_kwh
    allocation=[0.0]*n
    # Continuous linear knapsack solution when each slot is divisible and no
    # other coupling or nonlinear cost exists. Prioritize critical deficit.
    for i in sorted(range(n),key=lambda j:(-criticality[j],j)):
        need_kw=max(0,demand_kw[i]-variable_kw[i])
        max_energy=min(need_kw,max_hydro_kw)*slot_hours
        used=min(max_energy,left)
        allocation[i]=used/slot_hours
        left-=used
    served=[]
    for d,v,h in zip(demand_kw,variable_kw,allocation):served.append(min(d,v+h))
    shortfall=sum((d-s)*slot_hours for d,s in zip(demand_kw,served))
    spent=sum(allocation)*slot_hours
    return {'scope':'SYNTHETIC_WATER_BUDGET_RESEARCH_NOT_REAL_DISPATCH',
            'method':'CONTINUOUS_LINEAR_KNAPSACK_WEIGHTED_SERVICE',
            'hydro_schedule_kw':[round(v,5) for v in allocation],
            'total_served_kwh':round(sum(served)*slot_hours,5),
            'unserved_kwh':round(shortfall,5),
            'weighted_service_kwh':round(sum(s*w*slot_hours for s,w in zip(served,criticality)),5),
            'hydro_water_equivalent_m3':round(spent*3_600_000/(1000*9.81*net_head_m*turbine_efficiency),5),
            'hydro_budget_kwh':round(budget_kwh,5),
            'remaining_budget_kwh':round(max(0,left),5),
            'assumptions':['Fixed net head','Fixed efficiency','No ramp or start/stop constraints',
                           'No grid commitments','Water already available after environmental reserve'],
            'site_validated':False,'real_control_authorized':False}

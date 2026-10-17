"""Stages 2-5: synchronized SYNTHETIC physics and decision-support research.

Separate from the previously tested Stage-1 native portfolio; both are exposed
by the same local FastAPI application, but no real OT interface exists.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from math import cos, isfinite, pi, sin
import json

from advanced_v2.physics import SolarPhysics, WindPhysics, HydroPhysics, SCOPE, VERSION, clamp


def canonical(obj):
    return json.dumps(obj,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('utf-8')


def today_weather(index:int,mode:str='NORMAL'):
    """Deterministic synthetic weather, no API/network or real meteorology."""
    hour = (index%96)/4
    day = index//96
    sun = max(0.0, sin(pi * (hour-6)/12)) if 6 <= hour <= 18 else 0.0
    cloud = 0.78+0.15*sin(index*0.13+day*0.4)
    if mode == 'CLOUDY':cloud *= 0.35
    if mode == 'STORM':cloud *= 0.65
    irradiance = clamp(950*sun*cloud,0,1100)
    temperature = 19+10*sin(2*pi*(hour-8)/24)+1.5*sin(day*0.5)
    wind = clamp(8.5+2.7*sin(2*pi*(hour+2)/24)+0.4*cos(day*0.4),0.1,25)
    if mode=='STORM':wind=clamp(wind+9,0,34)
    return {'irradiance_wm2':round(irradiance,3),'air_temp_c':round(temperature,3),
            'wind_ms':round(wind,3),'wind_direction_deg':round(20+15*sin(day*.3+hour*.1),3),
            'inflow_m3s':round(8+1.3*sin(day*.25),3),
            'source':'DETERMINISTIC_SYNTHETIC_WEATHER_NOT_SITE_MEASURED'}


@dataclass(frozen=True)
class ResearchConfig:
    start_utc: str = '2026-01-01T00:00:00+00:00'
    days: int = 2
    demand_kw: float = 2500.0
    pv_blocks: int = 300
    mppt: str = 'INC_COND'
    weather_mode: str = 'NORMAL'
    shade_profile: str = 'NONE'
    solar_fault: str = 'NONE'
    wind_fault: str = 'NONE'
    hydro_fault: str = 'NONE'
    site_label: str = 'SYNTHETIC_LAB'

    def __post_init__(self):
        try:dt=datetime.fromisoformat(self.start_utc.replace('Z','+00:00'))
        except (ValueError,TypeError) as exc:raise ValueError('Invalid UTC start') from exc
        if dt.tzinfo is None or dt.utcoffset()!=timedelta(0) or dt.time().replace(tzinfo=None)!=datetime.min.time():
            raise ValueError('UTC start must be midnight with +00:00/Z offset')
        if type(self.days) is not int or not 1<=self.days<=31:raise ValueError('days must be 1..31')
        if type(self.pv_blocks) is not int or not 1<=self.pv_blocks<=10000:raise ValueError('pv_blocks must be 1..10000')
        if isinstance(self.demand_kw,bool) or not isinstance(self.demand_kw,(int,float)) or not isfinite(self.demand_kw) or not 0<=self.demand_kw<=100_000:
            raise ValueError('Invalid synthetic demand')
        if self.mppt not in ('PO','INC_COND','GLOBAL'):raise ValueError('Unknown MPPT')
        if self.weather_mode not in ('NORMAL','CLOUDY','STORM'):raise ValueError('Unknown weather mode')
        if self.shade_profile not in ('NONE','PARTIAL','HEAVY'):raise ValueError('Unknown shading')
        if self.solar_fault not in ('NONE','GRID_LOSS','INVERTER_TRIP','HOT_INVERTER','STRING_OPEN'):raise ValueError('Invalid GES fault')
        if self.wind_fault not in ('NONE','PITCH_STUCK','YAW_STUCK','BRAKE','HIGH_WIND','GRID_LOSS'):raise ValueError('Invalid RES fault')
        if self.hydro_fault not in ('NONE','NOZZLE_STUCK','LOAD_REJECTION','LOW_RESERVOIR','GRID_LOSS'):raise ValueError('Invalid HES fault')
        if not self.site_label or len(self.site_label)>48 or not all(c.isalnum() or c in '_- ' for c in self.site_label):
            raise ValueError('Invalid synthetic site label')

    @property
    def start(self):return datetime.fromisoformat(self.start_utc.replace('Z','+00:00')).astimezone(timezone.utc)
    @property
    def max_steps(self):return self.days*96


def dispatch(demand_kw, solar_kw, wind_kw, hydro_kw):
    """Energy balance; variable renewable accepted first, hydro follows.

    Synthetic merit-order, no actual reservoir dispatch permissions.
    """
    if any(not isfinite(x) or x < 0 for x in (demand_kw,solar_kw,wind_kw,hydro_kw)):
        raise ValueError('Invalid synthetic dispatch inputs')
    variable=solar_kw+wind_kw
    remaining=max(0.0,demand_kw-variable)
    hydro_used=min(hydro_kw,remaining)
    renew_used=min(variable,demand_kw)
    curtailed=max(0.0,variable-demand_kw)+(hydro_kw-hydro_used)
    shortfall=max(0.0,demand_kw-renew_used-hydro_used)
    return {'demand_kw':round(demand_kw,5),'solar_kw':round(solar_kw,5),
            'wind_kw':round(wind_kw,5),'hydro_kw':round(hydro_used,5),
            'gross_generation_kw':round(variable+hydro_kw,5),
            'served_kw':round(renew_used+hydro_used,5),'curtailment_kw':round(curtailed,5),
            'shortfall_kw':round(shortfall,5),
            'method':'RESEARCH_MERIT_ORDER_NO_GRID_OR_REAL_DISPATCH'}


def empirical_anomaly(power_kw, history, *, min_baseline=8):
    """Robust baseline deviation; not trained/validated industrial ML."""
    if len(history)<min_baseline:
        return {'flag':False,'score':None,'reason':'INSUFFICIENT_BASELINE','method':'ROBUST_MAD_RESEARCH'}
    from statistics import median
    baseline=history[-48:]
    m=median(baseline)
    mad=median(abs(v-m) for v in baseline)
    sigma=max(1.4826*mad, max(1,m)*0.02, 0.1)
    score=abs(power_kw-m)/sigma
    return {'flag':score>4.5,'score':round(score,3),'reason':'ROBUST_DEVIATION' if score>4.5 else 'WITHIN_BASELINE',
            'method':'ROBUST_MAD_RESEARCH_NOT_FAULT_DIAGNOSIS'}


def benchmark_bounds(rows):
    """Independent elementary thermodynamic/Betz ceilings, not OEM evidence."""
    pv=rows['GES'];res=rows['RES'];hydro=rows['HES']
    pv_irr=pv['irradiance_wm2']
    # For each 1 kW research block, simplistic standard irradiance ceiling 1.2 kW.
    pv_upper=1.2*pv['pv_blocks']*pv_irr/1000
    wind_speed=res['wind_ms']
    betz_upper_kw=2*0.5*1.225*3.141592653589793*24**2 * wind_speed**3 * (16/27)/1000
    hydro_upper_kw=1000*9.81*hydro['nozzle_m3s']*hydro['net_head_m']/1000
    return {'solar_within_illustrative_ceiling':pv['power_kw']<=pv_upper+1e-3,
            'wind_within_betz_bound':res['power_kw']<=betz_upper_kw+1e-3,
            'hydro_within_water_power_bound':hydro['power_kw']<=hydro_upper_kw+1e-3,
            'scope':'CONSERVATION_SANITY_CHECK_NOT_FIELD_VALIDATION',
            'bounds_kw':{'GES':round(pv_upper,3),'RES':round(betz_upper_kw,3),'HES':round(hydro_upper_kw,3)}}


class AdvancedEngine:
    def __init__(self,config:ResearchConfig,*,solar=None,wind=None,hydro=None):
        self.config=config
        self.solar=solar or SolarPhysics()
        self.wind=wind or WindPhysics()
        self.hydro=hydro or HydroPhysics()
        self.index=0
        self.totals={name:0.0 for name in ('HES','GES','RES')}
        self.power_history={name:[] for name in ('HES','GES','RES')}
        self.latest=None

    def advance(self):
        if self.index>=self.config.max_steps:raise ValueError('Research run complete')
        start=self.config.start+timedelta(seconds=self.index*900)
        weather=today_weather(self.index,self.config.weather_mode)
        if self.config.shade_profile=='PARTIAL':shade=((1.0,.35,1.0),(1.0,.75,1.0))
        elif self.config.shade_profile=='HEAVY':shade=((.2,1,.2),(1,.1,1))
        else:shade=((1.,1.,1.),(1.,1.,1.))
        solar=self.solar.advance(weather['irradiance_wm2'],weather['air_temp_c'],shade,
                                 self.config.mppt,self.config.solar_fault)
        solar['pv_blocks']=self.config.pv_blocks
        solar['block_kw']=solar['power_kw']
        solar['power_kw']=round(solar['power_kw']*self.config.pv_blocks,6)
        solar['energy_kwh']=round(solar['energy_kwh']*self.config.pv_blocks,6)
        wind=self.wind.advance(self.index,weather['wind_ms'],weather['wind_direction_deg'],self.config.wind_fault)
        # Hydro accepts residual scheduled demand after variable renewables.
        planned_hydro=max(0,self.config.demand_kw-solar['power_kw']-wind['power_kw'])
        hydro=self.hydro.advance(planned_hydro,weather['inflow_m3s'],self.config.hydro_fault)
        rows={'HES':hydro,'GES':solar,'RES':wind}
        for r in rows.values():
            if not isfinite(r['power_kw']) or r['power_kw']<0 or not isfinite(r['energy_kwh']) or r['energy_kwh']<0:
                raise ValueError('Invalid research physics result')
        decision=dispatch(self.config.demand_kw,solar['power_kw'],wind['power_kw'],hydro['power_kw'])
        bounds=benchmark_bounds(rows)
        anomalies={name:empirical_anomaly(rows[name]['power_kw'],self.power_history[name]) for name in rows}
        for name,r in rows.items():
            self.totals[name]=round(self.totals[name]+r['energy_kwh'],7)
            self.power_history[name].append(r['power_kw'])
            self.power_history[name]=self.power_history[name][-48:]
        result={'index':self.index,'utc_start':start.isoformat(),'utc_end':(start+timedelta(seconds=900)).isoformat(),
                'site_label':self.config.site_label,'weather':weather,'rows':rows,
                'dispatch':decision,'independent_bounds':bounds,'anomalies':anomalies,
                'cumulative_kwh':dict(self.totals),'scope':SCOPE,'model_revision':VERSION}
        self.latest=result
        self.index+=1
        return result

    def snapshot(self):
        data={'version':VERSION,'scope':SCOPE,'config':asdict(self.config),'index':self.index,
              'solar':self.solar.checkpoint(),'wind':self.wind.checkpoint(),
              'hydro':self.hydro.checkpoint(),'totals':self.totals,
              'power_history':self.power_history,'latest':self.latest}
        digest=sha256(canonical(data)).hexdigest()
        return canonical({'payload':data,'sha256':digest})

    @classmethod
    def recover(cls,raw):
        if not raw or len(raw)>500_000:raise ValueError('Missing/oversized research snapshot')
        try:
            obj=json.loads(raw)
            doc=obj['payload']
            if sha256(canonical(doc)).hexdigest()!=obj['sha256'] or doc['version']!=VERSION or doc['scope']!=SCOPE:
                raise ValueError('Research checkpoint hash/version mismatch')
            engine=cls(ResearchConfig(**doc['config']),solar=SolarPhysics.recover(doc['solar']),
                       wind=WindPhysics.recover(doc['wind']),hydro=HydroPhysics.recover(doc['hydro']))
            engine.index=doc['index']
            if type(engine.index) is not int or not 0<=engine.index<=engine.config.max_steps:raise ValueError('Bad slot')
            engine.totals=doc['totals']
            engine.power_history=doc['power_history']
            engine.latest=doc['latest']
            if set(engine.totals)!=set(('HES','GES','RES')):raise ValueError('Bad totals')
            for item in engine.totals.values():
                if not isfinite(item) or item<0:raise ValueError('Bad saved energy')
            return engine
        except (KeyError,TypeError,IndexError,ValueError,UnicodeError) as exc:
            raise ValueError('Cannot recover corrupt/incompatible research checkpoint') from exc

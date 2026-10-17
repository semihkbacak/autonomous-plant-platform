"""Offline research V2 regression; no field equipment used."""
import sqlite3
from pathlib import Path
import pytest
from research_v2.workspace import ResearchStore,comparison,parse_utc
from research_v2.validation import evaluate_pairs
from research_v2.physics import hydro_ideal_kw,pv_ideal_kw,wind_ideal_kw

def test_utc_rejects_naive():
    with pytest.raises(ValueError):parse_utc('2026-10-16T10:00:00')
    assert parse_utc('2026-10-16T13:00:00+03:00').hour==10

def test_persistence_and_energy(tmp_path):
    path=tmp_path/'store.sqlite3'; s=ResearchStore(path)
    s.create('s1','site_1','GES','NORMAL','2026-01-01T00:00:00Z',900)
    s.add('s1',0,200);s.add('s1',1,400)
    data=ResearchStore(path).get('s1')
    assert data['total_energy_kwh']==150
    assert data['samples'][1]['utc']=='2026-01-01T00:15:00+00:00'
    assert '150.0' not in ResearchStore(path).export_csv('s1') # export includes interval values, not sum

def test_validation_metrics_and_no_site_approval(tmp_path):
    s=ResearchStore(tmp_path/'db.sqlite3');s.create('a','site','HES','N','2026-01-01T00:00:00Z')
    s.add('a',0,100);s.add('a',1,120)
    s.measurements('a',[{'step_index':0,'measured_kw':90},{'step_index':1,'measured_kw':110}])
    report=s.evaluation('a'); assert report['mae_kw']==10
    assert report['site_validated'] is False and report['real_control_ready'] is False

def test_reject_bad_sessions(tmp_path):
    s=ResearchStore(tmp_path/'db.sqlite3')
    with pytest.raises(ValueError):s.create('../bad','site','GES','N','2026-01-01T00:00:00Z')
    with pytest.raises(ValueError):s.create('good','site','WATER','N','2026-01-01T00:00:00Z')
    s.create('good','site','RES','N','2026-01-01T00:00:00Z')
    with pytest.raises(ValueError):s.add('good',1,30)
    with pytest.raises(ValueError):s.add('good',0,-1)

def test_comparison(tmp_path):
    s=ResearchStore(tmp_path/'db.sqlite3')
    for label in ['one','two']:
        s.create(label,'farm','RES','N','2026-01-01T00:00:00Z')
        s.add(label,0,10)
    assert len(comparison(s,['one','two']))==2
    with pytest.raises(ValueError):comparison(s,['one','one'])

def test_screening_physics():
    assert abs(hydro_ideal_kw(1,10,1)-98.1)<1e-10
    assert pv_ideal_kw(10,1000,.2)==2
    assert wind_ideal_kw(1.2,10,10,.4)>0
    with pytest.raises(ValueError):wind_ideal_kw(1.2,10,10,.8)

def test_empty_measurement_not_validated(tmp_path):
    s=ResearchStore(tmp_path/'db.sqlite3');s.create('e','site','GES','N','2026-01-01T00:00:00Z')
    assert s.evaluation('e')['site_validated'] is False

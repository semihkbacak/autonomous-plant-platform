"""RC4 offline persistence and release-safety test suite; not a field certificate."""
from __future__ import annotations
from dataclasses import replace
import hashlib
from pathlib import Path
import pytest
from research_v2.workspace import ResearchStore
from research_v2.engine import ScreeningConfig, run_into_store


def test_resuming_screening_rejects_changed_physics_after_restart(tmp_path):
    db = tmp_path / 'research.sqlite3'
    st = ResearchStore(db)
    cfg = ScreeningConfig('2026-01-01T00:00:00Z', days=2, ges_area_m2=300)
    st.create('plant_1','site_1','GES','NORMAL',cfg.start_utc,cfg.step_s)
    assert len(run_into_store(st,'plant_1',cfg,limit=3)['samples']) == 3
    reopened = ResearchStore(db)
    with pytest.raises(ValueError,match='configuration changed'):
        run_into_store(reopened,'plant_1',replace(cfg,ges_area_m2=400),limit=1)
    assert len(reopened.get('plant_1')['samples'])==3
    assert len(run_into_store(reopened,'plant_1',cfg,limit=2)['samples'])==5
    with pytest.raises(ValueError,match='configuration changed'):
        run_into_store(reopened,'plant_1',replace(cfg,days=3),limit=1)


def test_existing_manual_session_cannot_falsely_bind_screening(tmp_path):
    st=ResearchStore(tmp_path/'research.sqlite3')
    c=ScreeningConfig('2026-01-01T00:00:00Z')
    st.create('legacy','site','RES','N',c.start_utc,c.step_s)
    st.add('legacy',0,5)
    with pytest.raises(ValueError, match='untracked samples'):
        run_into_store(st,'legacy',c,limit=3)


def test_verified_backup_restore_and_refuse_overwrite(tmp_path):
    st=ResearchStore(tmp_path/'primary.sqlite3')
    c=ScreeningConfig('2026-01-01T00:00:00Z')
    st.create('session','site','HES','NORMAL',c.start_utc,c.step_s)
    run_into_store(st,'session',c,limit=4)
    state=st.get('session')
    report=st.backup_verified(tmp_path/'backup.sqlite3')
    assert report['sqlite_integrity']=='ok'
    assert report['sha256']==hashlib.sha256((tmp_path/'backup.sqlite3').read_bytes()).hexdigest()
    restored=ResearchStore.restore_verified(tmp_path/'backup.sqlite3',tmp_path/'restored.sqlite3',report['sha256'])
    assert restored.get('session')['samples']==state['samples']
    assert len(run_into_store(restored,'session',c,limit=2)['samples'])==6
    with pytest.raises(FileExistsError):st.backup_verified(tmp_path/'backup.sqlite3')
    with pytest.raises(ValueError):ResearchStore.restore_verified(tmp_path/'backup.sqlite3',tmp_path/'bad.sqlite3','0'*64)
    assert not (tmp_path/'bad.sqlite3').exists()
    with pytest.raises(ValueError):ResearchStore.restore_verified(tmp_path/'backup.sqlite3',tmp_path/'restored.sqlite3',report['sha256'])


def test_backup_refuses_overwrite_primary_or_arbitrary_file(tmp_path):
    original=tmp_path/'db.sqlite3';st=ResearchStore(original)
    with pytest.raises(ValueError):st.backup_verified(original)
    with pytest.raises(ValueError):st.backup_verified(tmp_path/'random.pdf')


def test_release_workflow_requires_native_exe_smoke_and_never_automatically_publishes():
    path=Path(__file__).resolve().parents[1]/'.github/workflows/research-v20-windows-bundle.yml'
    text=path.read_text(encoding='utf-8')
    assert 'workflow_dispatch:' in text
    assert 'AutonomousPlantSimulatorV20_FIX11.exe' in text
    assert '--smoke-server' in text
    assert '--self-test' in text
    assert 'attestations: write' in text
    assert 'actions/attest@' in text
    assert 'actions/upload-artifact@' in text
    assert 'gh release create' not in text


def test_hydro_simulator_full_mutable_checkpoint_roundtrip(tmp_path):
    from simulator.hydro import HydroPlantSimulator
    from simulator.hydro_checkpoint import encode_checkpoint, decode_checkpoint, save_checkpoint, load_checkpoint
    one=HydroPlantSimulator();one.set_auto_tick(False)
    one.request_start('UNIT_1')
    for _ in range(9):one.tick()
    raw=encode_checkpoint(one)
    two=decode_checkpoint(raw)
    assert two.snapshot().model_dump(mode='json')==one.snapshot().model_dump(mode='json')
    assert two.auto_tick_enabled==one.auto_tick_enabled
    for _ in range(50):
        one.tick();two.tick()
        assert two.snapshot().model_dump(mode='json')==one.snapshot().model_dump(mode='json')
    recorded=save_checkpoint(two,tmp_path/'hes.json')
    three=load_checkpoint(tmp_path/'hes.json',recorded['sha256'])
    assert three.snapshot().model_dump(mode='json')==two.snapshot().model_dump(mode='json')
    with pytest.raises(FileExistsError):save_checkpoint(three,tmp_path/'hes.json')
    tampered=raw.replace(b'LOCAL_SYNTHETIC_HES_NO_OT',b'LOCAL_SYNTHETIC_HES_NO_XT')
    with pytest.raises(ValueError):decode_checkpoint(tampered)


def test_sbom_has_components_without_fabricated_license_approvals():
    from scripts.sbom_v20 import document
    d=document()
    assert d['bomFormat']=='CycloneDX' and d['specVersion']=='1.6'
    assert d['components']
    assert all(x['properties'][0]['value']=='NOT_VERIFIED' for x in d['components'])


def test_security_workflow_is_real_online_audit_not_invented_results():
    w=(Path(__file__).resolve().parents[1]/'.github/workflows/research-v20-security.yml').read_text(encoding='utf-8')
    assert 'pip_audit' in w and 'pip freeze' in w and 'scripts/sbom_v20.py' in w
    assert 'if: always()' in w

@pytest.mark.parametrize('cls,scenarios',[('res',['NORMAL','WAKE','LOW_WIND','CURTAIL_50']),('ges',['NORMAL','LOW_LIGHT','GRID_LOSS','CURTAIL_50'])])
def test_resumable_full_ges_res_simulator_replay(cls,scenarios):
    from app.sim_runtime import SolarSession,WindSession
    import json
    klass={'ges':SolarSession,'res':WindSession}[cls]
    sim=klass()
    for mode in scenarios:
        sim.configure(mode)
        sim.step()
    sim.start()
    raw=sim.export_replay()
    revived=klass.import_replay(raw)
    assert revived.status()==sim.status()
    assert revived._replay_trace==sim._replay_trace
    for _ in range(2):
        sim.step();revived.step()
        assert sim.status()==revived.status()
    fake=json.loads(raw)
    fake['payload']['trace'][0]['mode']='GRID_LOSS'
    with pytest.raises(ValueError):klass.import_replay(json.dumps(fake).encode())
    other={'ges':WindSession,'res':SolarSession}[cls]
    with pytest.raises(ValueError):other.import_replay(raw)


def test_paused_hes_ges_res_joint_checkpoint(tmp_path):
    from simulator.hydro import HydroPlantSimulator
    from app.sim_runtime import SimulatorSessions
    from simulator.portfolio_checkpoint import save_portfolio,load_portfolio,pack_portfolio
    hydro=HydroPlantSimulator();hydro.set_auto_tick(False)
    hydro.request_start('UNIT_1')
    for _ in range(8):hydro.tick()
    s=SimulatorSessions()
    s.ges.configure('LOW_LIGHT');s.res.configure('WAKE')
    for _ in range(4):s.ges.step();s.res.step()
    report=save_portfolio(tmp_path/'portfolio.json',hydro,s)
    h2,s2=load_portfolio(tmp_path/'portfolio.json',report['sha256'])
    assert h2.snapshot().model_dump(mode='json')==hydro.snapshot().model_dump(mode='json')
    assert s2.ges.status()==s.ges.status() and s2.res.status()==s.res.status()
    hydro.tick();h2.tick()
    assert h2.snapshot().model_dump(mode='json')==hydro.snapshot().model_dump(mode='json')
    s.ges.step();s2.ges.step();s.res.step();s2.res.step()
    assert s.ges.status()==s2.ges.status() and s.res.status()==s2.res.status()
    s.ges.start()
    with pytest.raises(ValueError,match='pause'):
        pack_portfolio(hydro,s)

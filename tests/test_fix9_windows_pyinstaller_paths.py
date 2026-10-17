"""Regression for FIX8's Windows relative --add-data path failure."""
from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[1]


def test_windows_builder_uses_absolute_sources_with_specpath():
    ps=(ROOT/'desktop/build_full_windows_v20.ps1').read_text(encoding='utf-8')
    assert "'--specpath',(Join-Path $root '.build_full_v20')" in ps
    for path_var,src,dst in (("staticSrc",r"app\static","app/static"),
                             ("modelsSrc","models","models"),
                             ("solarSrc",r"data\solar","data/solar")):
        assert f"${path_var} = Join-Path $root '{src}'" in ps
        assert f"'--add-data',(${path_var} + ';{dst}')" in ps
        assert f"'--add-data','{dst};{dst}'" not in ps
    assert 'Missing EXE build input:' in ps
    assert '$entrySrc' in ps


def test_github_windows_build_reproduces_isolated_specdir():
    ci=(ROOT/'.github/workflows/research-v20-windows-bundle.yml').read_text(encoding='utf-8')
    assert '--specpath "$root/.build_full_v20"' in ci
    for source,dst in (('static','app/static'),('models','models'),('solar','data/solar')):
        assert f'$'+source+' = (Resolve-Path ' in ci
        assert f'--add-data "${source};{dst}"' in ci
    assert 'AutonomousPlantSimulatorV20_FIX11' in ci


def test_builder_launcher_and_ci_versions_match():
    cmd=(ROOT/'06_WINDOWS_TAM_EXE_DERLE.cmd').read_text(encoding='utf-8')
    ps=(ROOT/'desktop/build_full_windows_v20.ps1').read_text(encoding='utf-8')
    ci=(ROOT/'.github/workflows/research-v20-windows-bundle.yml').read_text(encoding='utf-8')
    assert 'AutonomousPlantSimulatorV20_FIX11.exe' in cmd
    assert 'AutonomousPlantSimulatorV20_FIX11.exe' in ps
    assert 'AutonomousPlantSimulatorV20_FIX11.exe' in ci

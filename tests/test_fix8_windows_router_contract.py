"""FIX8: EXE self-test must validate live ASGI responses, not route internals."""
from pathlib import Path
from desktop.full_simulator_launcher import self_test


def test_self_test_uses_http_asgi_not_route_path_reflection():
    source = (Path(__file__).resolve().parents[1] / 'desktop/full_simulator_launcher.py').read_text(encoding='utf-8')
    target = source.split('def self_test():', 1)[1].split('def smoke_server():', 1)[0]
    assert 'with TestClient(probe_app) as client:' in target
    assert 'route.path' not in target
    assert 'SYNTHETIC_IN_MEMORY_NO_OT' in target
    assert 'SYNTHETIC_LOCAL_SIMULATION_NOT_A_REAL_TIME_SITE_TWIN' in target


def test_fix8_desktop_self_test_proves_live_http_routes():
    result = self_test()
    assert result['status'] == 'PASS'
    assert result['solar_twin'] == 'PASS'
    assert result['wind_twin'] == 'PASS'
    assert result['physical_control'] is False

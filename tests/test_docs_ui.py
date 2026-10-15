"""Read-only documentation portal checks, independent of the plant models."""
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.docs_ui import create_docs_router


def build_app():
    app = FastAPI(docs_url=None, title='Plant Simulator API')

    @app.get('/api/v1/plant', tags=['HES'])
    def plant():
        return {'power_mw': 5}

    @app.post('/api/v1/units/{unit_id}/start', tags=['HES'])
    def start(unit_id: str):
        return {'unit_id': unit_id}

    @app.get('/api/v1/wind/runs', tags=['RES'])
    def wind_runs():
        return []

    app.include_router(create_docs_router())
    return app


def test_modern_docs_page_and_navigation():
    r = TestClient(build_app()).get('/docs')
    assert r.status_code == 200
    for expected in ('Developer Center', 'Enerji santralleri',
                     'id="search"', 'id="results"',
                     '/openapi.json', '/docs/swagger'):
        assert expected in r.text


def test_rendered_portal_never_submits_control_requests():
    r = TestClient(build_app()).get('/docs')
    assert 'fetch(\'/openapi.json\'' in r.text
    assert 'supportedSubmitMethods' not in r.text
    assert 'Bu dokümantasyon ekranı kontrol komutu göndermez' in r.text
    assert 'fetch(curl)' not in r.text


def test_swagger_reference_read_only_try_it_out():
    r = TestClient(build_app()).get('/docs/swagger')
    assert r.status_code == 200
    assert 'supportedSubmitMethods' in r.text
    assert '[]' in r.text


def test_openapi_preserves_existing_endpoints():
    app = build_app()
    c = TestClient(app)
    spec = c.get('/openapi.json').json()
    assert '/api/v1/units/{unit_id}/start' in spec['paths']
    assert '/api/v1/wind/runs' in spec['paths']
    assert '/docs' not in spec['paths']
    assert c.get('/api/v1/plant').json() == {'power_mw': 5}


def test_openapi_docs_customization_adds_no_authentication():
    # Security note: changing the docs UI is cosmetic, not an access control.
    client = TestClient(build_app())
    assert client.post('/api/v1/units/UNIT_1/start').status_code == 200

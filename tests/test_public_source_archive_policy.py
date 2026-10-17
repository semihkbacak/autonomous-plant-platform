"""Public-source distribution excludes the private OEM research archive."""
from pathlib import Path
import json
import importlib.util

ROOT = Path(__file__).resolve().parents[1]


def test_private_archive_not_packaged_or_required():
    assert not (ROOT / 'ges_oem_research.zip').exists()
    manifest = json.loads((ROOT / 'WINDOWS_PACKAGE_MANIFEST.json').read_text(encoding='utf-8'))
    assert 'ges_oem_research.zip' not in manifest['required_fixtures_sha256']
    assert 'ges_oem_research.zip' not in manifest['release_fixture_allowlist']
    assert '!ges_oem_research.zip' not in (ROOT / '.gitignore').read_text(encoding='utf-8')


def test_windows_required_public_fixtures_pass():
    spec = importlib.util.spec_from_file_location('windows_stable_check', ROOT / 'windows/windows_start.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert 'ges_oem_research.zip' not in module.REQUIRED_FILES
    module.verify_files()


def test_apache_notice_and_limitations():
    lic = (ROOT / 'LICENSE').read_text(encoding='utf-8')
    assert 'Apache License' in lic and 'Version 2.0, January 2004' in lic
    assert 'APPENDIX: How to apply the Apache License to your work.' in lic
    assert 'Copyright 2026' in (ROOT / 'NOTICE').read_text(encoding='utf-8')
    assert 'v1.5.0' in (ROOT / 'docs/STABLE_PROMOTION_CHECKLIST_TR.md').read_text(encoding='utf-8')

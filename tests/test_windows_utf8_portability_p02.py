"""Regression: Windows cp1254 locale must not control source-code decoding."""
from __future__ import annotations

import ast
import codecs
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _missing_utf8_calls(source: str) -> list[int]:
    """Find source-reader calls that silently inherit the Windows ANSI code page."""
    tree = ast.parse(source)
    failures = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr == 'read_text' and not any(k.arg == 'encoding' for k in node.keywords):
            failures.append(node.lineno)
    return failures


def test_cp1254_failure_repro_and_explicit_utf8_resolution():
    # A deterministic UTF-8 source fixture (Ğ == bytes C4 9E) reproduces cp1254.
    # Do not depend on an incidental byte offset in app/main.py.
    raw = ('Ğ' + (ROOT / 'app/main.py').read_text(encoding='utf-8')).encode('utf-8')
    assert b'\x9e' in raw
    try:
        codecs.decode(raw, 'cp1254')
    except UnicodeDecodeError:
        pass
    else:
        raise AssertionError('Expected the reproduced Windows cp1254 decode failure')
    decoded = raw.decode('utf-8')
    assert 'create_stage1_router' in decoded
    assert 'create_advanced_router' in decoded


def test_tests_never_use_implicit_locale_when_reading_source():
    violations = {}
    for path in (ROOT / 'tests').glob('test_*.py'):
        missing = _missing_utf8_calls(path.read_text(encoding='utf-8'))
        if missing:
            violations[path.name] = missing
    assert not violations, f'Use read_text(encoding="utf-8") explicitly: {violations}'


def test_guard_detects_reintroduction():
    assert _missing_utf8_calls("p.read_text()\np.read_text(encoding='utf-8')") == [1]


def test_windows_runner_sets_file_encoding_not_just_console_encoding():
    source = (ROOT / 'windows/windows_start.py').read_text(encoding='utf-8')
    assert "child_env['PYTHONUTF8'] = '1'" in source
    assert "child_env['PYTHONIOENCODING'] = 'utf-8'" in source
    for batch in ('10_WINDOWS_ASAMA2_5_TEST.cmd', '13_WINDOWS_DISPATCH_KABUL.cmd'):
        assert 'PYTHONUTF8=1' in (ROOT / batch).read_text(encoding='utf-8')

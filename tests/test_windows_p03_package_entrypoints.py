"""Cross-platform regression for the complete Windows package and launchers.

Does not claim to execute Windows batch files on Linux.
"""
from pathlib import Path
import ast
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]


def _source(path):
    return (ROOT / path).read_text(encoding='utf-8')


def test_p03_complete_project_file_layout():
    required = ('APP_VERSION_P03.txt', 'START_HERE_WINDOWS.cmd',
                'tools/windows_prepare_env.cmd', 'windows/windows_start.py',
                'app/main.py', 'stage1/controller.py', 'advanced_v2/api.py',
                'desktop/full_simulator_launcher.py',
                'tests/test_stage1_three_plant_sync.py',
                'tests/test_stages_2_to_5_advanced.py',
                'requirements-windows.txt')
    assert all((ROOT/x).is_file() for x in required)


def test_utf8_portable_assertions_never_inherit_cp1254():
    for name in ('tests/test_stage1_three_plant_sync.py',
                 'tests/test_stages_2_to_5_advanced.py'):
        tree=ast.parse(_source(name))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr=='read_text':
                assert any(k.arg=='encoding' and isinstance(k.value, ast.Constant) and k.value.value=='utf-8'
                           for k in node.keywords), (name, node.lineno)


def test_all_primary_windows_entrypoints_have_utf8_mode_and_bootstrap():
    for name in ('10_WINDOWS_ASAMA2_5_TEST.cmd', '11_WINDOWS_ASAMA2_5_AC.cmd',
                 '13_WINDOWS_DISPATCH_KABUL.cmd', '14_WINDOWS_P02_KODLAMA_TEST.cmd'):
        text=_source(name).casefold()
        assert 'call "tools\\windows_prepare_env.cmd"'.casefold() in text
        assert 'pythonutf8=1' in text
        assert 'errorlevel 1' in text
    assert ':SETUP\ncall "01_WINDOWS_KUR_TEST_VE_BASLAT.cmd"' in _source('00_WINDOWS_BASLAT.cmd').replace('\r\n', '\n')
    assert 'START_HERE_WINDOWS.cmd' in _source('README.md')
    assert 'APP_VERSION_P03.txt' in _source('START_HERE_WINDOWS.cmd')
    assert '10_WINDOWS_ASAMA2_5_TEST.cmd' in _source('START_HERE_WINDOWS.cmd')


def test_bootstrap_is_separate_from_tests_and_gui():
    code=_source('windows/windows_start.py')
    assert "parser.add_argument('--setup-only'" in code
    assert 'if args.setup_only:' in code
    assert 'verify_complete_project()' in code
    assert 'sys.version_info[:2]' in _source('tools/windows_prepare_env.cmd')


def test_preflight_detects_a_missing_directory_without_writing(tmp_path):
    sys.path.insert(0,str(ROOT))
    try:
        from windows import windows_start
        with patch.object(windows_start,'ROOT',tmp_path):
            try:
                windows_start.verify_complete_project()
            except RuntimeError as exc:
                assert 'Incomplete P03 project' in str(exc)
                assert 'app/main.py' in str(exc)
            else:
                raise AssertionError('Missing project layout was silently accepted')
    finally:
        sys.path.remove(str(ROOT))


def test_windows_cmd_files_are_ascii_safe_without_control_characters():
    # Reject accidental Python-string escapes such as backslash-a/t/r in .cmd assets.
    for path in ROOT.glob('*.cmd'):
        data=path.read_bytes()
        assert not [b for b in data if b < 32 and b not in (9,10,13)], path.name
    data=(ROOT/'tools/windows_prepare_env.cmd').read_bytes()
    assert not [b for b in data if b < 32 and b not in (9,10,13)]
    assert b'advanced_v2\\api.py' in data
    assert b'tests\\test_stage1_three_plant_sync.py' in data


def test_new_clean_install_launcher_does_not_require_old_p01_package():
    text=_source('START_HERE_WINDOWS.cmd')
    assert 'call "10_WINDOWS_ASAMA2_5_TEST.cmd" --no-pause' in text
    assert 'call "11_WINDOWS_ASAMA2_5_AC.cmd"' in text
    assert 'APP_VERSION_P03.txt' in text
    assert 'P01' in text and 'P02' in text

"""Windows 3.13 helper for local simulation; never talks to field equipment.

This prepares a new Windows-specific virtualenv and launches LOCAL_ONLY SIMULATION.
No administrator permission, registry writes, PATH edits, or security-policy changes.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / '.venv'
PYTHON = ENV / 'Scripts' / 'python.exe'
REQUIRED_FILES = (
    'data/solar/demo_weather_15m.csv',
    'data/solar/reference/ges_component_parameters.csv',
    'data/solar/reference/ges_benchmark_results.csv',
    'outputs/ges_oem_shadow_v05/oem_shadow_audit.json',
)

def invoke(argv: list[str], label: str):
    print('\n[APP] ' + label, flush=True)
    return subprocess.run(argv, cwd=ROOT, check=True)

# Immutable fallback for the original (SHA-256 verified) research audit fixture.
# This is metadata, not measured production or real OEM calibration data.
_AUDIT_FILE = 'outputs/ges_oem_shadow_v05/oem_shadow_audit.json'
_AUDIT_B64 = (
    'ewogICJjcmVhdGVkX2F0X3V0YyI6ICIyMDI2LTEwLTE0VDIxOjM5OjAzLjg2NzQxOSswMDowMCIsCiAgInJlc',
    '2VhcmNoX3ppcF9zaGEyNTYiOiAiMjI2NjlkNjM2MGRhODY2ODE0OTYwMDlmYzQ0OWZlOTRhNTA4YzI1YWRjOT',
    'A1Njk3ZjU0YTlhNDQ4OWY1YzJiNyIsCiAgInNjZW5hcmlvX2RhdGFiYXNlIjogIm91dHB1dHMvZ2VzX3YwNV9',
    'tYXRyaXhfZnVsbC9oaXN0b3JpYW4uc3FsaXRlMyIsCiAgInNjZW5hcmlvX3J1bnMiOiA1NCwKICAibXBwdF9y',
    'b3dzIjogMjA3MzYsCiAgIm9lbV9jYXRhbG9nX3Jvd3MiOiAxNTgsCiAgImV2aWRlbmNlX3R5cGVzIjogewogI',
    'CAgIm9lbV9wdWJsaXNoZWQiOiAxMDksCiAgICAiZGVyaXZlZF9mcm9tX29lbSI6IDEwLAogICAgInVua25vd2',
    '4iOiAzOQogIH0sCiAgInZlcmlmaWNhdGlvbl9zdGF0dXNlcyI6IHsKICAgICJ2ZXJpZmllZF9zZWxlY3RlZF9',
    'kb2N1bWVudCI6IDExMSwKICAgICJ1bmtub3duIjogMzksCiAgICAidmVyaWZpZWRfc2VsZWN0ZWRfZG9jdW1l',
    'bnQ7IGNyb3NzX2RvY3VtZW50X3Njb3BlX2RpZmZlcmVuY2UiOiA0LAogICAgImNvbmRpdGlvbmFsX2Rlcml2Z',
    'WQiOiA0CiAgfSwKICAibWlzc2luZ19mb3JfZnVsbF9waHlzaWNzIjogewogICAgIlRSSU5BX1RTTTQ0NV9ORU',
    'c5UjI4IjogWwogICAgICAiYV9yZWZfdiIsCiAgICAgICJpX2xfcmVmX2EiLAogICAgICAiaV9vX3JlZl9hIiw',
    'KICAgICAgInJfc2hfcmVmX29obSIsCiAgICAgICJyX3Nfb2htIgogICAgXSwKICAgICJKSU5LT19KS001ODVO',
    'NzJITDRWIjogWwogICAgICAiYV9yZWZfdiIsCiAgICAgICJpX2xfcmVmX2EiLAogICAgICAiaV9vX3JlZl9hI',
    'iwKICAgICAgInJfc2hfcmVmX29obSIsCiAgICAgICJyX3Nfb2htIgogICAgXSwKICAgICJTTUFfU1RQNTBfND',
    'AiOiBbCiAgICAgICJldGFfbm9taW5hbF9jdXJ2ZV9wYXJhbWV0ZXIiCiAgICBdLAogICAgIlNVTkdST1dfU0c',
    'xMTBDWF9WMTUyIjogWwogICAgICAiZXRhX25vbWluYWxfY3VydmVfcGFyYW1ldGVyIiwKICAgICAgInJhdGVk',
    'X2FjX3ciCiAgICBdCiAgfSwKICAibW9kZWxfc2NyZWVuaW5nIjogewogICAgIlNNQV9TVFA1MF80MCI6IHsKI',
    'CAgICAgIm1wcHRfY291bnQiOiA2LjAsCiAgICAgICJtcHB0X21pbl92IjogNTAwLjAsCiAgICAgICJtcHB0X2',
    '1heF92IjogODAwLjAsCiAgICAgICJtYXhfZGNfdiI6IDEwMDAuMCwKICAgICAgIm1heF9vcGVyYXRpbmdfY3V',
    'ycmVudF9wZXJfbXBwdF9hIjogMjAuMCwKICAgICAgIm1heF9zaG9ydF9jaXJjdWl0X2N1cnJlbnRfcGVyX21w',
    'cHRfYSI6IDMwLjAsCiAgICAgICJtYXhfZGNfY3VycmVudF9hIjogMTIwLjAKICAgIH0sCiAgICAiU1VOR1JPV',
    '19TRzExMENYX1YxNTIiOiB7CiAgICAgICJtcHB0X2NvdW50IjogOS4wLAogICAgICAibXBwdF9taW5fdiI6ID',
    'IwMC4wLAogICAgICAibXBwdF9tYXhfdiI6IDEwMDAuMCwKICAgICAgIm1heF9kY192IjogMTEwMC4wLAogICA',
    'gICAibWF4X29wZXJhdGluZ19jdXJyZW50X3Blcl9tcHB0X2EiOiAyNi4wLAogICAgICAibWF4X3Nob3J0X2Np',
    'cmN1aXRfY3VycmVudF9wZXJfbXBwdF9hIjogNDAuMCwKICAgICAgIm1heF9kY19jdXJyZW50X2EiOiBudWxsC',
    'iAgICB9CiAgfSwKICAiZmxhZ3NfdG90YWwiOiAxMjU1OSwKICAibGltaXRhdGlvbnMiOiBbCiAgICAiT0VNIH',
    'NvdXJjZSBjbGFzc2lmaWNhdGlvbnMgb3JpZ2luYXRlIGZyb20gdGhlIHN1cHBsaWVkIHJlc2VhcmNoIHBhY2t',
    'hZ2UuIiwKICAgICJPcmlnaW5hbCBtYW51ZmFjdHVyZXIgUERGcyBhcmUgbm90IGluY2x1ZGVkIGluIHRoZSBa',
    'SVAuIiwKICAgICJUaGUgc2NlbmFyaW8gcG93ZXJzIGFyZSBzeW50aGV0aWMuIiwKICAgICJObyBuZXcgT0VNI',
    'GVuZXJneSBzaW11bGF0aW9uIHdhcyBydW4uIiwKICAgICJUaGlzIGlzIGFuIGVsZWN0cmljYWwgZW52ZWxvcG',
    'Ugc2NyZWVuaW5nLCBub3QgYW4gaW5zdGFsbGF0aW9uIGFwcHJvdmFsLiIsCiAgICAiRGUgU290byBhbmQgZnV',
    'sbCBpbnZlcnRlciBlZmZpY2llbmN5IGNhbGlicmF0aW9uIHJlbWFpbiBpbmNvbXBsZXRlLiIsCiAgICAiUmVx',
    'dWVzdGVkIFEgaXMgbm90IG1lYXN1cmVkIGRlbGl2ZXJlZCBRLiIKICBdCn0=',
)

def restore_missing_audit(expected_digest: str, *, root: Path = ROOT) -> bool:
    """Restore absent historical audit bytes only when matching the signed-in-manifest digest."""
    import base64
    import tempfile
    target = root / _AUDIT_FILE
    if target.exists():
        return False  # Never mask corrupted/modified data by overwriting.
    blob = base64.b64decode(''.join(_AUDIT_B64), validate=True)
    if hashlib.sha256(blob).hexdigest() != expected_digest:
        raise RuntimeError('Bundled audit recovery checksum mismatch; refuse recovery')
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile('wb', dir=target.parent, prefix='.audit_restore_', delete=False) as f:
            temporary = Path(f.name)
            f.write(blob)
        if target.exists():
            return False
        temporary.replace(target)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return True

def verify_files():
    expected = json.loads((ROOT / 'WINDOWS_PACKAGE_MANIFEST.json').read_text(encoding='utf-8'))['required_fixtures_sha256']
    for name in REQUIRED_FILES:
        path = ROOT / name
        if not path.is_file():
            if name == _AUDIT_FILE and restore_missing_audit(expected[name]):
                print('[APP] Verified historical GES audit restored from bundled backup.', flush=True)
            else:
                raise RuntimeError('Missing bundled input: ' + name)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != expected[name]:
            raise RuntimeError('SHA256 mismatch (do not run modified research data): ' + name)
    print('[APP] Required public demo fixtures: ' + str(len(REQUIRED_FILES)) + '/' + str(len(REQUIRED_FILES)) + ' SHA256 OK', flush=True)

def correct_interpreter() -> bool:
    if not PYTHON.is_file(): return False
    try:
        p = subprocess.run([str(PYTHON),'-c', "import sys; assert sys.platform == 'win32' and sys.version_info[:2] == (3, 13)"], stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10)
        return p.returncode == 0
    except (OSError,subprocess.TimeoutExpired): return False

def setup():
    if ENV.exists() and not correct_interpreter():
        backup=ROOT / ('.venv_linux_backup_'+time.strftime('%Y%m%d_%H%M%S'))
        if backup.exists(): raise RuntimeError('Backup directory already exists: '+str(backup))
        ENV.rename(backup)
        print('[APP] Invalid/cross-OS virtualenv preserved at: '+backup.name,flush=True)
    if not correct_interpreter():
        invoke([sys.executable,'-m','venv',str(ENV)],'Creating clean Windows Python 3.13 venv')
    invoke([str(PYTHON),'-m','pip','install','-r','requirements-windows.txt'],'Installing Windows dependencies (scikit-learn 1.9.1, internet required)')
    invoke([str(PYTHON),'-m','desktop.viewer_entry_v15','--self-test'],'Verifying read-only viewer')

def test():
    # On some Windows systems pytest-of-<Unicode username> under the user TEMP
    # directory is inaccessible (WinError 5). Give pytest a writable, private
    # project-local temporary area instead; do not alter machine-wide settings.
    temp_root = ROOT / '.windows_test_tmp'
    temp_root.mkdir(parents=True, exist_ok=True)
    base_temp = temp_root / ('pytest_' + time.strftime('%Y%m%d_%H%M%S') + '_' + str(os.getpid()))
    child_env = os.environ.copy()
    # Python tempfile and its child processes must use the same writable area.
    for key in ('TEMP', 'TMP', 'TMPDIR'):
        child_env[key] = str(temp_root)
    # File decoding as well as console I/O must be consistent on Windows
    # (PYTHONIOENCODING does not change Path.read_text() defaults).
    child_env['PYTHONUTF8'] = '1'
    child_env['PYTHONIOENCODING'] = 'utf-8'

    command = [str(PYTHON), '-m', 'pytest', '-q', '--assert=plain',
               '--tb=short', '--basetemp=' + str(base_temp), 'tests']
    report = ROOT / 'WINDOWS_TEST_RAPORU.txt'
    print('\n[APP] Running full regression tests.', flush=True)
    print('[APP] Test temporary directory: ' + str(base_temp), flush=True)
    print('[APP] Writing test report: ' + str(report), flush=True)
    with report.open('w', encoding='utf-8', newline='\n') as log:
        process = subprocess.Popen(command, cwd=ROOT, env=child_env,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, encoding='utf-8', errors='replace', bufsize=1)
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end='', flush=True)
            log.write(line)
            log.flush()
        status = process.wait()
    if status != 0:
        raise RuntimeError('Regression tests failed (exit ' + str(status) + '). See ' + str(report))

def start_simulation():
    # Never accept a healthy response from an *old* application occupying port
    # 8000. That previously opened a stale P01 dashboard while a P03/P04 launch
    # appeared successful. Never kill an unknown local process automatically.
    from socket import socket, AF_INET, SOCK_STREAM
    with socket(AF_INET, SOCK_STREAM) as check:
        if check.connect_ex(('127.0.0.1', 8000)) == 0:
            raise RuntimeError('127.0.0.1:8000 is already occupied (perhaps an old P01/P03 session). Close the previous simulator before starting P04. Nothing was stopped automatically.')
    mode='SIMULATION'
    args=[str(PYTHON),'-m','tools.v15_launcher','--mode',mode,'--enable-local-sim-commands']
    CREATE_NEW_CONSOLE=getattr(subprocess,'CREATE_NEW_CONSOLE',0)
    server=subprocess.Popen(args,cwd=ROOT,creationflags=CREATE_NEW_CONSOLE)
    url='http://127.0.0.1:8000'
    for attempt in range(60):
        if server.poll() is not None:
            raise RuntimeError('Simulator server exited early, code='+str(server.returncode)+'; check server console')
        try:
            with urllib.request.urlopen(url+'/api/v2/clock/build',timeout=1) as res:
                info=json.load(res)
                if info.get('build')=='UTC_DISPATCH_P04' and info.get('mode')=='SIMULATION':
                    break
                raise RuntimeError('Wrong application/build on 127.0.0.1:8000; stop the older session first')
        except Exception:
            time.sleep(.5)
    else:
        raise RuntimeError('Simulator did not respond on 127.0.0.1:8000; check whether port 8000 is occupied')
    print('[APP] Simulator P04 running at '+url+'/platform/synchronized',flush=True)
    webbrowser.open(url+'/platform/synchronized')
    try:
        subprocess.Popen([str(PYTHON),'-m','desktop.viewer_entry_v15'],cwd=ROOT,creationflags=CREATE_NEW_CONSOLE)
        print('[APP] Read-only desktop viewer started.',flush=True)
    except OSError as exc:
        print('[APP] Viewer GUI unavailable: '+str(exc),flush=True)

def build_exe():
    invoke([str(PYTHON),'-m','pip','install','pyinstaller==6.16.0'],'Installing PyInstaller for optional Windows EXE')
    invoke([str(PYTHON),'-m','PyInstaller','--noconfirm','--clean','--onefile','--windowed','--name','AutonomousPlantViewer','--paths',str(ROOT),'--distpath',str(ROOT/'Windows_EXE'),str(ROOT/'desktop'/'viewer_entry_v15.py')],'Building Windows VIEWER EXE (not a server)')
    print('Created: '+str(ROOT/'Windows_EXE'/'AutonomousPlantViewer.exe'),flush=True)

def verify_complete_project():
    required = ('app/main.py', 'stage1/controller.py', 'advanced_v2/api.py',
                'desktop/full_simulator_launcher.py', 'tests/test_stage1_three_plant_sync.py',
                'tests/test_stages_2_to_5_advanced.py', 'pytest.ini', 'requirements-windows.txt')
    missing = [x for x in required if not (ROOT/x).is_file()]
    if missing:
        raise RuntimeError('Incomplete P03 project: ' + ', '.join(missing) +
                           '. Extract the COMPLETE P03 ZIP to a NEW EMPTY folder.')

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--test-only',action='store_true')
    parser.add_argument('--skip-tests',action='store_true')
    parser.add_argument('--build-exe',action='store_true')
    parser.add_argument('--setup-only',action='store_true',
                        help='Prepare and verify Python venv without tests/server')
    args=parser.parse_args()
    if sys.platform != 'win32' or sys.version_info[:2] != (3,13):
        raise RuntimeError('Please use Windows Python 3.13 (py -3.13).')
    os.chdir(ROOT)
    verify_complete_project()
    verify_files()
    setup()
    if args.setup_only:
        print('[APP] Python environment ready; no tests/server launched.', flush=True)
        return
    if args.build_exe:
        build_exe()
        return
    if not args.skip_tests: test()
    if not args.test_only: start_simulation()
    print('\n[APP] Completed; open the simulator console to stop the local server.',flush=True)

if __name__=='__main__':
    try: main()
    except (RuntimeError, subprocess.CalledProcessError, OSError) as exc:
        print('\n[APP] FAILED: '+str(exc),file=sys.stderr,flush=True)
        sys.exit(1)

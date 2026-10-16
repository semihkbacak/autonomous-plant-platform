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
    'ges_oem_research.zip',
    'outputs/ges_oem_shadow_v05/oem_shadow_audit.json',
)

def invoke(argv: list[str], label: str):
    print('\n[APP] ' + label, flush=True)
    return subprocess.run(argv, cwd=ROOT, check=True)

def verify_files():
    expected = json.loads((ROOT / 'WINDOWS_PACKAGE_MANIFEST.json').read_text(encoding='utf-8'))['required_fixtures_sha256']
    for name in REQUIRED_FILES:
        path = ROOT / name
        if not path.is_file(): raise RuntimeError('Missing bundled input: ' + name)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != expected[name]:
            raise RuntimeError('SHA256 mismatch (do not run modified research data): ' + name)
    print('[APP] Original SSD test fixtures: 5/5 SHA256 OK', flush=True)

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
    child_env['PYTHONIOENCODING'] = 'utf-8'

    command = [str(PYTHON), '-m', 'pytest', '-q', '--assert=plain',
               '--tb=short', '--basetemp=' + str(base_temp)]
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
    mode='SIMULATION'
    args=[str(PYTHON),'-m','tools.v15_launcher','--mode',mode,'--enable-local-sim-commands']
    CREATE_NEW_CONSOLE=getattr(subprocess,'CREATE_NEW_CONSOLE',0)
    server=subprocess.Popen(args,cwd=ROOT,creationflags=CREATE_NEW_CONSOLE)
    url='http://127.0.0.1:8000'
    for attempt in range(60):
        if server.poll() is not None:
            raise RuntimeError('Simulator server exited early, code='+str(server.returncode)+'; check server console')
        try:
            with urllib.request.urlopen(url+'/api/v1/plant',timeout=1) as res:
                if res.status == 200: break
        except Exception:
            time.sleep(.5)
    else:
        raise RuntimeError('Simulator did not respond on 127.0.0.1:8000; check whether port 8000 is occupied')
    print('[APP] Simulator running at '+url+'/platform/dashboard',flush=True)
    webbrowser.open(url+'/platform/dashboard')
    try:
        subprocess.Popen([str(PYTHON),'-m','desktop.viewer_entry_v15'],cwd=ROOT,creationflags=CREATE_NEW_CONSOLE)
        print('[APP] Read-only desktop viewer started.',flush=True)
    except OSError as exc:
        print('[APP] Viewer GUI unavailable: '+str(exc),flush=True)

def build_exe():
    invoke([str(PYTHON),'-m','pip','install','pyinstaller==6.16.0'],'Installing PyInstaller for optional Windows EXE')
    invoke([str(PYTHON),'-m','PyInstaller','--noconfirm','--clean','--onefile','--windowed','--name','AutonomousPlantViewer','--paths',str(ROOT),'--distpath',str(ROOT/'Windows_EXE'),str(ROOT/'desktop'/'viewer_entry_v15.py')],'Building Windows VIEWER EXE (not a server)')
    print('Created: '+str(ROOT/'Windows_EXE'/'AutonomousPlantViewer.exe'),flush=True)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--test-only',action='store_true')
    parser.add_argument('--skip-tests',action='store_true')
    parser.add_argument('--build-exe',action='store_true')
    args=parser.parse_args()
    if sys.platform != 'win32' or sys.version_info[:2] != (3,13):
        raise RuntimeError('Please use Windows Python 3.13 (py -3.13).')
    os.chdir(ROOT)
    verify_files()
    setup()
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

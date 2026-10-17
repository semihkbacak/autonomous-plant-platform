"""Safe, interactive branch-only GitHub publisher for RC1. No force push."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

SOURCE_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_MAIN = '83e86742d6f0008844d1386493d2c64b89ece032'
BRANCH = 'release/v1.5-rc1'
DEFAULT_REMOTE = 'https://github.com/semihkbacak/autonomous-plant-platform.git'
MANIFEST_FILE = 'RC1_SOURCE_SHA256.json'


def git(cwd: Path, *args: str, capture: bool = False) -> str:
    cmd = ['git', '-C', str(cwd), *args]
    result = subprocess.run(cmd, text=True, encoding='utf-8', errors='replace', check=True,
                            stdout=subprocess.PIPE if capture else None,
                            stderr=subprocess.PIPE if capture else None)
    return result.stdout.strip() if capture else ''


def verify_source(root: Path) -> list[str]:
    manifest = json.loads((root / MANIFEST_FILE).read_text(encoding='utf-8'))
    if manifest['branch'] != BRANCH:
        raise RuntimeError('Release branch is not the expected RC branch')
    files = manifest['files']
    for name, digest in files.items():
        path = root/name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise RuntimeError(f'Corrupt or missing source file: {name}')
    return sorted(files)



def configure_commit_author(repo: Path) -> None:
    """Resolve verified GitHub login and set author only in the disposable clone."""
    if not shutil.which('gh'):
        raise RuntimeError('GitHub CLI (gh) is required to determine commit author.')
    info = subprocess.run(
        ['gh', 'api', 'user', '--jq', '{login: .login, id: .id}'],
        check=True, capture_output=True, text=True, encoding='utf-8', errors='replace',
    )
    profile = json.loads(info.stdout)
    login = profile.get('login')
    user_id = profile.get('id')
    if not isinstance(login, str) or login.lower() != 'semihkbacak':
        raise RuntimeError('GitHub CLI must be authenticated as repository owner semihkbacak.')
    if not isinstance(user_id, int) or user_id <= 0:
        raise RuntimeError('GitHub did not return a valid user ID.')
    # Never update --global Git configuration or expose the authentication token.
    git(repo, 'config', '--local', 'user.name', login)
    git(repo, 'config', '--local', 'user.email',
        f'{user_id}+{login}@users.noreply.github.com')
    print('Git commit author configured for temporary clone:', login, flush=True)


def publish(root: Path, remote: str, expected_main: str, dry_run: bool) -> bool:
    filelist = verify_source(root)
    if not shutil.which('git'):
        raise RuntimeError('Git not found. Install Git for Windows first.')
    with tempfile.TemporaryDirectory(prefix='app-rc1-publish-') as tmp:
        repo = Path(tmp)/'repo'
        print('Cloning main into a temporary directory (not your existing repo)...', flush=True)
        subprocess.run(['git', 'clone', '--branch', 'main', '--single-branch', remote, str(repo)], check=True)
        current = git(repo, 'rev-parse', 'HEAD', capture=True)
        print('Current main SHA:', current, flush=True)
        if current != expected_main:
            raise RuntimeError('main HEAD changed. STOP: review updates before releasing. No files pushed.')
        branch_exists = git(repo, 'ls-remote', '--heads', 'origin', BRANCH, capture=True)
        if branch_exists:
            remote_branch_sha = branch_exists.split()[0]
            if remote_branch_sha != current:
                raise RuntimeError('RC branch exists remotely with changes. Refusing to overwrite it or force push.')
            print('RC branch is a clean placeholder at main HEAD; a normal fast-forward push is allowed.', flush=True)
        git(repo, 'checkout', '-b', BRANCH)
        # A clean disposable clone is synchronized to the complete snapshot.
        for item in repo.iterdir():
            if item.name == '.git':
                continue
            if item.is_dir() and not item.is_symlink():
                shutil.rmtree(item)
            else:
                item.unlink()
        for rel in filelist:
            dest = repo/rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root/rel, dest)
        # the manifest is generated after source hashing: include it separately.
        shutil.copy2(root/MANIFEST_FILE, repo/MANIFEST_FILE)
        git(repo, 'add', '-A')
        # Historic Markdown soft-wraps trigger git whitespace checks.
        # Treat them as advisory rather than blocking unrelated release prep.
        print('\n--- RC1 STAGED CHANGE SUMMARY ---', flush=True)
        # Do not launch Git's interactive pager (less) on Windows.
        # The full diff could contain hundreds of paths and block publication.
        git(repo, '--no-pager', 'diff', '--cached', '--shortstat')
        print('--- END SUMMARY ---', flush=True)
        if not git(repo, '--no-pager', 'diff', '--cached', '--name-only', capture=True):
            raise RuntimeError('No changes versus main; nothing to publish')
        if dry_run:
            print('\nDRY RUN: Nothing committed or pushed. main unchanged.', flush=True)
            return True
        print('\nWARNING: LICENSE / OEM archive rights require review. RC1 is NOT a stable release.', flush=True)
        confirmation = input('To push ONLY release/v1.5-rc1, type YUKLE then Enter: ').strip()
        if confirmation != 'YUKLE':
            print('Cancelled. No changes pushed.', flush=True)
            return False
        configure_commit_author(repo)
        git(repo, 'commit', '-m', 'chore(release): prepare synthetic platform v1.5.0-rc.1 (P04)')
        git(repo, 'push', '-u', 'origin', BRANCH)
        print('\nSUCCESS: RC branch pushed. main was not changed.', flush=True)
        print('https://github.com/semihkbacak/autonomous-plant-platform/tree/' + BRANCH)
        return True


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument('--dry-run', action='store_true')
    group.add_argument('--publish', action='store_true')
    ap.add_argument('--remote', default=DEFAULT_REMOTE, help='Use only for automated local test remotes')
    ap.add_argument('--expected-main', default=EXPECTED_MAIN, help='Expected unmodified main commit SHA')
    ap.add_argument('--source', type=Path, default=SOURCE_ROOT)
    args = ap.parse_args(argv)
    try:
        published = publish(args.source.resolve(), args.remote, args.expected_main, args.dry_run)
        return 0 if published else 2
    except (OSError, subprocess.CalledProcessError, ValueError, RuntimeError) as exc:
        print('RELEASE PREPARATION FAILED:', exc, file=sys.stderr, flush=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())

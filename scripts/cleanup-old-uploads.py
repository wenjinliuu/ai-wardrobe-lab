"""Remove only three known failed release directories, after protecting live releases."""
import fcntl
import json
from pathlib import Path
import re
import shutil
import subprocess

FAILED_RELEASES = (
    'c8121eff03d1356bc4ae268990b0c5ea456c3a83',
    '905f2bf1205ff44e7fede0e7912ba4ce2db195a0',
    '571d65750ca3567ea31e9a3fd4d26139ae4fdb36',
)


def clean(base, protected):
    releases = base/'releases'
    if releases.is_symlink() or releases.resolve() != base.resolve()/'releases':
        raise RuntimeError('Unexpected releases directory')
    deleted = []
    for revision in FAILED_RELEASES:
        path = releases/revision
        if not path.exists():
            continue
        if path.is_symlink() or path.resolve() in protected:
            print('Preserved protected release:', revision, flush=True)
            continue
        if not path.is_dir() or not re.fullmatch('[a-f0-9]{40}', path.name):
            raise RuntimeError('Unexpected cleanup target')
        size = sum(p.stat().st_size for p in path.rglob('*') if p.is_file() and not p.is_symlink())
        shutil.rmtree(path)
        deleted.append(revision)
        print(f'Removed failed release {revision}: {size} bytes', flush=True)
    return deleted


def main():
    base = Path('/opt/wardrobe-lab')
    with (base/'deploy.lock').open('a') as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('Another deployment is running; cleanup skipped.')
        protected = set()
        current = base/'current'
        if current.exists() or current.is_symlink():
            protected.add(current.resolve())
        ids = subprocess.check_output(['docker', 'ps', '-aq', '--filter', 'label=com.docker.compose.project=wardrobe-lab'], text=True).split()
        if ids:
            containers = json.loads(subprocess.check_output(['docker', 'inspect', *ids], text=True))
            for container in containers:
                labels = container.get('Config', {}).get('Labels') or {}
                directory = labels.get('com.docker.compose.project.working_dir')
                if directory:
                    protected.add(Path(directory).resolve())
                image = container.get('Config', {}).get('Image', '')
                if image.startswith('wardrobe-lab:'):
                    protected.add((base/'releases'/image.split(':', 1)[1]).resolve())
        removed = clean(base, protected)
        print(f'Cleanup completed: {len(removed)} failed releases removed. Shared data and server configuration retained.', flush=True)


if __name__ == '__main__':
    main()

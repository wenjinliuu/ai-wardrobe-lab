"""Verify cleanup preserves live releases and server builds use measured mirrors."""
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('cleanup', ROOT/'scripts/cleanup-old-uploads.py')
cleanup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cleanup)


class DeploymentTests(unittest.TestCase):
    def test_unreadable_config_repairs_only_owner_mode_without_exposing_values(self):
        if os.geteuid()==0:self.skipTest('Permission checks require the non-root CI deployment identity')
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);base.chmod(0o777)
            sha='a'*40;target=base/'releases'/sha;target.mkdir(parents=True)
            shared=base/'shared';shared.mkdir();env_file=shared/'.env'
            secret='sentinel-value-must-stay-private';env_file.write_text(secret)
            env_file.chmod(0)
            binary=base/'bin';binary.mkdir();log=base/'docker-calls'
            docker=binary/'docker';docker.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$TEST_DOCKER_LOG"\nif [ "$1" = inspect ]; then printf "wardrobe-lab:'+('b'*40)+'\\n"; fi\nif [ "$1" = run ]; then chmod 600 "$TEST_ENV_FILE"; fi\nexit 0\n');docker.chmod(0o755)
            script=base/'deploy.sh';script.write_text((ROOT/'scripts/deploy.sh').read_text().replace('base=/opt/wardrobe-lab',f'base={base}'))
            env={**os.environ,'PATH':str(binary)+':'+os.environ['PATH'],'TEST_DOCKER_LOG':str(log),'TEST_ENV_FILE':str(env_file)}
            r=subprocess.run(['bash',str(script),sha],env=env,capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            self.assertEqual(env_file.read_text(),secret)
            self.assertEqual(env_file.stat().st_mode&0o777,0o600)
            self.assertNotIn(secret,r.stdout+r.stderr+log.read_text())
            self.assertIn('--network none --read-only',log.read_text())
            self.assertIn('dst=/repair.env',log.read_text())

    def test_cleanup_preserves_active_unknown_and_shared(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); releases = base/'releases';releases.mkdir()
            shared = base/'shared';shared.mkdir();(shared/'.env').write_text('keep')
            for sha in cleanup.FAILED_RELEASES:
                p=releases/sha;p.mkdir();(p/'images.tar.gz').write_bytes(b'partial')
            unknown=releases/('b'*40);unknown.mkdir()
            active=releases/cleanup.FAILED_RELEASES[0]
            removed=cleanup.clean(base, {active.resolve()})
            self.assertEqual(len(removed),2)
            self.assertTrue(active.exists());self.assertTrue(unknown.exists())
            self.assertEqual((shared/'.env').read_text(),'keep')

    def test_cleanup_preserves_symlink_target(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);(base/'releases').mkdir();outside=base/'shared';outside.mkdir()
            (outside/'data').write_text('keep')
            (base/'releases'/cleanup.FAILED_RELEASES[0]).symlink_to(outside, target_is_directory=True)
            self.assertEqual(cleanup.clean(base,set()),[])
            self.assertEqual((outside/'data').read_text(),'keep')

    def test_cleanup_rejects_redirected_releases_root(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);(base/'shared').mkdir();(base/'releases').symlink_to(base/'shared',target_is_directory=True)
            with self.assertRaises(RuntimeError):cleanup.clean(base,set())

    def test_server_build_pull_and_health_sequence(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);sha='a'*40;target=base/'releases'/sha;target.mkdir(parents=True)
            (base/'shared').mkdir();(base/'shared'/'.env').write_text('')
            binary=base/'bin';binary.mkdir();log=base/'docker-calls'
            docker=binary/'docker';docker.write_text('#!/bin/sh\nprintf "%s %s\\n" "$LAB_USE_TENCENT_MIRRORS" "$*" >> "$TEST_DOCKER_LOG"\nexit 0\n');docker.chmod(0o755)
            script=base/'deploy.sh';script.write_text((ROOT/'scripts/deploy.sh').read_text().replace('base=/opt/wardrobe-lab',f'base={base}'))
            env={**os.environ,'PATH':str(binary)+':'+os.environ['PATH'],'TEST_DOCKER_LOG':str(log)}
            r=subprocess.run(['bash',str(script),sha],env=env,capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            calls=log.read_text();self.assertIn('true compose --progress plain',calls)
            self.assertIn('build app',calls);self.assertIn('pull caddy',calls)
            self.assertIn('--no-build --pull never',calls)
            self.assertNotIn('load -i',calls)
            self.assertEqual((base/'current').resolve(),target)


if __name__=='__main__':unittest.main()

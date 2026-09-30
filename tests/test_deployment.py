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

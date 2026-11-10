#!/usr/bin/env python3
"""Hardware/network-free recipe tests; all repositories and images are fixtures."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from typing import Any
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('uz801_release', Path(__file__).with_name('uz801-release.py'))
assert spec is not None and spec.loader is not None
release: Any = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


def git(path, *args):
    return subprocess.check_output(['git', '-C', str(path), *args], stderr=subprocess.DEVNULL, text=True).strip()


class RecipeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='uz801-recipe-test-', dir=os.environ.get('UZ801_TEST_TMPDIR'))
        self.root = Path(self.tmp.name)
        self.up = self.root / 'upstream'
        self.up.mkdir()
        git(self.up, 'init')
        git(self.up, 'config', 'user.name', 'Synthetic fixture')
        git(self.up, 'config', 'user.email', 'fixture@localhost')
        (self.up / 'config.txt').write_text('old\n')
        git(self.up, 'add', 'config.txt')
        git(self.up, 'commit', '-m', 'fixture upstream')
        self.base = git(self.up, 'rev-parse', 'HEAD')
        (self.up / 'config.txt').write_text('new\n')
        diff = subprocess.check_output(['git', '-C', str(self.up), 'diff'], text=True)
        git(self.up, 'restore', 'config.txt')
        self.patchfile = self.root / 'downstream.patch'
        self.patchfile.write_text(diff)
        self.cfg = {'patch': 'downstream.patch', 'patch_sha256': release.sha(self.patchfile),
                    'tested_upstream_commit': self.base, 'upstream_url': str(self.up),
                    'required_files': {'config.txt': hashlib.sha256(b'new\n').hexdigest()}}
        self.recipefile = self.root / 'recipe.json'
        self.recipefile.write_text(json.dumps(self.cfg))
        self.saved = release.RECIPE
        release.RECIPE = self.recipefile
        self.dest = self.root / 'prepared'

    def tearDown(self):
        release.RECIPE = self.saved
        self.tmp.cleanup()

    def prepare(self, ref=None):
        args = argparse.Namespace(workdir=self.dest, upstream_ref=ref, upstream_url=None)
        release.prepare(args, self.cfg, self.patchfile)

    def test_prepare_real_git_and_provenance(self):
        self.prepare()
        self.assertEqual((self.dest / 'config.txt').read_text(), 'new\n')
        self.assertEqual(git(self.dest, 'status', '--porcelain'), '')
        meta = json.loads((self.dest / '.git/uz801-recipe.json').read_text())
        self.assertEqual(meta['upstream_commit'], self.base)
        self.assertEqual(meta['downstream_commit'], release.verify(self.dest, self.cfg))

    def test_existing_destination_preserved(self):
        self.dest.mkdir()
        (self.dest / 'sentinel').write_text('keep')
        with self.assertRaises(RuntimeError):
            self.prepare()
        self.assertEqual((self.dest / 'sentinel').read_text(), 'keep')

    def test_patch_identity_tampering_rejected(self):
        self.patchfile.write_text('tampered')
        with self.assertRaises(RuntimeError):
            release.recipe()

    def test_dirty_source_rejected(self):
        self.prepare()
        (self.dest / 'config.txt').write_text('unsafe\n')
        with self.assertRaisesRegex(RuntimeError, 'Tracked source changes'):
            release.verify(self.dest, self.cfg)

    def test_untracked_overlay_rejected(self):
        self.prepare()
        overlay = self.dest / 'openwrt-overlay'
        overlay.mkdir()
        (overlay / 'unreviewed').write_text('not in source archive')
        with self.assertRaisesRegex(RuntimeError, 'Untracked build input'):
            release.verify(self.dest, self.cfg)

    def test_ignored_overlay_rejected(self):
        self.prepare()
        (self.dest / '.gitignore').write_text('openwrt-overlay/ignored\n')
        git(self.dest, 'add', '.gitignore')
        git(self.dest, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@localhost', 'commit', '-m', 'ignore fixture')
        overlay = self.dest / 'openwrt-overlay'
        overlay.mkdir()
        (overlay / 'ignored').write_text('ignored but still a build input')
        with self.assertRaisesRegex(RuntimeError, 'Untracked build input'):
            release.verify(self.dest, self.cfg)

    def test_clean_but_unreviewed_contract_rejected(self):
        self.prepare()
        (self.dest / 'config.txt').write_text('unsafe\n')
        git(self.dest, 'add', '.')
        git(self.dest, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@localhost', 'commit', '-m', 'unreviewed')
        with self.assertRaisesRegex(RuntimeError, 'contract changed'):
            release.verify(self.dest, self.cfg)

    def test_conflicting_new_upstream_stops_without_fallback(self):
        (self.up / 'config.txt').write_text('upstream changed\n')
        git(self.up, 'add', '.')
        git(self.up, 'commit', '-m', 'incompatible new release')
        newer = git(self.up, 'rev-parse', 'HEAD')
        with self.assertRaises(subprocess.CalledProcessError):
            self.prepare(newer)
        self.assertEqual(git(self.dest, 'rev-parse', 'HEAD'), newer)
        self.assertEqual(git(self.dest, 'diff', '--cached'), '')

    def test_unrelated_new_upstream_change_preserved(self):
        (self.up / 'release-notes.txt').write_text('new version feature\n')
        git(self.up, 'add', '.')
        git(self.up, 'commit', '-m', 'compatible new release')
        newer = git(self.up, 'rev-parse', 'HEAD')
        self.prepare(newer)
        self.assertEqual((self.dest / 'release-notes.txt').read_text(), 'new version feature\n')
        self.assertEqual(json.loads((self.dest / '.git/uz801-recipe.json').read_text())['upstream_commit'], newer)

    def test_invalid_ref_does_not_create_checkout(self):
        with self.assertRaises(RuntimeError):
            self.prepare('--upload-pack=unexpected')
        self.assertFalse(self.dest.exists())

    def test_fresh_builder_clones_before_mounts_and_ignores_dry_run(self):
        # Real local Git clone; only Docker interactions are fixture calls.
        version = self.up / 'scripts/openwrt-version.sh'
        version.parent.mkdir()
        branch = git(self.up, 'rev-parse', '--abbrev-ref', 'HEAD')
        version.write_text('#!/bin/sh\nprintf "%s\\n" "' + branch + '"\n')
        original_run, original_text = release.run, release.text
        calls = []

        def fixture_text(args, **kwargs):
            if args[:2] == ['docker', 'inspect']:
                raise subprocess.CalledProcessError(1, args)
            return original_text(args, **kwargs)

        def fixture_run(args, **kwargs):
            calls.append([str(a) for a in args])
            if args[:2] == ['git', 'clone']:
                local = list(args)
                local[-2] = str(self.up)
                return original_run(local, **kwargs)
            self.assertTrue((self.up / 'openwrt/.git').is_dir())
            return subprocess.CompletedProcess(args, 0)

        env = dict(os.environ)
        env.pop('HOST_UID', None)
        env.pop('HOST_GID', None)
        env['DRY_RUN'] = '1'
        with patch.dict(os.environ, env, clear=True), \
             patch.object(release, 'text', side_effect=fixture_text), \
             patch.object(release, 'run', side_effect=fixture_run):
            built_env = release.builder(self.up)
        self.assertEqual(calls[0][:2], ['git', 'clone'])
        self.assertEqual(built_env['DRY_RUN'], '0')
        self.assertEqual(built_env['HOST_UID'], str(os.getuid()))
        self.assertEqual(calls[-1][5:7], ['chown', str(os.getuid()) + ':' + str(os.getgid())])

    def test_builder_does_not_take_over_another_checkout(self):
        inspected = json.dumps([{'Mounts': [{'Destination': '/repo', 'Source': str(self.root / 'other')}]}])
        with patch.object(release, 'text', return_value=inspected), patch.object(release, 'run') as called:
            with self.assertRaisesRegex(RuntimeError, 'different checkout'):
                release.builder(self.up)
            called.assert_not_called()

    def test_nonempty_uninitialized_openwrt_not_deleted(self):
        directory = self.up / 'openwrt'
        directory.mkdir()
        (directory / 'sentinel').write_text('preserve cache')
        with patch.object(release, 'text', side_effect=subprocess.CalledProcessError(1, ['docker', 'inspect'])), \
             patch.object(release, 'run') as called:
            with self.assertRaisesRegex(RuntimeError, 'Nonempty uninitialized'):
                release.builder(self.up)
            called.assert_not_called()
        self.assertEqual((directory / 'sentinel').read_text(), 'preserve cache')

    def test_prior_artifacts_cannot_satisfy_missing_new_build(self):
        self.prepare()
        target = self.dest / 'openwrt/bin/targets/msm89xx/msm8916'
        target.mkdir(parents=True)
        names = [release.BOARD_PREFIX + suffix for suffix in ['-squashfs-boot.img', '-squashfs-system.img', '.manifest']]
        for name in names:
            (target / name).write_bytes(b'old artifact fixture')
        out = self.root / 'out'
        out.mkdir()
        release.quarantine_outputs(self.dest, out)
        for name in names:
            self.assertFalse((target / name).exists())
            self.assertEqual((out / 'previous-build-local-only' / name).read_bytes(), b'old artifact fixture')
        for name in ['usr/sbin/himi-ok-guard', 'usr/sbin/diag_nv', 'etc/uci-defaults/99-uz801-private-management', 'etc/inittab']:
            path = self.dest / 'msm89xx/base-files' / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'fixture')
        gadget = self.dest / 'packages/uci-usb-gadget/files/usb-gadget.sh'
        gadget.parent.mkdir(parents=True, exist_ok=True)
        gadget.write_bytes(b'fixture')
        with patch.object(release, 'verify', return_value='fixture-commit'), patch.object(release, 'cat_image', return_value=b'fixture'):
            with self.assertRaisesRegex(RuntimeError, 'Missing build artifact'):
                release.collect(self.dest, out, self.cfg, 'fixture-commit')

    def test_stale_image_member_rejected_before_collection(self):
        self.prepare()
        out = self.root / 'out'
        out.mkdir()
        expected = self.dest / 'msm89xx/base-files/usr/sbin/himi-ok-guard'
        expected.parent.mkdir(parents=True)
        expected.write_bytes(b'new guard fixture')
        with patch.object(release, 'verify', return_value='fixture-commit'), \
             patch.object(release, 'cat_image', return_value=b'old guard fixture'):
            with self.assertRaisesRegex(RuntimeError, 'Stale/wrong system image'):
                release.collect(self.dest, out, self.cfg, 'fixture-commit')
        self.assertEqual(list(out.iterdir()), [])


    def test_stale_usb_gadget_rejected_before_collection(self):
        self.prepare()
        out = self.root / 'out'
        out.mkdir()
        for name in ['usr/sbin/himi-ok-guard', 'usr/sbin/diag_nv',
                     'etc/uci-defaults/99-uz801-private-management', 'etc/inittab']:
            path = self.dest / 'msm89xx/base-files' / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'fixture')
        gadget = self.dest / 'packages/uci-usb-gadget/files/usb-gadget.sh'
        gadget.parent.mkdir(parents=True, exist_ok=True)
        gadget.write_bytes(b'new gadget fixture')
        def member(source, system, name):
            return b'old gadget fixture' if name == 'usr/sbin/usb-gadget' else b'fixture'
        with patch.object(release, 'verify', return_value='fixture-commit'), \
             patch.object(release, 'cat_image', side_effect=member):
            with self.assertRaisesRegex(RuntimeError, 'Stale/wrong system image member: usr/sbin/usb-gadget'):
                release.collect(self.dest, out, self.cfg, 'fixture-commit')
        self.assertEqual(list(out.iterdir()), [])


if __name__ == '__main__':
    unittest.main()

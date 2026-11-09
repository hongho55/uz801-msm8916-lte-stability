#!/usr/bin/env python3
"""Prepare/build a reviewed UZ801 downstream recipe; never flash or publish."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
RECIPE = ROOT / 'firmware/uz801/recipe.json'
CONTAINER = 'openwrt-builder'
BOARD_PREFIX = 'msm8916-openwrt-msm89xx-msm8916-yiming-uz801v3'
BUILD_INPUTS = ['msm89xx', 'packages', 'diffconfigs', 'scripts', 'devenv',
                'openwrt-overlay', 'openwrt-patches']


def run(args, **kwargs):
    return subprocess.run([str(x) for x in args], check=True, **kwargs)


def text(args, **kwargs):
    return subprocess.check_output([str(x) for x in args], text=True, **kwargs).strip()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


RUNNER_SHA256 = sha(Path(__file__))


def recipe():
    cfg = json.loads(RECIPE.read_text())
    patch = RECIPE.parent / cfg['patch']
    if patch.parent.resolve() != RECIPE.parent.resolve() or sha(patch) != cfg['patch_sha256']:
        raise RuntimeError('Recipe patch identity mismatch')
    for name in cfg['required_files']:
        if Path(name).is_absolute() or '..' in Path(name).parts:
            raise RuntimeError('Unsafe recipe path')
    return cfg, patch


def verify(source, cfg):
    source = source.resolve()
    if Path(text(['git', '-C', source, 'rev-parse', '--show-toplevel'])).resolve() != source:
        raise RuntimeError('Source must be the repository root')
    status = run(['git', '-C', source, 'status', '--porcelain', '--untracked-files=no'], capture_output=True, text=True)
    if status.stderr:
        raise RuntimeError('Cannot audit source status cleanly (filesystem/symlink warning)')
    if status.stdout.strip():
        raise RuntimeError('Tracked source changes present; commit/review them first')
    # Include ignored files: cp -a consumes those too. Exclude only unrelated
    # research Docs and the generated openwrt tree by auditing actual inputs.
    extra = text(['git', '-C', source, 'ls-files', '--others', '--', *BUILD_INPUTS])
    if extra:
        raise RuntimeError('Untracked build input (including ignored files): ' + extra.splitlines()[0])
    for name, expected in cfg['required_files'].items():
        path = source / name
        if path.is_symlink() or not path.is_file() or sha(path) != expected:
            raise RuntimeError('Reviewed source contract changed: ' + name)
    print('PASS: reviewed source contracts and clean tracked tree')
    return text(['git', '-C', source, 'rev-parse', 'HEAD'])


def prepare(args, cfg, patch):
    target = args.workdir.resolve()
    if target.exists():
        raise RuntimeError('Refusing to overwrite existing workdir')
    # Upstream has case-distinct paths; macOS's default filesystem can alias them.
    with tempfile.TemporaryDirectory(prefix='uz801-case-', dir=target.parent) as temp:
        probe = Path(temp) / 'caseprobe'
        probe.touch()
        if (Path(temp) / 'CASEPROBE').exists():
            raise RuntimeError('Workdir must be on a case-sensitive filesystem (Linux or a case-sensitive APFS volume)')
    ref = args.upstream_ref or cfg['tested_upstream_commit']
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]*', ref):
        raise RuntimeError('Use an explicit tag, branch or full commit ref')
    run(['git', 'init', target])
    run(['git', '-C', target, 'fetch', '--depth=1', '--no-tags', args.upstream_url or cfg['upstream_url'], ref])
    run(['git', '-C', target, 'checkout', '--detach', 'FETCH_HEAD'])
    upstream = text(['git', '-C', target, 'rev-parse', 'HEAD'])
    # No fuzzy patching, forced checkout or fallback to an older upstream release.
    run(['git', '-C', target, 'apply', '--check', patch])
    run(['git', '-C', target, 'apply', '--index', patch])
    run(['git', '-C', target, '-c', 'user.name=UZ801 recipe builder',
         '-c', 'user.email=build@localhost', 'commit', '--no-gpg-sign',
         '-m', 'Apply reviewed UZ801 downstream recipe'])
    commit = verify(target, cfg)
    info = {'upstream_commit': upstream, 'downstream_commit': commit,
            'recipe_sha256': sha(RECIPE), 'patch_sha256': sha(patch)}
    (target / '.git/uz801-recipe.json').write_text(json.dumps(info, indent=2) + '\n')
    print(json.dumps(info, indent=2))


def builder(source):
    env = dict(os.environ)
    env['DRY_RUN'] = '0'  # An inherited upstream dry-run flag must never produce a candidate.
    env.setdefault('HOST_UID', str(os.getuid()))
    env.setdefault('HOST_GID', str(os.getgid()))
    try:
        info = json.loads(text(['docker', 'inspect', CONTAINER]))[0]
    except subprocess.CalledProcessError:
        info = None
    if info:
        mount = next((m for m in info['Mounts'] if m['Destination'] == '/repo'), None)
        if not mount or Path(mount['Source']).resolve() != source.resolve():
            raise RuntimeError('Existing builder belongs to a different checkout. Stop it explicitly before switching; caches are reusable.')
        project = info['Config']['Labels'].get('com.docker.compose.project')
        if project:
            env['COMPOSE_PROJECT_NAME'] = project
        user = info['Config'].get('User', '')
        if re.fullmatch(r'\d+:\d+', user):
            env['HOST_UID'], env['HOST_GID'] = user.split(':')
    openwrt = source / 'openwrt'
    if not (openwrt / '.git').is_dir():
        # Clone before mounting nested cache volumes: upstream's nonempty-tree
        # recovery path moves/deletes directories, which is unsafe for mountpoints.
        if openwrt.exists() and any(openwrt.iterdir()):
            raise RuntimeError('Nonempty uninitialized OpenWrt tree; inspect it manually before mounting caches')
        version = text(['bash', source / 'scripts/openwrt-version.sh', '--current'])
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]*', version):
            raise RuntimeError('Invalid upstream OpenWrt version')
        run(['git', 'clone', '--branch', version, '--single-branch',
             'https://git.openwrt.org/openwrt/openwrt.git', openwrt])
    for volume in ['uz801-owrt-tmp', 'uz801-owrt-build_dir', 'uz801-owrt-staging_dir']:
        run(['docker', 'volume', 'create', volume], stdout=subprocess.DEVNULL)
    run(['docker', 'compose', '-f', source / 'devenv/docker-compose.yml', 'up', '-d', 'builder'], env=env)
    run(['docker', 'exec', '--user', '0', CONTAINER, 'chown',
         env['HOST_UID'] + ':' + env['HOST_GID'], '/repo/openwrt/tmp',
         '/repo/openwrt/build_dir', '/repo/openwrt/staging_dir'])
    return env


def cat_image(source, image, member):
    relative = image.relative_to(source).as_posix()
    return subprocess.check_output(['docker', 'exec', CONTAINER,
        '/repo/openwrt/staging_dir/host/bin/unsquashfs4', '-cat', '/repo/' + relative, member])


def quarantine_outputs(source, output):
    target = source / 'openwrt/bin/targets/msm89xx/msm8916'
    for suffix in ['-squashfs-boot.img', '-squashfs-system.img', '.manifest']:
        origin = target / (BOARD_PREFIX + suffix)
        if origin.is_symlink():
            raise RuntimeError('Refusing symlink build artifact: ' + origin.name)
        if origin.exists():
            prior = output / 'previous-build-local-only'
            prior.mkdir(exist_ok=True)
            shutil.move(str(origin), prior / origin.name)


def collect(source, output, cfg, commit):
    if verify(source, cfg) != commit:
        raise RuntimeError('Source commit changed during build')
    target = source / 'openwrt/bin/targets/msm89xx/msm8916'
    system = target / (BOARD_PREFIX + '-squashfs-system.img')
    # Real extracted bytes, not filenames or a successful make exit, identify this image.
    for name in ['usr/sbin/himi-ok-guard', 'usr/sbin/diag_nv', 'etc/uci-defaults/99-uz801-private-management', 'etc/inittab']:
        expected = (source / 'msm89xx/base-files' / name).read_bytes()
        if cat_image(source, system, name) != expected:
            raise RuntimeError('Stale/wrong system image member: ' + name)
    for name in [BOARD_PREFIX + '-squashfs-boot.img', BOARD_PREFIX + '-squashfs-system.img', BOARD_PREFIX + '.manifest']:
        origin = target / name
        if not origin.is_file() or origin.stat().st_size == 0:
            raise RuntimeError('Missing build artifact: ' + name)
        shutil.copy2(origin, output / name)
    source_tar = output / 'bsp-source.tar.gz'
    run(['git', '-C', source, 'archive', '--format=tar.gz', '--prefix=uz801-bsp/',
         '--output=' + str(source_tar), commit, '--', '.', ':(exclude)Docs'])
    shutil.copy2(source / 'LICENSE', output / 'COPYING-BSP')
    shutil.copy2(source / 'openwrt/.config', output / 'openwrt.config')
    git_inside = ['docker', 'exec', CONTAINER, 'git', '-c', 'safe.directory=*', '-C']
    owrt = text(git_inside + ['/repo/openwrt', 'rev-parse', 'HEAD'])
    feeds = {name: text(git_inside + ['/repo/openwrt/feeds/' + name, 'rev-parse', 'HEAD'])
             for name in ['luci', 'packages', 'routing', 'telephony', 'video']}
    source_info = source / '.git/uz801-recipe.json'
    prepared = json.loads(source_info.read_text()) if source_info.exists() else None
    metadata = {'schema': 1, 'channel': 'candidate', 'hardware_validated': False,
        'automatic_nv2500_write': True, 'cellular_autoconnect': False,
        'universal_installer': False, 'board': 'yiming,uz801-v3',
        'measured_emmc_sectors': 7634944, 'bsp_commit': commit,
        'upstream_url': cfg['upstream_url'], 'prepared_source': prepared,
        'recipe_sha256': sha(RECIPE), 'patch_sha256': cfg['patch_sha256'],
        'pipeline_runner_sha256': RUNNER_SHA256,
        'builder_image_id': text(['docker', 'inspect', CONTAINER, '--format', '{{.Image}}']),
        'openwrt_commit': owrt, 'feeds': feeds,
        'image_member_verification': 'matched built guard, DIAG wrapper, firstboot and inittab bytes',
        'artifact_regeneration': 'prior board outputs quarantined before build; all three outputs recreated',
        'checks': ['synthetic DIAG replies', 'DIAG wrapper real-flock regression', 'guard regression', 'board profile self-check', 'management regression'],
        'warnings': ['NV2500 may be written on first boot', 'development USB shell/default account state',
                     'not sysupgrade/whole-device inputs', 'device qualification required; not stable']}
    (output / 'build-info.json').write_text(json.dumps(metadata, indent=2) + '\n')
    # Raw build.log is local diagnostics and not part of the distributable allow-list.
    files = sorted(p for p in output.iterdir() if p.is_file() and p.name != 'build.log')
    (output / 'SHA256SUMS').write_text(''.join(sha(p) + '  ' + p.name + '\n' for p in files))
    print('CANDIDATE_COLLECTED:', output)


def build(args, cfg):
    source = args.source.resolve()
    commit = verify(source, cfg)
    output = args.output.resolve()
    if output.exists() or output == source or source in output.parents:
        raise RuntimeError('Output must be a new directory outside the source tree')
    lockpath = Path.home() / '.cache/uz801-release-builder.lock'
    lockpath.parent.mkdir(parents=True, exist_ok=True)
    with lockpath.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        output.mkdir(parents=True)
        try:
            env = builder(source)
            with (output / 'build.log').open('w') as log:
                tests = ('set -e; cd /repo; python3 tests/himi-ok-guard/test-responses.py; '
                         'python3 tests/himi-ok-guard/test-diag-lock.py; '
                         'bash tests/himi-ok-guard/run.sh; bash tests/board-profile/run.sh --self-check; '
                         'python3 tests/private-usb-management/run.py')
                run(['docker', 'exec', CONTAINER, 'bash', '-lc', tests], stdout=log, stderr=subprocess.STDOUT)
                quarantine_outputs(source, output)
                run(['bash', source / 'build.sh', 'build', 'uz801'], cwd=source, env=env,
                    stdout=log, stderr=subprocess.STDOUT)
            collect(source, output, cfg, commit)
        except Exception:
            (output / 'FAILED').write_text('Candidate incomplete. Do not publish; inspect local build.log.\n')
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('prepare', help='Fetch a ref into a new checkout and apply the reviewed recipe')
    p.add_argument('--workdir', type=Path, required=True)
    p.add_argument('--upstream-ref')
    p.add_argument('--upstream-url', help='Optional mirror/cache; exact commit is always recorded')
    p = sub.add_parser('verify', help='Check source contracts without hardware or Docker')
    p.add_argument('--source', type=Path, required=True)
    p = sub.add_parser('build', help='Test, build and collect a candidate; never flash/publish/promote')
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    cfg, patch = recipe()
    if args.command == 'prepare':
        prepare(args, cfg, patch)
    elif args.command == 'verify':
        print('SOURCE_COMMIT:', verify(args.source, cfg))
    else:
        build(args, cfg)


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, subprocess.CalledProcessError, OSError) as exc:
        print('STOP:', exc, file=sys.stderr)
        sys.exit(1)

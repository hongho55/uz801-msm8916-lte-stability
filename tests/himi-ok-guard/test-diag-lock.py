#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Real Linux flock/descriptor tests; wrapper binary is a fixture, never DIAG."""
import fcntl
import os
from pathlib import Path
import shlex

import subprocess
import tempfile

source = Path(__file__).resolve().parents[2] / 'msm89xx/base-files/usr/sbin/diag_nv'
shell = shlex.split(os.environ.get('GUARD_SH', 'bash'))
with tempfile.TemporaryDirectory(prefix='diag-lock-', dir=os.environ.get('TMPDIR')) as td:
    root = Path(td)
    lock = root / 'lock'
    calls = root / 'calls'
    binary = root / 'binary'
    binary.write_text('''#!/usr/bin/env python3
import fcntl, os, sys
from pathlib import Path
with open(os.environ['TEST_LOCK'], 'a') as f:
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        pass
    else:
        sys.exit('binary ran without a held lock')
with Path(os.environ['TEST_CALLS']).open('a') as out:
    out.write('binary\\n')
''')
    binary.chmod(0o755)
    wrapper = root / 'wrapper'
    code = source.read_text().replace('DIAG_LOCK=/var/lock/himi-ok-diag.lock', 'DIAG_LOCK=' + shlex.quote(str(lock)))
    code = code.replace('exec /usr/libexec/diag_nv.bin', 'exec ' + shlex.quote(str(binary)))
    wrapper.write_text(code)
    env = dict(os.environ, TEST_LOCK=str(lock), TEST_CALLS=str(calls))

    def run_wrapper():
        return subprocess.run(shell + [str(wrapper), 'read', '2500'], env=env, capture_output=True, text=True, timeout=4)

    r = run_wrapper()
    assert r.returncode == 0, (r.stdout, r.stderr)
    print('PASS: standalone wrapper holds real flock through binary execution')
    calls.unlink()
    # A separate wrapper must wait for another process's transaction.
    with lock.open('a') as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        proc = subprocess.Popen(shell + [str(wrapper), 'read', '2500'], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            proc.wait(timeout=0.2)
        except subprocess.TimeoutExpired:
            pass
        else:
            raise AssertionError('wrapper did not wait for transaction lock')
        assert not calls.exists(), 'binary ran inside another locked transaction'
        fcntl.flock(held, fcntl.LOCK_UN)
        out, err = proc.communicate(timeout=4)
        assert proc.returncode == 0, (out, err)
    print('PASS: concurrent wrapper cannot interleave a held transaction')
    calls.unlink()
    # Inheriting fd200 must neither deadlock nor release the parent's lock.
    script = ('exec 200>' + shlex.quote(str(lock)) + '; flock -x 200; '
              + shlex.join(shell + [str(wrapper), 'read', '2500']) + ' || exit 1; '
              + shlex.quote(str(binary)) + ' || exit 1; flock -u 200')
    r = subprocess.run(shell + ['-c', script], env=env, capture_output=True, text=True, timeout=4)
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert calls.read_text().splitlines() == ['binary', 'binary']
    print('PASS: inherited lock is reused without deadlock or parent unlock')
    calls.unlink()
    failing = root / 'bin'
    failing.mkdir()
    stub = failing / 'flock'
    stub.write_text('#!/bin/sh\nexit 1\n')
    stub.chmod(0o755)
    r = subprocess.run(shell + [str(wrapper), 'read', '2500'], env=dict(env, PATH=str(failing) + ':' + env['PATH']), capture_output=True, timeout=4)
    assert r.returncode != 0 and not calls.exists()
    print('PASS: failed lock never executes binary')
    r = subprocess.run(shell + [str(wrapper), '--help'], env=env, capture_output=True, text=True, timeout=4)
    assert r.returncode == 0 and 'Usage:' in r.stdout and not calls.exists()
    print('PASS: help does not access binary')
print('5 DIAG wrapper lock cases passed; no modem access')

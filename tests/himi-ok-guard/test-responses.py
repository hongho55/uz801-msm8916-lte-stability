#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Run the real guard against synthetic DIAG replies; no device/root required."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(os.environ.get('GUARD_SOURCE', ROOT / 'msm89xx/base-files/usr/sbin/himi-ok-guard'))
HEADER = 'nvread 2500 (0x9c4): resp=137 bytes  status=0x0000'
TOKEN = b'HiMI_OK' + bytes(121)


def reply(data=bytes(128), header=HEADER):
    lines = [header]
    for i in range(0, len(data), 16):
        chunk = data[i:i + 16]
        ascii_text = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
        lines.append(f'{i:04x}  ' + ' '.join(f'{b:02x}' for b in chunk) + '  |' + ascii_text + '|')
    return '\n'.join(lines) + '\n'


zero = reply()
lines = zero.splitlines()
cases = [
    ('complete zero payload', zero, 0, True),
    ('complete existing token', reply(TOKEN), 0, False),
    ('foreign first byte', reply(b'X' + bytes(127)), 0, False),
    ('foreign final byte', reply(bytes(127) + b'X'), 0, False),
    ('empty output', '', 0, False),
    ('header only', HEADER + '\n', 0, False),
    ('one zero row', '\n'.join(lines[:2]) + '\n', 0, False),
    ('missing final row', '\n'.join(lines[:-1]) + '\n', 0, False),
    ('127 bytes', reply(bytes(127)), 0, False),
    ('129 bytes', reply(bytes(129)), 0, False),
    ('duplicate row', '\n'.join(lines + [lines[-1]]) + '\n', 0, False),
    ('wrong row offset', zero.replace('0010  ', '0020  '), 0, False),
    ('nonpadded zero offset', zero.replace('0000  ', '0  ', 1), 0, False),
    ('nonpadded row offset', zero.replace('0010  ', '10  ', 1), 0, False),
    ('missing middle row', '\n'.join(lines[:4] + lines[5:]) + '\n', 0, False),
    ('rows swapped', '\n'.join(lines[:1] + [lines[2], lines[1]] + lines[3:]) + '\n', 0, False),
    ('missing byte token', zero.replace('0000  00 ', '0000  ', 1), 0, False),
    ('extra byte token', zero.replace('0000  ', '0000  00 ', 1), 0, False),
    ('invalid hex', zero.replace('0000  00', '0000  gg', 1), 0, False),
    ('single nibble', zero.replace('0000  00', '0000  0', 1), 0, False),
    ('wrong decimal item', zero.replace('nvread 2500', 'nvread 2501'), 0, False),
    ('wrong hexadecimal item', zero.replace('0x9c4', '0x9c5'), 0, False),
    ('short response length', zero.replace('resp=137', 'resp=136'), 0, False),
    ('long response length', zero.replace('resp=137', 'resp=138'), 0, False),
    ('failed NV status', zero.replace('status=0x0000', 'status=0x0007'), 0, False),
    ('status prefix spoof', zero.replace('status=0x0000', 'status=0x00001'), 0, False),
    ('wrong command header', zero.replace('nvread ', 'nvwrite '), 0, False),
    ('duplicate header', HEADER + '\n' + zero, 0, False),
    ('trailing diagnostic line', zero + 'transport warning\n', 0, False),
    ('leading diagnostic line', 'transport warning\n' + zero, 0, False),
    ('missing ASCII delimiter', zero.replace('  |................|', '', 1), 0, False),
    ('short ASCII column', zero.replace('|................|', '|X|', 1), 0, False),
    ('contradictory ASCII column', zero.replace('|................|', '|X...............|', 1), 0, False),
    ('long ASCII column', zero.replace('|................|', '|.................|', 1), 0, False),
    ('ASCII zeroes hide foreign data', reply(bytes(127) + b'X').replace('|................|', '|0000000000000000|'), 0, False),
    ('nonzero exit with complete zeros', zero, 1, False),
    ('failed exit with existing token', reply(TOKEN), 1, False),
    ('write exit failure', zero, 0, True),
    ('lock acquisition failure', zero, 0, False),
]

with tempfile.TemporaryDirectory(prefix='himi-replies-', dir=os.environ.get('TMPDIR')) as temp:
    base = Path(temp)
    bin_dir = base / 'bin'
    bin_dir.mkdir()
    diag = bin_dir / 'diag_nv'
    diag.write_text('''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
p = Path(os.environ['FIXTURE'])
f = json.loads((p / 'fixture.json').read_text())
if sys.argv[1:] == ['read', '2500']:
    print(f['reply'], end='')
    sys.exit(f['exit_code'])
if sys.argv[1:] == ['write', '2500', '48694d495f4f4b']:
    with (p / 'writes').open('a') as out: out.write('write\\n')
    print('VERIFY: MATCH')
    sys.exit(f.get('write_exit_code', 0))
sys.exit(64)
''')
    (bin_dir / 'uci').write_text('#!/bin/sh\nexit 1\n')
    (bin_dir / 'logger').write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$FIXTURE/log"\n')
    for f in bin_dir.iterdir():
        f.chmod(0o755)
    source = SOURCE.read_text()
    assert source.count('sleep "$INTERVAL"') == 1
    shell = shlex.split(os.environ.get('GUARD_SH', 'bash'))
    for index, (name, output, exit_code, expect_write) in enumerate(cases):
        p = base / str(index)
        p.mkdir()
        (p / 'device').touch()
        (p / 'fixture.json').write_text(json.dumps({'reply': output, 'exit_code': exit_code,
                                                   'write_exit_code': int(name == 'write exit failure')}))
        guard = source.replace('DEV=/dev/rpmsg0', f'DEV={p}/device').replace('NV=/usr/sbin/diag_nv', f'NV={diag}')
        guard = guard.replace('DIAG_LOCK=/var/lock/himi-ok-diag.lock', f'DIAG_LOCK={p}/lock')
        guard = guard.replace('[ -c "$DEV" ]', '[ -e "$DEV" ]').replace('sleep "$INTERVAL"', 'break')
        (p / 'guard').write_text(guard)
        env = dict(os.environ, PATH=str(bin_dir) + ':' + os.environ['PATH'], FIXTURE=str(p))
        if name == 'lock acquisition failure':
            private_bin = p / 'bin'
            private_bin.mkdir()
            (private_bin / 'flock').write_text('#!/bin/sh\nexit 1\n')
            (private_bin / 'flock').chmod(0o755)
            env['PATH'] = str(private_bin) + ':' + env['PATH']
        result = subprocess.run(shell + [str(p / 'guard')], env=env, capture_output=True, text=True, timeout=5)
        calls = (p / 'writes').read_text().splitlines() if (p / 'writes').exists() else []
        assert result.returncode == 0, (name, result.returncode, result.stderr)
        assert len(calls) == int(expect_write), (name, 'unexpected write count', calls)
        if expect_write:
            logged_success = 'wrote HiMI_OK' in (p / 'log').read_text()
            assert logged_success == (name != 'write exit failure'), (name, 'false success log')
        print('PASS:', name)
print(f'{len(cases)} response cases passed; real parser/guard, synthetic DIAG only')

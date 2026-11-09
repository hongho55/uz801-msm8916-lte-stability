#!/usr/bin/env python3
"""Private build regressions; not a substitute for device boot verification."""
from pathlib import Path
import subprocess
r = Path(__file__).resolve().parents[2]
p = r / 'msm89xx/base-files/etc'
s = (p / 'uci-defaults/99-uz801-private-management').read_text()
init = (p / 'inittab').read_text()
assert 'ttyGS0::respawnlate:/sbin/askfirst /usr/libexec/login.sh' in init
assert 'ttyGS0::askfirst:' not in init
assert init.count('::sysinit:') == 1
assert init.count('::shutdown:') == 1
assert '99-msm89xx-firstboot' < '99-uz801-private-management'
subprocess.run(['sh', '-n', str(p / 'uci-defaults/99-uz801-private-management')], check=True)
for board in ['yiming,uz801-v3', 'jz02,other']:
    # Fixture replaces only board lookup and UCI; run the real shell script.
    harness = 'cat() { printf "%s\\n" "$TEST_BOARD"; }; uci() { command cat; };\n' + s
    import os
    result = subprocess.run(['sh'], input=harness, text=True, capture_output=True,
                            env={**os.environ, 'TEST_BOARD': board}, check=True)
    if board == 'yiming,uz801-v3':
        for setting in ["set network.modem.auto='0'", "set usbgadget.ecm.enabled='1'",
                        "set usbgadget.ncm.enabled='0'", "set network.@device[0].bridge_empty='1'",
                        "set modem-watchdog.recovery.himi_ok_boards='yiming,uz801-v3'",
                        "set modem-watchdog.recovery.himi_ok_enabled='1'",
                        "set modem-watchdog.recovery.himi_ok_interval='20'",
                        "set modem-watchdog.general.enabled='0'",
                        'commit network', 'commit usbgadget', 'commit modem-watchdog']:
            assert setting in result.stdout, setting
    else:
        assert not result.stdout, result.stdout
gadget = (r / 'packages/uci-usb-gadget/files/usb-gadget.sh').read_text()
assert 'echo "ttyGS0::respawnlate:/sbin/askfirst /usr/libexec/login.sh"' in gadget
assert 'echo "ttyGS0::askfirst:/usr/libexec/login.sh"' not in gadget
print('PASS: late-console declaration/persistence, firstboot ordering, shell syntax, UZ801 cellular-off/ECM settings, non-UZ801 guard')

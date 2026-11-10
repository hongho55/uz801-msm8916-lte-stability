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
# Execute the shipped setup/teardown functions in a redirected filesystem.
# PID1 signals, UCI and network reload are stubbed; no device is accessed.
import tempfile, shlex, re

def function(name):
    match = re.search(r'^' + name + r'\(\) \{\n.*?^\}', gadget, re.M | re.S)
    assert match, name
    return match.group(0)

with tempfile.TemporaryDirectory(prefix='usb-console-lifecycle-') as tmp:
    root = Path(tmp)
    configfs = root / 'configfs'
    configfs.mkdir()
    tab = root / 'inittab'
    tab.write_text(init)
    trace = root / 'trace'
    redirected = (function('setup_acm') + '\n' + function('teardown_gadget'))
    redirected = redirected.replace('/etc/inittab', shlex.quote(str(tab)))
    redirected = redirected.replace('/sys/kernel/config/usb_gadget', shlex.quote(str(configfs)))
    redirected = redirected.replace('/etc/init.d/network reload', 'network_reload')
    harness = '''
load_config() { :; }
log() { :; }
uci() { printf 'uci %s\\n' "$*" >> "$TRACE"; }
network_reload() { printf 'reload\\n' >> "$TRACE"; }
kill() { printf 'signal %s\\n' "$*" >> "$TRACE"; }
prepare() {
    mkdir -p "$CFG_GADGET_PATH/functions" "$CFG_CONFIG_PATH" "$CFG_GADGET_PATH/strings/0x409"
}
''' + redirected + '\n'
    env = {**os.environ, 'CFG_GADGET_PATH': str(configfs / 'g1'),
           'CFG_GADGET_NAME': 'g1', 'CFG_CONFIG_PATH': str(configfs / 'g1/configs/c.1'),
           'CFG_ACM_SHELL': '1', 'TRACE': str(trace)}
    def exercise(commands):
        subprocess.run(shlex.split(os.environ.get('USB_TEST_SHELL', 'sh')), input=harness + commands, env=env,
                       text=True, capture_output=True, check=True)
    # A subsequent boot parses this persistent file BEFORE gadget startup.
    exercise('prepare; setup_acm; teardown_gadget\n')
    assert tab.read_text() == init, 'shutdown erased the next-boot console declaration'
    for _ in range(3):
        exercise('prepare; setup_acm; teardown_gadget\n')
        assert tab.read_text() == init, 'repeated lifecycle changed persistent console policy'
    exercise('CFG_GADGET_PATH="$CFG_GADGET_PATH-absent"; teardown_gadget\n')
    assert tab.read_text() == init
    assert 'reload' in trace.read_text(), 'network teardown was not exercised'
    # Explicit shell=0 remains the separate opt-out policy, not ordinary stop.
    exercise('prepare; CFG_ACM_SHELL=0; setup_acm; teardown_gadget\n')
    assert 'ttyGS0' not in tab.read_text()
    exercise('prepare; CFG_ACM_SHELL=1; setup_acm; setup_acm; teardown_gadget\n')
    assert tab.read_text() == init, 'enable/repeated setup duplicated or lost console entry'
print('PASS: firstboot/board checks + real redirected USB lifecycle preserves next-boot console, repeated stop/start, explicit shell opt-out/enable')

#!/usr/bin/env python3
"""Validate sanitized public observations; never connects to a modem."""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
data = json.loads((root / 'docs/evidence/himi2500-20261110.json').read_text())
rows = data['samples']
assert len(rows) == data['summary']['samples'] == 40
assert len({(r['segment'], r['index']) for r in rows}) == len(rows)
assert all(r['network_up'] for r in rows)
assert all(not r['kernel_matches'] for r in rows)
assert all(not r['sampling_error'] and not r['usb_recovery'] for r in rows)
assert all(b['device_uptime_s'] >= a['device_uptime_s'] for a, b in zip(rows, rows[1:]))
assert all(b['data_uptime_s'] >= a['data_uptime_s'] for a, b in zip(rows, rows[1:]))
assert sum(r['ping_pass'] is True for r in rows) == data['summary']['ping_pass'] == 39
assert sum(r['ping_pass'] is False for r in rows) == data['summary']['ping_fail'] == 1
assert rows[0]['ping_pass'] is False and all(r['ping_pass'] for r in rows[1:])
assert rows[-1]['data_uptime_s'] == data['summary']['last_data_uptime_s'] == 2394
assert data['cleanup'] == {'network_up': False, 'pending': False, 'autostart': False,
                           'modem_state': 'disabled', 'packet_service_state': 'detached',
                           'traffic_guard_retained': True}
print('PASS: 40 distinct samples, 39 pass/1 initial fail, no observed uptime reset or selected kernel error, 2394s data uptime, verified data-off cleanup')

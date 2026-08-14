# UZ801 MSM8916 LTE stability notes

Reproducible diagnostics and recovery notes for periodic Qualcomm MPSS/ML1 failures on a UZ801 v3 running mainline-style OpenWrt.

> **Status:** mitigation verified; root cause not proven. Do not treat this repository as a firmware fix.

## Public investigation record

- [Forensic investigation and failed approaches](docs/uz801-ml1-failure-investigation-2026-08-14.md)
- [OpenStick and modem-firmware candidate audit](docs/uz801-msm8916-firmware-candidate-audit-2026-08-14.md)
- [Documentation index and privacy boundary](docs/README.md)

The `research/` directory is intentionally local-only and ignored. Raw remoteproc cores, modem/NV/QCN/EFS data, device identifiers, credentials, and unreviewed capture logs are not part of the public repository.

## Tested environment

- Board: `yiming,uz801-v3` / Qualcomm MSM8916
- OpenWrt: 25.12.5
- Kernel: 6.12.94
- ModemManager: 1.24.0-r8
- libqmi/qmicli: 1.36.0-r1
- Reported modem revision: `HIMI_U01_MODEM_V2.0 [May 13 2022 13:00:00]`
- Internal MPSS build string: `MPSS.DPM.1.0.2.c1-00142-M8936FAAAANVZM-1_20150513_025300`
- Carrier used for reproduction: KT LTE (Korea)

Identifiers, addresses, keys, SIM data, and raw crash dumps are intentionally omitted.

## Symptoms

The modem fails around the 15-minute range with one of these fatal messages:

```text
lte_ml1_common_dump.c:213: Assert 0 failed: No response from ML1. deadlock tmr
lte_ml1_common.c:324: Assert 0 failed
remoteproc remoteproc0: crash detected in 4080000.remoteproc: type fatal error
```

After subsystem restart, Linux may show a false-connected data path:

- ModemManager says `connected`;
- QMI says `registered`, `attached`, and sometimes `connected`;
- `wwan0` still has an address and route;
- but real traffic is zero or fails;
- WireGuard/other tunnels stop handshaking;
- BAM-DMUX may log `Channel already open` for channels 0-7.

OpenWrt and Wi-Fi can remain alive throughout.

## Reproduction evidence

### ModemManager path

Two clean-boot captures failed at approximately 927-930 seconds of OpenWrt/MPSS uptime:

```text
[  927.377719] ... fatal error received: lte_ml1_common_dump.c:213:Assert 0 failed: No response from ML1. deadlock tmr
[  927.377946] remoteproc remoteproc0: crash detected ...
```

```text
[  930.013065] ... fatal error received: lte_ml1_common.c:324:Assert 0 failed
[  930.013260] remoteproc remoteproc0: crash detected ...
```

The second event produced an 83,367,638-byte ELF32 remoteproc core with 21 `PT_LOAD` regions. Strings in the core confirmed:

```text
MPSS lte_ml1_common.c 00324
Error in file lte_ml1_common.c, line 324
```

The raw core is **not published** because modem memory can contain subscriber identifiers and other private data.

The dump is a synthetic remoteproc `ET_CORE` container: it has raw `PT_LOAD` memory ranges but no useful section table, symbol table, DWARF, or generic register/thread notes. It therefore confirms the MPSS build and fatal source line, but does **not** identify the running QuRT task, program counter, blocked mutex/semaphore, or deadlock owner. `Assert 0` may be the consequence of a watchdog rather than proof that the asserting task itself was deadlocked. Exact task-level analysis would require matching proprietary MPSS symbols/maps plus Qualcomm/Hexagon-aware crash tooling or additional QuRT task/register metadata.

Safe offline inspection should disable network-assisted symbol fetching and work only on an encrypted local copy:

```sh
umask 077
export DEBUGINFOD_URLS=
file mpss-core.elf
readelf -hW -lW -nW mpss-core.elf
strings -a -n 4 -t x mpss-core.elf |
  grep -Ei 'MPSS|lte_ml1|ML1|watchdog|dead|mutex|semaphore|sched|QURT|assert|error'
```

Nearby strings are only candidates: they may be firmware `.rodata` and do not prove association with the active task. Do not upload the dump to public analyzers, debuginfod, GitHub, issue trackers, or paste sites.

### Direct raw-IP QMI path

ModemManager was stopped and the connection was established with:

```sh
qmicli -d /dev/wwan0qmi0 \
  --device-open-net='net-raw-ip|net-no-qos-header' \
  --wds-start-network='3gpp-profile=3' \
  --device-open-proxy --wds-follow-network
```

In this mode no new remoteproc crash was recorded during the 16-minute run, but real traffic stopped around 15-16 minutes while QMI still reported `connected` and `attached`. RX/TX remained zero.

Adding `autoconnect=yes` was not usable on this firmware: the network start did not yield IP settings and netifd repeatedly retried. Do not assume autoconnect support merely because libqmi exposes the option.

### Pre-emptive bearer reconnect A/B

A controlled test reconnected only the ModemManager bearer at MPSS age 702 seconds. Real LTE traffic and WireGuard recovered immediately, but the modem still raised the same fatal assert at MPSS age 902 seconds:

```text
phase=after rproc_age=886 crash=1 internet=yes
phase=after rproc_age=902 crash=2 internet=no
lte_ml1_common_dump.c:213:Assert 0 failed: No response from ML1. deadlock tmr
```

This rules out periodic bearer/PDP reconnection as a workaround on the tested unit. The approximately 900-second deadline follows MPSS uptime, not bearer lifetime.

### Pre-emptive MPSS restart A/B

A controlled restart sequence stopped the tunnel and modem interface, stopped ModemManager, restarted only `remoteproc0`, then restored ModemManager, LTE, and WireGuard. It was run twice before the fatal deadline:

| Cycle | Planned restart age | Crash counter before/after | LTE result |
|---|---:|---:|---|
| 1 | 651 s | `2 → 2` | recovered on probe 4 |
| 2 | 675 s | `2 → 2` | recovered on probe 4 |

The final 90-second observation retained real LTE traffic and WireGuard, producing `PREEMPTIVE_MPSS_TWO_CYCLES_PASSED`.

This confirms that restarting MPSS resets the failing approximately 900-second epoch. It is technically usable as a preventive workaround, but it was **not installed as a recurring job**: the orderly planned restart caused roughly 30 seconds of interruption, whereas the latest natural crash plus watchdog recovery took about 8 seconds. For this vehicle-hotspot use case, planned downtime every 11 minutes was worse than recovering the failure on demand.

## What is proven vs. not proven

### Proven on the tested unit

- The stock and running `modem.mdt`, `modem.b*`, and `mba.mbn` files matched by SHA-256.
- The MPSS itself raises an ML1 fatal assert; it is not only a DNS or WireGuard problem.
- `ifstatus`, ModemManager, QMI attachment, an IP address, and a route are insufficient health checks.
- A real packet probe through `wwan0` detects the false-connected condition.
- Restarting only the modem remote processor plus ModemManager can restore LTE without rebooting OpenWrt or dropping Wi-Fi.
- On some recoveries, the kernel's BAM-DMUX state remains wedged; a full AP/OpenWrt reboot is then needed to clear `Channel already open` state.
- The modem may restore QMI profile 3 APN to `ctlte` after cold boot. On the tested KT SIM this caused `limited-regional`, registration timeout, or detach until profile 3 was repaired.
- The packaged `rmtfs` runs as `rmtfs -P -r -s`. In upstream rmtfs, `-r` means the NV partitions are copied to RAM shadow storage and modem writes are not persisted. This explains why a QMI profile change can disappear after MPSS or device restart; it does not by itself prove the ML1 crash cause.
- The live reserved-memory layout matched the upstream MSM8916 UFI layout: RMTFS `0x86700000/0xe0000`, RFSA `0x867e0000/0x20000`, and MPSS at `0x86800000` with a device-specific `0x5500000` size.

### Not proven

- This is **not proven to be a KT network fault**.
- The exact 900-second mechanism remains unknown. No public source found in this investigation directly ties this MPSS assert to a named LTE RRC/NAS timer; assigning it to T3412, a PDN lease, RF calibration, or another 3GPP timer would be speculation.
- ModemManager is not proven to be the root cause. It changes the observed failure from a silent data stall to an MPSS assert, but both paths fail near the same time range.
- No safe, validated replacement MPSS firmware has been identified.
- A cross-device modem firmware or generic NV/QCN should not be flashed based on this report.

## Important APN persistence quirk

On the tested KT subscription, profile 3 needed to contain `lte.ktfwing.com` and be selected as the LTE attach PDN. The modem sometimes restored `ctlte` at cold boot.

Inspect first:

```sh
qmicli -d /dev/wwan0qmi0 --device-open-proxy --wds-get-profile-list=3gpp
qmicli -d /dev/wwan0qmi0 --device-open-proxy --wds-get-lte-attach-pdn-list
```

The KT-specific repair used in testing was:

```sh
ifdown modem || true
MID="$(mmcli -L | sed -n 's#.*Modem/\([0-9][0-9]*\).*#\1#p' | head -1)"
mmcli -m "$MID" --disable || true
sleep 2
qmicli -d /dev/wwan0qmi0 --device-open-proxy \
  --wds-modify-profile='3gpp,3,apn=lte.ktfwing.com,pdp-type=IPV4V6,auth=NONE'
qmicli -d /dev/wwan0qmi0 --device-open-proxy --wds-set-lte-attach-pdn-list=3
mmcli -m "$MID" --enable || true
ifup modem
```

This mutates only QMI profile 3, but it is still carrier-specific. Verify your own APN before using it.

## Recovery watchdog

`scripts/ensure-lte.sh` implements the tested recovery hierarchy:

1. verify actual traffic through `wwan0`;
2. repair the expected profile only if configured and missing;
3. reconnect the bearer;
4. if the data path remains false-connected, restart ModemManager and `remoteproc0` only;
5. never reboot the whole router automatically.

Review and edit its configuration variables before installation. It assumes:

- modem interface name `modem`;
- netdev `wwan0`;
- remoteproc index `remoteproc0`;
- optional tunnel interface `wgcar`;
- ModemManager netifd protocol.

Example cron entry:

```cron
* * * * * /usr/local/sbin/ensure-lte.sh
```

The script internally rate-limits healthy probes to reduce data use.

## RMTFS and Device Tree cross-check

The tested OpenWrt image was compared against the MSM8916 UFI Device Tree and upstream `linux-msm/rmtfs` implementation.

| Item | Live value | Upstream UFI value | Result |
|---|---:|---:|---|
| RMTFS base/size | `0x86700000 / 0xe0000` | `0x86700000 / 0xe0000` | match |
| RMTFS client ID | `1` | `1` | match |
| RFSA base/size | `0x867e0000 / 0x20000` | `0x867e0000 / 0x20000` | match |
| MPSS base/size | `0x86800000 / 0x5500000` | UFI override `0x86800000 / 0x5500000` | match |
| rmtfs arguments | `-P -r -s` | upstream service `-r -P -s` | equivalent |
| BAM-DMUX | enabled | enabled by `msm8916-ufi.dtsi` | match |

Relevant source paths:

- `arch/arm64/boot/dts/qcom/msm8916.dtsi`
- `arch/arm64/boot/dts/qcom/msm8916-ufi.dtsi`
- `drivers/remoteproc/qcom_q6v5_mss.c`
- `drivers/net/wwan/qcom_bam_dmux.c`
- `linux-msm/rmtfs`: `rmtfs.c`, `storage.c`, `rmtfs.service.in`

In rmtfs, `-P` selects raw partitions, while `-r` enables read-only backing storage. The partitions are copied into RAM shadow buffers; subsequent modem writes update the shadow, not `modemst1/2` on eMMC. This is why a QMI profile modification can appear successful and then disappear after MPSS restart. Removing `-r` would make modem NV writes persistent and was **not** done during this investigation.

No reserved-memory, RMTFS client-ID, partition-label, or firmware-file mismatch was found that explains the periodic ML1 assert.

## Capturing a remoteproc core safely

The tested kernel exposed:

```text
/sys/kernel/debug/remoteproc/remoteproc0/coredump
/sys/kernel/debug/remoteproc/remoteproc0/recovery
/sys/class/devcoredump/devcdN/data
```

Check memory first. The MSM8916 modem core can be tens of megabytes:

```sh
free -m
cat /sys/kernel/debug/remoteproc/remoteproc0/coredump
cat /sys/kernel/debug/remoteproc/remoteproc0/recovery
```

Enable one capture while keeping recovery enabled:

```sh
echo enabled > /sys/kernel/debug/remoteproc/remoteproc0/coredump
```

After a crash, copy the core locally with restrictive permissions:

```sh
umask 077
dd if=/sys/class/devcoredump/devcdN/data of=/secure/path/mpss-core.elf bs=1M
sha256sum /secure/path/mpss-core.elf > /secure/path/mpss-core.elf.sha256
```

Then disable collection and release the devcoredump:

```sh
echo disabled > /sys/kernel/debug/remoteproc/remoteproc0/coredump
echo 1 > /sys/class/devcoredump/devcdN/data
```

Do **not** publish a raw MPSS core, `modemst1/2`, `fsg`, QCN/EFS dumps, or unredacted logs.

## Safe firmware inspection

Read-only checks used in this investigation:

```sh
sha256sum /lib/firmware/modem.mdt /lib/firmware/modem.b* /lib/firmware/mba.mbn
strings /lib/firmware/modem.b* | grep -E 'QC_IMAGE_VERSION|MPSS\.DPM' | sort -u
qmicli -d /dev/wwan0qmi0 --device-open-proxy --dms-get-revision
```

Before any firmware experiment, preserve and verify the full eMMC plus at least:

- `modem`, `mba`/boot firmware as applicable;
- `modemst1`, `modemst2`, `fsg`, `fsc`;
- bootloader chain and partition table.

Never replace radio calibration/NV with another unit's copy.

## Next useful experiments

- Same SIM and location under the original Android userspace.
- Same device and image with a different carrier SIM.
- RF-quality-controlled test to separate poor RSRQ/SNR from the periodic timer.
- DIAG/QXDM-compatible ML1/NAS logging, if a safe DIAG endpoint can be exposed.
- Symbol-aware analysis by someone with the matching proprietary MPSS map/symbol package.

## Related upstream material

- Linux remoteproc framework: https://docs.kernel.org/staging/remoteproc.html
- Qualcomm remoteproc coredump guidance: https://dragonwingdocs.qualcomm.com/System/Kernel/configure-the-remoteprocessor-remoteproc-subsystems
- OpenWrt ModemManager package history: https://github.com/openwrt/packages/commits/openwrt-25.12/net/modemmanager/
- UZ801 fork reporting ModemManager/QMI quirks: https://github.com/ImMALWARE/uz801-openwrt
- Linux MSM8916 modem remoteproc driver: https://github.com/torvalds/linux/blob/v6.12/drivers/remoteproc/qcom_q6v5_mss.c

## License and warranty

MIT. No warranty. Modem firmware, NV, SIM service, and remoteproc operations can leave a device offline. Keep a verified full backup and a physical recovery path.

# UZ801: guarded HiMI_OK / NV2500 experiment — 2026-11-10

**Result: promising single-device experiment, not a universal or long-term fix.** The installed image kept its LTE data connection up to **2,394 seconds (39 min 54 s)** without an observed MPSS fatal or uptime reset. The final sampled OpenWrt uptime was **3,028.50 seconds**. Cellular data was explicitly disabled after the trial.

## Credit and investigation continuity

Thank you to **@akbar-npj**, who opened [our issue #1](https://github.com/hongho55/uz801-msm8916-lte-stability/issues/1) and pointed us to [msm8916-openwrt issue #5](https://github.com/akbar-npj/msm8916-openwrt/issues/5). The HiMI_OK idea, DIAG utility and guard originate in that upstream project; they are **not discoveries made by this repository**. Our contribution here is the exact-device integration, management/build corrections, guarded installation and a limited independent observation on this UZ801.

The August investigation remains a dated record, not a statement of the current evidence. In particular, this new experiment is different from reconnecting a bearer or periodically restarting MPSS. No preventive restart was used during this trial.

## Device and image identity

- Board compatible: `yiming,uz801-v3`; existing `yiming-uz801v3` profile reused.
- Reported modem: `HIMI_U01_MODEM_V2.0`.
- MPSS build: `MPSS.DPM.1.0.2.c1-00142-M8936FAAAANVZM-1_20150513_025300`.
- Measured eMMC: 7,634,944 sectors / 3,909,091,328 bytes. Do not assume all devices sold as UZ801 have this size or layout.
- Built OpenWrt: `25.12.6-r8`, `r33311-981c978eff`; kernel `6.12.112`; ModemManager `1.24.0-r11`.
- Firmware/BSP source commit: [`f8afa82620e9092a5b717be3ceabd763920a2008`](https://github.com/hongho55/uz801-msm8916-lte-stability/tree/f8afa82620e9092a5b717be3ceabd763920a2008), preserved on `firmware/uz801-himi2500-experiment`.
- Upstream BSP base: `akbar-npj/msm8916-openwrt` commit `487dfc0` (full object identity is in the source history).

## What was changed, and what was not

1. **UIM recognition is not fatal prevention.** The R9-equivalent ModemManager UIM-status fallback helped recognition/connectivity, but did not fix the approximately 15-minute fatal. A pre-opt-in management-image test still reproduced `lte_ml1_common_timer.c:390: Assert 0 failed` at approximately 919 seconds. An earlier cold-boot capture had `lte_ml1_common.c:324` at MPSS age 917.043768 seconds. These clocks and experiments are not interchangeable.
2. **USB management:** persistent `ttyGS0::respawnlate:/sbin/askfirst /usr/libexec/login.sh`, including the gadget-generated entry; ACM serial and ECM enabled, NCM disabled. USB serial access was exercised. Do not infer that macOS USB Ethernet routing has been fully validated.
3. **Builder fixes:** Linux filesystem volumes for OpenWrt tmp/build/staging permissions on a virtiofs host share; an existing Go 1.18 bootstrap on Linux ARM64; overlay entries copied individually.
4. **Exact-board experiment:** firstboot explicitly opts `yiming,uz801-v3` into the existing upstream HiMI_OK guard, every 20 seconds. UZ801 is not included in our fallback/global board list. That firstboot opt-in means this image **can write NV2500 automatically after installation/boot**.
5. **Data-cost defaults:** `network.modem.auto=0` and `modem-watchdog.general.enabled=0`. The HiMI_OK polling service is separate from the disabled bearer-recovery watchdog. Connecting for the trial was manual.
6. **Storage profile:** the source records this unit's measured `GPT_TOT_SECTORS=7634944`. Installation did **not** rewrite the device GPT.

The patch relative to the upstream BSP base is [here](patches/uz801-himi2500-f8afa82.patch). It is upstream-derived GPL work; see [GPL-2.0](patches/COPYING-GPL-2.0). The root documentation repository's MIT license does not relicense the firmware, upstream code, patch or packaged components.

## NV2500 evidence and safety limits

Before this opt-in experiment, an independent DIAG read of item **2500** returned status `0x0000` and a complete **128-byte all-zero payload**. After boot, the guard logged `item 2500 was cleared; wrote HiMI_OK`. A separate DIAG read returned status `0x0000` and began:

```text
48 69 4d 49 5f 4f 4b 00 00 00 00 00 00 00 00 00
 H  i  M  I  _  O  K
```

The full after-write payload transfer was interrupted by a user unplug/replug. **No independently verified full post-write payload hash is claimed.** That physical reconnection happened before the final continuous trial; it is not evidence of automatic recovery or a spontaneous firmware reboot.

The existing guard skips failed reads, an already-present token and parsed non-zero foreign content; it serializes DIAG with a lock and checks the write utility's verification result. These safeguards do **not** establish that generic factory-data item 2500 is safe on another modem. They are not a complete NV integrity guarantee. Do not copy NV/QCN/EFS/calibration data between devices, and do not blindly write this item based on a model name.

## Installation scope actually exercised

A complete device backup was retained privately before experimentation. Software EDL entry using `/sbin/reboot-mode-raw edl` was observed as USB `05c6:9008`. Only the intended boot/rootfs prefix ranges and an approximately 2 MiB rootfs-data reset were written, with readback. Protected GPT/radio/NV/bootloader/tail ranges compared equal to a fresh pre-write scoped backup **before first boot**. The first-boot NV2500 write is an explicit, separate mutation and is not covered by that pre-boot preservation statement.

The release contains standalone **boot** and **system/squashfs** images, **not a universal flashing package**. It contains no GPT image, full eMMC dump, modem firmware, modemst/fsg/persist backup, NV/QCN, subscriber data or device-specific installer. They are not demonstrated LuCI sysupgrade inputs. Use only a verified board/layout-specific recovery procedure; never flash a whole disk or calibration partition from these notes. The image has a development USB shell/default account state: secure credentials and management access before ordinary use. The experiment does not validate use on other UZ801 variants.

## Low-data trial: measured results

The two monitor segments sampled the **same** live LTE connection. The first monitor was deliberately killed for handoff; its `-9` exit was not an MPSS crash. The second completed normally and performed cleanup. No sampling USB recovery was needed.

- First segment: 19 samples, 18 successful pings and **one initial failed ping**.
- Second segment: all 21 expected samples collected; 21 successful pings.
- Combined: **40 distinct samples, 39 successes, 1 initial failure, 0 unavailable samples**. This is sampled reachability, not proof of zero packet loss between samples.
- Last netifd connection uptime: **2,394 seconds**; sampled observation span: **2,341.95 seconds**.
- Device uptime and data-interface uptime were non-decreasing across every sample and the handoff.
- No matches in the collected kernel filter `fatal|Assert 0|Channel already open`. This is not an unfiltered full-log audit.
- Final `wwan0` counters: RX **3,444 bytes**, TX **3,772 bytes**. These are interface counters, **not carrier-billed usage**.
- Traffic guard allowed only a paced ICMP echo to `1.1.1.1` through `wwan0`, dropped other output through that interface, and blocked forwarded WWAN traffic.
- Cleanup readback: interface `up=false`, `pending=false`, `autostart=false`; modem `disabled`; packet service `detached`. Traffic guard retained.

[Sanitized machine-readable samples](evidence/himi2500-20261110.json) are included. Validate locally with:

```sh
python3 scripts/validate-himi2500-evidence.py
```

**What this supports:** the guarded image crossed this unit's previously failing approximately 15-minute window and maintained sampled reachability up to 39 min 54 s of data connection uptime.

**What it does not establish:** causality isolated by repeated on/off A/B testing; stability across repeated cold boots or warm SSR; performance under sustained traffic; overnight reliability; full independent NV readback; or safety/effectiveness on every V2.0/UZ801 modem. A successful short trial is not a reason to remove the experimental label.

## Build source and verification

The exact firmware/BSP commit above is published separately from the documentation branch so the original build history is retained. Build inputs used:

- OpenWrt: `64900e756efa667774214f9c6b17c113222e01f7` (`openwrt/openwrt`).
- Feed luci: `75a306df84a020c57a631ef5b4c02ace56d93387` (`openwrt/luci`).
- Feed packages: `093d551675b1119a06ef224d419905e8d6b2af1a` (`openwrt/packages`).
- Feed routing: `48c808034414a2112cf9d5261a20a320e8d0d170` (`openwrt/routing`).
- Feed telephony: `2618106d5846a4a542fdf5809f0d3ed228ce439b` (`openwrt/telephony`).
- Feed video: `094bf58da6682f895255a35a84349a79dab4bf95` (`openwrt/video`).

Checkout the exact BSP commit, follow its build/devenv instructions, create the three named external Docker volumes, pin the OpenWrt checkout/feeds to the identities above, then build `./build.sh build uz801`. The original full build succeeded; the release reuses those exact installed/tested image bytes, rather than claiming a new or byte-reproducible rebuild. Preserve component licenses and obtain upstream package sources corresponding to the supplied package manifest; source refs alone are not a substitute for reviewing component distribution obligations.

Pre-publication reruns on the unchanged source:

- `sh tests/himi-ok-guard/run.sh`: **25 passed, 0 failed**.
- `bash tests/board-profile/run.sh --self-check`: **45 passed, 0 failed, 3 skipped**. Run with bash, not sh. The general shared-file diff gate was not run because this invocation did not specify a base ref; the regression fixtures were exercised.
- `python3 tests/private-usb-management/run.py`: passed.
- Boot/system/package-manifest byte counts and SHA-256 matched the original build manifest.
- Extracted release system image: no pre-generated SSH/dropbear host private keys, no populated root home, no modem firmware blobs; only `regulatory.db` under `lib/firmware`. Network/wireless configuration is generated at boot, not copied from the test device.

## Next useful evidence

Repeat cold boots and a longer bounded-data test; observe warm modem restarts separately; obtain a complete independent post-write NV read without triggering unnecessary writes. Only a carefully approved reversible A/B design could isolate the NV predicate on this exact modem build. Do not disable the guard for an unsupervised test or alter proprietary modem code merely to obtain a stronger headline.

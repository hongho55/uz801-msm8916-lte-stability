# UZ801 candidate f00a436 — partial hardware qualification (2026-11-10)

**Channel: candidate / prerelease. Not stable. One device, one short trial.**

> **Historical image-qualification snapshot:** the findings below describe the original published f00a436 image and initial restart attempt. Later script-only overlay tests confirmed Wi-Fi management during failures and narrower USB recovery, but did not fix warm-reboot console reliability. See the [latest USB-console / vehicle-use follow-up](uz801-usb-console-vehicle-followup-2026-11-10.md). The full dbe882c image was not installed; the old release assets and measurements are unchanged.

Target: `yiming,uz801-v3`, modem `HIMI_U01_MODEM_V2.0`, 7,634,944-sector eMMC only.

## What was installed

Candidate built from `firmware/uz801/recipe.json` + `downstream.patch` (source commit `f00a436`), not the earlier experimental binary. The previous experiment is preserved unchanged. Install used EDL writes limited to boot, rootfs and the first 2 MiB of rootfs_data, each read back; GPT, modem, NV and bootloader partitions were not written. A full eMMC backup and a scoped pre-write backup (read twice, hashes equal) were taken first.

## Finding that changed the guard

The bundled `diag_nv` printed `resp=136` for the existing `HiMI_OK`+121 zero payload, while earlier all-zero reads printed `resp=137`. `resp=N` is the byte count returned by `read(2)` on `/dev/rpmsg0`, not the decoded payload length. The cause of the one-byte difference is **not established**. The guard now accepts exactly two shapes: 137 with an all-zero 128-byte payload (write-eligible) and 136 with exactly `HiMI_OK`+121 zeros (read-only). Other record sizes are rejected; size137 foreign/nonzero values are left untouched. Neither existing tokens nor foreign data are write-eligible. 42 synthetic response cases pass, including real BusyBox ash/awk.

## NV2500

Pre-install and post-boot payloads have the same SHA-256. The guard log for this boot reports `item 2500 was cleared; wrote HiMI_OK`; the zero state before that write was not independently captured, so the state transition is taken from the guard log only.

## Low-data trial

29 of a planned 41 once-a-minute samples (stopped early by the operator at about 28 minutes): 29 ping successes, 0 failures, device uptime monotonic from 423 s to 2104 s, no selected fatal/assert/BAM lines. The earlier baseline failed at about 907-919 s of modem uptime; this run passed that point. Traffic was limited to ICMP to one address; the modem was disabled afterward.

## Software restart / USB console blocker

One ordinary software restart was attempted on this candidate. USB ACM enumerated again, but the console stayed silent for more than ten minutes; a host-side USB reset did not recover it. A fresh S20 scan saw the same AP with an age of a few seconds, supporting continued Wi-Fi beaconing, not proving DHCP, SSH, web or modem health. Mac ECM connectivity was never established before this attempt either: do not label its absence a new restart regression.

The earlier management image has a separate private record of the same software-restart symptom. This is not yet a controlled comparison with unmodified upstream.

### Code-level lead (not a device-confirmed root cause)

[Upstream USB-gadget teardown](https://github.com/akbar-npj/msm8916-openwrt/blob/main/packages/uci-usb-gadget/files/usb-gadget.sh) removes `ttyGS0` from `/etc/inittab`, then sends SIGHUP to PID1. The candidate source `packages/uci-usb-gadget/files/usb-gadget.sh` retains that removal. On next startup the gadget script adds the entry again, but the actual built procd reads inittab before sysinit; its `signal.c` routes SIGHUP to `sa_dummy`, not an inittab reload. This gives a concrete mechanism for a present USB ACM device without a spawned console. The post-restart inittab was not read on the device, so the mechanism is still a hypothesis. It does not explain or prove a Mac ECM driver fault.

The upstream [UZ801 recovery PR #80](https://github.com/akbar-npj/msm8916-openwrt/pull/80) reports a successful reboot from recovery to OpenWrt; that is a different path and not proof that the production USB console survives ordinary restart. Upstream sysupgrade teardown documentation concerns upgrade-time modem/RMTFS lockups, not a confirmed match to this symptom.

**No fix, replacement image, additional restart, modem cycle or handset DHCP/DNS/web test was performed after finding this lead.** Physical recovery is pending. This release must remain a prerelease, not deployment-ready.

## Not shown

Not tested: repeated cold boots, handset DHCP/DNS/web use, a run as long as the earlier 39m54s observation, overnight stability, or an A/B comparison on this image. This is not evidence of a root-cause fix or of behavior on other UZ801 variants. `build-info.json` keeps `hardware_validated=false`.

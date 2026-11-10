# UZ801 candidate f00a436 — partial hardware qualification (2026-11-10)

**Channel: candidate / prerelease. Not stable. One device, one short trial.**

Target: `yiming,uz801-v3`, modem `HIMI_U01_MODEM_V2.0`, 7,634,944-sector eMMC only.

## What was installed

Candidate built from `firmware/uz801/recipe.json` + `downstream.patch` (source commit `f00a436`), not the earlier experimental binary. The previous experiment is preserved unchanged. Install used EDL writes limited to boot, rootfs and the first 2 MiB of rootfs_data, each read back; GPT, modem, NV and bootloader partitions were not written. A full eMMC backup and a scoped pre-write backup (read twice, hashes equal) were taken first.

## Finding that changed the guard

The bundled `diag_nv` printed `resp=136` for the existing `HiMI_OK`+121 zero payload, while earlier all-zero reads printed `resp=137`. `resp=N` is the byte count returned by `read(2)` on `/dev/rpmsg0`, not the decoded payload length. The cause of the one-byte difference is **not established**. The guard now accepts exactly two shapes: 137 with an all-zero 128-byte payload (write-eligible) and 136 with exactly `HiMI_OK`+121 zeros (read-only). Everything else is rejected. 42 synthetic response cases pass, including real BusyBox ash/awk.

## NV2500

Pre-install and post-boot payloads have the same SHA-256. The guard log for this boot reports `item 2500 was cleared; wrote HiMI_OK`; the zero state before that write was not independently captured, so the state transition is taken from the guard log only.

## Low-data trial

29 of a planned 41 once-a-minute samples (stopped early by the operator at about 28 minutes): 29 ping successes, 0 failures, device uptime monotonic from 423 s to 2104 s, no selected fatal/assert/BAM lines. The earlier baseline failed at about 907-919 s of modem uptime; this run passed that point. Traffic was limited to ICMP to one address; the modem was disabled afterward.

## Not shown

Not tested: repeated cold boots, handset DHCP/DNS/web use, a run as long as the earlier 39m54s observation, overnight stability, or an A/B comparison on this image. This is not evidence of a root-cause fix or of behavior on other UZ801 variants. `build-info.json` keeps `hardware_validated=false`.

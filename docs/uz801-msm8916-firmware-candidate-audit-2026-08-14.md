# UZ801/MSM8916 modem-firmware candidate audit

**As of:** 2026-08-14
**Question:** Does OpenStick modify the MPSS modem firmware, and is there a newer compatible candidate for the tested UZ801/MSM8916 unit?

## Direct conclusion

No public image inspected here is a proven newer, exact-board-compatible replacement for the tested MPSS. The newest 2026 UZ801 OpenWrt releases are primarily AP OS, boot, GPT, and boot-chain releases; their firmware bundles do **not** contain `modem.mdt`/`modem.bXX` MPSS files. The OpenStick workflow normally uses the device's own stock modem partition/files rather than rebuilding or patching the proprietary ML1 binary.[12][13][14][15][26][27][28]

The closest offline comparison candidate is the public `uz801_v3.0_stock_new` full dump. Its modem partition is materially different, but its MBA identifies an older/different MPSS family (`MPSS.DPM.1.0.1.c1-00121...20150907`) than the tested baseline (`MPSS.DPM.1.0.2.c1-00142...20150513`). It is therefore **not established as an upgrade** and remains analysis-only / NO-GO for flashing.[9][29]

## What OpenStick actually changes

### Official OpenStick v1

The official v1 release includes a `firmware-uz801.zip` package with a 2021-era set of `mba.mbn`, `modem.mdt`, and split `modem.bXX` files. Offline inspection found 22 modem/MBA entries. The embedded MBA build path is `MPSS.DPM.1.0.r6-00002-M8916EAAAANVZM-1_20140714_075522`, which is older than the tested baseline. More importantly, the v1 release note explicitly says that the UZ801 modem was unavailable/not working in that release.[1][24]

The generic `base-generic.zip` package contains boot/GPT/partition and radio-state files, but no `modem.*` MPSS split set.[25]

### Current OpenWrt-style UZ801 flashing

The latest inspected ImMALWARE UZ801 release, `openwrt-2` published 2026-07-25, contains a firmware ZIP with exactly five `.mbn` files:

```text
aboot.mbn
hyp.mbn
rpm.mbn
sbl1.mbn
tz.mbn
```

It contains no `modem.mdt`, `modem.bXX`, or `mba.mbn`.[13][26]

Its flash script writes GPT, those boot-chain files, boot, and rootfs, then backs up/restores `fsc`, `fsg`, `modemst1`, `modemst2`, `modem`, and `persist`. It does not replace the modem MPSS partition with a new binary.[12][27]

The newer `hkfuertes/msm8916-openwrt` UZ801 release `v1.0.14` (2026-07-06) has the same shape: an OpenWrt UZ801 image plus a five-file boot-chain firmware bundle, not a new MPSS split image.[14][15][28]

**Result:** OpenStick/OpenWrt changes the AP kernel/rootfs, bootloader/boot chain, partition layout, and userspace/QMI integration. It may ship or copy a modem blob for convenience, but the inspected current implementation does not demonstrate a modified ML1/MPSS binary.

## Candidate comparison

| Candidate | Public date | Offline content/result | Relationship to tested MPSS | Decision |
|---|---:|---|---|---|
| Tested stock baseline | device baseline | `mba.mbn` build `MPSS.DPM.1.0.2.c1-00142...20150513`; 22 split entries | Reference | Keep immutable |
| OpenStick v1 `firmware-uz801.zip` | 2022 release; modem files dated 2021-12 | 22 split entries; MBA `MPSS.DPM.1.0.r6-00002...20140714` | Older | Reject as upgrade |
| OpenStick `stick-blobs/stock-uz801` | repository last activity 2022 | 64 MiB stock modem partition; its extracted 22 modem/MBA files are byte-identical to the official v1 package | Same old public stock set | Not newer; stock reference only |
| Mio `uz801_v3.0_stock_new` | Stock release 2022-11-18 | 64 MiB modem partition; files dated 2022-04-20; MBA `MPSS.DPM.1.0.1.c1-00121...20150907` | Different/older family than current `1.0.2.c1-00142` | Best offline comparison candidate, not a flash candidate |
| ImMALWARE `openwrt-2` | 2026-07-25 | Boot-chain `.mbn` only; no MPSS split files | Does not change modem firmware | AP/OS A/B only |
| hkfuertes `v1.0.14` | 2026-07-06 | OpenWrt UZ801 image plus boot-chain bundle; no MPSS split files | Does not change modem firmware | AP/OS A/B only |
| LongQT OpenStick Builder `v1.2` | 2025-06-04 | Debian/OpenStick image release; no proof of a newer exact-board MPSS | Unknown / likely stock-file dependent | Not a modem candidate |
| asvdvl UZ801 v3.0 stuff | 2024 releases | Board-specific community image/releases; no newer MPSS build proven | Unknown | Reference only |
| OpenStick issue #69 “v3.4.33” | issue, not firmware release | A user request for firmware; comments describe donor firmware, country-specific modem behavior, IMEI/NV problems, and no confirmed resolution | Unsafe donor provenance | Reject |

Public UZ801 documentation repeatedly warns that board revisions and stock modem files differ, and recommends copying `modem.*`, `mba.mbn`, and region-specific `mcfg_sw.mbn` from the device's own stock image.[3][20][21]

## Important evidence from the requested issue #69

Issue #69 is not a release of a `v3.4.33` modem. It is a support request. The thread shows a downloaded donor dump, a statement that the default modem only worked for the Philippines, later IMEI/NV persistence problems, and no confirmed resolution.[4]

That is directly relevant to this investigation: a modem partition can be “accepted” by a flashing tool while still being the wrong country/board/NV combination. It is not evidence that the donor MPSS fixes an ML1 deadlock.

## Why the public stock candidates are not automatically safer

The public `stick-blobs` repository labels its material as stock blobs, not a repaired MPSS build.[6][7] It also documents that Qualcomm modem NV partitions (`fsg`, `fsc`, `modemst1`, `modemst2`) are encrypted with a SoC-unique key and are not generally shareable between devices.[8]

The current unit's modem image has an exact current-stock executable mapping and a captured ML1 fatal. Replacing only `modem.*`, mixing a donor MCFG, or carrying donor NV would destroy the clean baseline and could create a second problem that looks like a fix or a new failure.

## Firmware-search result

**No newer exact-compatible MPSS candidate was found in the bounded public search.**

The public candidates fall into three classes:

1. **Older modem sets:** OpenStick v1/stock blobs and the Mio v3.0 stock dump.
2. **Newer AP distributions with no modem MPSS:** 2026 OpenWrt builds.
3. **Unverified or donor dumps:** issue/forum/community images with board, country, MCFG, or NV uncertainty.

This does not prove that no vendor-only image exists. It means no public candidate inspected here has enough provenance to be called a safe update for this exact board and baseline.

## Safe next step

Before any runtime A/B, keep the current stock image immutable and perform only:

1. extract `modem.mdt`, `mba.mbn`, all split `modem.bXX`, and region MCFG from each public candidate;
2. compare ELF/PT_LOAD layout, ISA flags, build identifiers, sizes, hashes, and all split coverage;
3. classify whether the candidate is an actual MPSS replacement or only boot/AP firmware;
4. check exact board/HW revision and modem/NV provenance;
5. preserve rollback, GPT, loader, partition map, calibration, and NV boundaries;
6. do not flash until authentication/checksum and same-device recovery are independently verified.

The current result remains **candidate-only / NO-GO**. No candidate has been installed, and no firmware/NV bytes were modified.

## Sources

[1] https://github.com/OpenStick/OpenStick/releases/tag/v1
[3] https://github.com/OpenStick/OpenStick/issues/46
[4] https://github.com/OpenStick/OpenStick/issues/69
[6] https://github.com/OpenStick/stick-blobs
[7] https://github.com/OpenStick/stick-blobs/tree/main/stock-uz801
[8] https://github.com/OpenStick/stick-blobs/issues/1
[9] https://github.com/Mio-sha512/openstick-stuff/releases/tag/Stock
[12] https://github.com/ImMALWARE/uz801-openwrt
[13] https://github.com/ImMALWARE/uz801-openwrt/releases/tag/openwrt-2
[14] https://github.com/hkfuertes/msm8916-openwrt
[15] https://github.com/hkfuertes/msm8916-openwrt/releases/tag/v1.0.14
[20] https://wvthoog.nl/openstick
[21] https://github.com/u0d7i/uz801
[24] https://github.com/OpenStick/OpenStick/releases/download/v1/firmware-uz801.zip
[25] https://github.com/OpenStick/OpenStick/releases/download/v1/base-generic.zip
[26] https://github.com/ImMALWARE/uz801-openwrt/releases/download/openwrt-2/openwrt-msm89xx-msm8916-yiming-uz801v3-firmware.zip
[27] https://github.com/ImMALWARE/uz801-openwrt/releases/download/openwrt-2/openwrt-msm89xx-msm8916-yiming-uz801v3-flash.sh
[28] https://github.com/hkfuertes/msm8916-openwrt/releases/download/v1.0.14/openwrt_firmware_uz801_v25.12.5_202607062022.zip
[29] https://github.com/Mio-sha512/openstick-stuff/releases/download/Stock/uz801_v3.0_stock_new.zip

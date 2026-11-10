# Investigation documents

This directory contains the sanitized, public record of the UZ801/MSM8916 LTE stability investigation.

- [`uz801-usb-console-vehicle-followup-2026-11-10.md`](uz801-usb-console-vehicle-followup-2026-11-10.md) — latest script-only live tests, remaining USB TX failure, narrow recovery, and unverified cold-boot/vehicle-use boundaries; not a stable release.
- [`uz801-candidate-f00a436-qualification-2026-11-10.md`](uz801-candidate-f00a436-qualification-2026-11-10.md) — original f00a436 image qualification snapshot; 29/29 pings and known restart limitation, with a link to the later follow-up.
- [`uz801-himi2500-experiment-2026-11-10.md`](uz801-himi2500-experiment-2026-11-10.md) — earlier single-device guarded NV2500 experiment, final 39 min 54 s connection observation, source/patch identity, installation boundaries and verified data-off cleanup.

- [`uz801-ml1-failure-investigation-2026-08-14.md`](uz801-ml1-failure-investigation-2026-08-14.md) — reproducible failure timeline, experiments, forensic findings, failed approaches, and the current patch gate.
- [`uz801-msm8916-firmware-candidate-audit-2026-08-14.md`](uz801-msm8916-firmware-candidate-audit-2026-08-14.md) — OpenStick implementation review and public modem-firmware candidate audit.
- [`uz801-follow-up-research-closure-2026-08-14.md`](uz801-follow-up-research-closure-2026-08-14.md) — sanitized synthesis of the repeated-epoch evidence, completed/blocked experiments, offline forensic follow-up, and closure decision.

## Privacy boundary

The repository intentionally excludes raw remoteproc cores, unrestricted modem strings, subscriber identifiers, NV/QCN/EFS/modemst/fsg/fsc/persist data, credentials, private network details, and device-specific recovery artifacts. Hashes and metadata are retained only where they do not expose those materials.

A candidate image is not a fix. No firmware mutation or flash is authorized by these documents.

The November experimental release contains clean build outputs (standalone boot/system images and package manifest), not dumps of the device or its NV. Its upstream-derived firmware source/patches retain GPL/component licensing, separate from the MIT documentation. Publishing an experiment does not authorize installing it on another device.

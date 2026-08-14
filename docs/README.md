# Investigation documents

This directory contains the sanitized, public record of the UZ801/MSM8916 LTE stability investigation.

- [`uz801-ml1-failure-investigation-2026-08-14.md`](uz801-ml1-failure-investigation-2026-08-14.md) — reproducible failure timeline, experiments, forensic findings, failed approaches, and the current patch gate.
- [`uz801-msm8916-firmware-candidate-audit-2026-08-14.md`](uz801-msm8916-firmware-candidate-audit-2026-08-14.md) — OpenStick implementation review and public modem-firmware candidate audit.

## Privacy boundary

The repository intentionally excludes raw remoteproc cores, unrestricted modem strings, subscriber identifiers, NV/QCN/EFS/modemst/fsg/fsc/persist data, credentials, private network details, and device-specific recovery artifacts. Hashes and metadata are retained only where they do not expose those materials.

A candidate image is not a fix. No firmware mutation or flash is authorized by these documents.

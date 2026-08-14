# UZ801 follow-up research and closure — 2026-08-14

## Status

This document is the sanitized public synthesis of the follow-up work performed after the initial ML1 failure report. The raw research workspace remains local-only; this file contains conclusions, experiment classification, and safety decisions rather than raw modem data.

**Bottom line:** the failure was narrowed substantially, but it was not repaired. The stock modem firmware remains the only approved firmware, firmware mutation remains **NO-GO**, and the UZ801 was demoted from a primary gateway to a research/backup device.

## Executive findings

### 1. The approximately 900-second recurrence is real, but the cause is not decoded

The retained same-device timeline contains at least 30 natural MPSS fatal/recovery events. Across the observed boots and recovered modem epochs, failures recur mainly around approximately **901.5–914.8 seconds of recovered MPSS age**. The events span ML1 common-timer, common-dump, sleep/idle-state-machine, and related assert paths.

This is stronger evidence for a recurring stock-MPSS/ML1 epoch condition than for a one-time Linux uptime coincidence. It does **not** identify the proprietary predicate, mailbox, mutex owner, missing response, RF/NAS trigger, or initiating transport fault.

`BAM-DMUX Channel already open` messages repeatedly followed SSR recovery. They are retained as a recovery complication; no evidence proves that BAM-DMUX initiated the original ML1 fatal.

### 2. No valid causal A/B pass exists

The nominated idle/keepalive versus continuous-small-uplink A/B was not started. The required passive DIAG/QMDL gate failed closed because the inspected device exposed AT/QMI and NCM paths but no already-exposed passive GM/PHY capture path or usable capture tool.

Therefore:

- valid nominated samples: **0A + 0B**;
- valid no-fatal runs reaching the 1,200–1,250 second gate: **0**;
- no claim can be made that traffic, sleep, RF, or uplink scheduling prevents the fatal.

A no-fatal interval without the required trace would be censored/weak evidence, not a firmware fix.

### 3. Completed experiments and their actual meaning

| Investigation | Result | What it establishes |
|---|---|---|
| Single-AP-CPU/offline-CPU run | Failed; ML1 fatal still occurred | CPU offlining is not a sufficient mitigation |
| Direct raw-IP QMI path | False-connected/zero-traffic behavior observed | Changes failure presentation; does not prove prevention |
| Pre-emptive bearer reconnect | Traffic recovered temporarily; fatal recurred near the same MPSS-age boundary | Bearer/PDP lifetime is not a sufficient workaround |
| Two pre-emptive MPSS restart cycles | Both restored service during a short follow-up window | Restart resets the failing MPSS epoch; recovery evidence only, not a cure |
| Clean AP/OpenWrt reboot fallback | Restored service after modem-only recovery failed; recurrence returned on the next boot | AP reboot can clear a recovery-state failure; it does not fix ML1 |
| QCRIL-like NAS/WDS indication test | Not run | qmicli does not expose the required direct registration actions, and prior-mask/CID restoration was not proven safe |
| Thermal/input-power A/B | Not run | Thermal and power remain unresolved hypotheses, not findings |
| Donor-firmware override | Not run; all inspected donors remain NO-GO | No compatible, exact-board, repeatedly validated replacement was identified |

The two-cycle MPSS restart result is a practical epoch-reset observation, not evidence supporting a periodic preventive restart. Planned interruption was materially longer than the observed natural recovery in the tested case, and no 1,200-second causal validation was obtained.

## Offline forensic follow-up

### Natural core capture

One complete raw MPSS core was captured at a natural fatal without inducing a crash. It was retained privately and analyzed read-only. The public record contains no raw core bytes, unrestricted strings, subscriber data, or private hashes.

The capture confirmed:

- a valid ELF32/QDSP6 remoteproc core;
- correlation with the observed natural fatal and SSR;
- successful restoration of the temporary capture state;
- no evidence that the capture itself caused the failure.

### Hexagon and core comparison

The crash PC/LR map into the exact stock executable region and decode coherently with a Hexagon V5 decoder. Relocation-aware comparison also placed public MSM8916 ML1 timer, dump, and Grant Manager objects into structurally corresponding regions of the stock image.

The newer natural-fatal core identifies the `LTE_CPHY_CON_RELE` request at a **request-specific reporting call site** with high confidence. A second core reaches a different generic reporting branch. Both incidents share common fatal/report machinery, but the comparison does not prove one common upstream request or predicate.

Patching the shared fatal/report routine would suppress reporting rather than restore a missing response, release ML1 state, repair a mailbox, or provide safe continuation semantics. Patching the request-specific call would likewise hide one report path without repairing the deadlock.

**Patch decision: analysis-only / NO-GO.** No instruction mutation, runtime override, or flash is justified.

### Public role evidence

Public Qualcomm/Android/QMI material supports interpreting `ML1 GM` as the LTE ML1 Grant Manager path, involving uplink scheduling, control channels, and sleep-related state. This is role and protocol evidence only. It does not transfer a predicate or fix from another chipset, firmware build, or modem family to this UZ801.

## Firmware compatibility conclusion

The candidate audit covered the public UZ801/OpenStick and other MSM8916-derived firmware collections. No candidate met all of the required conditions:

- exact UZ801 board/revision provenance;
- coherent modem/MBA/load-map lineage;
- compatible authentication and memory bounds;
- matching region/carrier configuration provenance;
- repeated same-device stability beyond the failure boundary;
- rollback evidence.

The target's stock/current set is the only approved set, even though it is the known failing baseline. Donor MPSS, MCFG, NV/QCN/EFS, modemst/fsg/fsc, partition, boot-chain, and `/lib/firmware` changes remain prohibited.

## Operational closure

After the investigation was stopped, automation was explicitly decommissioned rather than left running unattended:

- UZ801 root cron entries were removed;
- `crond`, the LTE fast watcher, quota automation, and the measurement observer were stopped and disabled;
- related Hermes UZ801 scheduled jobs were removed;
- no firmware, NV, MCFG, QCN/EFS, partition, DIAG, QMI-mask, or boot-chain mutation was made;
- the UZ801 is treated as a research/backup device, not a primary always-on gateway.

The earlier watchdog/recovery experiments remain documented as historical mitigation evidence. They must not be read as the current device configuration after this closure.

## What remains unresolved

The following are explicitly **not** answered by this investigation:

- the exact proprietary ML1 timeout predicate and response owner;
- whether LTE scheduling, sleep/DRX, RF/network state, thermal behavior, input power, runtime-PM, or transport state modulates the race;
- whether a vendor firmware revision exists that fixes this exact board/build;
- whether a safe passive DIAG/QMDL path can ever be exposed without a state-changing configuration action;
- whether a controlled thermal/power A/B would shift the boundary.

The thermal/power experiment was intentionally left pending and was not silently converted into a result.

## Public/private boundary

Publicly retained:

- sanitized failure timeline and forensic interpretation;
- sanitized firmware candidate audit;
- this follow-up synthesis and closure decision.

Kept local-only:

- raw remoteproc cores and crash logs;
- modem blobs, firmware archives, extracted images, NV/QCN/EFS/modemst/fsg/fsc material;
- device-specific identifiers, endpoints, credentials, and unrestricted research outputs.

The local `research/` directory is ignored by Git and was not uploaded. The temporary candidate/analysis workspaces were removed separately; preserving the private research workspace is intentional so the public record does not become the only copy of the investigation evidence.

## Related public documents

- [Initial ML1 failure investigation](uz801-ml1-failure-investigation-2026-08-14.md)
- [MSM8916 firmware candidate audit](uz801-msm8916-firmware-candidate-audit-2026-08-14.md)
- [Public documentation index and privacy boundary](README.md)

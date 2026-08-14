# UZ801/MSM8916 periodic ML1 fatal — sanitized investigation record

**Date:** 2026-08-14
**Status:** mitigation verified; root cause and a safe permanent firmware fix remain unproven.

## Executive result

The tested UZ801/MSM8916 unit repeatedly enters this broad failure pattern:

```text
MPSS starts
  -> approximately 900–930 seconds of MPSS uptime
  -> ML1 fatal/deadlock report
  -> remoteproc subsystem restart (SSR)
  -> QMI may look attached while real traffic is dead
  -> recovery restores LTE or leaves BAM-DMUX wedged
```

A natural-fatal remoteproc core was captured without inducing a crash. Its materialized report identified:

```text
lte_ml1_common_dump.c:213
No response from ML1. deadlock tmr expiry on LTE_CPHY_CON_RELE
request = 0x040c0206
task = ML1 MGR
```

That is a high-confidence identification of the **request-specific reporting branch**, not proof of the upstream producer, missing mailbox response, timeout predicate, mutex owner, or safe continuation.

## Tested baseline

- Board: `yiming,uz801-v3`
- SoC: Qualcomm MSM8916 / QDSP6 modem
- OpenWrt: 25.12.5
- Kernel: 6.12.94
- ModemManager: 1.24.0-r8
- libqmi/qmicli: 1.36.0-r1
- Current MPSS/MBA baseline: `MPSS.DPM.1.0.2.c1-00142-M8936FAAAANVZM-1_20150513_025300`
- Reported modem revision: `HIMI_U01_MODEM_V2.0`

The exact device identifiers, SIM data, raw core, unrestricted dump strings, and private recovery paths are intentionally omitted.

## What was tried

### 1. Basic health checks were insufficient

After SSR, Linux and userspace could report a healthy-looking connection:

- ModemManager: connected;
- QMI: registered/attached/occasionally connected;
- `wwan0`: address and route present;
- actual packets: zero or failing;
- tunnels: no handshake.

The investigation therefore used a real packet probe through `wwan0`, not QMI state alone.

### 2. Userspace/QMI isolation

ModemManager was stopped and the direct raw-IP qmicli path was tested. It avoided a newly logged remoteproc fatal during one bounded run, but real traffic still stopped around the same 15–16 minute region while QMI continued to report attached/connected. This was not accepted as a fix: the observation was censored and did not show a pre-fatal causal difference.

### 3. Bearer reconnection A/B

The bearer was reconnected before the expected deadline. Traffic recovered temporarily, but the modem still raised the same fatal at approximately the same MPSS age. This showed that the deadline follows the MPSS epoch rather than the bearer lifetime.

### 4. Planned MPSS restart A/B

A controlled restart of only `remoteproc0`, with ModemManager and LTE restored afterward, reset the failure epoch twice and restored real traffic. It caused roughly 30 seconds of interruption and was not installed as a recurring job because on-demand SSR recovery was shorter for the tested vehicle-hotspot workload.

This is a mitigation, not a firmware repair.

### 5. Natural-fatal core capture

A bounded capture window enabled the normal remoteproc coredump mode, temporarily isolated only the LTE recovery watchdog that would have removed the evidence, and waited for the next natural fatal. No forced crash, firmware/NV change, DIAG/QMDL session, QMI indication-mask write, or artificial modem workload was used.

The capture produced one complete private ELF32 remoteproc core:

- size: `83,367,638` bytes;
- ELF32 little-endian `ET_CORE`;
- 21 program headers / non-empty `PT_LOAD` regions;
- raw bytes retained privately and not committed or uploaded.

The original coredump mode, watchdog, crontab, remoteproc recovery, LTE route, traffic, and management tunnel were restored and read back after capture.

## Offline forensic result

### Exact-image mapping

The current stock `modem.mdt`, `mba.mbn`, and split `modem.bXX` files were frozen and re-hashed before and after analysis: 22/22 entries remained identical. The captured PC/LR mapped through the MDT into the exact current `modem.b16` executable bytes.

The captured registers were:

```text
PC = 0xc08983e4
LR = 0xc0896d04
```

Hexagon V5 decoding placed both addresses in common crash-context/report machinery. The PC is an epilogue/return area, not the original assert instruction.

### Request-specific branch

The bounded captured stack contained the return address immediately after the request-specific report call:

```text
0xc0459294 -> call 0xc0896cf0
return     = 0xc04592a0
comparison = request 0x040c0206
```

The common target `0xc0896cf0` is reached by multiple timer/dump fatal classes. It is therefore not a safe global patch point.

### Two-core comparison

The earlier private core and the new natural-fatal core shared:

- complete ELF layout;
- exact PC/LR pair in current stock `modem.b16`;
- common crash-report return path;
- `BADVA=0` and `ELR=0`;
- the same file-backed/runtime-mutated segment classification.

They differed in:

- source line and message detail;
- reported task (`ML1 GM` versus `ML1 MGR`);
- TCB/SP/FP/report descriptor;
- generic report branch versus the new `LTE_CPHY_CON_RELE` branch.

The earlier core does not preserve a request identity. Therefore the two incidents are not proven to be the same request, and variation is not proven either.

## Failed approaches and why they were rejected

### IDA Pro/MCP

The installed environment did not contain a usable licensed IDA runtime/`libidalib.so`, and no live IDA endpoint was available. No license bypass or unofficial patcher was used.

### Public AMSS source/object material

Public material provided useful structural reference objects and relocations, but not the exact current source/build/linker context. It cannot establish the current proprietary predicate or a safe rebuild.

### Generic fatal suppression

NOPing or bypassing the shared fatal target could turn a visible recoverable SSR into a silent stuck ML1/GM state, false-connected bearer, later memory corruption, or a different fatal. The request-specific call at `0xc0459294` only reports the timeout; it does not create the missing response or release the state machine.

### Public donor firmware

Different UZ801/UF896/UFI revisions, MCFG regions, NV, calibration, and board layouts make donor images unsafe. LTE attach or a short successful boot is not compatibility proof.

### “No crash” as a fix

A run that ends before the fatal deadline, or only changes userspace, is censored evidence unless it passes the full timed runtime, real-traffic, recovery, and rollback gates.

## What is proven

- The tested modem firmware itself raises an ML1 fatal/deadlock report.
- The natural-fatal request-specific branch is `LTE_CPHY_CON_RELE` (`0x040c0206`).
- The common PC/LR addresses are report machinery, not the original deadlock predicate.
- QMI/ModemManager state alone can be falsely healthy.
- A real traffic probe detects the false-connected condition.
- Restarting only the modem subsystem can restore LTE without rebooting the AP in some cases.
- The stock image was not mutated; no firmware flash was performed.

## What remains unknown

- Which producer issued `LTE_CPHY_CON_RELE`;
- which ML1/PHY mailbox or state transition failed;
- whether the response was lost or the responder was wedged;
- the exact timeout predicate and recovery contract;
- whether the trigger is firmware logic, MCFG/NV/RF/power/thermal coupling, or a cross-layer event;
- whether any public firmware candidate fixes this exact board/build.

## Current decision

**Analysis-only / NO-GO for firmware mutation, runtime override, or flash.**

The next high-value evidence would be passive ML1/GM telemetry, an exact-build vendor change with provenance, or multiple comparable cores that preserve the producer/state transition. A safe candidate must pass offline packet/ELF/load-map/authentication checks, same-device rollback, and repeated timed runtime validation before any deployment discussion.

## Public artifact boundary

Not published:

- raw private cores or unrestricted crash logs;
- IMEI/IMSI/ICCID, QCN/NV/EFS/modemst/fsg/fsc/persist data;
- credentials, private IPs, or management details;
- loader/recovery packages whose disclosure is unnecessary;
- any modified modem image.

The repository contains only sanitized conclusions and read-only analysis helpers.

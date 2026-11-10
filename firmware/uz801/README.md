# Repeatable UZ801 downstream releases

새 upstream 릴리즈가 나오면 **소스 ref 지정 → 검토한 패치 적용 → 회귀 테스트 → 빌드 → 이미지/출처/체크섬 수집**을 반복합니다. 이미 배포된 바이너리를 임의로 뜯어 고치는 도구가 아니며, 자동 플래시·자동 공개·자동 정식 승격은 하지 않습니다.

## Scope

This recipe targets the measured `yiming,uz801-v3` / `HIMI_U01_MODEM_V2.0` experiment, not all hardware sold as UZ801. The profile assumes 7,634,944 eMMC sectors. Boot can automatically write NV2500 through the opted-in guard. Cellular autoconnect and bearer-recovery watchdog remain disabled. Development USB-shell/default account state must be secured before ordinary deployment.

The original [experimental release](https://github.com/hongho55/uz801-msm8916-lte-stability/releases/tag/uz801-himi2500-experiment-20261110) is preserved. Its 39m54s observation applies to its original image, **not automatically to a newly built candidate**.

## USB-console source follow-up

The recipe now targets source `dbe882c`: ordinary gadget teardown preserves the persistent console inittab entry. The redirected real setup/teardown regression reproduced the loss on f00a436 and passes with this change, including repeated cycles and explicit shell opt-out/enable under Linux sh and candidate BusyBox ash. The collector additionally compares the packaged USB-gadget script against source (five critical members total). Script-only overlay tests on the f00a436 base still reproduced warm-reboot console failures; Wi-Fi management remained alive and one ACM data-interface reset could recover output. The complete dbe882c image was not installed or hardware-qualified. The published f00a436 prerelease remains unchanged and does not include this fix. See the [USB-console / vehicle-use follow-up](../../docs/uz801-usb-console-vehicle-followup-2026-11-10.md); no stable promotion or periodic USB reset is included. USB Ethernet investigation is deferred.

## Prerequisites

- Python 3, Git, Docker with Compose; one builder at a time.
- A **case-sensitive** source filesystem: Linux or a case-sensitive APFS volume on macOS. Upstream has case-distinct `Docs`/`docs` paths; ordinary macOS storage can create symlink loops. The tool checks before cloning and refuses warnings during source-status audit.
- Upstream's Docker build dependencies/image (`./build.sh image` for first setup), adequate disk space and network access for package sources. The existing source build system is reused, not reimplemented.
- Three named Docker volumes are created/reused for OpenWrt tmp/build/staging. Their caches are not removed. The tool refuses to commandeer an existing `openwrt-builder` mounted from a different source checkout; stop that checkout's builder explicitly before switching.

## Commands

Run from this documentation repository. `SOURCE_DIR` must be a new path on a case-sensitive filesystem; `OUT_DIR` must be a new directory outside the source tree.

```sh
# 1. Prepare the tested upstream commit from recipe.json (safe first reproduction).
python3 scripts/uz801-release.py prepare --workdir "$SOURCE_DIR"

# 2. Check clean tracked source and the critical source/DIAG contracts.
python3 scripts/uz801-release.py verify --source "$SOURCE_DIR"

# 3. Run the real regressions and upstream build, then inspect and collect images.
python3 scripts/uz801-release.py build --source "$SOURCE_DIR" --output "$OUT_DIR"
```

For the next upstream release, use another **new** checkout and an explicitly selected upstream tag or commit:

```sh
python3 scripts/uz801-release.py prepare \
  --upstream-ref "$UPSTREAM_TAG_OR_COMMIT" --workdir "$NEW_SOURCE_DIR"
python3 scripts/uz801-release.py build --source "$NEW_SOURCE_DIR" --output "$NEW_OUT_DIR"
```

A source mirror/cache can be supplied with `--upstream-url`; the resolved upstream commit, not a moving tag alone, is recorded. A local mirror is useful for repeated testing without refetching the same upstream objects.

## What stops an upgrade

- Existing destination, modified tracked files, filesystem warnings or a wrong repository root. Untracked **and ignored** files in the audited BSP/package/overlay/patch/config/script/build-environment input directories are rejected too; unrelated research Docs and generated OpenWrt caches are not blanket-deleted.
- Tampered recipe patch checksum, a patch that no longer applies, or changed critical files/DIAG utility. There is no force/fuzzy-patch/old-version fallback.
- Regression failure, build failure, missing images, or source changes during the build.
- Prior boot/system/manifest outputs are quarantined under `previous-build-local-only/` before make runs, so all three must be recreated. The rebuilt system's extracted guard, DIAG wrapper, firstboot, inittab and USB-gadget script must match source. This is targeted member/provenance validation, **not** a byte-for-byte audit of the complete filesystem or a proof of reproducible binaries.
- A concurrent recipe build; the shared builder is host-locked. Do not also launch unrelated manual builds into the same cache while this tool runs.

On an incompatible upstream version, review the upstream changes, port the smallest required patch, rerun regressions, update the recipe checksums and try again in a fresh checkout. **Do not remove checks to make an upgrade pass.** Critical file hashes intentionally require explicit review when the DIAG format or guard changes.

## NV2500 hardening included

The guarded read must succeed as a process and match the bundled utility's complete output contract: item2500/0x9c4, observed rpmsg read-record size137, status0x0000, eight ordered rows0000..0070, sixteen valid hex bytes each, total128bytes, and exact 16-character ASCII columns consistent with those bytes. Wrong/short/extra/ambiguous output is read-only. Existing tokens and foreign payloads are not rewritten. No DIAG cycle is run without a successful lock; a failed write process is not logged as verified success.

The synthetic response suite covers 42 cases. Hardware preflight found a valid136-byte read record for the exact HiMI_OK+121zero payload; that one captured value is accepted read-only. All-zero write eligibility remains size137 only. The tool reports read(2) record bytes, not normalized NV payload length; the136/137 difference has not been attributed to CRC/escaping. The prior parser was observed attempting a write on a one-row all-zero fixture; the hardened parser rejects that case. These are **fixture tests**, not real-device NV experiments. Both ordinary Linux tools and the candidate rootfs's BusyBox ash/awk were exercised. The standalone guard harness requires Linux `flock`; use the builder rather than assuming an unmodified macOS host has it. Its redirected device fixture does not test the real character-device gate or long-running retry timing. A failed lock skips that DIAG cycle and is retried later; fail-closed does not mean the daemon exits. The parser is deliberately coupled to the bundled utility; a changed format must be reviewed rather than guessed.

## Hardware status of the current candidate

See [partial qualification of the earlier f00a436 image](../../docs/uz801-candidate-f00a436-qualification-2026-11-10.md): 29/29 pings over ~28 minutes on one device. The recipe now targets dbe882c; those earlier measurements do not qualify the full dbe882c image. Still a candidate, not stable.

## Candidate output

The normal `diag_nv` wrapper now acquires the same real flock and reuses the guard's inherited descriptor, keeping the read/check/write transaction exclusive without deadlocking or unlocking its parent. Five Linux lock tests cover standalone use, competing callers, inherited-descriptor lifetime, failed locking and help-only behavior; the tests were also run with candidate BusyBox ash. Direct invocation of the underlying binary or another raw DIAG client can bypass this convention and **must** honor the same lock; this is not a modem-side atomic compare-and-swap.

- Original build outputs: standalone boot/system images and package manifest.
- `bsp-source.tar.gz`: tracked source at the built commit, excluding upstream research `Docs/`; no private device capture.
- `COPYING-BSP`, the final `openwrt.config`, `build-info.json`, `SHA256SUMS`.
- `build.log`: **local diagnostic only**, intentionally excluded from the checksum/distribution allow-list because raw build paths/logs have not been privacy-reviewed.
- `previous-build-local-only/`: preserved old generated outputs, never part of the release allow-list.

`build-info.json` always starts as `channel=candidate`, `hardware_validated=false`. It records the exact BSP/OpenWrt/feed commits, recipe/patch/runner identity, builder image ID and image-member checks. OpenWrt/package-feed sources are not bundled in the BSP archive; obtain the matching source repositories and review all component licenses before binary distribution. The MIT documentation license does not relicense GPL firmware/patches; [GPL-2.0 text](../../docs/patches/COPYING-GPL-2.0) is preserved.

A failed run leaves a `FAILED` marker and available logs. Do not publish that directory or reuse it as a successful candidate. Output directories are immutable-by-workflow: use a fresh path for another attempt.

## Qualification and publication are separate

Before making a new candidate stable: establish the exact board/layout and recoverable backup, independently read the full NV payload, repeat supervised cold boots and warm modem restarts, test an actual client/DHCP/DNS/data path, and perform a cost-safe longer observation. Keep WWAN traffic guards, an independent off timer and data-off readback. Do not run billable overnight traffic under an assumed budget. Do not force a fatal or rewrite modem firmware/GPT/calibration to get stronger evidence.

Then publish a **new** version/tag with explicitly chosen files and measured results. Verify remote commits/assets and downloaded checksums. Keep old experimental releases and their evidence intact. This tool deliberately does not merge branches, upload releases, promote a prerelease or touch a device.

## Tests for the recipe tool

```sh
# Hardware/network-free: temporary synthetic Git repositories and stale-image fixtures.
# On macOS, point this at a case-sensitive directory.
UZ801_TEST_TMPDIR="$CASE_SENSITIVE_TEMP_PARENT" python3 scripts/test-uz801-release.py
```

The tests exercise real Git prepare/commit/provenance, compatible and incompatible future-upstream fixtures, patch tampering, dirty/changed contracts, invalid refs, preservation of existing destinations and stale-image rejection. They do not simulate a successful firmware build or claim hardware stability.

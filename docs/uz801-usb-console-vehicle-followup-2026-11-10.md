# USB-console and vehicle-use follow-up — 2026-11-10

**Status: investigation / experimental prerelease only. No stable promotion.**

This report updates the earlier [f00a436 qualification snapshot](uz801-candidate-f00a436-qualification-2026-11-10.md). It separates observed USB-console failures from router boot failure and from untested vehicle power cycles. Results concern one `yiming,uz801-v3` / `HIMI_U01_MODEM_V2.0` device, not every product sold as UZ801.

## Exact image and source boundaries

- The published [f00a436 prerelease](https://github.com/hongho55/uz801-msm8916-lte-stability/releases/tag/uz801-candidate-f00a436-20261110) and its binary/checksum assets remain unchanged. They do **not** contain the later teardown fix.
- The tested unit still runs the `f00a436cac1e1294b7a4015db0a1e551b6a28b98` base image. Only its live `/usr/sbin/usb-gadget` overlay was replaced with the exact script from source [`dbe882c425c9efb74c2716580a648f27520c8aa8`](https://github.com/hongho55/uz801-msm8916-lte-stability/commit/dbe882c425c9efb74c2716580a648f27520c8aa8).
- This script preserves the persistent `ttyGS0` inittab entry during teardown. Redirected lifecycle tests pass under Linux sh and candidate BusyBox ash, but that fix alone does not make live console recovery reliable.
- A complete dbe882c candidate was built and its listed artifact hashes and five critical image members checked. That full image was **not installed**. Script-only overlay testing is not qualification of the complete image; `hardware_validated=false` remains appropriate.
- The follow-up made no EDL, partition-table, bootloader, modem-firmware, NV/calibration or full-image writes. No kernel patch was installed.

## Bounded observations

Cellular data and automatic modem startup were kept disabled for these USB-only trials. No additional long LTE soak was performed.

- **Patched script, composite ACM+ECM:** first two warm reboots recovered console at approximately 44.98 s and 82.45 s. The third did not recover in the configured 150-second observation window or a later 35-second probe.
- **Delayed host open:** on one reboot, the USB node returned at 37.02 s. The host left it unopened for 90 seconds and opened at 127.59 s; console and data-off readback succeeded. One pass does not establish that rapid port polling caused the failures.
- **ACM only, ECM temporarily disabled:** first two warm reboots recovered at 65.48 s and 65.66 s; the third again failed in the configured 150-second window. Removing USB Ethernet is not a sufficient fix. This comparison stopped at the failing ACM-only arm; it was not a completed two-arm A/B study.
- **Original composite configuration restored:** a later bounded repeat passed at 64.67 s and 43.52 s, then failed on the third reboot in the configured 150-second window. The repeated pattern is an observation, not proof of an inherent every-third-boot mechanism.

These timings include host-side observation/checks, not a controlled measurement of kernel boot duration. Each three-reboot sequence has a failure; none is a three-of-three qualification pass. The separate delayed-open observation is only a single pass.

## What remains alive when the console is silent

An independent phone Wi-Fi management path obtained DHCP connectivity and read the running board, uptime and boot identity over HTTP/ubus. The `ttyGS0` inittab entry and its ash process were present, and the USB controller reported configured.

A command sent from the Mac through the silent USB console actually created a marker file on the device, independently read over Wi-Fi. Host readback remained empty. This demonstrates working host-to-device command execution in that failure while the device-to-host console return path was not working. It is not evidence that the router itself failed to boot.

This establishes DHCP and local management in those failures, **not** general client DNS, internet access or vehicle-ready LTE operation.

## Narrow recovery and controller evidence

- A host XON probe did not recover output.
- Restarting only the TTY ash process produced a new shell but did not clear the failed TX queue or restore console output.
- Endpoint GET_STATUS reported no halt; that does not prove queued transfers are progressing.
- A single standard `SET_INTERFACE` request selecting alternate setting 0 on the descriptor-verified ACM data interface restored console output without rebooting the device or unbinding the whole UDC. This narrower recovery succeeded in two separately observed failures, including after restoring the original composite configuration.
- ChipIdea debugfs and read-only controller-register observations found **16 outstanding ACM EP1 TX requests while EP1 TX was neither primed nor active**, with no pending TX completion bit at capture. The first queued dTD remained ACTIVE while later descriptors had inactive/completed tokens. After interface-level recovery, the EP1 TX software queue was empty and actual serial command/readback worked.

These are adjacent observations, **not an atomic DMA snapshot**. A QH current pointer may retain the last completed dTD even after a queue is empty. A clear completion register does not prove no completion interrupt occurred earlier. The evidence does not establish queue corruption, a particular hardware erratum, a Mac-driver root cause, or the origin of the first missed transfer.

Live ID-register bits, interpreted using upstream v6.12.112 `ci_get_revision`, map to the source's 1.x classification rather than the 2.2/2.4 conditions of the existing reprime workarounds. This is a source-derived interpretation, not a direct read of the running kernel's `ci->rev` field. Blindly broadening those retry conditions would not be an evidence-backed production fix.

Relevant public source and candidate research:

- [Linux v6.12.112 ChipIdea enqueue/dequeue](https://github.com/gregkh/linux/blob/v6.12.112/drivers/usb/chipidea/udc.c)
- [ACM interface reconnect path](https://github.com/gregkh/linux/blob/v6.12.112/drivers/usb/gadget/function/f_acm.c)
- [Serial disconnect/connect and write buffering](https://github.com/gregkh/linux/blob/v6.12.112/drivers/usb/gadget/function/u_serial.c)
- [Upstream dTD link-logic patch discussion](https://www.spinics.net/lists/linux-usb/msg261645.html): a related guard exists in v6.13 and is absent from the compared v6.12.112 code. It is a review candidate, **not an applied or hardware-proven fix for this device**.

No periodic interface reset, automatic USB-recovery daemon or host-side recovery utility was installed or published as a solution. Manual recovery is not a firmware stability pass.

## Vehicle-use interpretation / 차량 사용 판단

차량 USB 전원이 실제로 차단됐다 다시 공급되면 소프트웨어 재부팅이 아니라 완전 전원 재연결 조건입니다. 차량·포트에 따라 주차 중에도 전원이 유지될 수 있으므로, 시동 상태만으로 전원 차단을 가정하면 안 됩니다.

이번 결과는 **소프트 재부팅 뒤 USB 관리 콘솔이 불안정하다**는 증거이지, 완전 전원 재연결 뒤 차량용 공유기가 정상 동작한다는 증거도, 동작하지 않는다는 증거도 아닙니다.

Priority for vehicle qualification:

1. Establish whether the intended vehicle port actually removes power, and check repeated supervised complete power-off/on recovery.
2. Verify Wi-Fi AP return, client DHCP and local management on that power path.
3. Only with an explicitly authorized data budget, verify LTE startup and actual client DNS/internet traffic. Current data-off settings intentionally prevent this; do not call it an LTE startup failure or silently enable data.
4. Retain the warm-reboot USB-console limitation in the release notes. Treat it separately from successful cold-boot/vehicle tests, if those are obtained later.

Vehicle cold-boot qualification, normal handset DNS/web traffic and unattended deployment security remain incomplete. Do not add speculative kernel changes or periodic resets merely to remove this limitation from the checklist. A Mac-attached recovery method is not a standalone vehicle recovery design.

## Publication and safety decision

Keep the existing release experimental/prerelease, preserve its immutable binary provenance, and publish this sanitized investigation separately. Do not advertise a resolved USB-console problem, a fully qualified dbe882c image, stable vehicle operation or unattended deployment readiness.

The tested unit was left with working console, the original USB configuration restored, cellular interface down, autostart disabled and ModemManager startup disabled. These are live test-unit settings, not a claim that all future boots or every downloaded image have been checked. Management defaults still require hardening before ordinary use. Existing NV2500 opt-in/write warnings continue to apply.

Raw device logs, USB serials, boot UUIDs, process/memory addresses, private networks, credentials, subscriber information and recovery backups are intentionally excluded from this public report.

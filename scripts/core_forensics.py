#!/usr/bin/env python3
"""Read-only, sanitized Qualcomm MPSS ELF/MDT forensic extractor.

The output is metadata and labelled crash context only. It deliberately does not
emit arbitrary dump strings, binary bytes, SIM/NV data, or full task memory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import mmap
import os
import re
import struct
from pathlib import Path
from typing import Any

ELF32_HEADER = "<16sHHIIIIIHHHHHH"
PHDR = "<IIIIIIII"
PT_LOAD = 1


def parse_elf(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    with path.open("rb") as f:
        data = f.read()
    if len(data) < struct.calcsize(ELF32_HEADER) or data[:4] != b"\x7fELF":
        raise ValueError(f"not ELF: {path}")
    h = struct.unpack_from(ELF32_HEADER, data, 0)
    if h[0][4] != 1 or h[0][5] != 1:
        raise ValueError("expected ELF32 little-endian")
    header = {
        "class": 32,
        "data": "little",
        "type": h[1],
        "machine": h[2],
        "version": h[3],
        "entry": h[4],
        "phoff": h[5],
        "shoff": h[6],
        "flags": h[7],
        "phentsize": h[9],
        "phnum": h[10],
        "shentsize": h[11],
        "shnum": h[12],
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
    }
    phdrs: list[dict[str, Any]] = []
    for i in range(h[10]):
        vals = struct.unpack_from(PHDR, data, h[5] + i * h[9])
        t, off, vaddr, paddr, filesz, memsz, flags, align = vals
        phdrs.append({
            "index": i,
            "type": t,
            "offset": off,
            "vaddr": vaddr,
            "paddr": paddr,
            "filesz": filesz,
            "memsz": memsz,
            "flags": flags,
            "align": align,
        })
    return header, phdrs


def hx(n: int | None) -> str | None:
    return None if n is None else f"0x{n:08x}"


def printable_flat(data: bytes) -> str:
    return "".join(chr(x) if 32 <= x < 127 else " " for x in data)


def match_text(flat: str, pattern: str) -> str | None:
    m = re.search(pattern, flat, flags=re.I)
    return m.group(1).strip() if m else None


def int_from_hex(text: str | None) -> int | None:
    if not text:
        return None
    try:
        return int(text, 16)
    except ValueError:
        return None


def locate(addr: int, loads: list[dict[str, Any]], include_mem: bool = False) -> dict[str, Any] | None:
    for seg in loads:
        end = seg["paddr"] + (seg["memsz"] if include_mem else seg["filesz"])
        if seg["paddr"] <= addr < end:
            delta = addr - seg["paddr"]
            return {
                "segment": seg["index"],
                "paddr": hx(addr),
                "offset": hx(seg["offset"] + delta),
                "segment_start": hx(seg["paddr"]),
                "delta": hx(delta),
            }
    return None


def locate_vaddr(addr: int, loads: list[dict[str, Any]], include_mem: bool = False) -> dict[str, Any] | None:
    """Map a QDSP6 virtual address against modem.mdt program headers."""
    for seg in loads:
        end = seg["vaddr"] + (seg["memsz"] if include_mem else seg["filesz"])
        if seg["vaddr"] <= addr < end:
            delta = addr - seg["vaddr"]
            return {
                "segment": seg["index"],
                "vaddr": hx(addr),
                "mdt_file_offset": hx(seg["offset"] + delta),
                "segment_vaddr": hx(seg["vaddr"]),
                "physical_address": hx(seg["paddr"] + delta),
                "physical_address_int": seg["paddr"] + delta,
                "delta": hx(delta),
            }
    return None


def report_context(core: Path, core_loads: list[dict[str, Any]], mdt_loads: list[dict[str, Any]]) -> dict[str, Any]:
    with core.open("rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
        # The firmware contains a static format string named "ERR crash log
        # report" early in .rodata.  Prefer the materialized report that also
        # contains the labelled "Error in file" record.
        anchors = []
        pos = 0
        while True:
            pos = mm.find(b"ERR crash log report", pos)
            if pos < 0:
                break
            anchors.append(pos)
            pos += 1
        def report_score(x: int) -> int:
            # Materialized records follow their report marker.  Static format
            # strings elsewhere in .rodata often precede the marker and must
            # not win merely because the surrounding window contains labels.
            window = mm[x : min(len(mm), x + 0x10000)]
            labels = (
                b"Error in file",
                b"Error message:",
                b"Time of crash",
                b"Uptime",
                b"Build ID:",
                b"REX_TCB ptr:",
                b"tcb.task_name:",
                b"Coredump ARCH type",
                b"Register values",
            )
            return sum(label in window for label in labels)

        anchor = max(anchors, key=report_score, default=-1)
        if anchor < 0:
            return {"found": False}
        window = bytes(mm[anchor : min(len(mm), anchor + 0x10000)])
        flat = printable_flat(window)
        fields: dict[str, Any] = {
            "found": True,
            "file_offset": hx(anchor),
            "report_version": match_text(flat, r"ERR crash log report\.\s+Version\s+(\d+)"),
            "error_file": match_text(flat, r"Error in file\s+(.+?)\s+Error message"),
            "error_message": match_text(flat, r"Error message:\s*(.+?)\s+Time of crash"),
            "time_of_crash": match_text(flat, r"Time of crash\s*\(m-d-y h:m:s\):\s*(.+?)\s+Uptime"),
            "uptime": match_text(flat, r"Uptime\s*\(h:m:s\):\s*(.+?)\s+Build ID"),
            "build_id": match_text(flat, r"Build ID:\s*(.+?)\s+REX_TCB"),
            "tcb_task_name": match_text(flat, r"tcb\.task_name:\s*(.+?)\s+Coredump ARCH"),
            "arch": match_text(flat, r"Coredump ARCH type is:\s*(.+?)\s+Register values"),
        }
        tcb_text = match_text(flat, r"REX_TCB ptr:\s*(0x[0-9a-f]+)")
        fields["tcb_ptr"] = tcb_text
        tcb_addr = int_from_hex(tcb_text) or -1
        fields["tcb_mapping"] = locate(tcb_addr, core_loads, include_mem=True)
        regs: dict[str, str] = {}
        for name, value in re.findall(r"(QDSP6_[A-Z0-9_]+)\s*:\s*(0x[0-9a-f]+)", flat, flags=re.I):
            regs[name] = value.lower()
        mapped_regs = {}
        for name, value in regs.items():
            number = int(value, 16)
            virtual = locate_vaddr(number, mdt_loads, include_mem=True)
            physical = locate(number, core_loads, include_mem=True)
            if virtual:
                physical = locate(virtual["physical_address_int"], core_loads, include_mem=True)
                virtual.pop("physical_address_int", None)
            mapped_regs[name] = {
                "value": value,
                "core_physical_mapping": physical,
                "mdt_virtual_mapping": virtual,
            }
        fields["registers"] = mapped_regs
        fields["end_dog_report_present"] = "End Dog Report" in flat
        fields["data_err_present"] = "DATA ERR" in flat
        return fields


def mapped_words(core: Path, core_loads: list[dict[str, Any]], address: int, radius: int = 0x800) -> dict[str, Any]:
    with core.open("rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
        loc = locate(address, core_loads, include_mem=False)
        if not loc:
            return {"address": hx(address), "mapped": False}
        off = int(loc["offset"], 16)
        lo = max(0, off - radius)
        hi = min(len(mm), off + radius)
        pointers: list[dict[str, Any]] = []
        for i in range(lo & ~3, max(lo & ~3, hi - 3), 4):
            value = struct.unpack_from("<I", mm, i)[0]
            vloc = locate(value, core_loads, include_mem=True)
            if vloc:
                pointers.append({"at": hx(i), "value": hx(value), "mapping": vloc})
        return {
            "address": hx(address),
            "mapped": True,
            "file_offset": hx(off),
            "printable_strings": [
                s.decode("ascii", "replace")
                for s in re.findall(rb"[\x20-\x7e]{4,96}", mm[lo:hi])
            ],
            "mapped_pointer_words": pointers,
        }


def correlate(core_loads: list[dict[str, Any]], mdt_loads: list[dict[str, Any]], bfiles: dict[int, int]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for c in core_loads:
        c0, c1 = c["paddr"], c["paddr"] + c["memsz"]
        for m in mdt_loads:
            m0, m1 = m["paddr"], m["paddr"] + m["memsz"]
            start, end = max(c0, m0), min(c1, m1)
            if start >= end:
                continue
            idx = m["index"]
            rows.append({
                "core_segment": c["index"],
                "mdt_phdr": idx,
                "firmware_blob": f"modem.b{idx:02d}" if idx in bfiles else None,
                "overlap_start": hx(start),
                "overlap_end": hx(end),
                "overlap_size": end - start,
                "core_paddr": hx(c["paddr"]),
                "core_memsz": c["memsz"],
                "core_filesz": c["filesz"],
                "mdt_paddr": hx(m["paddr"]),
                "mdt_filesz": m["filesz"],
                "mdt_memsz": m["memsz"],
                "mdt_file_offset": hx(m["offset"]),
                "blob_size": bfiles.get(idx),
                "flags": m["flags"],
            })
    return rows


def compare_file_backed_segments(
    core: Path,
    core_loads: list[dict[str, Any]],
    mdt_loads: list[dict[str, Any]],
    blob_dir: Path | None,
) -> list[dict[str, Any]]:
    """Compare captured file-backed bytes with the matching split modem.bXX."""
    if blob_dir is None:
        return []
    rows: list[dict[str, Any]] = []
    with core.open("rb") as cf:
        for m in mdt_loads:
            if not m["filesz"]:
                continue
            blob = blob_dir / f"modem.b{m['index']:02d}"
            if not blob.is_file() or blob.stat().st_size != m["filesz"]:
                rows.append({
                    "mdt_phdr": m["index"],
                    "blob": blob.name,
                    "status": "not-comparable",
                    "reason": "missing or size differs",
                    "mdt_filesz": m["filesz"],
                    "blob_size": blob.stat().st_size if blob.is_file() else None,
                })
                continue
            c = next((x for x in core_loads if x["paddr"] <= m["paddr"] < x["paddr"] + x["filesz"]), None)
            if c is None or m["paddr"] + m["filesz"] > c["paddr"] + c["filesz"]:
                rows.append({"mdt_phdr": m["index"], "blob": blob.name, "status": "not-comparable", "reason": "core load does not contain full file-backed range"})
                continue
            cf.seek(c["offset"] + (m["paddr"] - c["paddr"]))
            core_bytes = cf.read(m["filesz"])
            blob_bytes = blob.read_bytes()
            rows.append({
                "mdt_phdr": m["index"],
                "blob": blob.name,
                "status": "match" if core_bytes == blob_bytes else "mismatch",
                "size": m["filesz"],
                "core_sha256": hashlib.sha256(core_bytes).hexdigest(),
                "blob_sha256": hashlib.sha256(blob_bytes).hexdigest(),
                "physical_start": hx(m["paddr"]),
            })
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("core", type=Path)
    ap.add_argument("mdt", type=Path)
    ap.add_argument("--blob-dir", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    core_h, core_ph = parse_elf(args.core)
    mdt_h, mdt_ph = parse_elf(args.mdt)
    core_loads = [x for x in core_ph if x["type"] == PT_LOAD and x["filesz"]]
    mdt_loads = [x for x in mdt_ph if x["type"] == PT_LOAD and x["memsz"]]
    bfiles: dict[int, int] = {}
    if args.blob_dir:
        for p in args.blob_dir.glob("modem.b[0-9][0-9]"):
            bfiles[int(p.name[-2:])] = p.stat().st_size
    crash_report = report_context(args.core, core_loads, mdt_loads)
    tcb = crash_report.get("tcb_ptr")
    output: dict[str, Any] = {
        "tool": "core_forensics.py",
        "core": {"path_basename": args.core.name, "header": core_h, "load_count": len(core_loads), "loads": core_loads},
        "mdt": {"path_basename": args.mdt.name, "header": mdt_h, "load_count": len(mdt_loads), "loads": mdt_loads},
        "crash_report": crash_report,
        "core_mdt_overlap": correlate(core_loads, mdt_loads, bfiles),
        "file_backed_comparison": compare_file_backed_segments(args.core, core_loads, mdt_loads, args.blob_dir),
        "tcb_window": mapped_words(args.core, core_loads, int(tcb, 16)) if tcb else None,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2) + "\n")
    os.chmod(args.out, 0o600)
    print(json.dumps({
        "out": str(args.out),
        "core_sha256": core_h["sha256"],
        "core_size": core_h["size"],
        "core_load_count": len(core_loads),
        "mdt_load_count": len(mdt_loads),
        "crash_report": output["crash_report"],
        "overlap_rows": len(output["core_mdt_overlap"]),
    }, indent=2))


if __name__ == "__main__":
    main()

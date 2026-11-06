#!/usr/bin/env python3
"""Replace (or patch in place) one file inside an ISO9660 image.

Growing a file is allowed only while it fits in the sectors already allocated to
it: the next file starts at the next sector, so the allocated size is a hard
ceiling. The directory record's data-length field is updated in both byte orders
(ISO9660 stores every multi-byte numeric field little-endian *and* big-endian,
so a naive "<II" write would corrupt the recording date that follows it).

No ISO9660 rebuild: the volume descriptor, the directory extents and the total
image size all stay untouched.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from iso9660 import SECTOR, Iso9660  # noqa: E402


def _scan(iso: Iso9660, extent: int, size: int, name: str):
    """Find a directory record inside a directory, returning its file offset."""
    iso.f.seek(extent * SECTOR)
    data = iso.f.read(size)
    pos = 0
    while pos < len(data):
        rec_len = data[pos]
        if rec_len == 0:
            pos = ((pos // SECTOR) + 1) * SECTOR
            if pos >= len(data):
                break
            continue
        rec = data[pos:pos + rec_len]
        try:
            entry = iso._parse_record(rec)
        except ValueError:
            entry = None
        if entry is not None and entry.name.upper() == name.upper():
            return extent * SECTOR + pos, rec
        pos += rec_len
    return None, None


def find_record(iso: Iso9660, path: str):
    """Absolute offset of the directory record for `path` (plus the parsed entry)."""
    parts = [p for p in path.replace("\\", "/").split("/") if p]
    cur = iso.root
    cur_off = iso.pvd_offset + 156  # the root record lives in the PVD
    for i, part in enumerate(parts):
        off, rec = _scan(iso, cur.extent, cur.size, part)
        if off is None:
            raise FileNotFoundError(f"{part!r} not found in {path}")
        cur_off, cur = off, iso._parse_record(rec)
        if not cur.is_dir and i != len(parts) - 1:
            raise NotADirectoryError(path)
    return cur_off, cur


def allocated_bytes(size: int) -> int:
    return ((size + SECTOR - 1) // SECTOR) * SECTOR


def read_iso_file(iso_path: str, inner_path: str) -> bytes:
    iso = Iso9660(iso_path)
    try:
        return iso.read_file(inner_path)
    finally:
        iso.close()


def _readback(iso_path: str, inner_path: str) -> tuple[bytes, int, int]:
    """(contents, extent, directory-record offset) as seen by a fresh reader."""
    iso = Iso9660(iso_path)
    try:
        data = iso.read_file(inner_path)
        rec_off, entry = find_record(iso, inner_path)
        return data, entry.extent, rec_off
    finally:
        iso.close()


def replace_file(src_iso: str, dst_iso: str, inner_path: str, new_data: bytes,
                 label: str | None = None) -> dict:
    """Copy `src_iso` to `dst_iso` and replace `inner_path` with `new_data`."""
    iso = Iso9660(src_iso)
    try:
        rec_off, entry = find_record(iso, inner_path)
        old = iso.read_file(inner_path)
    finally:
        iso.close()
    ceiling = allocated_bytes(entry.size)
    if len(new_data) > ceiling:
        raise ValueError(
            f"{inner_path}: {len(new_data)} bytes does not fit in the {ceiling} "
            f"allocated bytes (the next file starts at the next sector)")
    shutil.copyfile(src_iso, dst_iso)
    with open(dst_iso, "r+b") as f:
        f.seek(entry.extent * SECTOR)
        f.write(new_data)
        f.seek(rec_off + 10)
        f.write(struct.pack("<I", len(new_data)))   # little endian
        f.write(struct.pack(">I", len(new_data)))   # big endian
    back, extent2, rec_off2 = _readback(dst_iso, inner_path)
    report = {"path": inner_path, "label": label, "record_offset": rec_off,
              "extent_lba": entry.extent, "old_size": entry.size,
              "new_size": len(new_data), "ceiling": ceiling,
              "slack_used": len(new_data) - entry.size,
              "old_sha256": hashlib.sha256(old).hexdigest(),
              "new_sha256": hashlib.sha256(new_data).hexdigest(),
              "readback_size": len(back), "readback_extent": extent2,
              "readback_record_offset": rec_off2,
              "readback_sha256": hashlib.sha256(back).hexdigest()}
    report["roundtrip"] = report["new_sha256"] == report["readback_sha256"]
    return report


def patch_bytes(iso_path: str, inner_path: str, offset: int, data: bytes,
                expected: bytes | None = None) -> dict:
    """Overwrite `len(data)` bytes inside a file of the ISO (size unchanged)."""
    iso = Iso9660(iso_path)
    try:
        entry = iso.resolve(inner_path)
        iso.f.seek(entry.extent * SECTOR + offset)
        before = iso.f.read(len(data))
    finally:
        iso.close()
    if expected is not None and before != expected:
        raise ValueError(f"{inner_path}+{offset:#x}: expected {expected.hex()}, "
                         f"found {before.hex()}")
    with open(iso_path, "r+b") as f:
        f.seek(entry.extent * SECTOR + offset)
        f.write(data)
    iso = Iso9660(iso_path)
    try:
        entry = iso.resolve(inner_path)
        iso.f.seek(entry.extent * SECTOR + offset)
        after = iso.f.read(len(data))
    finally:
        iso.close()
    if after != data:
        raise ValueError(f"{inner_path}+{offset:#x}: readback mismatch "
                         f"({after.hex()} != {data.hex()})")
    return {"path": inner_path, "offset": offset, "before": before.hex(),
            "after": after.hex(), "roundtrip": True}


def main(argv: list[str]) -> int:
    if len(argv) < 5:
        print(__doc__)
        print("usage: iso_replace.py <src.iso> <dst.iso> <inner.path> <new_file>")
        return 2
    src, dst, inner, new_file = argv[1:5]
    report = replace_file(src, dst, inner, open(new_file, "rb").read())
    for k, v in report.items():
        print(f"  {k}: {v}")
    if not report["roundtrip"]:
        print("ROUND TRIP MISMATCH")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

#!/usr/bin/env python3
"""E6 ISO9660 space analyser + extent mover (read-only analysis, stdlib only).

The E6 card container no longer fits in the 550 currently-allocated sectors of
`PSP_GAME/USRDIR/duelsys/cardinfo_spa.ehp`, so it has to be *moved* to a
contiguous region nobody references.  A file's identity in ISO9660 is its
directory record, so moving a file means only rewriting the extent LBA (bytes
2..9 of the record, little- and big-endian) and, when its size changes, the data
length (bytes 10..17, little- and big-endian).

This module walks the directory tree, collects every referenced extent (files and
directories), and reports the free (unreferenced) contiguous regions.  It never
writes the image by itself; `relocate_record` is the only mutator and is used by
tools/e6_build_18.py.

Measured layout of the Spanish ULES00600 image (base ISO): fully packed, the
only unreferenced sectors are the ISO9660 system area + the volume descriptors
and path tables inside the leading metadata, far below the ~1.14 MB the E6
container needs.
"""
from __future__ import annotations

import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from iso9660 import SECTOR, Iso9660  # noqa: E402


def volume_sectors(iso: Iso9660) -> int:
    """Volume Space Size, in 2048-byte logical sectors, from the PVD."""
    iso.f.seek(iso.pvd_offset + 80)
    return struct.unpack_from("<I", iso.f.read(4))[0]


def _scan_record(iso: Iso9660, extent: int, size: int, name: str):
    """Find one directory record by name, returning (file offset, parsed entry)."""
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
            return extent * SECTOR + pos, entry
        pos += rec_len
    return None, None


def walk(iso: Iso9660) -> list[tuple[str, object, int]]:
    """Every entry reachable from the root: (path, DirEntry, record file offset)."""
    out: list[tuple[str, object, int]] = []

    def descend(entry, path: str) -> None:
        for e in iso._read_dir(entry.extent, entry.size):
            if e.name in (".", ".."):
                continue
            off, parsed = _scan_record(iso, entry.extent, entry.size, e.name)
            if parsed is None:
                raise RuntimeError(f"cannot locate directory record for {path}/{e.name}")
            full = f"{path}/{e.name}"
            out.append((full, parsed, off))
            if parsed.is_dir:
                descend(parsed, full)

    descend(iso.root, "")
    return out


def allocated_sectors(size: int) -> int:
    return (size + SECTOR - 1) // SECTOR


def occupied(iso: Iso9660) -> list[tuple[int, int, str]]:
    """(start_sector, end_sector, path) for every referenced extent (inclusive
    start, exclusive end)."""
    spans = [(iso.root.extent, iso.root.extent + allocated_sectors(iso.root.size),
              "<root dir>")]
    for path, e, _off in walk(iso):
        spans.append((e.extent, e.extent + allocated_sectors(e.size), path))
    return spans


def free_regions(iso: Iso9660) -> list[tuple[int, int]]:
    """Free contiguous [start, end) sector ranges inside the volume."""
    vols = volume_sectors(iso)
    merged: list[list[int]] = []
    for s, e, _p in sorted(occupied(iso)):
        if merged and s <= merged[-1][1]:
            if e > merged[-1][1]:
                merged[-1][1] = e
        else:
            merged.append([s, e])
    gaps: list[tuple[int, int]] = []
    prev = 0
    for s, e in merged:
        if s > prev:
            gaps.append((prev, s))
        prev = max(prev, e)
    if prev < vols:
        gaps.append((prev, vols))
    return gaps


def overlaps_file(iso: Iso9660, lba: int, sectors: int, ignore: str | None = None):
    """Any referenced extent that intersects [lba, lba+sectors)."""
    hits = []
    for path, e, _off in walk(iso):
        if ignore is not None and path == ignore:
            continue
        s, end = e.extent, e.extent + allocated_sectors(e.size)
        if lba < end and s < lba + sectors:
            hits.append((path, s, end))
    return hits


def relocate_record(iso_path: str, rec_off: int, extent: int, size: int) -> None:
    """Rewrite a directory record's extent LBA and data length in both endians."""
    with open(iso_path, "r+b") as f:
        f.seek(rec_off)
        rec = bytearray(f.read(34))
        struct.pack_into("<I", rec, 2, extent)
        struct.pack_into(">I", rec, 6, extent)
        struct.pack_into("<I", rec, 10, size)
        struct.pack_into(">I", rec, 14, size)
        f.seek(rec_off)
        f.write(rec)


def report(iso_path: str, needed_bytes: int) -> dict:
    iso = Iso9660(iso_path)
    try:
        vols = volume_sectors(iso)
        gaps = free_regions(iso)
        files = [(p, e, off) for p, e, off in walk(iso) if not e.is_dir]
        need_sectors = allocated_sectors(needed_bytes)
        biggest = max(gaps, key=lambda g: g[1] - g[0]) if gaps else (0, 0)
        top = sorted(files, key=lambda t: t[1].size, reverse=True)
        return {
            "volume_sectors": vols,
            "needed_bytes": needed_bytes,
            "needed_sectors": need_sectors,
            "free_regions": gaps,
            "largest_free_sectors": biggest[1] - biggest[0],
            "largest_free_lba": biggest[0],
            "largest_free_bytes": (biggest[1] - biggest[0]) * SECTOR,
            "top_files": [(p, e.size, e.extent, allocated_sectors(e.size)) for p, e, _ in top],
        }
    finally:
        iso.close()


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("iso")
    ap.add_argument("--needed-bytes", type=int, default=0,
                    help="size the container will need (to test fit)")
    ap.add_argument("--top", type=int, default=20, help="how many large files to list")
    args = ap.parse_args(argv[1:])
    rep = report(args.iso, args.needed_bytes)
    print(f"image: {args.iso}")
    print(f"volume: {rep['volume_sectors']} sectors "
          f"({rep['volume_sectors'] * SECTOR} bytes)")
    if args.needed_bytes:
        print(f"needed: {rep['needed_bytes']} bytes = {rep['needed_sectors']} sectors")
    print(f"free regions (start..end sectors, size):")
    if not rep["free_regions"]:
        print("  NONE")
    for s, e in rep["free_regions"]:
        print(f"  LBA {s:>7}..{e:<7}  {e - s:>6} sectors  {(e - s) * SECTOR:>10} bytes")
    print(f"largest free region: {rep['largest_free_sectors']} sectors "
          f"({rep['largest_free_bytes']} bytes) @ LBA {rep['largest_free_lba']}")
    print(f"\nlargest files (size, extent LBA, allocated sectors):")
    for p, size, ext, alloc in rep["top_files"][:args.top]:
        print(f"  {size:>12}  LBA {ext:>7}  {alloc:>6} sec  {p}")
    if args.needed_bytes:
        ok = rep["largest_free_sectors"] >= rep["needed_sectors"]
        print(f"\nFIT: {'yes' if ok else 'NO -- a file must be shrunk or moved'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

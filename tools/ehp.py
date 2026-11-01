#!/usr/bin/env python3
"""EHP v3 container reader (TF1 cardinfo_<lng>.ehp).

Layout observed on cardinfo_eng.ehp:
  0x00  magic   b"EHP" + version 0x03   (u32 masked 0xFFFFFF == 0x504845)
  0x04  total   u32 total container size
  0x08  marker  b"NOT "
  0x0C  count   u32 number of entries
  0x10  table   count * 8 bytes: (name_offset u32, data_offset u32)
        name_offset is relative to the container start; names are NUL-terminated.
  data regions are contiguous, so each file's size = next data_offset - this one
  (last file: total - data_offset).
"""
from __future__ import annotations

import os
import struct
import sys

MAGIC = 0x504845


def parse(data: bytes) -> dict[str, bytes]:
    total = struct.unpack_from("<I", data, 4)[0]
    if data[:3] != b"EHP":
        raise ValueError("not an EHP container")
    version = data[3]
    marker = data[8:12]
    count = struct.unpack_from("<I", data, 12)[0]
    entries = []
    for i in range(count):
        name_off, data_off = struct.unpack_from("<II", data, 16 + i * 8)
        end = data.index(b"\x00", name_off)
        name = data[name_off:end].decode("ascii", "replace")
        entries.append((name, data_off))
    files: dict[str, bytes] = {}
    for i, (name, off) in enumerate(entries):
        if i + 1 < len(entries):
            end = entries[i + 1][1]
        else:
            end = total
        files[name] = data[off:end]
    meta = {
        "version": version,
        "marker": marker,
        "declared_total": total,
        "actual_total": len(data),
        "count": count,
        "order": [n for n, _ in entries],
    }
    return {"meta": meta, "files": files}


def _main(argv: list[str]) -> int:
    if len(argv) < 3:
        print("usage: ehp.py <ehp> <ls|extract> [outdir]")
        return 2
    data = open(argv[1], "rb").read()
    parsed = parse(data)
    meta = parsed["meta"]
    print(f"version={meta['version']} marker={meta['marker']!r} "
          f"count={meta['count']} total={meta['declared_total']} "
          f"(actual {meta['actual_total']})")
    for name in meta["order"]:
        print(f"  {len(parsed['files'][name]):>10}  {name}")
    if argv[2] == "extract":
        outdir = argv[3] if len(argv) > 3 else os.path.dirname(argv[1])
        os.makedirs(outdir, exist_ok=True)
        for name, blob in parsed["files"].items():
            path = os.path.join(outdir, name)
            with open(path, "wb") as out:
                out.write(blob)
        print(f"extracted {len(parsed['files'])} files to {outdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))

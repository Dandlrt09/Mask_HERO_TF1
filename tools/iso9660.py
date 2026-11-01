#!/usr/bin/env python3
"""Minimal ISO9660 reader (read-only) for the TF1 spike.

Only what E2 needs: walk the directory tree by path and extract single files.
No Rock Ridge / Joliet support (the PSP ISO uses plain ISO9660).
"""
from __future__ import annotations

import struct
import sys
from dataclasses import dataclass

SECTOR = 2048


@dataclass
class DirEntry:
    name: str
    extent: int          # LBA
    size: int
    is_dir: bool


class Iso9660:
    def __init__(self, path: str):
        self.f = open(path, "rb")
        self.pvd_offset = self._find_pvd()
        root = self._read_root_record()
        self.root = root

    def _find_pvd(self) -> int:
        # Primary Volume Descriptor: sector 16, type byte 1
        for i in range(16, 24):
            self.f.seek(i * SECTOR)
            sec = self.f.read(SECTOR)
            if len(sec) < 8:
                raise ValueError("ISO truncated while scanning for PVD")
            if sec[0] == 1 and sec[1:6] == b"CD001":
                return i * SECTOR
        raise ValueError("Primary Volume Descriptor not found")

    def _read_root_record(self) -> DirEntry:
        self.f.seek(self.pvd_offset + 156)
        rec = self.f.read(34)
        return self._parse_record(rec)

    @staticmethod
    def _parse_record(rec: bytes) -> DirEntry:
        length = rec[0]
        if length == 0:
            raise ValueError("empty directory record")
        extent = struct.unpack_from("<I", rec, 2)[0]
        size = struct.unpack_from("<I", rec, 10)[0]
        flags = rec[25]
        name_len = rec[32]
        name_raw = rec[33:33 + name_len]
        if name_len == 1 and name_raw in (b"\x00", b"\x01"):
            name = "." if name_raw == b"\x00" else ".."
        else:
            name = name_raw.decode("ascii", "replace").split(";")[0]
        return DirEntry(name, extent, size, bool(flags & 0x02))

    def _read_dir(self, extent: int, size: int) -> list[DirEntry]:
        self.f.seek(extent * SECTOR)
        data = self.f.read(size)
        entries: list[DirEntry] = []
        pos = 0
        while pos < len(data):
            rec_len = data[pos]
            if rec_len == 0:
                # advance to next sector boundary
                pos = ((pos // SECTOR) + 1) * SECTOR
                if pos >= len(data):
                    break
                continue
            rec = data[pos:pos + rec_len]
            try:
                entries.append(self._parse_record(rec))
            except ValueError:
                pass
            pos += rec_len
        return entries

    def resolve(self, path: str) -> DirEntry:
        parts = [p for p in path.replace("\\", "/").split("/") if p]
        cur = self.root
        for part in parts:
            wanted = part.upper()
            found = None
            for e in self._read_dir(cur.extent, cur.size):
                if e.name.upper() == wanted:
                    found = e
                    break
            if found is None:
                raise FileNotFoundError(f"{part!r} not found in {path}")
            cur = found
        return cur

    def read_file(self, path: str) -> bytes:
        entry = self.resolve(path)
        if entry.is_dir:
            raise IsADirectoryError(path)
        self.f.seek(entry.extent * SECTOR)
        return self.f.read(entry.size)

    def extract(self, path: str, out_path: str):
        data = self.read_file(path)
        with open(out_path, "wb") as out:
            out.write(data)
        return len(data)

    def listdir(self, path: str) -> list[DirEntry]:
        entry = self.resolve(path)
        return self._read_dir(entry.extent, entry.size)

    def close(self):
        self.f.close()


def _main(argv: list[str]) -> int:
    if len(argv) < 3:
        print("usage: iso9660.py <iso> <command> [args]")
        print("  commands: ls <dir> | cat <file> | extract <file> <out>")
        return 2
    iso = Iso9660(argv[1])
    cmd = argv[2]
    try:
        if cmd == "ls":
            for e in iso.listdir(argv[3]):
                if e.name in (".", ".."):
                    continue
                kind = "DIR " if e.is_dir else "    "
                print(f"{kind}{e.size:>12}  {e.name}")
        elif cmd == "cat":
            sys.stdout.buffer.write(iso.read_file(argv[3]))
        elif cmd == "extract":
            n = iso.extract(argv[3], argv[4])
            print(f"wrote {n} bytes to {argv[4]}")
        else:
            print(f"unknown command {cmd!r}")
            return 2
    finally:
        iso.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))

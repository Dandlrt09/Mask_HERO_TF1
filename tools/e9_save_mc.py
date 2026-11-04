#!/usr/bin/env python3
"""E9: set the owned-copy count of one card in the plaintext TF1 save.

The E6 layout is reused, not re-derived: one 4-byte record per internal card
index at TABLE_OFFSET (stride 4) = {flag (0x04 = owned), copies, limit level, 0}.

  SAVE OUT --index N --copies C

Refuses unless: the save is the plaintext 65536-byte one, the record is owned,
the game limit allows C copies, and afterwards ONLY the flag/copies byte of that
record changed (verified against the original, byte by byte).
"""
from __future__ import annotations

import argparse
import hashlib
import sys

sys.path.insert(0, "tools")
from e6_patch_save import (  # noqa: E402
    NO_LIMIT, OWNED_FLAG, SAVE_SIZE, STRIDE, TABLE_OFFSET,
)


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("save")
    ap.add_argument("out")
    ap.add_argument("--index", type=int, required=True, help="internal card index")
    ap.add_argument("--copies", type=int, required=True)
    a = ap.parse_args()

    orig = open(a.save, "rb").read()
    if len(orig) != SAVE_SIZE:
        print(f"STOP: {a.save} is {len(orig)} bytes, expected {SAVE_SIZE}")
        return 1
    if a.copies < 1:
        print("STOP: copies must be >= 1")
        return 1
    off = TABLE_OFFSET + a.index * STRIDE
    flag, copies, level = orig[off], orig[off + 1], orig[off + 2]
    print(f"save {a.save} ({len(orig)} bytes, sha256 {sha(orig)})")
    print(f"index {a.index} @ {off:#x}: flag={flag:#04x} copies={copies} level={level}")
    if flag != OWNED_FLAG:
        print(f"STOP: index {a.index} is not owned (flag {flag:#04x} != {OWNED_FLAG:#04x})")
        return 1
    if level == 0:
        print("STOP: index is Forbidden (level 0) in this save")
        return 1
    if a.copies > level:
        limit = "Unlimited" if level == NO_LIMIT else f"{level} copies"
        print(f"STOP: {a.copies} copies exceed the game limit ({limit})")
        return 1
    if copies >= a.copies:
        print(f"STOP: already has {copies} copies (>= {a.copies}); nothing to do")
        return 1

    data = bytearray(orig)
    data[off + 1] = a.copies
    out = bytes(data)
    changed = {i for i in range(len(orig)) if orig[i] != out[i]}
    if changed != {off + 1}:
        print(f"STOP: refusing, unexpected changed bytes {sorted(changed)}")
        return 1
    assert data[off] == OWNED_FLAG and data[off + 1] == a.copies
    with open(a.out, "wb") as f:
        f.write(out)
    print(f"patched: copies {copies} -> {a.copies} (limit level {level} untouched)")
    print(f"changed bytes: {sorted(changed)} (1 byte, exactly the copies field)")
    print(f"wrote {a.out} ({len(out)} bytes, sha256 {sha(out)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

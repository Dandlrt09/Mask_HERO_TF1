#!/usr/bin/env python3
"""E6/T14: grant ownership of the 18 Masked HERO cards in the plaintext TF1 save.

Layout measured on `DATA0` once PPSSPP writes it with `EncryptSave = False`
(65536 bytes, see ESTADO-E6.md §10):

  * one 4-byte record per **internal card index** at `TABLE_OFFSET`, stride 4,
    2480 records covering internal indices 0..2479:
      byte0  0x04 when the player has the card, 0 otherwise
      byte1  number of copies owned
      byte2  limit level: 3 Unlimited, 2 Semi-Limited, 1 Limited, 0 Forbidden
             (this is the record the E5-C2 level reader reads per index)
      byte3  0
  * the 3079 bytes after the table (0x3C1C..0x4823) are zero and unreferenced, so
    the table can be extended with the 18 new indices 2480..2497 (72 bytes).

On a fresh starter save the 35 non-zero records match the 35 distinct CardIDs of
the player's deck exactly, which is how the table was identified.

  show  SAVE [--ehp container]           print the current ownership
  patch SAVE OUT [--ehp container]       grant the 18 new indices, with verification

The patch writes `04 01 03 00` (owned, 1 copy, Unlimited) at each new index and
refuses to touch anything else: every pre-existing record must stay byte-identical.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import struct
import sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
import cardinfo_add as cia   # noqa: E402

TABLE_OFFSET = 0x155C
STRIDE = 4
RECORDS = 2480
FIRST_NEW_INDEX = 2480
TABLE_END = TABLE_OFFSET + RECORDS * STRIDE          # 0x3C1C
SAVE_SIZE = 65536
OWNED_FLAG = 0x04
UNLIMITED = 3
DEFAULT_SAVE = os.path.join(ROOT, "trabajo", "save", "ULES006000001", "DATA0")
DEFAULT_OUT = os.path.join(ROOT, "trabajo", "e6", "DATA0.18")
DEFAULT_EHP = os.path.join(ROOT, "trabajo", "e6", "cardinfo_spa_18.ehp")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_owned(data: bytes, records: int = RECORDS) -> list[dict]:
    """Every record whose byte0 marks the card as owned (indices 0..records-1)."""
    out = []
    for idx in range(records):
        off = TABLE_OFFSET + idx * STRIDE
        flag = data[off]
        if flag:
            out.append({"index": idx, "flag": flag, "copies": data[off + 1],
                        "level": data[off + 2], "pad": data[off + 3]})
    return out


def index_to_cardid(ehp_path: str) -> dict[int, int]:
    """internal index -> CardID, read from the built container's CARD_IntID."""
    _, entries = cia.parse(open(ehp_path, "rb").read())
    intid = cia.region(entries, "CARD_IntID").body
    out = {}
    for slot in range(len(intid) // 2):
        idx = struct.unpack_from("<H", intid, slot * 2)[0]
        if idx:
            out.setdefault(idx, 4000 + slot)
    return out


def show(args) -> int:
    data = open(args.save, "rb").read()
    print(f"{args.save}: {len(data)} bytes, sha256 {sha256(data)}")
    owned = read_owned(data)
    idmap = index_to_cardid(args.ehp) if os.path.exists(args.ehp) else {}
    print(f"owned records: {len(owned)} (expect 35 on the starter save)")
    for rec in owned:
        print(f"  index {rec['index']:4d}  CardID {idmap.get(rec['index'], 0):5d}  "
              f"flag=0x{rec['flag']:02x} copies={rec['copies']} level={rec['level']}")
    tail = data[TABLE_END:TABLE_END + 18 * STRIDE]
    print(f"records for the 18 new indices (0x{TABLE_END:X}..0x{TABLE_END + 72:X}):")
    for i in range(18):
        idx = FIRST_NEW_INDEX + i
        off = TABLE_END + i * STRIDE
        raw = data[off:off + STRIDE]
        print(f"  index {idx}  CardID {idmap.get(idx, 0):5d}  "
              f"flag=0x{raw[0]:02x} copies={raw[1]} level={raw[2]}"
              if any(raw) else f"  index {idx}  CardID {idmap.get(idx, 0):5d}  "
              f"not owned (0x{raw.hex()})")
    free = data[TABLE_END + 18 * STRIDE:TABLE_END + 128]
    print(f"bytes 0x{TABLE_END + 72:X}..0x{TABLE_END + 128:X} all zero = {not any(free)}")
    return 0


def patch(args) -> int:
    orig = open(args.save, "rb").read()
    data = bytearray(orig)
    if len(data) != SAVE_SIZE:
        print(f"STOP: save is {len(data)} bytes, expected {SAVE_SIZE} "
              f"(is it the plaintext one? the encrypted save is 65552)")
        return 1
    before = read_owned(data)
    print(f"save: {args.save} ({len(data)} bytes, sha256 {sha256(bytes(data))})")
    print(f"pre-existing owned records: {len(before)}")

    # --- preconditions -------------------------------------------------------
    problems = []
    region = data[TABLE_END:TABLE_END + 18 * STRIDE]
    if any(region):
        problems.append(f"the 18 records after the table are not zero: {region.hex()}")
    idmap = index_to_cardid(args.ehp)
    for i in range(18):
        idx = FIRST_NEW_INDEX + i
        if not idmap.get(idx):
            problems.append(f"index {idx} has no CardID in {os.path.basename(args.ehp)}")
    if problems:
        print("STOP: preconditions failed:")
        for p in problems:
            print(f"  FAIL: {p}")
        return 1
    print("preconditions: the 18 new records are in the zero tail of the table "
          "and every one of them is mapped by CARD_IntID")

    # --- the patch ----------------------------------------------------------
    for i in range(18):
        off = TABLE_END + i * STRIDE
        data[off:off + STRIDE] = bytes([OWNED_FLAG, 1, UNLIMITED, 0])
    out = bytes(data)

    # --- verification -------------------------------------------------------
    fails = []
    after = read_owned(out, RECORDS + 18)
    kept = [r for r in after if r["index"] < FIRST_NEW_INDEX]
    if kept != before:
        fails.append("a pre-existing ownership record changed")
    new = {r["index"]: r for r in after if r["index"] >= FIRST_NEW_INDEX}
    want = set(range(FIRST_NEW_INDEX, FIRST_NEW_INDEX + 18))
    if set(new) != want:
        fails.append(f"new records are {sorted(new)} != {sorted(want)}")
    for idx, rec in new.items():
        if (rec["flag"], rec["copies"], rec["level"], rec["pad"]) != (OWNED_FLAG, 1, UNLIMITED, 0):
            fails.append(f"index {idx}: record {rec} is not 04 01 03 00")
    changed = {o for o in range(len(data)) if data[o] != orig[o]}
    allowed = set(range(TABLE_END, TABLE_END + 18 * STRIDE))
    extra = changed - allowed
    if extra:
        fails.append(f"{len(extra)} bytes changed outside 0x{TABLE_END:X}.."
                     f"0x{TABLE_END + 72:X}: {sorted(extra)[:8]}")
    if fails:
        print(f"VERIFICATION FAILED ({len(fails)}):")
        for f in fails:
            print(f"  FAIL: {f}")
        return 1
    print(f"verified: {len(before)} pre-existing records byte-identical, "
          f"{len(new)} new records 04 01 03 00, "
          f"{len(changed)} bytes changed (all inside the 72-byte extension)")
    for i in range(18):
        idx = FIRST_NEW_INDEX + i
        print(f"  index {idx}: CardID {idmap[idx]} owned, 1 copy, Unlimited")

    with open(args.out, "wb") as f:
        f.write(out)
    print(f"wrote {args.out} ({len(out)} bytes, sha256 {sha256(out)})")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("show", help="print the current ownership table")
    s.add_argument("save", nargs="?", default=DEFAULT_SAVE)
    s.add_argument("--ehp", default=DEFAULT_EHP)
    s.set_defaults(func=show)
    p = sub.add_parser("patch", help="grant the 18 new indices")
    p.add_argument("save", nargs="?", default=DEFAULT_SAVE)
    p.add_argument("--out", default=DEFAULT_OUT)
    p.add_argument("--ehp", default=DEFAULT_EHP)
    p.set_defaults(func=patch)
    args = ap.parse_args(argv[1:])
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

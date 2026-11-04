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
  grant SAVE --out OUT [--recipe TSV]    grant an arbitrary card set (a deck recipe)

`patch` writes `04 01 03 00` (owned, 1 copy, Unlimited) at each new index and
refuses to touch anything else: every pre-existing record must stay byte-identical.

`grant` takes a recipe of `cardid<TAB>copies` rows (see `datos/receta_hero.tsv`),
resolves each CardID to its internal index through the container's `CARD_IntID`,
and sets only byte0 (`0x04`, owned) and byte1 (copies). It deliberately leaves
byte2 (the limit level) untouched: the save already carries the game's real level
for every index, and that is the byte the E5-C2 reader consumes. Refusing to
invent a level is what keeps the banlist intact. A recipe that asks for more
copies than the game's level allows, or for a Forbidden card, is rejected whole.
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
DEFAULT_RECIPE = os.path.join(ROOT, "datos", "receta_hero.tsv")
NO_LIMIT = 3


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


def read_recipe(path: str) -> list[dict]:
    """`cardid<TAB>copies<TAB>...` rows; `#` comments and a `cardid` header skipped."""
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.startswith("#") or not line.strip():
                continue
            parts = line.rstrip("\n").split("\t")
            if parts[0] == "cardid":
                continue
            rows.append({"cardid": int(parts[0]), "copies": int(parts[1]),
                         "name": parts[2] if len(parts) > 2 else str(parts[0])})
    return rows


def cardid_to_index(ehp_path: str) -> dict[int, int]:
    """CardID -> internal index, read from the container's CARD_IntID.

    Every mapping is cross-checked against `CARD_Prop`, so a CardID the container
    does not really carry is absent instead of silently pointing at index 0.
    """
    _, entries = cia.parse(open(ehp_path, "rb").read())
    intid = cia.region(entries, "CARD_IntID").body
    prop = cia.region(entries, "CARD_Prop").body
    slots = len(prop) // 8
    out = {}
    for slot in range(len(intid) // 2):
        idx = struct.unpack_from("<H", intid, slot * 2)[0]
        if not 0 < idx < slots:
            continue
        card_id = struct.unpack_from("<i", prop, idx * 8)[0] & 0x1FFF
        if card_id == 4000 + slot:
            out[card_id] = idx
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


def grant(args) -> int:
    orig = open(args.save, "rb").read()
    if len(orig) != SAVE_SIZE:
        print(f"STOP: save is {len(orig)} bytes, expected {SAVE_SIZE} "
              f"(is it the plaintext one? the encrypted save is 65552)")
        return 1
    data = bytearray(orig)
    recipe = read_recipe(args.recipe)
    if not recipe:
        print(f"STOP: recipe {args.recipe} has no rows")
        return 1
    idmap = cardid_to_index(args.ehp)
    print(f"save: {args.save} ({len(orig)} bytes, sha256 {sha256(orig)})")
    print(f"recipe: {args.recipe} ({len(recipe)} cards)")
    print(f"container: {args.ehp}")

    # --- preconditions: build the whole plan before touching a byte ----------
    problems, plan, seen = [], [], {}
    for row in recipe:
        card_id, copies, name = row["cardid"], row["copies"], row["name"]
        idx = idmap.get(card_id)
        if idx is None:
            problems.append(f"CardID {card_id} ({name}) has no internal index in the container")
            continue
        if idx >= FIRST_NEW_INDEX:
            problems.append(f"CardID {card_id} ({name}) sits at index {idx}, outside the base pool")
            continue
        if idx in seen:
            problems.append(f"index {idx} is claimed by both {seen[idx]} and {name}")
            continue
        seen[idx] = name
        if copies < 1:
            problems.append(f"CardID {card_id} ({name}): copies must be >= 1, got {copies}")
            continue
        off = TABLE_OFFSET + idx * STRIDE
        level = data[off + 2]
        if level == 0:
            problems.append(f"CardID {card_id} ({name}): index {idx} is Forbidden (level 0) in this save")
            continue
        if copies > level:
            limit = "Unlimited" if level == NO_LIMIT else f"{level} {'copy' if level == 1 else 'copies'}"
            problems.append(f"CardID {card_id} ({name}): {copies} copies exceed the game limit ({limit})")
            continue
        have = data[off + 1] if data[off] == OWNED_FLAG else 0
        plan.append({"index": idx, "cardid": card_id, "name": name, "level": level,
                     "copies": max(have, copies), "already": have})
    if problems:
        print("STOP: preconditions failed, nothing written:")
        for p in problems:
            print(f"  FAIL: {p}")
        return 1
    print(f"preconditions: {len(plan)} cards resolved, no index collisions, "
          f"no Forbidden card and every copy count within the game limit")

    # --- the patch: possession and copies only, the level byte stays ----------
    before = read_owned(data, RECORDS + 18)
    for p in plan:
        off = TABLE_OFFSET + p["index"] * STRIDE
        data[off] = OWNED_FLAG
        data[off + 1] = p["copies"]
    out = bytes(data)

    # --- verification -------------------------------------------------------
    fails = []
    allowed = set()
    for p in plan:
        off = TABLE_OFFSET + p["index"] * STRIDE
        allowed.update((off, off + 1))
    changed = {i for i in range(len(data)) if data[i] != orig[i]}
    stray = changed - allowed
    if stray:
        fails.append(f"{len(stray)} bytes changed outside the granted records: {sorted(stray)[:8]}")
    for p in plan:
        off = TABLE_OFFSET + p["index"] * STRIDE
        rec = data[off:off + STRIDE]
        if rec[0] != OWNED_FLAG:
            fails.append(f"index {p['index']}: flag is 0x{rec[0]:02x}, expected 0x04")
        if rec[1] != p["copies"]:
            fails.append(f"index {p['index']}: {rec[1]} copies, expected {p['copies']}")
        if rec[2] != p["level"]:
            fails.append(f"index {p['index']}: level became {rec[2]}, was {p['level']}")
    after = read_owned(out, RECORDS + 18)
    outside = set(seen)
    kept = [r for r in after if r["index"] not in outside]
    if kept != before:
        fails.append("an ownership record outside the recipe changed")
    tail = slice(TABLE_END, TABLE_END + 18 * STRIDE)
    if out[tail] != orig[tail]:
        fails.append("the 18 E6 records (indices 2480..2497) changed")
    if fails:
        print(f"VERIFICATION FAILED ({len(fails)}), nothing written:")
        for f in fails:
            print(f"  FAIL: {f}")
        return 1

    owned_total = len(after)
    gained = sum(1 for p in plan if not p["already"])
    print(f"verified: {gained} new cards granted, {len(plan) - gained} already owned, "
          f"{len(changed)} bytes changed (all inside the granted records), "
          f"level byte preserved on every one, the 18 E6 records untouched")
    for p in plan:
        tag = f"already had {p['already']}" if p["already"] else "new"
        limit = "Unlimited" if p["level"] == NO_LIMIT else f"limit {p['level']}"
        print(f"  index {p['index']:4d}  CardID {p['cardid']:5d}  {p['copies']}x  "
              f"{limit:10}  {p['name']}  ({tag})")
    print(f"owned records: {len(before)} -> {owned_total}")
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
    g = sub.add_parser("grant", help="grant a deck recipe's cards without touching the limit levels")
    g.add_argument("save")
    g.add_argument("--out", required=True)
    g.add_argument("--recipe", default=DEFAULT_RECIPE)
    g.add_argument("--ehp", default=DEFAULT_EHP)
    g.set_defaults(func=grant)
    args = ap.parse_args(argv[1:])
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

#!/usr/bin/env python3
"""E1-test: build a test ISO that has one extra card and reuses existing art.

Everything happens on a COPY (`dst`); the source ISO is only ever read.

  1. read PSP_GAME/USRDIR/duelsys/cardinfo_eng.ehp from the source ISO and append
     one card record to it (tools/cardinfo_add.py)
  2. replace that file inside the copy (tools/iso_replace.py), updating the
     directory record's data length; aborts if it does not fit in the sectors
     already allocated to the file
  3. alias the artwork: copy the donor CardID's 8-byte slot in
     PSP_GAME/USRDIR/card/cardh_e.cip and cardm_e.cip into the new CardID's slot
     (a free CardID's slot is zeroed today, i.e. it points at block 0 = the
     container header) and into every `--repoint` CardID's slot

`--repoint CARDID` also points a CardID the save already owns at the appended
record. The deck editor and the album only list owned cards, so a free CardID is
invisible there: repointing an owned card is what makes the new record observable
without touching the save.
  4. read everything back from the patched ISO and check it matches

See ESTADO-E1-test.md for the measurements behind each choice.
"""
from __future__ import annotations

import hashlib
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cardinfo_add  # noqa: E402
import iso_replace  # noqa: E402

EHP_PATH = "PSP_GAME/USRDIR/duelsys/cardinfo_eng.ehp"
ART_PATHS = ("PSP_GAME/USRDIR/card/cardh_e.cip", "PSP_GAME/USRDIR/card/cardm_e.cip")
DEFAULT_SRC = "Yu-Gi-Oh! GX - Tag Force 1 [JP Voice enabled].iso"
DEFAULT_DST = "trabajo/TF1-E1-test.iso"


def cip_slot(blob: bytes, card_id: int) -> int:
    """Byte offset of a CardID's 8-byte entry in a CIP/CPM offset table."""
    if blob[0:3] not in (b"CIP", b"CPM"):
        raise ValueError(f"not a CIP/CPM container: {blob[0:4]!r}")
    mins = struct.unpack_from("<I", blob, 0x14)[0]
    maxs = struct.unpack_from("<I", blob, 0x18)[0]
    table = struct.unpack_from("<I", blob, 0x1C)[0]
    if not mins <= card_id <= maxs:
        raise ValueError(f"CardID {card_id} outside {mins}..{maxs}")
    return table + ((card_id - mins) << 3)


def build(src: str, dst: str, *, card_id: int, donor: int, name: str,
          desc: str | None, atk: int, level: int,
          canaries: tuple[tuple[int, int], ...], repoints: tuple[int, ...]) -> int:
    print(f"--- 1. append card {card_id} to {EHP_PATH} (donor {donor}) ---")
    ehp = iso_replace.read_iso_file(src, EHP_PATH)
    new_ehp, report = cardinfo_add.add_card(
        ehp, card_id=card_id, donor_card_id=donor, name=name, desc=desc, atk=atk,
        level=level, canaries=canaries, also_map=repoints)
    for k, v in report.items():
        print(f"    {k}: {v}")

    print(f"--- 2. copy ISO and replace the container ---")
    rep = iso_replace.replace_file(src, dst, EHP_PATH, new_ehp, label="cardinfo_eng.ehp")
    for k, v in rep.items():
        print(f"    {k}: {v}")
    if not rep["roundtrip"]:
        print("ROUND TRIP MISMATCH after replacing the EHP")
        return 1

    targets = (card_id,) + tuple(c for c in repoints if c != card_id)
    print(f"--- 3. alias the artwork into {targets} ---")
    for art in ART_PATHS:
        blob = iso_replace.read_iso_file(src, art)
        donor_slot = cip_slot(blob, donor)
        entry = blob[donor_slot:donor_slot + 8]
        for target in targets:
            slot = cip_slot(blob, target)
            before = blob[slot:slot + 8]
            out = iso_replace.patch_bytes(dst, art, slot, entry, expected=before)
            print(f"    {art}: slot {target} @0x{slot:X} "
                  f"{before.hex()} -> {out['after']} (donor {donor} @0x{donor_slot:X})")

    print("--- 4. readback from the patched ISO ---")
    back = iso_replace.read_iso_file(dst, EHP_PATH)
    same = hashlib.sha256(back).hexdigest() == hashlib.sha256(new_ehp).hexdigest()
    print(f"    cardinfo_eng.ehp: {len(back)} bytes, sha256 match: {same}")
    if not same:
        print("READBACK MISMATCH: the ISO does not contain the container we built")
        return 1
    card = cardinfo_add.describe(back, card_id)
    print(f"    new card {card_id}: {card}")
    for cid in repoints:
        print(f"    repointed {cid}: {cardinfo_add.describe(back, cid)}")
    for cid, catk in canaries:
        print(f"    canary {cid}: {cardinfo_add.describe(back, cid)}")
    for art in ART_PATHS:
        blob = iso_replace.read_iso_file(dst, art)
        for target in targets:
            slot = cip_slot(blob, target)
            print(f"    {art}: slot {target} now {blob[slot:slot + 8].hex()}")
    print(f"\nOK -> {dst}")
    print("Test in PPSSPP (English), starting a fresh screen:")
    for cid, catk in canaries:
        print(f"  canary: CardID {cid} must show ATK {catk}")
    for cid in repoints:
        print(f"  card {cid} must now read as {name!r}, ATK {atk}, level {level}")
    return 0


def main(argv: list[str]) -> int:
    src, dst = DEFAULT_SRC, DEFAULT_DST
    card_id, donor, atk, level = 4661, 4047, 4900, 4
    name = "E1 TEST CARD"
    desc: str | None = None
    canaries: tuple[tuple[int, int], ...] = ()
    repoints: tuple[int, ...] = ()
    i = 1
    while i < len(argv):
        a = argv[i]
        if a == "--src":
            src = argv[i + 1]; i += 2
        elif a == "--dst":
            dst = argv[i + 1]; i += 2
        elif a == "--card-id":
            card_id = int(argv[i + 1]); i += 2
        elif a == "--donor":
            donor = int(argv[i + 1]); i += 2
        elif a == "--name":
            name = argv[i + 1]; i += 2
        elif a == "--desc":
            desc = argv[i + 1]; i += 2
        elif a == "--atk":
            atk = int(argv[i + 1]); i += 2
        elif a == "--level":
            level = int(argv[i + 1]); i += 2
        elif a == "--canary":
            cid, catk = argv[i + 1].split(":")
            canaries = canaries + ((int(cid), int(catk)),); i += 2
        elif a == "--repoint":
            repoints = repoints + (int(argv[i + 1]),); i += 2
        elif a == "--no-canary":
            canaries = (); i += 1
        else:
            raise SystemExit(f"unknown option {a}")
    if len(argv) > 1 and not os.path.exists(src):
        raise SystemExit(f"source ISO not found: {src}")
    return build(src, dst, card_id=card_id, donor=donor, name=name, desc=desc,
                 atk=atk, level=level, canaries=canaries, repoints=repoints)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

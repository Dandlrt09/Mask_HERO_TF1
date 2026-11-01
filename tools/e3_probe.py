#!/usr/bin/env python3
"""E3 probe: locate the in-RAM genre array and toggle a card's genre bit.

Goal of E3: decide whether the engine READS CARD_Genre for the rule
"Cannot perform Normal Summon" (byte4 bit1), or whether genre is only filter
metadata. Test: take a card that is normally summonable and has byte4 == 0,
set bit1 of its genre byte4 in RAM, and try to Normal Summon it.

How to find the array in PPSSPP: search the emulator's memory for the 24-byte
signature below. It is unique inside cardinfo_eng.ehp. If it is found at
address A, then the genre array base is B = A - SIG_OFFSET, and the genre
record of internal index i lives at B + i*6 (byte4 at B + i*6 + 4).
"""
from __future__ import annotations

import struct
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from tfcard import CardInfo  # noqa: E402

SIG_OFFSET_IN_GENRE = 0x2538


def find_signature(folder: str) -> tuple[bytes, int]:
    from tfcard import CardInfo as _CI
    ci = _CI(folder)
    # reuse the known distinctive window, confirm it is still unique
    sig = ci.genre[SIG_OFFSET_IN_GENRE:SIG_OFFSET_IN_GENRE + 24]
    assert ci.genre.count(sig) == 1, "signature no longer unique"
    return sig, SIG_OFFSET_IN_GENRE


def main(argv: list[str]) -> int:
    folder = argv[1] if len(argv) > 1 else "trabajo/e2/eng"
    target = argv[2] if len(argv) > 2 else "Celtic Guardian"
    ci = CardInfo(folder)
    sig, sig_off = find_signature(folder)
    card = ci.by_name(target)
    if card is None:
        print(f"NOT FOUND: {target}")
        return 1
    i = card.index
    off_byte4 = i * 6 + 4
    orig = card.genre[4]
    new = orig | 0x02  # byte4 bit1 = Cannot perform Normal Summon

    print(f"target: {card.name} (CardID {card.card_id}, internal index {i})")
    print(f"  kind={card.kind} level={card.level} atk={card.atk} def={card.dfn}")
    print(f"  genre now = {card.genre.hex()}  byte4=0x{orig:02X}  tags={card.genres}")
    print()
    print("STEP 1 - PPSSPP memory search (Debug -> Memory View -> search hex):")
    print(f"  signature ({len(sig)} bytes): {sig.hex().upper()}")
    print(f"  when found at address A -> genre array base B = A - 0x{sig_off:X}")
    print()
    print("STEP 2 - target address:")
    print(f"  genre record of internal index {i}: B + 0x{i*6:X}")
    print(f"  byte4 (the field to poke):        B + 0x{off_byte4:X}")
    print(f"  write 0x{new:02X}  (was 0x{orig:02X})")
    print()
    print("STEP 3 - verify:")
    print(f"  put {card.name} in your deck and try to Normal Summon it.")
    print("  blocked  -> engine reads the genre bit  => rule is DATA-DRIVEN")
    print("  allowed  -> genre is filter metadata only => rule lives in code")
    print()
    print("PPSSPP cheat template (fill <BASE> once you know it):")
    print(f"  _C1 E3 poke {card.name}")
    print(f"  _L 0x0<BASE+{off_byte4:05X}> 0x{new:08X}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

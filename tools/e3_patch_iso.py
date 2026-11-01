#!/usr/bin/env python3
"""E3/E1 data patch: write a new ISO with genre bits flipped, original untouched.

Test: set CARD_Genre byte4 bit1 ("Cannot perform Normal Summon") on a set of
normally-summonable monsters that every player owns (they start in the Initial
Deck). Leave other monsters alone as a paired control.

Patching one byte in place keeps every file size identical, so the ISO9660
directory stays valid and NO EHP rebuild is needed: we write the byte directly
at  file_offset + genre_offset_in_ehp + internal_index*6 + 4  ,  for each of the
6 language cardinfo files.
"""
from __future__ import annotations

import os
import shutil
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from iso9660 import Iso9660      # noqa: E402
from tfcard import CardInfo      # noqa: E402


def ehp_entry_offset(data: bytes, wanted: str) -> int:
    """Exact data offset of one internal file, from the EHP entry table."""
    count = struct.unpack_from("<I", data, 12)[0]
    for i in range(count):
        name_off, data_off = struct.unpack_from("<II", data, 16 + i * 8)
        end = data.index(b"\x00", name_off)
        if data[name_off:end].decode("ascii", "replace") == wanted:
            return data_off
    raise KeyError(wanted)

# Cards to flag "Cannot perform Normal Summon" (all owned: Initial Deck).
PATCH = ["Aqua Madoor", "Gagagigo", "Jellyfish", "Fiend Kraken",
         "Flying Penguin", "Night Lizard"]
# Left untouched on purpose, as the control group.
CONTROL = ["Giant Red Seasnake", "Sea Serpent Warrior of Darkness",
           "Humanoid Slime", "Torpedo Fish", "Kappa Avenger",
           "Waterdragon Fairy"]
LANGS = ["eng", "fra", "ger", "ita", "jpn", "spa"]


def main(argv: list[str]) -> int:
    src = argv[1] if len(argv) > 1 else "Yu-Gi-Oh! GX - Tag Force 1 [JP Voice enabled].iso"
    dst = argv[2] if len(argv) > 2 else "trabajo/TF1-E3-test.iso"
    ci = CardInfo("trabajo/e2/eng")
    targets = []
    for name in PATCH:
        c = ci.by_name(name)
        assert c is not None, name
        assert c.genre[4] & 0x02 == 0, f"{name} already flagged"
        targets.append((name, c.index, c.genre[4]))
    print("flags to set:")
    for name, idx, b4 in targets:
        print(f"  {name:32} idx={idx:5} byte4 0x{b4:02X} -> 0x{b4 | 0x02:02X}")

    print(f"copying {src} -> {dst} ...")
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    shutil.copyfile(src, dst)

    iso = Iso9660(src)  # layout is identical in the copy
    writes = 0
    with open(dst, "r+b") as out:
        for lng in LANGS:
            path = f"/PSP_GAME/USRDIR/duelsys/cardinfo_{lng}.ehp"
            entry = iso.resolve(path)
            data = iso.read_file(path)
            genre_off = ehp_entry_offset(data, "CARD_Genre.bin")
            file_off = entry.extent * 2048
            for name, idx, b4 in targets:
                abs_off = file_off + genre_off + idx * 6 + 4
                out.seek(abs_off)
                out.write(bytes([b4 | 0x02]))
                writes += 1
            print(f"  {lng}: genre@0x{genre_off:x} patched {len(targets)} cards")
    iso.close()
    print(f"done: {writes} bytes written to {dst}")
    print("\ncontrols left untouched:", ", ".join(CONTROL))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

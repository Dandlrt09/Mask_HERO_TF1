#!/usr/bin/env python3
"""TF1 CardInfo library (read-only).

Reads an extracted cardinfo_<lng> set (the 12 files from the EHP container) and
exposes the three parallel arrays the engine actually has:

  internal index (0..N-1)  <-- IntID[CardID - CARD_ID_BASE]
      CARD_Prop.bin    8 bytes/card  (Prop1, Prop2 bit-packed)
      CARD_Genre.bin   6 bytes/card  (genre bit flags, 5 bytes used)
      CARD_Pass.bin    4 bytes/card
      CARD_Indx_E.bin  int32 pairs -> name/desc offsets
      CARD_Name_E.bin  UTF-16-LE buffer
      CARD_Desc_E.bin  UTF-16-LE buffer

Measured on ULES00600 cardinfo_eng.ehp:
  CARD_ID_BASE = 4000, first real CardID = 4007, last = 6957
  2479 real cards, 472 free CardIDs inside the range.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

CARD_ID_BASE = 4000
FIRST_CARD_ID = 4007

GENRE_BITS = {
    0: {1: "Remove card from play", 2: "Destroy Spell/Trap", 3: "Destroy monster",
        4: "Deck destruction", 5: "Hand destruction", 6: "LV Monsters", 7: "Toon"},
    1: {0: "Spirit", 1: "Union", 2: "Fusion Material", 3: "Token", 4: "Flip Effect",
        5: "Change card position", 6: "Get control", 7: "Cancel out Effect"},
    2: {0: "Attribute", 1: "Type", 2: "Return card", 3: "Increase draw", 4: "Search Deck",
        5: "Recover cards from Graveyard", 6: "Increase/Decrease ATK/DEF", 7: "Pierce"},
    3: {0: "Cannot be destroyed", 1: "Restrict Attack", 2: "Direct Attack",
        3: "Multiple Attack", 4: "Reduce Life Points", 5: "Recover Life Points",
        6: "Spell Counter", 7: "Gamble"},
    4: {0: "Special Summon", 1: "Cannot perform Normal Summon", 2: "Game Original",
        3: "Card with a different artwork"},
    5: {},
}


@dataclass
class Card:
    index: int
    card_id: int
    name: str
    description: str
    password: int
    atk: int
    dfn: int
    exist: bool
    kind: int
    attr: int
    level: int
    icon: int
    ctype: int
    rarity: int
    genre: bytes
    prop1: int
    prop2: int

    @property
    def genres(self) -> list[str]:
        out = []
        for byte, bits in GENRE_BITS.items():
            for bit, label in bits.items():
                if self.genre[byte] & (1 << bit):
                    out.append(label)
        return out


class CardInfo:
    def __init__(self, folder: str, lang_suffix: str = "_E"):
        self.folder = folder
        self.lang = lang_suffix
        self.prop = self._read("CARD_Prop.bin")
        self.genre = self._read("CARD_Genre.bin")
        self.passw = self._read("CARD_Pass.bin")
        self.intid = self._read("CARD_IntID.bin")
        self.index = self._read(f"CARD_Indx{lang_suffix}.bin")
        self.names = self._read(f"CARD_Name{lang_suffix}.bin")
        self.descs = self._read(f"CARD_Desc{lang_suffix}.bin")
        self.count = len(self.prop) // 8

    def _read(self, name: str) -> bytes:
        with open(f"{self.folder}/{name}", "rb") as f:
            return f.read()

    # --- raw arrays ---------------------------------------------------------
    def internal_id(self, card_id: int) -> int:
        off = (card_id - CARD_ID_BASE) * 2
        return struct.unpack_from("<H", self.intid, off)[0]

    def card_ids(self) -> list[int]:
        return sorted(struct.unpack_from("<i", self.prop, i * 8)[0] & 0x1FFF
                      for i in range(1, self.count))

    def free_card_ids(self) -> list[int]:
        ids = self.card_ids()
        present = set(ids)
        return [c for c in range(min(ids), max(ids) + 1) if c not in present]

    # --- strings ------------------------------------------------------------
    def _string(self, buf: bytes, off: int) -> str:
        end = buf.index(b"\x00\x00", off)
        if end % 2:
            end += 1
        return buf[off:end].decode("utf-16-le", "replace")

    # --- card access --------------------------------------------------------
    def get_by_index(self, i: int) -> Card:
        p1, p2 = struct.unpack_from("<ii", self.prop, i * 8)
        name_off, desc_off = struct.unpack_from("<ii", self.index, i * 8)
        pw = struct.unpack_from("<i", self.passw, i * 4)[0] if len(self.passw) >= (i + 1) * 4 else 0
        return Card(
            index=i,
            card_id=p1 & 0x1FFF,
            name=self._string(self.names, name_off),
            description=self._string(self.descs, desc_off),
            password=pw,
            atk=((p1 >> 13) & 0x1FF) * 10,
            dfn=((p1 >> 22) & 0x1FF) * 10,
            exist=bool((p1 >> 31) & 1),
            kind=p2 & 0xF,
            attr=(p2 >> 4) & 0xF,
            level=(p2 >> 8) & 0xF,
            icon=(p2 >> 12) & 0x7,
            ctype=(p2 >> 15) & 0x1F,
            rarity=(p2 >> 20) & 0x7,
            genre=self.genre[i * 6:(i + 1) * 6],
            prop1=p1, prop2=p2,
        )

    def get(self, card_id: int) -> Card:
        return self.get_by_index(self.internal_id(card_id))

    def by_name(self, name: str) -> Card | None:
        for i in range(1, self.count):
            if self._string(self.names, struct.unpack_from("<i", self.index, i * 8)[0]) == name:
                return self.get_by_index(i)
        return None

    def all_cards(self):
        return (self.get_by_index(i) for i in range(1, self.count))


if __name__ == "__main__":
    import sys
    ci = CardInfo(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "_E")
    print(f"cards={ci.count} ids {min(ci.card_ids())}..{max(ci.card_ids())} "
          f"free={len(ci.free_card_ids())}")
    for name in sys.argv[3:]:
        c = ci.by_name(name)
        if c:
            print(f"{c.card_id:5} {c.name:40} k={c.kind} atk={c.atk} def={c.dfn} "
                  f"genre={c.genre.hex()} {c.genres}")
        else:
            print(f"NOT FOUND: {name}")

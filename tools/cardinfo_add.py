#!/usr/bin/env python3
"""EHP v3 container rebuild + card append (TF1 cardinfo_<lng>.ehp).

Reads an EHP container, appends one brand new card record at the end of the
per-index arrays, and writes a rebuilt container. The header (including the
internal file-name strings) is preserved byte for byte; only the data offsets
and the total size are recomputed.

Evidence this is based on (all measured, see ESTADO-E1-test.md):
  - EHP v3: 0x00 magic+version, 0x04 total size, 0x08 "NOT ", 0x0C entry count,
            0x10 table of `count` * 8 bytes (name_offset, data_offset).
  - Regions are contiguous and sorted by data_offset; a region's size is the
    next region's offset minus its own (the last one ends at `total`).
  - CARD_Prop / CARD_Genre / CARD_Pass / CARD_Sort_E are 8/6/4/2 bytes per card
    indexed by internal index; CARD_Indx_E is 8 bytes per card and has two extra
    empty placeholder records at the end.
  - CARD_IntID is uint16 indexed by (CardID - 4000).
  - Every free CardID maps to internal index 0 (the null card), so a new card
    needs a new internal index appended, not a free one.
"""
from __future__ import annotations

import struct
import sys
from dataclasses import dataclass

MAGIC = b"EHP"
CARD_ID_BASE = 4000
EXIST_BIT = 0x80000000
CARD_ID_MASK = 0x1FFF
ATK_SHIFT, DEF_SHIFT, ATK_MASK = 13, 22, 0x1FF
LEVEL_SHIFT, LEVEL_MASK = 8, 0xF


@dataclass
class Entry:
    name: str
    table_index: int
    name_off: int
    data_off: int
    size: int
    body: bytes


def parse(data: bytes) -> tuple[bytes, list[Entry]]:
    """Return (header blob, entries sorted by data_offset)."""
    if data[0:3] != MAGIC:
        raise ValueError(f"not an EHP container: magic={data[0:4]!r}")
    total = struct.unpack_from("<I", data, 0x04)[0]
    count = struct.unpack_from("<I", data, 0x0C)[0]
    raw = []
    for i in range(count):
        name_off, data_off = struct.unpack_from("<II", data, 0x10 + i * 8)
        end = data.index(b"\x00", name_off)
        raw.append((data[name_off:end].decode("ascii"), i, name_off, data_off))
    if total != len(data):
        raise ValueError(f"total field {total} != file size {len(data)}")
    header_end = min(t[3] for t in raw)
    order = sorted(raw, key=lambda t: t[3])
    entries = []
    for i, (name, ti, name_off, data_off) in enumerate(order):
        end = order[i + 1][3] if i + 1 < len(order) else total
        entries.append(Entry(name, ti, name_off, data_off, end - data_off,
                             data[data_off:end]))
    if sum(e.size for e in entries) != total - header_end:
        raise ValueError("regions do not tile the container")
    return data[:header_end], entries


def rebuild(data: bytes, bodies: dict[str, bytes]) -> bytes:
    """Rebuild the container with the given regions replaced."""
    header, entries = parse(data)
    out = bytearray(header)
    offs = {}
    for e in entries:
        offs[e.name] = len(out)
        out += bodies.get(e.name, e.body)
    struct.pack_into("<I", out, 0x04, len(out))
    for e in entries:
        struct.pack_into("<I", out, 0x10 + e.table_index * 8 + 4, offs[e.name])
    return bytes(out)


def region(entries: list[Entry], prefix: str) -> Entry:
    hits = [e for e in entries if e.name.startswith(prefix)]
    if len(hits) != 1:
        raise ValueError(f"region {prefix!r}: {len(hits)} matches")
    return hits[0]


def internal_id(intid: bytes, card_id: int, base: int = CARD_ID_BASE) -> int:
    off = (card_id - base) * 2
    if off + 2 > len(intid):
        raise ValueError(f"CardID {card_id} outside CARD_IntID ({len(intid)//2} entries)")
    return struct.unpack_from("<H", intid, off)[0]


def _descramble(p1: int, p2: int) -> dict:
    return {"card_id": p1 & CARD_ID_MASK, "atk": ((p1 >> ATK_SHIFT) & ATK_MASK) * 10,
            "dfn": ((p1 >> DEF_SHIFT) & ATK_MASK) * 10, "exist": bool(p1 >> 31),
            "level": (p2 >> LEVEL_SHIFT) & LEVEL_MASK}


def describe(data: bytes, card_id: int, base: int = CARD_ID_BASE) -> dict:
    _, entries = parse(data)
    intid = region(entries, "CARD_IntID").body
    idx = internal_id(intid, card_id, base)
    prop = region(entries, "CARD_Prop").body
    p1, p2 = struct.unpack_from("<II", prop, idx * 8)
    info = _descramble(p1, p2)
    indx = region(entries, "CARD_Indx").body
    name_off, desc_off = struct.unpack_from("<II", indx, idx * 8)
    names = region(entries, "CARD_Name").body
    end = names.index(b"\x00\x00", name_off)
    if end % 2:  # a UTF-16LE NUL terminator can be found mid-character
        end += 1
    info.update(internal_index=idx, prop1=p1, prop2=p2, name_off=name_off,
                desc_off=desc_off, genre=region(entries, "CARD_Genre").body[idx * 6:(idx + 1) * 6],
                name=names[name_off:end].decode("utf-16-le", "replace"))
    return info


def add_card(data: bytes, *, card_id: int, donor_card_id: int, name: str,
             atk: int | None = None, dfn: int | None = None, level: int | None = None,
             canaries: tuple[tuple[int, int], ...] = (),
             base: int = CARD_ID_BASE) -> tuple[bytes, dict]:
    """Append one new card and optionally patch ATK canaries on existing cards."""
    _, entries = parse(data)
    bodies = {e.name: e.body for e in entries}
    prop = bodies[region(entries, "CARD_Prop").name]
    intid = bytearray(bodies[region(entries, "CARD_IntID").name])
    idx = len(prop) // 8

    indx_entry = region(entries, "CARD_Indx")
    if idx * 8 >= len(indx_entry.body):
        raise ValueError(f"internal index {idx} is past CARD_Indx ({len(indx_entry.body)//8} entries)")

    donor_idx = internal_id(bytes(intid), donor_card_id, base)
    p1, p2 = struct.unpack_from("<II", prop, donor_idx * 8)
    donor_desc_off = struct.unpack_from("<II", bodies[indx_entry.name], donor_idx * 8)[1]

    new_p1 = (p1 & ~CARD_ID_MASK) | (card_id & CARD_ID_MASK) | EXIST_BIT
    if atk is not None:
        new_p1 = (new_p1 & ~(ATK_MASK << ATK_SHIFT)) | ((atk // 10 & ATK_MASK) << ATK_SHIFT)
    if dfn is not None:
        new_p1 = (new_p1 & ~(ATK_MASK << DEF_SHIFT)) | ((dfn // 10 & ATK_MASK) << DEF_SHIFT)
    new_p2 = p2
    if level is not None:
        new_p2 = (new_p2 & ~(LEVEL_MASK << LEVEL_SHIFT)) | ((level & LEVEL_MASK) << LEVEL_SHIFT)

    report = {"internal_index": idx, "donor_internal_index": donor_idx,
              "donor_prop1": p1, "donor_prop2": p2, "new_prop1": new_p1,
              "new_prop2": new_p2, "old_size": len(data)}

    # canaries on existing cards (they keep their CardID, only the stats change)
    prop = bytearray(prop)
    for cid, catk in canaries:
        ci = internal_id(bytes(intid), cid, base)
        cp1, cp2 = struct.unpack_from("<II", prop, ci * 8)
        before = ((cp1 >> ATK_SHIFT) & ATK_MASK) * 10
        cp1 = (cp1 & ~(ATK_MASK << ATK_SHIFT)) | ((catk // 10 & ATK_MASK) << ATK_SHIFT)
        struct.pack_into("<II", prop, ci * 8, cp1, cp2)
        report.setdefault("canaries", []).append(
            {"card_id": cid, "internal_index": ci, "atk_before": before, "atk_after": catk})

    # the new record at internal index `idx`
    prop = bytes(prop[:idx * 8]) + struct.pack("<II", new_p1, new_p2) + bytes(prop[idx * 8:])
    bodies[region(entries, "CARD_Prop").name] = prop

    genre_entry = region(entries, "CARD_Genre")
    bodies[genre_entry.name] = genre_entry.body[:idx * 6] + genre_entry.body[donor_idx * 6:donor_idx * 6 + 6]

    passw_entry = region(entries, "CARD_Pass")
    bodies[passw_entry.name] = passw_entry.body[:idx * 4] + passw_entry.body[donor_idx * 4:donor_idx * 4 + 4]

    sort_entry = region(entries, "CARD_Sort")
    bodies[sort_entry.name] = sort_entry.body[:idx * 2] + sort_entry.body[donor_idx * 2:donor_idx * 2 + 2]

    names_entry = region(entries, "CARD_Name")
    name_off = len(names_entry.body)
    encoded = name.encode("utf-16-le") + b"\x00\x00"
    bodies[names_entry.name] = names_entry.body + encoded
    report.update(name_off=name_off, name_bytes=len(encoded), desc_off=donor_desc_off)

    bodies[indx_entry.name] = (indx_entry.body[:idx * 8]
                               + struct.pack("<II", name_off, donor_desc_off)
                               + indx_entry.body[idx * 8:])

    struct.pack_into("<H", intid, (card_id - base) * 2, idx)
    bodies[region(entries, "CARD_IntID").name] = bytes(intid)
    report["intid_slot"] = (card_id - base) * 2

    out = rebuild(data, bodies)
    report["new_size"] = len(out)
    report["growth"] = len(out) - len(data)
    return out, report


def main(argv: list[str]) -> int:
    if len(argv) < 4:
        print(__doc__)
        print("usage: cardinfo_add.py <in.ehp> <out.ehp> --card-id N --name S "
              "--donor N [--atk N] [--def N] [--level N] [--canary ID:ATK]...\n"
              "       cardinfo_add.py <in.ehp> --print-card N")
        return 1
    src, dst = argv[1], argv[2]
    opts = {"atk": None, "dfn": None, "level": None}
    canaries: list[tuple[int, int]] = []
    card_id = donor = None
    name = None
    i = 3
    while i < len(argv):
        a = argv[i]
        if a == "--card-id":
            card_id = int(argv[i + 1]); i += 2
        elif a == "--donor":
            donor = int(argv[i + 1]); i += 2
        elif a == "--name":
            name = argv[i + 1]; i += 2
        elif a in ("--atk", "--def", "--level"):
            opts["dfn" if a == "--def" else a[2:]] = int(argv[i + 1]); i += 2
        elif a == "--canary":
            cid, catk = argv[i + 1].split(":")
            canaries.append((int(cid), int(catk))); i += 2
        elif a == "--print-card":
            print(describe(open(src, "rb").read(), int(argv[i + 1]))); return 0
        else:
            raise SystemExit(f"unknown option {a}")
    data = open(src, "rb").read()
    out, report = add_card(data, card_id=card_id, donor_card_id=donor, name=name,
                           canaries=tuple(canaries), **opts)
    with open(dst, "wb") as f:
        f.write(out)
    print(f"wrote {dst}: {len(data)} -> {len(out)} bytes (+{report['growth']})")
    for k, v in report.items():
        print(f"  {k}: {v}")
    print("readback:", describe(out, card_id))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

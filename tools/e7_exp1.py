#!/usr/bin/env python3
"""E7/T7 experiment: is the `{u16 CardID; u16 0; u32 handler_ptr}` table live?

`ESTADO-E7.md` §7.2 measured, inside `libduel_eng.prx` `.data`, a contiguous
table of 8-byte entries starting at VMA `0x10b018`.  This tool parses the whole
table, patches exactly one pointer word of a card the player owns (so the card
runs `Monster Reborn`'s handler instead of its own), and verifies that a copy of
the E8 ISO differs from the source image in exactly those 4 bytes.

Measured coordinates (ESTADO-E7.md §7.2/§7.5, re-checked by this tool):

  * `libduel_eng.prx` is a plain ELF, 1470794 bytes; inside the E8 ISO it lives
    at `PSP_GAME/USRDIR/gmodule/libduel_eng.prx` and is byte-identical to the
    copy extracted in `trabajo/e1c/gm/`.
  * file offset = VMA - 0xfe1b4 + 0xfe214  (i.e. VMA + 0x60).
  * the table starts at VMA 0x10b018 and holds 363 contiguous entries whose
    CardIDs strictly ascend inside the card-database range 4007..6957; the next
    word (VMA 0x10bb70) has the out-of-range key 0xfffe, so the walk stops
    there (363 entries, 2904 bytes).  Right after it come the keys 0xfffe and
    0xffff (both pad 0, both with real handler pointers), then seven
    `ff ff ff ff ff ff ff ff` words, then unrelated data.
  * the pointer word of entry `e` sits at VMA `e.vma + 4`; every one of the 365
    pointer words carries an `R_MIPS_32` (type 2) entry in `.rel.data`
    (file 0x159b48, size 0xd5e0), so writing another relocated absolute VMA is
    consistent with the loader.
  * source card (this experiment): `Salvage` CardID 5908, entry VMA 0x10b5d0,
    pointer word VMA 0x10b5d4 = file 0x10b634, today 0x000b2844.
    Save evidence (`trabajo/e6/DATA0.hero`): owned record `04 01 03 00` at the
    index of CardID 5908, and CardID 5908 is one of the 35 distinct CardIDs of
    the player's deck (list at save 0x4830, count 42).
  * donor: `Monster Reborn` CardID 4842, entry VMA 0x10b0b0, pointer word VMA
    0x10b0b4 = file 0x10b114, value 0x000adbcc.

Subcommands (every one refuses to write when an invariant fails):

  table  [--src ISO] [--prx FILE] [--ehp-dir DIR] [--out FILE]
         Walk the table, assert its layout and relocs, print every entry with
         its CardID, resolved card name and pointer (and optionally save the
         dump as TSV).

  patch  --out FILE [--src ISO] [--prx FILE] [--card N] [--donor N]
         Read the pristine `.prx`, re-derive the source and donor entries from
         the table itself (never from free text), assert every precondition and
         write a copy with the single pointer word changed.

  verify --pristine FILE --patched FILE [--prx FILE] [--card N] [--donor N]
         Assert every changed byte lies inside the declared 4-byte pointer word
         at the declared offset, that the word now holds the donor pointer, and
         that nothing else (including .rel.data) changed.  Note: because
         0x000b2844 and 0x000adbcc share the high byte 0x00, only 3 of the 4
         bytes actually change value; the tool reports that count instead of
         pretending it is 4.

  iso    --patched-prx FILE --out FILE [--src ISO] [--card N] [--donor N]
         Verify the patched `.prx`, copy the source ISO, replace the 4 bytes in
         place (size unchanged) and prove by a full chunked comparison that the
         image differs from the source only in the sector(s) covering those
         bytes.  Prints sha256 and size of the result.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import struct
import sys
from dataclasses import dataclass

TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
import iso_replace                       # noqa: E402
from iso9660 import SECTOR, Iso9660      # noqa: E402

PRX_IN_ISO = "PSP_GAME/USRDIR/gmodule/libduel_eng.prx"
DEFAULT_SRC_ISO = os.path.join(ROOT, "trabajo", "e8", "TF1-E8-G6.iso")
DEFAULT_OUT_ISO = os.path.join(ROOT, "trabajo", "e7", "TF1-E7-EXP1.iso")
DEFAULT_EHP_DIR = os.path.join(ROOT, "trabajo", "e2", "eng")
DEFAULT_LANG = "_E"

# --- measured constants ------------------------------------------------------
PRX_SIZE = 1470794
PRX_SHA256 = "6867fb17d48479a429cb71b660daa7ebb8e4be90e0a63c2f4c619ceaa54bcf91"
VMA_BASE = 0xFE1B4                        # .data VMA (ELF load segment base)
FILE_BASE = 0xFE214                       # .data file offset
DELTA = FILE_BASE - VMA_BASE              # +0x60
TEXT_VMA = 0x60
DATA_END_VMA = VMA_BASE + 0xDECC          # 0x10c080
TABLE_VMA = 0x10B018
TABLE_END_VMA = 0x10BB70
TABLE_ENTRIES = 363
TAIL_KEYS = (0xFFFE, 0xFFFF)              # two non-ascending markers after the table
TAIL_PAD_WORDS = 7                        # `ff ff ...` words after the markers
REL_DATA_OFF = 0x159B48
REL_DATA_SIZE = 0xD5E0
R_MIPS_32 = 2
CARD_ID_MIN = 4007
CARD_ID_MAX = 6957

SOURCE_CARD = 5908                        # Salvage (owned, in the player deck)
DONOR_CARD = 4842                         # Monster Reborn


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_offset(vma: int) -> int:
    return vma - VMA_BASE + FILE_BASE


@dataclass
class TableEntry:
    vma: int
    card_id: int
    ptr: int

    @property
    def file_offset(self) -> int:
        return file_offset(self.vma)

    @property
    def ptr_offset(self) -> int:
        return file_offset(self.vma + 4)


def parse_table(prx: bytes) -> tuple[list[TableEntry], int]:
    """Walk the 8-byte table while the measured layout holds; return (entries, end_vma).

    Raises ValueError on the first layout violation instead of guessing.
    """
    if len(prx) != PRX_SIZE:
        raise ValueError(f"prx is {len(prx)} bytes, expected {PRX_SIZE}")
    entries: list[TableEntry] = []
    vma = TABLE_VMA
    prev: int | None = None
    stop = "ran past the end of the module"
    while True:
        off = file_offset(vma)
        if off + 8 > len(prx):
            break
        card_id, pad, ptr = struct.unpack_from("<HHI", prx, off)
        if pad != 0:
            stop = f"pad of the word at VMA {vma:#x} is {pad:#x}, not 0"
            break
        if not CARD_ID_MIN <= card_id <= CARD_ID_MAX:
            stop = f"CardID {card_id} at VMA {vma:#x} is outside " \
                   f"{CARD_ID_MIN}..{CARD_ID_MAX}"
            break
        if prev is not None and card_id <= prev:
            stop = f"CardID {card_id} at VMA {vma:#x} does not ascend from {prev}"
            break
        if not TEXT_VMA <= ptr < DATA_END_VMA:
            stop = f"handler {ptr:#x} at VMA {vma:#x} is outside the module image"
            break
        entries.append(TableEntry(vma=vma, card_id=card_id, ptr=ptr))
        prev = card_id
        vma += 8

    if vma != TABLE_END_VMA:
        raise ValueError(f"the table walked {len(entries)} entries and stopped at "
                         f"VMA {vma:#x} ({stop}), expected it to hold up to "
                         f"{TABLE_END_VMA:#x}")
    if len(entries) != TABLE_ENTRIES:
        raise ValueError(f"the table has {len(entries)} entries, expected "
                         f"{TABLE_ENTRIES}")
    for i, key in enumerate(TAIL_KEYS):
        off = file_offset(TABLE_END_VMA) + i * 8
        cid, pad, _ptr = struct.unpack_from("<HHI", prx, off)
        if (cid, pad) != (key, 0):
            raise ValueError(f"tail marker {i} at VMA {TABLE_END_VMA + i * 8:#x} is "
                             f"({cid:#06x}, pad {pad:#x}), expected "
                             f"({key:#06x}, pad 0)")
    pad_off = file_offset(TABLE_END_VMA) + len(TAIL_KEYS) * 8
    words = [prx[pad_off + i * 8:pad_off + i * 8 + 8] for i in range(TAIL_PAD_WORDS)]
    if any(w != b"\xff" * 8 for w in words):
        raise ValueError(f"the {TAIL_PAD_WORDS} words after the tail markers are "
                         f"not all 0xff")
    return entries, vma


def relocations(prx: bytes) -> dict[int, int]:
    """VMA -> relocation type, from `.rel.data`."""
    rel: dict[int, int] = {}
    for i in range(REL_DATA_SIZE // 8):
        off, typ = struct.unpack_from("<II", prx, REL_DATA_OFF + i * 8)
        rel[off] = typ
    return rel


def assert_relocs(prx: bytes, entries: list[TableEntry]) -> None:
    rel = relocations(prx)
    missing = [e for e in entries if rel.get(e.vma + 4) != R_MIPS_32]
    if missing:
        raise ValueError(f"{len(missing)} of {len(entries)} pointer words have no "
                         f"R_MIPS_32 reloc, e.g. VMA "
                         f"{missing[0].vma + 4:#x} (CardID {missing[0].card_id})")


def load_prx(args) -> tuple[bytes, str]:
    """The pristine module: from `--prx` if given, else from `--src` ISO."""
    if getattr(args, "prx", None):
        with open(args.prx, "rb") as f:
            return f.read(), args.prx
    src = getattr(args, "src", None) or DEFAULT_SRC_ISO
    if not os.path.exists(src):
        raise SystemExit(f"missing input ISO: {src}")
    return iso_replace.read_iso_file(src, PRX_IN_ISO), f"{src}:{PRX_IN_ISO}"


def check_pristine(prx: bytes, source: str) -> None:
    got = sha256(prx)
    if got != PRX_SHA256:
        raise ValueError(f"{source}: sha256 {got} differs from the pinned pristine "
                         f"{PRX_SHA256}")
    print(f"pristine `{source}`: {len(prx)} bytes, sha256 {got} (pinned, OK)")


def find_entry(entries: list[TableEntry], card_id: int) -> TableEntry:
    hits = [e for e in entries if e.card_id == card_id]
    if len(hits) != 1:
        raise ValueError(f"CardID {card_id} has {len(hits)} entries in the table, "
                         f"expected exactly 1")
    return hits[0]


def resolve_names(ehp_dir: str, lang: str) -> dict[int, tuple[str, int]]:
    """CardID -> (name, kind), through the independent reader tools/tfcard.py.

    `kind` 1 = monster, 13 = Spell, 14 = Trap (measured; see ESTADO-E0.md §2).
    """
    import tfcard
    ci = tfcard.CardInfo(ehp_dir, lang)
    info: dict[int, tuple[str, int]] = {}
    for i in range(1, ci.count):
        card = ci.get_by_index(i)
        info.setdefault(card.card_id, (card.name, card.kind))
    return info


def plan_patch(prx: bytes, entries: list[TableEntry], source_id: int,
               donor_id: int) -> dict:
    """Validate every precondition and return the single-word patch plan."""
    source = find_entry(entries, source_id)
    donor = find_entry(entries, donor_id)
    if source.card_id == donor.card_id:
        raise ValueError("source and donor are the same card: the patch would be a no-op")
    if source.ptr == donor.ptr:
        raise ValueError(f"CardID {source_id} already points at the donor handler "
                         f"{donor.ptr:#x}: the patch would be a no-op")
    before = prx[source.ptr_offset:source.ptr_offset + 4]
    want_before = struct.pack("<I", source.ptr)
    if before != want_before:
        raise ValueError(f"CardID {source_id}: bytes at file {source.ptr_offset:#x} "
                         f"are {before.hex()}, the table says {want_before.hex()}")
    rel = relocations(prx).get(source.vma + 4)
    if rel != R_MIPS_32:
        raise ValueError(f"CardID {source_id}: pointer word VMA {source.vma + 4:#x} "
                         f"has reloc type {rel}, expected R_MIPS_32 ({R_MIPS_32})")
    after = prx[:source.ptr_offset] + struct.pack("<I", donor.ptr) \
        + prx[source.ptr_offset + 4:]
    changed = [i for i in range(len(prx)) if prx[i] != after[i]]
    want = list(range(source.ptr_offset, source.ptr_offset + 4))
    if not set(changed) <= set(want):
        raise ValueError(f"the patch changed bytes outside the declared word: "
                         f"{sorted(set(changed) - set(want))}")
    return {"source": source, "donor": donor, "before": before, "after": want_before,
            "patched": after, "reloc_vma": source.vma + 4, "reloc_type": rel,
            "bytes_changed": len(changed)}


def verify_pair(pristine: bytes, patched: bytes, entries: list[TableEntry],
                source_id: int, donor_id: int) -> tuple[list[str], dict]:
    """Independent check of a patched file against the pristine one."""
    fails: list[str] = []
    plan: dict = {}
    try:
        source = find_entry(entries, source_id)
        donor = find_entry(entries, donor_id)
    except ValueError as exc:
        return [str(exc)], plan
    if len(pristine) != len(patched):
        return [f"size changed: {len(pristine)} -> {len(patched)}"], plan
    changed = [i for i in range(len(pristine)) if pristine[i] != patched[i]]
    want = list(range(source.ptr_offset, source.ptr_offset + 4))
    if not changed:
        fails.append("the file is byte-identical to the pristine: nothing was "
                     "patched")
    outside = sorted(set(changed) - set(want))
    if outside:
        fails.append(f"{len(outside)} bytes outside the declared pointer word "
                     f"changed (first {outside[0]:#x}); the file differs in "
                     f"{len(changed)} bytes, expected all inside "
                     f"{want[0]:#x}..{want[-1]:#x}")
    got = struct.unpack_from("<I", patched, source.ptr_offset)[0]
    if got != donor.ptr:
        fails.append(f"patched pointer is {got:#010x}, expected the donor "
                     f"pointer {donor.ptr:#010x}")
    actual = struct.unpack_from("<HHI", patched, source.file_offset)
    if actual != (source.card_id, 0, donor.ptr):
        fails.append(f"patched entry reads {actual}, expected "
                     f"({source.card_id}, 0, {donor.ptr:#x})")
    if patched[REL_DATA_OFF:REL_DATA_OFF + REL_DATA_SIZE] != \
            pristine[REL_DATA_OFF:REL_DATA_OFF + REL_DATA_SIZE]:
        fails.append(".rel.data changed (the loader's relocations must stay intact)")
    plan = {"source": source, "donor": donor,
            "before": pristine[source.ptr_offset:source.ptr_offset + 4],
            "after": patched[source.ptr_offset:source.ptr_offset + 4],
            "bytes_changed": len(changed),
            "word": (want[0], want[-1] + 1)}
    if len(changed) != 4 and not fails:
        fails_note = (f"note: the 4-byte pointer word is rewritten but only "
                      f"{len(changed)} of its byte values change, because "
                      f"0x{source.ptr:08x} and 0x{donor.ptr:08x} share the high "
                      f"byte 0x00")
        plan["note"] = fails_note
    return fails, plan


def print_patch_map(plan: dict) -> None:
    source, donor = plan["source"], plan["donor"]
    print(f"  source: CardID {source.card_id} entry VMA {source.vma:#08x}, "
          f"pointer word VMA {source.vma + 4:#08x} = file {source.ptr_offset:#08x}")
    print(f"  donor : CardID {donor.card_id} entry VMA {donor.vma:#08x}, "
          f"pointer word VMA {donor.vma + 4:#08x} = file {donor.ptr_offset:#08x}")
    print(f"  patch : file {source.ptr_offset:#08x}  "
          f"{plan['before'].hex()}  ->  {plan['after'].hex()}"
          f"   (0x{source.ptr:08x} -> 0x{donor.ptr:08x}, R_MIPS_32 at VMA "
          f"{source.vma + 4:#08x})")
    if plan.get("bytes_changed") is not None:
        print(f"  bytes actually changing value: {plan['bytes_changed']} of the "
              f"4-byte word (the high byte of both pointers is 0x00)")
    if plan.get("note"):
        print(f"  {plan['note']}")


# --------------------------------------------------------------------------- #
# subcommands
# --------------------------------------------------------------------------- #
def cmd_table(args) -> int:
    prx, source = load_prx(args)
    check_pristine(prx, source)
    entries, end = parse_table(prx)
    assert_relocs(prx, entries)
    print(f"table: {len(entries)} entries at VMA {TABLE_VMA:#08x}..{end:#08x} "
          f"(file {file_offset(TABLE_VMA):#08x}..{file_offset(end):#08x})")
    tail = []
    for i, key in enumerate(TAIL_KEYS):
        cid, pad, ptr = struct.unpack_from("<HHI", prx,
                                           file_offset(end) + i * 8)
        tail.append(f"{key:#06x}->{ptr:#010x}")
    print(f"  tail after the table: keys {' and '.join(tail)}, then "
          f"{TAIL_PAD_WORDS} words of 0xffffffff, then unrelated data")
    try:
        info = resolve_names(args.ehp_dir, args.lang)
    except Exception as exc:                                  # noqa: BLE001
        info = {}
        print(f"  note: card names unavailable ({exc})")
    lines = ["#\tvma\tfile\tcardid\tkind\tptr\treloc\tname"]
    rows = []
    for i, e in enumerate(entries):
        name, kind = info.get(e.card_id, ("<not in card database>", -1))
        rows.append(f"{i}\t{e.vma:#08x}\t{e.ptr_offset:#08x}\t{e.card_id}\t{kind}\t"
                    f"{e.ptr:#010x}\tR_MIPS_32\t{name}")
        print(f"  {i:3d}  {e.vma:#08x}  file {e.ptr_offset:#08x}  "
              f"CardID {e.card_id:5d}  kind {kind:2d}  ptr {e.ptr:#010x}  {name}")
    marker = {SOURCE_CARD: "source", DONOR_CARD: "donor"}
    for cid, role in marker.items():
        e = find_entry(entries, cid)
        print(f"  {role}: CardID {cid} entry VMA {e.vma:#08x}, pointer word VMA "
              f"{e.vma + 4:#08x} = file {e.ptr_offset:#08x}, value {e.ptr:#010x}")
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write("\n".join(lines + rows) + "\n")
        print(f"  dump written to {args.out}")
    return 0


def cmd_patch(args) -> int:
    prx, source = load_prx(args)
    print("--- preconditions")
    check_pristine(prx, source)
    entries, _ = parse_table(prx)
    assert_relocs(prx, entries)
    print(f"    table: {len(entries)} entries, all {len(entries)} pointer words "
          f"relocated R_MIPS_32")
    plan = plan_patch(prx, entries, args.card, args.donor)
    print("--- patch map")
    print_patch_map(plan)
    if os.path.exists(args.out):
        print(f"STOP: refusing to overwrite {args.out}")
        return 1
    with open(args.out, "wb") as f:
        f.write(plan["patched"])
    print(f"--- wrote {args.out}")
    print(f"    {len(plan['patched'])} bytes, sha256 {sha256(plan['patched'])}")
    fails, _ = verify_pair(prx, plan["patched"], entries, args.card, args.donor)
    if fails:
        print(f"SELF-VERIFY FAILED ({len(fails)}):")
        for x in fails:
            print(f"  FAIL: {x}")
        return 1
    print(f"    self-verify: every changed byte ({plan['bytes_changed']}) is inside "
          f"the 4 declared bytes at file {plan['source'].ptr_offset:#x}")
    return 0


def cmd_verify(args) -> int:
    with open(args.pristine, "rb") as f:
        pristine = f.read()
    with open(args.patched, "rb") as f:
        patched = f.read()
    print(f"pristine: {args.pristine} ({len(pristine)} bytes, sha256 "
          f"{sha256(pristine)})")
    print(f"patched : {args.patched} ({len(patched)} bytes, sha256 "
          f"{sha256(patched)})")
    check_pristine(pristine, args.pristine)
    entries, _ = parse_table(pristine)
    assert_relocs(pristine, entries)
    fails, plan = verify_pair(pristine, patched, entries, args.card, args.donor)
    if fails:
        print(f"VERIFICATION FAILED ({len(fails)}):")
        for x in fails:
            print(f"  FAIL: {x}")
        return 1
    print("--- patch map")
    print_patch_map(plan)
    print(f"verification: OK - the patched file differs from the pristine only "
          f"inside the declared 4-byte word at file {plan['source'].ptr_offset:#x} "
          f"({plan['bytes_changed']} byte values changed), and the word now holds "
          f"the donor pointer 0x{plan['donor'].ptr:08x}")
    return 0


def changed_sectors(a: str, b: str, chunk: int = 1 << 23) -> set[int]:
    """LBA of every 2048-byte sector whose bytes differ between two images."""
    out: set[int] = set()
    with open(a, "rb") as fa, open(b, "rb") as fb:
        base = 0
        while True:
            x, y = fa.read(chunk), fb.read(chunk)
            if not x and not y:
                break
            if len(x) != len(y):
                raise ValueError(f"image sizes differ at offset {base}")
            if x != y:
                for i in range(0, len(x), SECTOR):
                    if x[i:i + SECTOR] != y[i:i + SECTOR]:
                        out.add((base + i) // SECTOR)
            base += len(x)
    return out


def cmd_iso(args) -> int:
    with open(args.patched_prx, "rb") as f:
        patched_prx = f.read()
    pristine_prx = iso_replace.read_iso_file(args.src, PRX_IN_ISO)
    print(f"source ISO: {args.src}")
    print(f"  {PRX_IN_ISO}: {len(pristine_prx)} bytes, sha256 "
          f"{sha256(pristine_prx)}")
    print(f"  patched .prx : {len(patched_prx)} bytes, sha256 "
          f"{sha256(patched_prx)}")
    print("--- 1. the patched module verifies on its own")
    check_pristine(pristine_prx, f"{args.src}:{PRX_IN_ISO}")
    entries, _ = parse_table(pristine_prx)
    assert_relocs(pristine_prx, entries)
    fails, plan = verify_pair(pristine_prx, patched_prx, entries, args.card,
                              args.donor)
    if fails:
        print(f"STOP: the patched module does not verify ({len(fails)}):")
        for x in fails:
            print(f"  FAIL: {x}")
        return 1
    print_patch_map(plan)
    print(f"    OK: all changed bytes are inside the declared word and .rel.data "
          f"is untouched")

    iso = Iso9660(args.src)
    try:
        entry = iso.resolve(PRX_IN_ISO)
        src_size = os.path.getsize(args.src)
    finally:
        iso.close()
    lba = entry.extent + plan["source"].ptr_offset // SECTOR
    print(f"--- 2. the 4 bytes live inside ISO sector {lba} "
          f"(file extent LBA {entry.extent} + {plan['source'].ptr_offset:#x})")
    if os.path.exists(args.out):
        print(f"STOP: refusing to overwrite {args.out}")
        return 1
    print(f"--- 3. copy {args.src} -> {args.out}")
    shutil.copyfile(args.src, args.out)
    report = iso_replace.patch_bytes(args.out, PRX_IN_ISO,
                                     plan["source"].ptr_offset,
                                     struct.pack("<I", plan["donor"].ptr),
                                     expected=struct.pack("<I", plan["source"].ptr))
    print(f"    replaced {report['before']} -> {report['after']} "
          f"(roundtrip {report['roundtrip']})")

    print("--- 4. verification from the written ISO")
    back = iso_replace.read_iso_file(args.out, PRX_IN_ISO)
    if back != patched_prx:
        print("FAIL: the module read back from the ISO differs from the artifact")
        return 1
    if len(back) != PRX_SIZE:
        print(f"FAIL: module size {len(back)} != {PRX_SIZE}")
        return 1
    diff = changed_sectors(args.src, args.out)
    errs: list[str] = []
    if diff != {lba}:
        errs.append(f"changed sectors are {sorted(diff)}, expected exactly [{lba}]")
    out_size = os.path.getsize(args.out)
    if out_size != src_size:
        errs.append(f"ISO size {out_size} != source size {src_size}")
    print(f"    changed sectors: {len(diff)} -> {sorted(diff)}")
    print(f"    every other sector of {out_size} bytes is byte-identical "
          f"(full chunked comparison)")
    print(f"    {PRX_IN_ISO} read back equals the patched artifact")
    if errs:
        print(f"VERIFICATION FAILED ({len(errs)}):")
        for x in errs:
            print(f"  FAIL: {x}")
        return 1
    print(f"OK -> {args.out}")
    print(f"    size {out_size} bytes, sha256 {sha256_file(args.out)}")
    return 0


def sha256_file(path: str, chunk: int = 1 << 23) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            block = f.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--src", default=DEFAULT_SRC_ISO,
                        help=f"source ISO (default {DEFAULT_SRC_ISO})")
        sp.add_argument("--prx", default=None,
                        help="pristine libduel_eng.prx file (overrides --src)")

    t = sub.add_parser("table", help="parse and print the whole CardID table")
    common(t)
    t.add_argument("--ehp-dir", default=DEFAULT_EHP_DIR,
                   help="extracted cardinfo folder for names")
    t.add_argument("--lang", default=DEFAULT_LANG)
    t.add_argument("--out", default=None, help="optional TSV dump path")
    t.set_defaults(func=cmd_table)

    c = sub.add_parser("patch", help="patch one pointer word into a .prx copy")
    common(c)
    c.add_argument("--out", required=True)
    c.add_argument("--card", type=int, default=SOURCE_CARD)
    c.add_argument("--donor", type=int, default=DONOR_CARD)
    c.set_defaults(func=cmd_patch)

    v = sub.add_parser("verify", help="verify a patched .prx against the pristine")
    v.add_argument("--pristine", required=True)
    v.add_argument("--patched", required=True)
    v.add_argument("--card", type=int, default=SOURCE_CARD)
    v.add_argument("--donor", type=int, default=DONOR_CARD)
    v.set_defaults(func=cmd_verify)

    i = sub.add_parser("iso", help="build and verify the experiment ISO")
    i.add_argument("--src", default=DEFAULT_SRC_ISO)
    i.add_argument("--patched-prx", required=True)
    i.add_argument("--out", default=DEFAULT_OUT_ISO)
    i.add_argument("--card", type=int, default=SOURCE_CARD)
    i.add_argument("--donor", type=int, default=DONOR_CARD)
    i.set_defaults(func=cmd_iso)
    return p


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, FileNotFoundError) as exc:
        print(f"STOP: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

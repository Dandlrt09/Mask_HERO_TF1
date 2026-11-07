#!/usr/bin/env python3
"""B1/T2 EXP3: front-B viability probe -- our own code in the 2nd PT_LOAD.

`odd/tasks/frente-b-efectos-magicas.md` T2 (specs S1, S9) builds a MINIMAL probe:
one card that executes a tiny stub living in the grown 2nd `PT_LOAD` of
`libduel_eng`, whose only job is to prove, in one PPSSPP round, that

  * the 24-byte dispatch entry's `slot4` (the activation resolver, measured by
    E7/T1) is a LIVE lever, and
  * code appended to the 2nd `PT_LOAD` segment actually executes.

Base module: `trabajo/e7/libduel_eng_f4.prx` (E7 front A, closed and validated
in-game), sha256 `c2873ad9...aa650`, size 0x1674e0.  Base ISO:
`trabajo/e7/TF1-E7-F4.iso`, sha256 `4323b0aa...2b96`, 798787584 B.  Neither is
ever modified: this tool only reads them.

Measured layout of the base module (re-asserted on every run):

  * ELF32, 2 `PT_LOAD`; `e_phoff` 0x167150, `e_phnum` 2, `e_phentsize` 32.
  * PH[0]: type 1, off 0x60, vaddr 0, paddr 0xfc9b0, filesz 0x10c080,
    memsz 0x112910, flags 7.
  * PH[1]: type 1, off 0x167190, vaddr 0x112910, filesz = memsz = 0x350
    (the 848-byte / 105-record fusion recipe table + terminator of E7 F4),
    flags 7.  file = VMA + 0x54880 for this segment (vma 0x112c58 = file
    0x1674d8, the `(10,0,0,0)` terminator).
  * `.data` file = VMA + 0x60; the 4 x 24-byte dispatch tables are
    T1 0x100644 (764), T2 0x104dfc (454), T3 0x1078a4 (175), T4 0x108924 (213),
    entry `{u16 CardID@+0; u16 pad@+2; u32 slot4@+4; ... slot20@+20}`.

The probe (values fixed by the approved design; file=append point is exact):

  * append an 8-byte stub at file `0x1674e0` = VMA `0x112c60`, right AFTER the
    recipe payload's terminator (`[0x167190, 0x1674e0)` is untouched):

        j   0x7837c      ; word 0x0801E0DF  (Dark Hole 4342's slot4 resolver)
        nop              ; word 0x00000000

  * grow PH[1] `p_filesz`/`p_memsz` 0x350 -> 0x358; result size 0x1674e8.
  * card 4844 (Olla de la Codicia, T1@0x10116c): slot4 -> 0x112c60 (our stub),
    slot8 -> 0x503e8 (Dark Hole's field filter).  Its slot4 is our OWN code in
    the new segment, so a visible change proves both halves at once.
  * card 5328 (Refuerzo del Ejercito, T1@0x1023b4): slot4 -> 0x7837c (Dark
    Hole's resolver, direct), slot8 -> 0x503e8.  Data-only half: proves slot4
    is live even without our code.
  * slot12/16/20 untouched, no other entry touched, no relocation added.

Subcommands (every writer refuses unless ALL preconditions hold):

  dump   [--prx FILE]
         Read-only: print the base layout, the 4 dispatch tables, every located
         probe entry with its 5 slots, and the exact patch plan.

  build  [--prx FILE] [--out FILE]
         Validate the pinned base, locate both entries by CardID, re-assert
         PH[1], build the patched module, self-verify and write it.

  verify [--pristine FILE] [--patched FILE]
         Independently re-derive the patched image from the base and assert the
         stub words, PH[1] 0x358, both entry slots, the untouched recipe
         payload, and that every other byte of [0, 0x1674e0) is unchanged.

  iso    [--src ISO] [--patched-prx FILE] [--out FILE]
         Verify the patched module, prove the base ISO's module equals it, copy
         the ISO, replace the module in place (directory size 0x1674e8), and
         prove the image differs from the source only in the declared sectors.
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
import iso_replace                              # noqa: E402
from iso9660 import SECTOR, Iso9660             # noqa: E402

# reuse the T1/B1 recon parser ONLY to locate entries by CardID and cross-check
RECON = os.path.join(ROOT, "trabajo", "b1", "recon")
if RECON not in sys.path:
    sys.path.insert(0, RECON)
from prxelf import Elf as ReconElf              # noqa: E402
from tables import load as recon_load           # noqa: E402

PRX_IN_ISO = "PSP_GAME/USRDIR/gmodule/libduel_eng.prx"
NEXT_MODULE_IN_ISO = "PSP_GAME/USRDIR/gmodule/libduel_mgr.prx"

BASE_PRX = os.path.join(ROOT, "trabajo", "e7", "libduel_eng_f4.prx")
BASE_ISO = os.path.join(ROOT, "trabajo", "e7", "TF1-E7-F4.iso")
DEFAULT_OUT_PRX = os.path.join(ROOT, "trabajo", "b1", "libduel_eng_exp3.prx")
DEFAULT_OUT_ISO = os.path.join(ROOT, "trabajo", "b1", "TF1-B1-EXP3.iso")

# --- pinned base artefacts ---------------------------------------------------
BASE_PRX_SHA256 = "c2873ad9680e66d07d2fbda51b858d0affc783db868e4810e11e661a330aa650"
BASE_PRX_SIZE = 0x1674E0
BASE_ISO_SHA256 = "4323b0aa2ded8753230159d6a5517bf1a2f8f6747fd145ade1f70f6e37462b96"
BASE_ISO_SIZE = 798787584

ISO_PRX_EXTENT = 12048
ISO_PRX_ALLOC = 1472512                          # 719 * 2048
MGR_LBA_EXPECTED = 12767

FILE_DELTA = 0x60                                # file = VMA + 0x60 (in .data)
OLD_PHOFF = 0x167150
PHENTSIZE = 32
PH1_INDEX = 1
PH1_OFF = 0x167190
PH1_VADDR = 0x112910
PH1_OLD_SIZE = 0x350
PH1_NEW_SIZE = 0x358                             # + the 8-byte stub
PH0_EXPECTED = (1, 0x60, 0x0, 0xFC9B0, 0x10C080, 0x112910, 7, 16)
PH1_EXPECTED = (1, PH1_OFF, PH1_VADDR, PH1_VADDR, PH1_OLD_SIZE, PH1_OLD_SIZE,
                7, 16)
E_SHOFF = 0x10C230
E_SHNUM = 25
E_SHENTSIZE = 40
SECTION_TABLE_END = E_SHOFF + E_SHNUM * E_SHENTSIZE
REL_DATA_OFF = 0x159B48
REL_DATA_SIZE = 0xD5E0

# stub: appended right AFTER the recipe payload's terminator
STUB_FILE_OFF = 0x1674E0                         # == PH1_OFF + PH1_OLD_SIZE
STUB_VMA = 0x112C60                              # == PH1_VADDR + PH1_NEW_SIZE - 8
STUB_WORDS = (0x0801E0DF, 0x00000000)            # j 0x7837c ; nop

DARK_HOLE_CARD = 4342
DARK_HOLE_RESOLVER = 0x7837C
DARK_HOLE_FILTER = 0x503E8

TABLES = (("T1", 0x100644, 764), ("T2", 0x104dfc, 454),
          ("T3", 0x1078a4, 175), ("T4", 0x108924, 213))


@dataclass(frozen=True)
class Patch:
    card_id: int
    table: str
    entry_vma: int
    slot4: int
    slot8: int
    label: str


PATCHES = (
    Patch(4844, "T1", 0x10116C, STUB_VMA, DARK_HOLE_FILTER,
          "Olla de la Codicia: slot4 -> stub propio 0x%05x, slot8 -> filtro de "
          "Agujero Oscuro 0x%05x" % (STUB_VMA, DARK_HOLE_FILTER)),
    Patch(5328, "T1", 0x1023B4, DARK_HOLE_RESOLVER, DARK_HOLE_FILTER,
          "Refuerzo del Ejercito: slot4 -> resolutor de Agujero Oscuro 0x%05x, "
          "slot8 -> filtro 0x%05x" % (DARK_HOLE_RESOLVER, DARK_HOLE_FILTER)),
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str, chunk: int = 1 << 23) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            block = f.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def file_offset(vma: int) -> int:
    return vma + FILE_DELTA


def byte_ranges(indices) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    for i in indices:
        if runs and i == runs[-1][1]:
            runs[-1] = (runs[-1][0], i + 1)
        else:
            runs.append((i, i + 1))
    return runs


@dataclass
class ElfHeader:
    e_phoff: int
    e_phnum: int
    e_phentsize: int
    e_shoff: int
    e_shnum: int
    e_shentsize: int


def parse_elf_header(prx: bytes) -> ElfHeader:
    if len(prx) < 52:
        raise ValueError("file is too short to hold an ELF32 header")
    if prx[:4] != b"\x7fELF" or prx[4] != 1 or prx[5] != 1:
        raise ValueError("not a little-endian ELF32 file")
    (_t, _m, _v, _e, e_phoff, e_shoff, _f, _eh, e_phentsize, e_phnum,
     e_shentsize, e_shnum, _shstrndx) = struct.unpack_from("<HHIIIIIHHHHHH",
                                                           prx, 16)
    return ElfHeader(e_phoff, e_phnum, e_phentsize, e_shoff, e_shnum,
                     e_shentsize)


def parse_ph(prx: bytes, hdr: ElfHeader) -> list[tuple]:
    return [struct.unpack_from("<IIIIIIII", prx,
                               hdr.e_phoff + i * hdr.e_phentsize)
            for i in range(hdr.e_phnum)]


def locate_entries(path: str) -> tuple[dict, list]:
    """CardID -> [(table, vma, slots), ...] via the recon parser.

    The same CardID can legitimately live in more than one of the 4 dispatch
    tables, so a CardID maps to a list and callers select the expected table.
    """
    elf = ReconElf(path)
    idx: dict[int, list[tuple[str, int, tuple]]] = {}
    order: list[tuple[str, int, int]] = []
    for name, base, cnt, entries, ok in recon_load(elf):
        if not ok:
            raise ValueError(f"dispatch table {name} at 0x{base:x} is not "
                             f"strictly ascending")
        if len(entries) != cnt:
            raise ValueError(f"dispatch table {name} has {len(entries)} entries, "
                             f"expected {cnt}")
        for key, slots, va in entries:
            idx.setdefault(key, []).append((name, va, tuple(slots)))
        order.append((name, base, cnt))
    return idx, order


def select_entry(idx: dict, card_id: int, table: str):
    """The single entry for CardID in `table` (raising on 0 or >1 matches)."""
    hits = [h for h in idx.get(card_id, []) if h[0] == table]
    if len(hits) != 1:
        raise ValueError(f"CardID {card_id} has {len(hits)} entries in {table}, "
                         f"expected exactly 1")
    return hits[0]


def assert_base(prx: bytes, source: str) -> None:
    if len(prx) != BASE_PRX_SIZE:
        raise ValueError(f"{source}: {len(prx)} bytes, expected {BASE_PRX_SIZE}")
    got = sha256(prx)
    if got != BASE_PRX_SHA256:
        raise ValueError(f"{source}: sha256 {got} differs from the pinned F4 "
                         f"{BASE_PRX_SHA256}")
    hdr = parse_elf_header(prx)
    if (hdr.e_phoff, hdr.e_phnum, hdr.e_phentsize) != (OLD_PHOFF, 2, PHENTSIZE):
        raise ValueError(f"{source}: e_phoff/e_phnum/e_phentsize are "
                         f"{hdr.e_phoff:#x}/{hdr.e_phnum}/{hdr.e_phentsize}, "
                         f"expected {OLD_PHOFF:#x}/2/{PHENTSIZE}")
    phs = parse_ph(prx, hdr)
    if phs != [PH0_EXPECTED, PH1_EXPECTED]:
        raise ValueError(f"{source}: program headers are {phs}, expected "
                         f"[{PH0_EXPECTED}, {PH1_EXPECTED}]")
    if PH1_NEW_SIZE != PH1_OLD_SIZE + 8:
        raise ValueError("internal: PH1_NEW_SIZE is not PH1_OLD_SIZE + 8")
    if STUB_FILE_OFF != PH1_OFF + PH1_OLD_SIZE:
        raise ValueError("internal: STUB_FILE_OFF != PH1_OFF + PH1_OLD_SIZE")
    if STUB_VMA != PH1_VADDR + PH1_NEW_SIZE - 8:
        raise ValueError("internal: STUB_VMA != PH1_VADDR + PH1_NEW_SIZE - 8")
    if len(prx) != STUB_FILE_OFF:
        raise ValueError(f"{source}: size {len(prx):#x} is not the append point "
                         f"{STUB_FILE_OFF:#x}")


def _mapping_ok(prx: bytes, elf: ReconElf) -> None:
    for va in (0x100644, 0x10116C, 0x10116C + 24, 0x1023B4):
        if prx[file_offset(va):file_offset(va) + 8] != elf.read_vaddr(va, 8):
            raise ValueError(f"file = VMA + 0x60 does not hold at VMA {va:#x}")


def load_base(path: str):
    with open(path, "rb") as f:
        prx = f.read()
    assert_base(prx, path)
    elf = ReconElf(path)
    idx, order = locate_entries(path)
    _mapping_ok(prx, elf)
    return prx, parse_elf_header(prx), idx, order


def plan(prx: bytes, hdr: ElfHeader, idx: dict) -> dict:
    """Validate every precondition and return the exact patch plan."""
    ph1_file = hdr.e_phoff + PH1_INDEX * hdr.e_phentsize
    filesz_off = ph1_file + 16
    memsz_off = ph1_file + 20
    for off, want, name in ((filesz_off, PH1_OLD_SIZE, "p_filesz"),
                            (memsz_off, PH1_OLD_SIZE, "p_memsz")):
        got = struct.unpack_from("<I", prx, off)[0]
        if got != want:
            raise ValueError(f"PH[1] {name} at file {off:#x} is 0x{got:x}, "
                             f"expected 0x{want:x}")
    sites = []
    for p in PATCHES:
        try:
            name, va, slots = select_entry(idx, p.card_id, p.table)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        if va != p.entry_vma:
            raise ValueError(f"CardID {p.card_id} entry VMA is 0x{va:x}, expected "
                             f"0x{p.entry_vma:x}")
        s4 = file_offset(va + 4)
        s8 = file_offset(va + 8)
        old4 = struct.unpack_from("<I", prx, s4)[0]
        old8 = struct.unpack_from("<I", prx, s8)[0]
        if old4 != slots[0] or old8 != slots[1]:
            raise ValueError(f"CardID {p.card_id}: file slots do not match the "
                             f"locator ({old4:#x}/{old8:#x} vs "
                             f"{slots[0]:#x}/{slots[1]:#x})")
        if old4 == p.slot4:
            raise ValueError(f"CardID {p.card_id}: slot4 already 0x{p.slot4:x}")
        if old8 == p.slot8:
            raise ValueError(f"CardID {p.card_id}: slot8 already 0x{p.slot8:x}")
        sites.append({"card_id": p.card_id, "table": name, "entry_vma": va,
                      "s4": s4, "s8": s8, "old4": old4, "old8": old8,
                      "new4": p.slot4, "new8": p.slot8, "label": p.label,
                      "slots12_20": (slots[2], slots[3], slots[4])})
    if len({s["card_id"] for s in sites}) != len(sites):
        raise ValueError("two patches target the same card")
    return {"filesz_off": filesz_off, "memsz_off": memsz_off, "sites": sites}


def declared_offsets(pl: dict) -> set[int]:
    declared: set[int] = set()
    for off in (pl["filesz_off"], pl["memsz_off"]):
        declared.update(range(off, off + 4))
    for s in pl["sites"]:
        declared.update(range(s["s4"], s["s4"] + 4))
        declared.update(range(s["s8"], s["s8"] + 4))
    return declared


def build_patched(prx: bytes, hdr: ElfHeader, idx: dict) -> dict:
    """Return the patched image and the exact plan (raising on any doubt)."""
    pl = plan(prx, hdr, idx)
    if len(prx) != STUB_FILE_OFF:
        raise ValueError(f"base size {len(prx):#x} != append point "
                         f"{STUB_FILE_OFF:#x}")
    patched = bytearray(prx) + struct.pack("<2I", *STUB_WORDS)
    if len(patched) != BASE_PRX_SIZE + 8:
        raise ValueError(f"built image is {len(patched)} bytes, expected "
                         f"{BASE_PRX_SIZE + 8}")
    struct.pack_into("<I", patched, pl["filesz_off"], PH1_NEW_SIZE)
    struct.pack_into("<I", patched, pl["memsz_off"], PH1_NEW_SIZE)
    for s in pl["sites"]:
        struct.pack_into("<I", patched, s["s4"], s["new4"])
        struct.pack_into("<I", patched, s["s8"], s["new8"])
    declared = declared_offsets(pl)
    changed = [i for i in range(BASE_PRX_SIZE) if prx[i] != patched[i]]
    outside = sorted(set(changed) - declared)
    if outside:
        raise ValueError(f"bytes outside the declared regions changed, first "
                         f"{outside[0]:#x}")
    if not set(changed) <= declared:
        raise ValueError("diff outside the declared regions")
    return {"patched": bytes(patched), "plan": pl, "declared": sorted(declared),
            "changed": changed}


def verify_module(pristine: bytes, patched: bytes, hdr0: ElfHeader,
                  idx: dict) -> tuple[list[str], dict]:
    """Independent re-derivation and detailed check of a patched module."""
    fails: list[str] = []
    ev: dict = {}
    try:
        assert_base(pristine, "pristine")
    except ValueError as exc:
        return [str(exc)], ev

    # --- re-derive ------------------------------------------------------
    try:
        built = build_patched(pristine, hdr0, idx)
    except ValueError as exc:
        return fails + [str(exc)], ev
    ev["pristine_size"] = len(pristine)
    ev["pristine_sha256"] = sha256(pristine)
    ev["expected_size"] = BASE_PRX_SIZE + 8
    ev["expected_sha256"] = sha256(built["patched"])
    ev["plan"] = built["plan"]

    if len(patched) != BASE_PRX_SIZE + 8:
        fails.append(f"patched size is {len(patched):#x}, expected "
                     f"{BASE_PRX_SIZE + 8:#x}")
        return fails, ev
    if patched != built["patched"]:
        i = next((k for k in range(len(patched))
                  if patched[k] != built["patched"][k]), None)
        fails.append(f"patched image differs from the re-derived image at "
                     f"offset {i:#x}" if i is not None else
                     "patched image differs from the re-derived image")
        return fails, ev
    ev["patched_size"] = len(patched)
    ev["patched_sha256"] = sha256(patched)

    pl = built["plan"]

    # --- stub words -----------------------------------------------------
    stub = struct.unpack_from("<2I", patched, STUB_FILE_OFF)
    ev["stub_file_off"] = STUB_FILE_OFF
    ev["stub_vma"] = STUB_VMA
    ev["stub_words"] = stub
    if stub != STUB_WORDS:
        fails.append(f"stub words at file {STUB_FILE_OFF:#x} are "
                     f"[0x{stub[0]:08x}, 0x{stub[1]:08x}], expected "
                     f"[0x{STUB_WORDS[0]:08x}, 0x{STUB_WORDS[1]:08x}]")

    # --- PH[1] grown to 0x358 -------------------------------------------
    hdr = parse_elf_header(patched)
    phs = parse_ph(patched, hdr)
    ev["patched_ph"] = phs
    want_ph1 = (1, PH1_OFF, PH1_VADDR, PH1_VADDR, PH1_NEW_SIZE, PH1_NEW_SIZE,
                7, 16)
    if phs != [PH0_EXPECTED, want_ph1]:
        fails.append(f"patched program headers are {phs}, expected "
                     f"[{PH0_EXPECTED}, {want_ph1}]")
    else:
        if phs[1][4] != PH1_NEW_SIZE or phs[1][5] != PH1_NEW_SIZE:
            fails.append("PH[1] p_filesz/p_memsz are not 0x358")
        if phs[1][2] + phs[1][5] != STUB_VMA + 8:
            fails.append("PH[1] does not fully cover the stub VMA")

    # --- entries --------------------------------------------------------
    entry_ev = []
    for s in pl["sites"]:
        a4 = struct.unpack_from("<I", patched, s["s4"])[0]
        a8 = struct.unpack_from("<I", patched, s["s8"])[0]
        p12 = struct.unpack_from("<3I", patched, s["s4"] + 8)
        q12 = struct.unpack_from("<3I", pristine, s["s4"] + 8)
        ok4 = a4 == s["new4"]
        ok8 = a8 == s["new8"]
        okrest = p12 == q12
        entry_ev.append(dict(card_id=s["card_id"], entry_vma=s["entry_vma"],
                             s4=s["s4"], s8=s["s8"], old4=s["old4"],
                             old8=s["old8"], new4=a4, new8=a8, ok4=ok4, ok8=ok8,
                             rest_same=okrest, slots12_20=p12))
        if not ok4:
            fails.append(f"CardID {s['card_id']}: slot4 is 0x{a4:x}, expected "
                         f"0x{s['new4']:x}")
        if not ok8:
            fails.append(f"CardID {s['card_id']}: slot8 is 0x{a8:x}, expected "
                         f"0x{s['new8']:x}")
        if not okrest:
            fails.append(f"CardID {s['card_id']}: slot12/16/20 changed "
                         f"({p12} != {q12})")
    ev["entries"] = entry_ev

    # --- original part: only declared bytes; recipe payload intact ------
    declared = set(built["declared"])
    changed = [i for i in range(BASE_PRX_SIZE) if pristine[i] != patched[i]]
    outside = sorted(set(changed) - declared)
    ev["changed_count"] = len(changed)
    ev["changed_ranges"] = byte_ranges(changed)
    ev["declared_count"] = len(declared)
    if outside:
        fails.append(f"{len(outside)} byte(s) outside the declared regions "
                     f"changed, first {outside[0]:#x}")
    payload = patched[PH1_OFF:STUB_FILE_OFF]
    payload_ok = payload == pristine[PH1_OFF:STUB_FILE_OFF]
    ev["payload_len"] = len(payload)
    ev["payload_ok"] = payload_ok
    if not payload_ok:
        fails.append(f"the {len(payload)}-byte recipe payload at file "
                     f"{PH1_OFF:#x} changed")
    rel = patched[REL_DATA_OFF:REL_DATA_OFF + REL_DATA_SIZE]
    rel_ok = rel == pristine[REL_DATA_OFF:REL_DATA_OFF + REL_DATA_SIZE]
    ev["rel_data_ok"] = rel_ok
    if not rel_ok:
        fails.append(".rel.data changed (a relocation was added or altered)")

    # --- section table untouched ----------------------------------------
    sl = E_SHNUM * E_SHENTSIZE
    sec_ok = (patched[E_SHOFF:E_SHOFF + sl] == pristine[E_SHOFF:E_SHOFF + sl])
    ev["section_table_ok"] = sec_ok
    if not sec_ok:
        fails.append("the section header table bytes changed")
    if (hdr.e_shoff, hdr.e_shnum, hdr.e_shentsize) != (E_SHOFF, E_SHNUM,
                                                       E_SHENTSIZE):
        fails.append("section table header changed")

    # --- appended range is exactly the stub -----------------------------
    if patched[BASE_PRX_SIZE:] != struct.pack("<2I", *STUB_WORDS):
        fails.append("the appended range is not exactly the 8 stub bytes")
    return fails, ev


# --------------------------------------------------------------------------- #
# subcommands
# --------------------------------------------------------------------------- #
def cmd_dump(args) -> int:
    prx, hdr, idx, order = load_base(args.prx)
    print(f"base `{args.prx}`: {len(prx)} bytes, sha256 {sha256(prx)}")
    print(f"  ELF32, e_phoff {hdr.e_phoff:#x}, e_phnum {hdr.e_phnum}, "
          f"e_phentsize {hdr.e_phentsize}")
    for i, ph in enumerate(parse_ph(prx, hdr)):
        t, off, va, pa, fs, ms, fl, al = ph
        print(f"  PH{i}: type={t} p_offset={off:#x} p_vaddr={va:#x} "
              f"p_paddr={pa:#x} p_filesz={fs:#x} p_memsz={ms:#x} p_flags={fl} "
              f"p_align={al}")
    print(f"  file = VMA + 0x{FILE_DELTA:x} (.data)")
    print("--- dispatch tables")
    for name, base, cnt in order:
        print(f"  {name} base=0x{base:x} count={cnt}")
    print("--- probe entries (located by CardID)")
    for p in PATCHES:
        name, va, slots = select_entry(idx, p.card_id, p.table)
        s = " ".join(f"{x:08x}" for x in slots)
        print(f"  CardID {p.card_id} {name}@{va:#x}  slots[{s}]")
        print(f"    slot4 file {file_offset(va + 4):#08x}  0x{slots[0]:08x} -> "
              f"0x{p.slot4:08x}")
        print(f"    slot8 file {file_offset(va + 8):#08x}  0x{slots[1]:08x} -> "
              f"0x{p.slot8:08x}")
        print(f"    {p.label}")
    dh = idx.get(DARK_HOLE_CARD, [])
    for name, va, slots in dh:
        print(f"--- donor: CardID {DARK_HOLE_CARD} {name}@{va:#x}  "
              f"slots[{' '.join('%08x' % x for x in slots)}]")
    print(f"--- stub: file {STUB_FILE_OFF:#x} = VMA {STUB_VMA:#x}, words "
          f"[0x{STUB_WORDS[0]:08x}, 0x{STUB_WORDS[1]:08x}]")
    print(f"    PH[1] p_filesz/p_memsz {PH1_OLD_SIZE:#x} -> {PH1_NEW_SIZE:#x}; "
          f"result size {BASE_PRX_SIZE + 8:#x}")
    return 0


def cmd_build(args) -> int:
    prx, hdr, idx, _order = load_base(args.prx)
    print(f"base `{args.prx}`: {len(prx)} bytes, sha256 {sha256(prx)} (pinned F4)")
    if os.path.exists(args.out):
        print(f"STOP: refusing to overwrite {args.out}")
        return 1
    for inp in (args.prx, BASE_ISO, args.src if getattr(args, "src", None) else ""):
        if inp and os.path.realpath(args.out) == os.path.realpath(inp):
            print(f"STOP: --out is an input file ({inp})")
            return 1
    print("--- preconditions")
    built = build_patched(prx, hdr, idx)
    pl = built["plan"]
    print(f"    base pin OK; both CardIDs located; PH[1] 0x{PH1_OLD_SIZE:x}; "
          f"append point 0x{STUB_FILE_OFF:x} == EOF")
    print("--- patch plan")
    _print_plan(pl)
    fails, ev = verify_module(prx, built["patched"], hdr, idx)
    if fails:
        print(f"SELF-VERIFY FAILED ({len(fails)}):")
        for x in fails:
            print(f"  FAIL: {x}")
        return 1
    with open(args.out, "wb") as f:
        f.write(built["patched"])
    print(f"--- wrote {args.out}")
    print(f"    {len(built['patched'])} bytes, sha256 {sha256(built['patched'])}")
    print("    self-verify: OK")
    return 0


def _print_plan(pl: dict) -> None:
    print(f"  PH[1] p_filesz file {pl['filesz_off']:#08x}: "
          f"0x{PH1_OLD_SIZE:08x} -> 0x{PH1_NEW_SIZE:08x}")
    print(f"  PH[1] p_memsz  file {pl['memsz_off']:#08x}: "
          f"0x{PH1_OLD_SIZE:08x} -> 0x{PH1_NEW_SIZE:08x}")
    for s in pl["sites"]:
        print(f"  CardID {s['card_id']} {s['table']}@{s['entry_vma']:#x}")
        print(f"    slot4 file {s['s4']:#08x}: 0x{s['old4']:08x} -> "
              f"0x{s['new4']:08x}")
        print(f"    slot8 file {s['s8']:#08x}: 0x{s['old8']:08x} -> "
              f"0x{s['new8']:08x}")
    print(f"  stub  file {STUB_FILE_OFF:#08x}..{STUB_FILE_OFF + 8:#08x}: "
          f"0x{STUB_WORDS[0]:08x} 0x{STUB_WORDS[1]:08x}")
    print(f"  result size {BASE_PRX_SIZE:#x} -> {BASE_PRX_SIZE + 8:#x}")


def cmd_verify(args) -> int:
    with open(args.pristine, "rb") as f:
        pristine = f.read()
    with open(args.patched, "rb") as f:
        patched = f.read()
    if os.path.realpath(args.pristine) != os.path.realpath(args.prx):
        # still pin the given pristine, but locate from the canonical base
        assert_base(pristine, args.pristine)
    hdr0 = parse_elf_header(pristine)
    idx, _order = locate_entries(args.prx)
    print(f"pristine: {args.pristine} ({len(pristine)} bytes, sha256 "
          f"{sha256(pristine)})")
    print(f"patched : {args.patched} ({len(patched)} bytes, sha256 "
          f"{sha256(patched)})")
    fails, ev = verify_module(pristine, patched, hdr0, idx)
    if fails:
        print(f"VERIFICATION FAILED ({len(fails)}):")
        for x in fails:
            print(f"  FAIL: {x}")
        return 1
    print(f"--- 1. re-derived size/sha256")
    print(f"    {ev['expected_size']} bytes, sha256 {ev['expected_sha256']}")
    print(f"--- 2. stub")
    print(f"    file {ev['stub_file_off']:#x} = VMA {ev['stub_vma']:#x}: "
          f"[0x{ev['stub_words'][0]:08x}, 0x{ev['stub_words'][1]:08x}]")
    print(f"--- 3. PH[1]")
    for i, ph in enumerate(ev["patched_ph"]):
        t, off, va, pa, fs, ms, fl, al = ph
        print(f"    PH{i}: type={t} p_offset={off:#x} p_vaddr={va:#x} "
              f"p_filesz={fs:#x} p_memsz={ms:#x} p_flags={fl}")
    print(f"--- 4. entries")
    for e in ev["entries"]:
        print(f"    CardID {e['card_id']} entry VMA {e['entry_vma']:#x}")
        print(f"      slot4 file {e['s4']:#08x}: 0x{e['old4']:08x} -> "
              f"0x{e['new4']:08x}  {'OK' if e['ok4'] else 'FAIL'}")
        print(f"      slot8 file {e['s8']:#08x}: 0x{e['old8']:08x} -> "
              f"0x{e['new8']:08x}  {'OK' if e['ok8'] else 'FAIL'}")
        print(f"      slot12/16/20 {[f'0x{x:08x}' for x in e['slots12_20']]} "
              f"unchanged: {'OK' if e['rest_same'] else 'FAIL'}")
    print(f"--- 5. original part [0, {STUB_FILE_OFF:#x})")
    print(f"    differing bytes: {ev['changed_count']} of the declared "
          f"{ev['declared_count']}")
    for start, end in ev["changed_ranges"]:
        print(f"    changed range [{start:#x}, {end:#x}) ({end - start} B)")
    print(f"    recipe payload [{PH1_OFF:#x}, {STUB_FILE_OFF:#x}) "
          f"({ev['payload_len']} B) byte-identical: {ev['payload_ok']}")
    print(f"    .rel.data byte-identical: {ev['rel_data_ok']}")
    print(f"    section header table byte-identical: {ev['section_table_ok']}")
    print(f"--- 6. appended range [{BASE_PRX_SIZE:#x}, "
          f"{BASE_PRX_SIZE + 8:#x}) is exactly the stub bytes")
    print(f"verification: OK - the patched module (= {ev['patched_size']} bytes, "
          f"sha256 {ev['patched_sha256']}) differs from the pinned F4 module only "
          f"in PH[1] p_filesz/p_memsz, the four declared slot words and the 8 "
          f"appended stub bytes; the recipe payload, .rel.data and the section "
          f"table are untouched")
    return 0


def changed_sectors(a: str, b: str, chunk: int = 1 << 23) -> set[int]:
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


def expected_iso_sectors(src: str, patched: bytes,
                         rec_off: int) -> tuple[set[int], list[tuple[int, int]]]:
    with open(src, "rb") as f:
        f.seek(ISO_PRX_EXTENT * SECTOR)
        before = f.read(ISO_PRX_ALLOC)
    if len(before) != ISO_PRX_ALLOC:
        raise ValueError("could not read the module's allocated extent")
    after = patched + before[len(patched):]
    if len(after) != len(before):
        raise ValueError("extent reconstruction length mismatch")
    changed = [i for i in range(len(before)) if before[i] != after[i]]
    out = {ISO_PRX_EXTENT + i // SECTOR for i in changed}
    out.add(rec_off // SECTOR)
    return out, byte_ranges(changed)


def cmd_iso(args) -> int:
    with open(args.patched_prx, "rb") as f:
        patched_prx = f.read()
    prx, hdr, idx, _order = load_base(args.prx)
    print(f"base module `{args.prx}`: {len(prx)} bytes, sha256 {sha256(prx)}")
    print(f"patched module `{args.patched_prx}`: {len(patched_prx)} bytes, "
          f"sha256 {sha256(patched_prx)}")
    print("--- 1. the patched module verifies against the pinned F4 base")
    fails, ev = verify_module(prx, patched_prx, hdr, idx)
    if fails:
        print(f"STOP: the patched module does not verify ({len(fails)}):")
        for x in fails:
            print(f"  FAIL: {x}")
        return 1
    print("    OK: stub words, PH[1] 0x358, both slot pairs; payload/.rel.data/"
          "section table untouched")

    if os.path.exists(args.out):
        print(f"STOP: refusing to overwrite {args.out}")
        return 1
    if os.path.realpath(args.out) in {os.path.realpath(args.src),
                                      os.path.realpath(args.prx),
                                      os.path.realpath(args.patched_prx)}:
        print("STOP: --out is an input file")
        return 1

    print(f"--- 2. source ISO {args.src}")
    got = sha256_file(args.src)
    if got != BASE_ISO_SHA256:
        print(f"STOP: source ISO sha256 {got} differs from the pinned F4 "
              f"{BASE_ISO_SHA256}")
        return 1
    src_size = os.path.getsize(args.src)
    if src_size != BASE_ISO_SIZE:
        print(f"STOP: source ISO size {src_size} != {BASE_ISO_SIZE}")
        return 1
    iso = Iso9660(args.src)
    try:
        entry = iso.resolve(PRX_IN_ISO)
        rec_off, rec = iso_replace.find_record(iso, PRX_IN_ISO)
        mgr_lba = iso.resolve(NEXT_MODULE_IN_ISO).extent
        in_iso = iso.read_file(PRX_IN_ISO)
    finally:
        iso.close()
    print(f"    sha256 {got} (pinned), size {src_size} B")
    print(f"    module extent LBA {entry.extent} size {entry.size:#x}, allocation "
          f"{iso_replace.allocated_bytes(entry.size)} B")
    print(f"    directory record at file {rec_off:#x} (sector {rec_off // SECTOR})")
    print(f"    next module {NEXT_MODULE_IN_ISO} at LBA {mgr_lba}")
    if (entry.extent != ISO_PRX_EXTENT or entry.size != BASE_PRX_SIZE
            or mgr_lba != MGR_LBA_EXPECTED):
        print("STOP: source ISO geometry differs from the pinned values")
        return 1
    if in_iso != prx:
        print("STOP: the module inside the source ISO != the pinned F4 module")
        return 1
    if len(patched_prx) > iso_replace.allocated_bytes(entry.size):
        print("STOP: the patched module does not fit the allocated extent")
        return 1

    print(f"--- 3. copy the ISO and replace the module in place")
    report = iso_replace.replace_file(args.src, args.out, PRX_IN_ISO,
                                      patched_prx, label="B1-EXP3")
    print(f"    old size {report['old_size']:#x} -> new {report['new_size']:#x} "
          f"(ceiling {report['ceiling']:#x}); directory data-length updated; "
          f"roundtrip {report['roundtrip']}")

    print("--- 4. verification from the written ISO")
    back = iso_replace.read_iso_file(args.out, PRX_IN_ISO)
    errs: list[str] = []
    if back != patched_prx:
        errs.append("the module read back from the ISO differs from the artifact")
    if len(back) != BASE_PRX_SIZE + 8:
        errs.append(f"module size read back is {len(back):#x}, expected "
                    f"{BASE_PRX_SIZE + 8:#x}")
    diff = changed_sectors(args.src, args.out)
    expected, mod_changed = expected_iso_sectors(args.src, patched_prx, rec_off)
    if diff != expected:
        errs.append(f"changed sectors are {sorted(diff)}, expected "
                    f"{sorted(expected)}")
    out_size = os.path.getsize(args.out)
    if out_size != src_size or out_size != BASE_ISO_SIZE:
        errs.append(f"ISO size {out_size} != source {src_size} != "
                    f"{BASE_ISO_SIZE}")
    iso2 = Iso9660(args.out)
    try:
        mgr_after = iso2.resolve(NEXT_MODULE_IN_ISO).extent
        rec2_off, rec2 = iso_replace.find_record(iso2, PRX_IN_ISO)
    finally:
        iso2.close()
    if mgr_after != mgr_lba:
        errs.append(f"the next module moved from LBA {mgr_lba} to {mgr_after}")
    with open(args.out, "rb") as f:
        f.seek(rec2_off + 10)
        rec_size_le = struct.unpack("<I", f.read(4))[0]
        rec_size_be = struct.unpack(">I", f.read(4))[0]
    if rec_size_le != BASE_PRX_SIZE + 8 or rec_size_be != BASE_PRX_SIZE + 8:
        errs.append(f"directory record size is {rec_size_le:#x}/{rec_size_be:#x}, "
                    f"expected {BASE_PRX_SIZE + 8:#x}")

    print(f"    .prx read back equals the patched artifact: {back == patched_prx}")
    print(f"    ISO size {out_size} B (source {src_size} B, unchanged)")
    print(f"    directory record size for the module: {rec_size_le:#x} (LE) / "
          f"{rec_size_be:#x} (BE)")
    print(f"    next module still at LBA {mgr_after} (untouched)")
    print(f"    module-extent changed bytes ({len(mod_changed)} runs):")
    for start, end in mod_changed:
        print(f"      extent+0x{start:x}..0x{end:x} ({end - start} B) -> LBA "
              f"{ISO_PRX_EXTENT + start // SECTOR}")
    print(f"    changed sectors: {len(diff)} -> {sorted(diff)} (expected "
          f"{sorted(expected)})")
    if errs:
        print(f"VERIFICATION FAILED ({len(errs)}):")
        for x in errs:
            print(f"  FAIL: {x}")
        return 1
    print(f"OK -> {args.out}")
    print(f"    size {out_size} bytes, sha256 {sha256_file(args.out)}")
    return 0


# =========================================================================== #
# EXP4 -- paired probe: donor 4844 (Olla de la Codicia), A = 5330, B = 6431
#
# EXP3 above is left byte-for-byte untouched: this block is self-contained and
# only reachable through the new dump4/build4/verify4/iso4 subcommands.
#
# Corrected arithmetic (a premise of the T3c brief that does NOT match the
# bytes): MIPS `jalr rd, rs` writes PC+8, so the wrapper's `0x497e4 jalr ra,v0`
# leaves `ra = base + 0x497ec`, not `base + 0x497e8`.  The brief's
# `0x79ea0 - 0x497e8 = 0x2ffb8` is also wrong arithmetically (it is 0x306b8)
# and lands at `base + 0x797a4`, missing the donor resolver `0x79ea0` by
# 0x6fc.  The stub therefore uses
#     delta = 0x79ea0 - 0x497ec = 0x306b4   (hi=3, lo=0x06b4)
# and `_assert_stub_arithmetic` pins it.
# =========================================================================== #
EXP4_OUT_PRX = os.path.join(ROOT, "trabajo", "b1", "libduel_eng_exp4.prx")
EXP4_OUT_ISO = os.path.join(ROOT, "trabajo", "b1", "TF1-B1-EXP4.iso")

EXP4_STUB_FILE_OFF = 0x1674E0
EXP4_STUB_VMA = 0x112C60
EXP4_STUB_LEN = 20
EXP4_PH1_NEW_SIZE = 0x364
EXP4_RESULT_SIZE = 0x1674F4

EXP4_RA_VMA = 0x497EC                       # return address written by jalr
EXP4_DONOR_CARD = 4844
EXP4_DONOR_SLOTS = (0x79EA0, 0x0, 0x68F54, 0x0, 0xA4934)
EXP4_DELTA = EXP4_DONOR_SLOTS[0] - EXP4_RA_VMA      # 0x306b4
EXP4_HI = (EXP4_DELTA + 0x8000) >> 16                # 3
EXP4_LO = EXP4_DELTA & 0xFFFF                        # 0x06b4
EXP4_STUB_WORDS = (
    (0x0F << 26) | (25 << 16) | EXP4_HI,             # lui   t9, hi(delta)
    (0x09 << 26) | (25 << 21) | (25 << 16) | EXP4_LO,  # addiu t9, t9, lo
    0x033FC821,                                     # addu  t9, t9, ra
    0x03200008,                                     # jr    t9
    0x00000000,                                     # nop
)
EXP4_CARD_A = 5330
EXP4_CARD_A_ENTRY = 0x1023E4
EXP4_CARD_B = 6431
EXP4_CARD_B_ENTRY = 0x1041E4

EXP4_WRAPPER_JALR_VMA = 0x497E4
EXP4_WRAPPER_JALR_WORD = 0x0040F809
EXP4_WRAPPER_SAVE_RA_VMA = 0x49748
EXP4_WRAPPER_SAVE_RA_WORD = 0xAFBF000C

REL_TEXT_OFF = 0x10C618
REL_TEXT_SIZE = 0x4D040


@dataclass(frozen=True)
class Exp4Patch:
    card_id: int
    table: str
    entry_vma: int
    new_slots: tuple
    label: str


EXP4_PATCHES = (
    Exp4Patch(EXP4_CARD_A, "T1", EXP4_CARD_A_ENTRY, EXP4_DONOR_SLOTS,
              "5330 El Guerrero Volviendo Con Vida: copia literal del donante"),
    Exp4Patch(EXP4_CARD_B, "T1", EXP4_CARD_B_ENTRY,
              (EXP4_STUB_VMA, 0x0, 0x68F54, 0x0, 0xA4934),
              "6431 Recuperacion de Fusion: donante con slot4 -> stub 0x112c60"),
)


def _decode_stub_word(word: int):
    """Decode one stub word to (mnemonic, (operands...)).

    Added after the first EXP4 build shipped a mis-encoded `addu t9, t9, t9`
    (0x0339C821) where the design required `addu t9, t9, ra` (0x033FC821): the
    old check compared the stored words against a literal tuple, which is
    tautological and cannot catch an encoding slip. Assert the semantics.
    """
    op = word >> 26
    rs = (word >> 21) & 31
    rt = (word >> 16) & 31
    rd = (word >> 11) & 31
    fn = word & 63
    if word == 0:
        return ("nop", ())
    if op == 0x0F:
        return ("lui", (rt, word & 0xFFFF))
    if op == 0x09:
        return ("addiu", (rt, rs, word & 0xFFFF))
    if op == 0x00 and fn == 0x21:
        return ("addu", (rd, rs, rt))
    if op == 0x00 and fn == 0x08:
        return ("jr", (rs,))
    return (f"unknown/0x{word:08x}", ())


def _assert_stub_arithmetic() -> None:
    if EXP4_DELTA != 0x306B4:
        raise ValueError(f"EXP4 delta is 0x{EXP4_DELTA:x}, expected 0x306b4")
    if EXP4_HI != 3 or EXP4_LO != 0x06B4:
        raise ValueError(f"EXP4 delta split is hi={EXP4_HI:#x} lo={EXP4_LO:#x}, "
                         f"expected hi=3 lo=0x06b4")
    decoded = [_decode_stub_word(w) for w in EXP4_STUB_WORDS]
    want = [("lui", (25, EXP4_HI)),
            ("addiu", (25, 25, EXP4_LO)),
            ("addu", (25, 25, 31)),      # addu t9, t9, ra  (rd, rs, rt)
            ("jr", (25,)),              # jr t9
            ("nop", ())]
    if decoded != want:
        raise ValueError(f"EXP4 stub decodes to {decoded}, expected {want}")
    if EXP4_RA_VMA + EXP4_DELTA != EXP4_DONOR_SLOTS[0]:
        raise ValueError("EXP4 ra + delta is not the donor resolver")


def _assert_wrapper(prx: bytes) -> None:
    for vma, want, name in ((EXP4_WRAPPER_JALR_VMA, EXP4_WRAPPER_JALR_WORD,
                             "jalr ra, v0"),
                            (EXP4_WRAPPER_SAVE_RA_VMA, EXP4_WRAPPER_SAVE_RA_WORD,
                             "sw ra, 12(sp)")):
        got = struct.unpack_from("<I", prx, file_offset(vma))[0]
        if got != want:
            raise ValueError(f"wrapper word at VMA {vma:#x} is 0x{got:08x}, "
                             f"expected {name} 0x{want:08x}")


def _reloc_map(prx: bytes) -> dict:
    out = {}
    for i in range(REL_DATA_SIZE // 8):
        off = REL_DATA_OFF + i * 8
        r_off, r_info = struct.unpack_from("<II", prx, off)
        out[r_off] = r_info & 0xFF
    return out


def _deck_has(path: str, card_ids) -> dict:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    return {cid: (f"| {cid} |" in text) for cid in card_ids}


def plan4(prx: bytes, hdr: ElfHeader, idx: dict) -> dict:
    """Validate every EXP4 precondition and return the patch plan."""
    _assert_stub_arithmetic()
    _assert_wrapper(prx)
    ph1_file = hdr.e_phoff + PH1_INDEX * hdr.e_phentsize
    filesz_off = ph1_file + 16
    memsz_off = ph1_file + 20
    for off, want, name in ((filesz_off, PH1_OLD_SIZE, "p_filesz"),
                            (memsz_off, PH1_OLD_SIZE, "p_memsz")):
        got = struct.unpack_from("<I", prx, off)[0]
        if got != want:
            raise ValueError(f"PH[1] {name} at file {off:#x} is 0x{got:x}, "
                             f"expected 0x{want:x}")
    relocs = _reloc_map(prx)
    sites = []
    for p in EXP4_PATCHES:
        try:
            name, va, slots = select_entry(idx, p.card_id, p.table)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        if va != p.entry_vma:
            raise ValueError(f"CardID {p.card_id} entry VMA is 0x{va:x}, "
                             f"expected 0x{p.entry_vma:x}")
        s4 = file_offset(va + 4)
        old_slots = struct.unpack_from("<5I", prx, s4)
        if old_slots != slots:
            raise ValueError(f"CardID {p.card_id}: file slots do not match the "
                             f"locator ({old_slots} vs {slots})")
        if old_slots == p.new_slots:
            raise ValueError(f"CardID {p.card_id}: slots already patched")
        cells = []
        for k in range(5):
            vma = va + 4 + 4 * k
            new = p.new_slots[k]
            old = old_slots[k]
            rt = relocs.get(vma)
            cells.append(dict(slot=k, vma=vma, file=file_offset(vma),
                              old=old, new=new, reloc_type=rt))
            if new != 0 and rt != 2:
                raise ValueError(
                    f"CardID {p.card_id} slot{k} VMA {vma:#x}: new value "
                    f"0x{new:x} is non-zero but the cell has no R_MIPS_32 "
                    f"(reloc type {rt})")
            if new == 0 and old != 0 and rt == 2:
                raise ValueError(
                    f"CardID {p.card_id} slot{k} VMA {vma:#x}: writing 0 to "
                    f"an R_MIPS_32 cell would become base, not 0")
        sites.append({"card_id": p.card_id, "table": name, "entry_vma": va,
                      "s4": s4, "old_slots": old_slots,
                      "new_slots": p.new_slots, "cells": cells,
                      "label": p.label})
    donor_hits = idx.get(EXP4_DONOR_CARD, [])
    if len(donor_hits) != 1:
        raise ValueError(f"donor CardID {EXP4_DONOR_CARD} has "
                         f"{len(donor_hits)} entries, expected 1")
    donor_va = donor_hits[0][1]
    donor_slots = struct.unpack_from("<5I", prx, file_offset(donor_va + 4))
    if donor_slots != EXP4_DONOR_SLOTS:
        raise ValueError(f"donor slots are {donor_slots}, expected "
                         f"{EXP4_DONOR_SLOTS}")
    deck_path = os.path.join(ROOT, "trabajo", "b1", "T2-CANDIDATOS.md")
    if not os.path.exists(deck_path):
        raise ValueError(f"deck list not found: {deck_path}")
    has = _deck_has(deck_path, [p.card_id for p in EXP4_PATCHES])
    missing = [cid for cid, ok in has.items() if not ok]
    if missing:
        raise ValueError(f"card IDs not in the deck list: {missing}")
    return {"filesz_off": filesz_off, "memsz_off": memsz_off, "sites": sites,
            "relocs": relocs, "donor_va": donor_va, "donor_slots": donor_slots,
            "deck": has}


def declared_offsets4(pl: dict) -> set:
    declared = set()
    for off in (pl["filesz_off"], pl["memsz_off"]):
        declared.update(range(off, off + 4))
    for s in pl["sites"]:
        for c in s["cells"]:
            declared.update(range(c["file"], c["file"] + 4))
    return declared


def build_patched4(prx: bytes, hdr: ElfHeader, idx: dict) -> dict:
    pl = plan4(prx, hdr, idx)
    if len(prx) != EXP4_STUB_FILE_OFF:
        raise ValueError(f"base size {len(prx):#x} != append point "
                         f"{EXP4_STUB_FILE_OFF:#x}")
    patched = bytearray(prx) + struct.pack("<5I", *EXP4_STUB_WORDS)
    if len(patched) != EXP4_RESULT_SIZE:
        raise ValueError(f"built image is {len(patched)} bytes, expected "
                         f"{EXP4_RESULT_SIZE:#x}")
    struct.pack_into("<I", patched, pl["filesz_off"], EXP4_PH1_NEW_SIZE)
    struct.pack_into("<I", patched, pl["memsz_off"], EXP4_PH1_NEW_SIZE)
    for s in pl["sites"]:
        for c in s["cells"]:
            if c["new"] != c["old"]:
                struct.pack_into("<I", patched, c["file"], c["new"])
    declared = declared_offsets4(pl)
    changed = [i for i in range(BASE_PRX_SIZE) if prx[i] != patched[i]]
    outside = sorted(set(changed) - declared)
    if outside:
        raise ValueError(f"bytes outside the declared regions changed, first "
                         f"{outside[0]:#x}")
    return {"patched": bytes(patched), "plan": pl, "declared": sorted(declared),
            "changed": changed}


def verify_module4(pristine: bytes, patched: bytes, hdr0: ElfHeader,
                   idx: dict):
    fails = []
    ev = {}
    try:
        assert_base(pristine, "pristine")
    except ValueError as exc:
        return [str(exc)], ev
    try:
        built = build_patched4(pristine, hdr0, idx)
    except ValueError as exc:
        return fails + [str(exc)], ev
    ev["pristine_size"] = len(pristine)
    ev["pristine_sha256"] = sha256(pristine)
    ev["expected_size"] = EXP4_RESULT_SIZE
    ev["expected_sha256"] = sha256(built["patched"])
    ev["plan"] = built["plan"]
    if len(patched) != EXP4_RESULT_SIZE:
        fails.append(f"patched size is {len(patched):#x}, expected "
                     f"{EXP4_RESULT_SIZE:#x}")
        return fails, ev
    if patched != built["patched"]:
        i = next((k for k in range(len(patched))
                  if patched[k] != built["patched"][k]), None)
        fails.append(f"patched image differs from the re-derived image at "
                     f"offset {i:#x}" if i is not None else
                     "patched image differs from the re-derived image")
        return fails, ev
    ev["patched_size"] = len(patched)
    ev["patched_sha256"] = sha256(patched)
    pl = built["plan"]

    stub = struct.unpack_from("<5I", patched, EXP4_STUB_FILE_OFF)
    ev["stub_file_off"] = EXP4_STUB_FILE_OFF
    ev["stub_vma"] = EXP4_STUB_VMA
    ev["stub_words"] = stub
    if stub != EXP4_STUB_WORDS:
        fails.append(f"stub words at file {EXP4_STUB_FILE_OFF:#x} are "
                     f"{[hex(x) for x in stub]}, expected "
                     f"{[hex(x) for x in EXP4_STUB_WORDS]}")

    hdr = parse_elf_header(patched)
    phs = parse_ph(patched, hdr)
    ev["patched_ph"] = phs
    want_ph1 = (1, PH1_OFF, PH1_VADDR, PH1_VADDR, EXP4_PH1_NEW_SIZE,
                EXP4_PH1_NEW_SIZE, 7, 16)
    if phs != [PH0_EXPECTED, want_ph1]:
        fails.append(f"patched program headers are {phs}, expected "
                     f"[{PH0_EXPECTED}, {want_ph1}]")
    else:
        if phs[1][4] != EXP4_PH1_NEW_SIZE or phs[1][5] != EXP4_PH1_NEW_SIZE:
            fails.append(f"PH[1] p_filesz/p_memsz are not "
                         f"0x{EXP4_PH1_NEW_SIZE:x}")
        if phs[1][2] + phs[1][5] != EXP4_STUB_VMA + EXP4_STUB_LEN:
            fails.append("PH[1] does not fully cover the stub VMA")

    donor_slots = struct.unpack_from("<5I", patched,
                                     file_offset(pl["donor_va"] + 4))
    ev["donor"] = dict(vma=pl["donor_va"], slots=donor_slots)
    if donor_slots != EXP4_DONOR_SLOTS:
        fails.append(f"donor slots changed to {donor_slots}")

    entry_ev = []
    for s in pl["sites"]:
        new_slots = struct.unpack_from("<5I", patched, s["s4"])
        cells = []
        for c in s["cells"]:
            rt = pl["relocs"].get(c["vma"])
            covered = ((c["new"] == 0 and rt is None)
                       or (c["new"] != 0 and rt == 2))
            cells.append(dict(slot=c["slot"], vma=c["vma"], file=c["file"],
                              old=c["old"], new=c["new"], reloc_type=rt,
                              covered=covered, changed=(c["new"] != c["old"])))
            if not covered:
                fails.append(f"CardID {s['card_id']} slot{c['slot']} VMA "
                             f"{c['vma']:#x}: new 0x{c['new']:x}, reloc {rt} "
                             f"(not covered)")
        entry_ev.append(dict(card_id=s["card_id"], entry_vma=s["entry_vma"],
                             slots=new_slots, cells=cells, label=s["label"]))
    ev["entries"] = entry_ev

    a = next(e for e in entry_ev if e["card_id"] == EXP4_CARD_A)
    b = next(e for e in entry_ev if e["card_id"] == EXP4_CARD_B)
    if a["slots"] != EXP4_DONOR_SLOTS:
        fails.append(f"Card A (5330) slots are {a['slots']}, expected donor "
                     f"{EXP4_DONOR_SLOTS}")
    expect_b = (EXP4_STUB_VMA,) + tuple(EXP4_DONOR_SLOTS[1:])
    if b["slots"] != expect_b:
        fails.append(f"Card B (6431) slots are {b['slots']}, expected "
                     f"{expect_b}")

    declared = set(built["declared"])
    changed = [i for i in range(BASE_PRX_SIZE) if pristine[i] != patched[i]]
    outside = sorted(set(changed) - declared)
    ev["changed_count"] = len(changed)
    ev["changed_ranges"] = byte_ranges(changed)
    ev["declared_count"] = len(declared)
    if outside:
        fails.append(f"{len(outside)} byte(s) outside the declared regions "
                     f"changed, first {outside[0]:#x}")
    payload_ok = (patched[PH1_OFF:EXP4_STUB_FILE_OFF]
                  == pristine[PH1_OFF:EXP4_STUB_FILE_OFF])
    ev["payload_len"] = EXP4_STUB_FILE_OFF - PH1_OFF
    ev["payload_ok"] = payload_ok
    if not payload_ok:
        fails.append(f"the {ev['payload_len']}-byte recipe payload changed")
    rel_ok = (patched[REL_DATA_OFF:REL_DATA_OFF + REL_DATA_SIZE]
              == pristine[REL_DATA_OFF:REL_DATA_OFF + REL_DATA_SIZE])
    ev["rel_data_ok"] = rel_ok
    if not rel_ok:
        fails.append(".rel.data changed")
    relt_ok = (patched[REL_TEXT_OFF:REL_TEXT_OFF + REL_TEXT_SIZE]
               == pristine[REL_TEXT_OFF:REL_TEXT_OFF + REL_TEXT_SIZE])
    ev["rel_text_ok"] = relt_ok
    if not relt_ok:
        fails.append(".rel.text changed")
    sl = E_SHNUM * E_SHENTSIZE
    sec_ok = patched[E_SHOFF:E_SHOFF + sl] == pristine[E_SHOFF:E_SHOFF + sl]
    ev["section_table_ok"] = sec_ok
    if not sec_ok:
        fails.append("the section header table bytes changed")
    if (hdr.e_shoff, hdr.e_shnum, hdr.e_shentsize) != (E_SHOFF, E_SHNUM,
                                                       E_SHENTSIZE):
        fails.append("section table header changed")
    if patched[BASE_PRX_SIZE:] != struct.pack("<5I", *EXP4_STUB_WORDS):
        fails.append("the appended range is not exactly the 20 stub bytes")
    return fails, ev


def cmd_dump4(args) -> int:
    prx, hdr, idx, _order = load_base(args.prx)
    pl = plan4(prx, hdr, idx)
    print(f"EXP4 base `{args.prx}`: {len(prx)} bytes, sha256 {sha256(prx)}")
    print(f"  donor 4844 @0x{pl['donor_va']:x}: slots "
          f"{[hex(x) for x in pl['donor_slots']]} (untouched)")
    print(f"  delta = 0x{EXP4_DELTA:x} (ra 0x{EXP4_RA_VMA:x}); "
          f"hi={EXP4_HI:#x} lo={EXP4_LO:#x}")
    print(f"  stub words: {[hex(x) for x in EXP4_STUB_WORDS]}")
    for s in pl["sites"]:
        print(f"  CardID {s['card_id']} {s['table']}@0x{s['entry_vma']:x}: "
              f"{s['label']}")
        for c in s["cells"]:
            print(f"    slot{c['slot']} VMA 0x{c['vma']:x} file 0x{c['file']:x} "
                  f"reloc={c['reloc_type']} 0x{c['old']:08x} -> 0x{c['new']:08x}")
    print(f"  decks: {pl['deck']}")
    print(f"  PH[1] 0x{PH1_OLD_SIZE:x} -> 0x{EXP4_PH1_NEW_SIZE:x}; "
          f"result size 0x{EXP4_RESULT_SIZE:x}")
    return 0


def cmd_build4(args) -> int:
    prx, hdr, idx, _order = load_base(args.prx)
    print(f"EXP4 base `{args.prx}`: {len(prx)} bytes, sha256 {sha256(prx)}")
    if os.path.exists(args.out):
        print(f"STOP: refusing to overwrite {args.out}")
        return 1
    for inp in (args.prx, BASE_ISO):
        if os.path.realpath(args.out) == os.path.realpath(inp):
            print(f"STOP: --out is an input file ({inp})")
            return 1
    built = build_patched4(prx, hdr, idx)
    fails, ev = verify_module4(prx, built["patched"], hdr, idx)
    if fails:
        print(f"EXP4 SELF-VERIFY FAILED ({len(fails)}):")
        for x in fails:
            print(f"  FAIL: {x}")
        return 1
    with open(args.out, "wb") as f:
        f.write(built["patched"])
    print(f"wrote {args.out}")
    print(f"  {len(built['patched'])} bytes, sha256 {sha256(built['patched'])}")
    print("  self-verify: OK")
    return 0


def cmd_verify4(args) -> int:
    with open(args.pristine, "rb") as f:
        pristine = f.read()
    with open(args.patched, "rb") as f:
        patched = f.read()
    hdr0 = parse_elf_header(pristine)
    idx, _order = locate_entries(args.prx)
    print(f"EXP4 pristine: {args.pristine} ({len(pristine)} bytes, sha256 "
          f"{sha256(pristine)})")
    print(f"EXP4 patched : {args.patched} ({len(patched)} bytes, sha256 "
          f"{sha256(patched)})")
    fails, ev = verify_module4(pristine, patched, hdr0, idx)
    if fails:
        print(f"EXP4 VERIFICATION FAILED ({len(fails)}):")
        for x in fails:
            print(f"  FAIL: {x}")
        return 1
    print(f"--- 1. re-derived size/sha256")
    print(f"    {ev['expected_size']} bytes, sha256 {ev['expected_sha256']}")
    print(f"--- 2. stub")
    print(f"    file {ev['stub_file_off']:#x} = VMA {ev['stub_vma']:#x}: "
          f"{[hex(x) for x in ev['stub_words']]}")
    print(f"--- 3. PH[1]")
    for i, ph in enumerate(ev["patched_ph"]):
        t, off, va, pa, fs, ms, fl, al = ph
        print(f"    PH{i}: type={t} p_offset={off:#x} p_vaddr={va:#x} "
              f"p_filesz={fs:#x} p_memsz={ms:#x} p_flags={fl}")
    print(f"--- 4. donor")
    print(f"    4844 @0x{ev['donor']['vma']:x}: "
          f"{[hex(x) for x in ev['donor']['slots']]}")
    print(f"--- 5. entries and per-cell reloc table")
    for e in ev["entries"]:
        print(f"    CardID {e['card_id']} entry VMA 0x{e['entry_vma']:x}: "
              f"{[hex(x) for x in e['slots']]}")
        for c in e["cells"]:
            print(f"      slot{c['slot']} VMA 0x{c['vma']:x} file 0x{c['file']:x} "
                  f"old 0x{c['old']:08x} new 0x{c['new']:08x} "
                  f"reloc={c['reloc_type']} covered={c['covered']} "
                  f"changed={c['changed']}")
    print(f"--- 6. original part [0, 0x{EXP4_STUB_FILE_OFF:x})")
    print(f"    differing bytes: {ev['changed_count']} of the declared "
          f"{ev['declared_count']}")
    for start, end in ev["changed_ranges"]:
        print(f"    changed range [0x{start:x}, 0x{end:x}) ({end - start} B)")
    print(f"    recipe payload ({ev['payload_len']} B) byte-identical: "
          f"{ev['payload_ok']}")
    print(f"    .rel.data byte-identical: {ev['rel_data_ok']}")
    print(f"    .rel.text byte-identical: {ev['rel_text_ok']}")
    print(f"    section header table byte-identical: {ev['section_table_ok']}")
    print(f"--- 7. appended range [0x{BASE_PRX_SIZE:x}, "
          f"0x{EXP4_RESULT_SIZE:x}) is exactly the 20 stub bytes")
    print(f"EXP4 verification: OK - {ev['patched_size']} bytes, sha256 "
          f"{ev['patched_sha256']}")
    return 0


def cmd_iso4(args) -> int:
    with open(args.patched_prx, "rb") as f:
        patched_prx = f.read()
    prx, hdr, idx, _order = load_base(args.prx)
    print(f"EXP4 base module `{args.prx}`: {len(prx)} bytes, sha256 "
          f"{sha256(prx)}")
    print(f"EXP4 patched module `{args.patched_prx}`: {len(patched_prx)} bytes, "
          f"sha256 {sha256(patched_prx)}")
    fails, ev = verify_module4(prx, patched_prx, hdr, idx)
    if fails:
        print(f"STOP: the patched module does not verify ({len(fails)}):")
        for x in fails:
            print(f"  FAIL: {x}")
        return 1
    print(f"    OK: stub 20 B, PH[1] 0x{EXP4_PH1_NEW_SIZE:x}, A/B slots, "
          f"donor; payload/.rel.data/.rel.text/section table untouched")
    if os.path.exists(args.out):
        print(f"STOP: refusing to overwrite {args.out}")
        return 1
    if os.path.realpath(args.out) in {os.path.realpath(args.src),
                                      os.path.realpath(args.prx),
                                      os.path.realpath(args.patched_prx)}:
        print("STOP: --out is an input file")
        return 1
    got = sha256_file(args.src)
    if got != BASE_ISO_SHA256:
        print(f"STOP: source ISO sha256 {got} differs from the pinned F4 "
              f"{BASE_ISO_SHA256}")
        return 1
    src_size = os.path.getsize(args.src)
    if src_size != BASE_ISO_SIZE:
        print(f"STOP: source ISO size {src_size} != {BASE_ISO_SIZE}")
        return 1
    iso = Iso9660(args.src)
    try:
        entry = iso.resolve(PRX_IN_ISO)
        rec_off, rec = iso_replace.find_record(iso, PRX_IN_ISO)
        mgr_lba = iso.resolve(NEXT_MODULE_IN_ISO).extent
        in_iso = iso.read_file(PRX_IN_ISO)
    finally:
        iso.close()
    print(f"    sha256 {got} (pinned), size {src_size} B")
    print(f"    module extent LBA {entry.extent} size {entry.size:#x}, "
          f"allocation {iso_replace.allocated_bytes(entry.size)} B")
    print(f"    directory record at file {rec_off:#x} (sector {rec_off // SECTOR})")
    print(f"    next module {NEXT_MODULE_IN_ISO} at LBA {mgr_lba}")
    if (entry.extent != ISO_PRX_EXTENT or entry.size != BASE_PRX_SIZE
            or mgr_lba != MGR_LBA_EXPECTED):
        print("STOP: source ISO geometry differs from the pinned values")
        return 1
    if in_iso != prx:
        print("STOP: the module inside the source ISO != the pinned F4 module")
        return 1
    if len(patched_prx) > iso_replace.allocated_bytes(entry.size):
        print("STOP: the patched module does not fit the allocated extent")
        return 1
    report = iso_replace.replace_file(args.src, args.out, PRX_IN_ISO,
                                      patched_prx, label="B1-EXP4")
    print(f"    old size {report['old_size']:#x} -> new {report['new_size']:#x} "
          f"(ceiling {report['ceiling']:#x}); dir data-length updated; "
          f"roundtrip {report['roundtrip']}")
    back = iso_replace.read_iso_file(args.out, PRX_IN_ISO)
    errs = []
    if back != patched_prx:
        errs.append("the module read back from the ISO differs from the "
                    "artifact")
    if len(back) != EXP4_RESULT_SIZE:
        errs.append(f"module size read back is {len(back):#x}, expected "
                    f"{EXP4_RESULT_SIZE:#x}")
    diff = changed_sectors(args.src, args.out)
    expected, mod_changed = expected_iso_sectors(args.src, patched_prx, rec_off)
    if diff != expected:
        errs.append(f"changed sectors are {sorted(diff)}, expected "
                    f"{sorted(expected)}")
    out_size = os.path.getsize(args.out)
    if out_size != src_size or out_size != BASE_ISO_SIZE:
        errs.append(f"ISO size {out_size} != source {src_size} != "
                    f"{BASE_ISO_SIZE}")
    iso2 = Iso9660(args.out)
    try:
        mgr_after = iso2.resolve(NEXT_MODULE_IN_ISO).extent
        rec2_off, rec2 = iso_replace.find_record(iso2, PRX_IN_ISO)
    finally:
        iso2.close()
    if mgr_after != mgr_lba:
        errs.append(f"the next module moved from LBA {mgr_lba} to {mgr_after}")
    with open(args.out, "rb") as f:
        f.seek(rec2_off + 10)
        rec_size_le = struct.unpack("<I", f.read(4))[0]
        rec_size_be = struct.unpack(">I", f.read(4))[0]
    if rec_size_le != EXP4_RESULT_SIZE or rec_size_be != EXP4_RESULT_SIZE:
        errs.append(f"directory record size is {rec_size_le:#x}/"
                    f"{rec_size_be:#x}, expected {EXP4_RESULT_SIZE:#x}")
    print(f"    .prx read back equals the patched artifact: "
          f"{back == patched_prx}")
    print(f"    ISO size {out_size} B (source {src_size} B, unchanged)")
    print(f"    directory record size for the module: {rec_size_le:#x} (LE) / "
          f"{rec_size_be:#x} (BE)")
    print(f"    next module still at LBA {mgr_after} (untouched)")
    print(f"    module-extent changed bytes ({len(mod_changed)} runs):")
    for start, end in mod_changed:
        print(f"      extent+0x{start:x}..0x{end:x} ({end - start} B) -> LBA "
              f"{ISO_PRX_EXTENT + start // SECTOR}")
    print(f"    changed sectors: {len(diff)} -> {sorted(diff)} (expected "
          f"{sorted(expected)})")
    if errs:
        print(f"EXP4 ISO VERIFICATION FAILED ({len(errs)}):")
        for x in errs:
            print(f"  FAIL: {x}")
        return 1
    print(f"EXP4 ISO OK -> {args.out}")
    print(f"    size {out_size} bytes, sha256 {sha256_file(args.out)}")
    return 0


# =========================================================================== #
# EXP5 -- T3f: anchor on 4844 (in-game baseline "draw 2", E19) and replace its
# entry resolver with a CARD-INDEPENDENT donor resolver.
#
# T3f step 2 (measured): the EXP4 donor resolver 0x79ea0 is a SHARED "draw"
# resolver that switches on the activated card's own CardID (`lhu a2,0(a0)`) to
# pick the count; an unknown CardID falls through to s0 = 0 and `blezl s0`
# skips the draw.  A verbatim entry copy therefore calls the right resolver but
# the resolver reads the TARGET's CardID and does nothing (this is exactly the
# E19 negative).
#
# EXP5 uses a resolver that reads neither the record's CardID nor any of
# slot8/12/16/20:
#   donor 4529 (T2@0x105024, slots {0x7c758,0,0,0,0}, slot8 == 0)
#   resolver 0x7c758: v0=1; a1=2; a0=1-(byte2&1); jal 0xbebfc  => the player
#   opposite the card's owner draws 2.  Unconditional, card-independent.
#
# Patches (only slot4 of each card; every other cell untouched):
#   4844 (T1@0x10116c): slot4 -> our 20-byte relocation-free stub 0x112c60
#        (forwarding to 0x7c758) => proves our 2nd-PT_LOAD code executes.
#   5328 (T1@0x1023b4): slot4 -> 0x7c758 directly => proves entry+4 is the
#        live lever without new code.
# =========================================================================== #
EXP5_OUT_PRX = os.path.join(ROOT, "trabajo", "b1", "libduel_eng_exp5.prx")
EXP5_OUT_ISO = os.path.join(ROOT, "trabajo", "b1", "TF1-B1-EXP5.iso")

EXP5_STUB_FILE_OFF = 0x1674E0
EXP5_STUB_VMA = 0x112C60
EXP5_STUB_LEN = 20
EXP5_PH1_NEW_SIZE = 0x364
EXP5_RESULT_SIZE = 0x1674F4

EXP5_RA_VMA = 0x497EC                       # return address written by jalr
EXP5_DONOR_CARD = 4529                      # El Carnicero del Bistro (T2)
EXP5_DONOR_TABLE = "T2"
EXP5_DONOR_ENTRY = 0x105024
EXP5_DONOR_RESOLVER = 0x7C758
EXP5_DONOR_SLOTS = (0x7C758, 0x0, 0x0, 0x0, 0x0)
EXP5_DELTA = EXP5_DONOR_RESOLVER - EXP5_RA_VMA      # 0x32f6c
EXP5_HI = (EXP5_DELTA + 0x8000) >> 16                # 3
EXP5_LO = EXP5_DELTA & 0xFFFF                        # 0x2f6c
EXP5_STUB_WORDS = (
    (0x0F << 26) | (25 << 16) | EXP5_HI,             # lui   t9, hi(delta)
    (0x09 << 26) | (25 << 21) | (25 << 16) | EXP5_LO,  # addiu t9, t9, lo
    0x033FC821,                                     # addu  t9, t9, ra
    0x03200008,                                     # jr    t9
    0x00000000,                                     # nop
)
EXP5_CARD_A = 4844
EXP5_CARD_A_ENTRY = 0x10116C
EXP5_CARD_B = 5328
EXP5_CARD_B_ENTRY = 0x1023B4

# 0x7c758 body, pinned word-by-word (the base module is sha256-pinned anyway):
#   v0=1; a1=2; a0=1-(byte2&1); jal 0xbebfc => the non-owner draws 2.
EXP5_RESOLVER_WORDS = (
    0x27BDFFF0,  # addiu sp,sp,-16
    0xAFBF000C,  # sw    ra,12(sp)
    0x90830002,  # lbu   v1,2(a0)
    0x24020001,  # addiu v0,zero,1
    0x24050002,  # addiu a1,zero,2
    0x30630001,  # andi  v1,v1,0x0001
    0x0C02FAFF,  # jal   0xbebfc
    0x00432023,  # subu  a0,v0,v1
    0x8FBF000C,  # lw    ra,12(sp)
    0x00001021,  # addu  v0,zero,zero
    0x03E00008,  # jr    ra
)


def _decode_resolver_word5(word: int):
    """Decode the donor resolver's words so the check asserts SEMANTICS."""
    op = word >> 26
    rs = (word >> 21) & 31
    rt = (word >> 16) & 31
    rd = (word >> 11) & 31
    sa = (word >> 6) & 31
    fn = word & 63
    imm = word & 0xFFFF
    simm = imm - 0x10000 if imm & 0x8000 else imm
    if word == 0:
        return ("nop", ())
    if op == 0x0F:
        return ("lui", (rt, imm))
    if op == 0x09:
        return ("addiu", (rt, rs, simm))
    if op == 0x24:
        return ("lbu", (rt, simm, rs))
    if op == 0x0C:
        return ("andi", (rt, rs, imm))
    if op == 0x23:
        return ("lw", (rt, simm, rs))
    if op == 0x2B:
        return ("sw", (rt, simm, rs))
    if op == 0x03:
        return ("jal", ((((0) + 4) & 0xF0000000) | ((word & 0x3FFFFFF) << 2),))
    if op == 0x00 and fn == 0x23:
        return ("subu", (rd, rs, rt))
    if op == 0x00 and fn == 0x21:
        return ("addu", (rd, rs, rt))
    if op == 0x00 and fn == 0x08:
        return ("jr", (rs,))
    return (f"unknown/0x{word:08x}", ())


@dataclass(frozen=True)
class Exp5Patch:
    card_id: int
    table: str
    entry_vma: int
    new_slot4: int
    label: str


EXP5_PATCHES = (
    Exp5Patch(EXP5_CARD_A, "T1", EXP5_CARD_A_ENTRY, EXP5_STUB_VMA,
              "4844 Olla de la Codicia: slot4 -> stub 0x112c60 (-> 0x7c758)"),
    Exp5Patch(EXP5_CARD_B, "T1", EXP5_CARD_B_ENTRY, EXP5_DONOR_RESOLVER,
              "5328 Refuerzo del Ejercito: slot4 -> 0x7c758 directo"),
)


def _assert_stub_arithmetic5() -> None:
    if EXP5_DELTA != 0x32F6C:
        raise ValueError(f"EXP5 delta is 0x{EXP5_DELTA:x}, expected 0x32f6c")
    if EXP5_HI != 3 or EXP5_LO != 0x2F6C:
        raise ValueError(f"EXP5 delta split is hi={EXP5_HI:#x} lo={EXP5_LO:#x}, "
                         f"expected hi=3 lo=0x2f6c")
    decoded = [_decode_stub_word(w) for w in EXP5_STUB_WORDS]
    want = [("lui", (25, 3)),
            ("addiu", (25, 25, 0x2F6C)),
            ("addu", (25, 25, 31)),
            ("jr", (25,)),
            ("nop", ())]
    if decoded != want:
        raise ValueError(f"EXP5 stub decodes to {decoded}, expected {want}")
    if EXP5_RA_VMA + EXP5_DELTA != EXP5_DONOR_RESOLVER:
        raise ValueError("EXP5 ra + delta is not the donor resolver")


def _assert_donor_resolver5(prx: bytes) -> None:
    for i, want in enumerate(EXP5_RESOLVER_WORDS):
        va = EXP5_DONOR_RESOLVER + 4 * i
        got = struct.unpack_from("<I", prx, file_offset(va))[0]
        if got != want:
            raise ValueError(f"donor resolver word at VMA {va:#x} is "
                             f"0x{got:08x}, expected 0x{want:08x}")
    decoded = [_decode_resolver_word5(w) for w in EXP5_RESOLVER_WORDS]
    if (decoded[2] != ("lbu", (3, 2, 4))
            or decoded[4] != ("addiu", (5, 0, 2))
            or decoded[5] != ("andi", (3, 3, 1))
            or decoded[7] != ("subu", (4, 2, 3))):
        raise ValueError(f"donor resolver 0x7c758 does not match the "
                         f"'non-owner draws 2' shape: {decoded}")


def plan5(prx: bytes, hdr: ElfHeader, idx: dict) -> dict:
    """Validate every EXP5 precondition and return the patch plan."""
    _assert_stub_arithmetic5()
    _assert_wrapper(prx)
    _assert_donor_resolver5(prx)
    ph1_file = hdr.e_phoff + PH1_INDEX * hdr.e_phentsize
    filesz_off = ph1_file + 16
    memsz_off = ph1_file + 20
    for off, want, name in ((filesz_off, PH1_OLD_SIZE, "p_filesz"),
                            (memsz_off, PH1_OLD_SIZE, "p_memsz")):
        got = struct.unpack_from("<I", prx, off)[0]
        if got != want:
            raise ValueError(f"PH[1] {name} at file {off:#x} is 0x{got:x}, "
                             f"expected 0x{want:x}")
    relocs = _reloc_map(prx)
    sites = []
    for p in EXP5_PATCHES:
        try:
            name, va, slots = select_entry(idx, p.card_id, p.table)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        if va != p.entry_vma:
            raise ValueError(f"CardID {p.card_id} entry VMA is 0x{va:x}, "
                             f"expected 0x{p.entry_vma:x}")
        s4 = file_offset(va + 4)
        old_slots = struct.unpack_from("<5I", prx, s4)
        if old_slots != slots:
            raise ValueError(f"CardID {p.card_id}: file slots do not match the "
                             f"locator ({old_slots} vs {slots})")
        new_slots = (p.new_slot4,) + old_slots[1:]
        if old_slots[0] == new_slots[0]:
            raise ValueError(f"CardID {p.card_id}: slot4 already 0x{p.new_slot4:x}")
        cells = []
        for k in range(5):
            vma = va + 4 + 4 * k
            new = new_slots[k]
            old = old_slots[k]
            rt = relocs.get(vma)
            cells.append(dict(slot=k, vma=vma, file=file_offset(vma),
                              old=old, new=new, reloc_type=rt))
            if new != 0 and rt != 2:
                raise ValueError(
                    f"CardID {p.card_id} slot{k} VMA {vma:#x}: new value "
                    f"0x{new:x} is non-zero but the cell has no R_MIPS_32 "
                    f"(reloc type {rt})")
            if new == 0 and old != 0 and rt == 2:
                raise ValueError(
                    f"CardID {p.card_id} slot{k} VMA {vma:#x}: writing 0 to "
                    f"an R_MIPS_32 cell would become base, not 0")
        sites.append({"card_id": p.card_id, "table": name, "entry_vma": va,
                      "s4": s4, "old_slots": old_slots,
                      "new_slots": new_slots, "cells": cells,
                      "label": p.label})
    donor_name, donor_va, donor_slots = select_entry(idx, EXP5_DONOR_CARD,
                                                     EXP5_DONOR_TABLE)
    if donor_va != EXP5_DONOR_ENTRY:
        raise ValueError(f"donor CardID {EXP5_DONOR_CARD} entry VMA is "
                         f"0x{donor_va:x}, expected 0x{EXP5_DONOR_ENTRY:x}")
    if tuple(donor_slots) != EXP5_DONOR_SLOTS:
        raise ValueError(f"donor slots are {donor_slots}, expected "
                         f"{EXP5_DONOR_SLOTS}")
    deck_path = os.path.join(ROOT, "trabajo", "b1", "T2-CANDIDATOS.md")
    if not os.path.exists(deck_path):
        raise ValueError(f"deck list not found: {deck_path}")
    has = _deck_has(deck_path, [p.card_id for p in EXP5_PATCHES])
    missing = [cid for cid, ok in has.items() if not ok]
    if missing:
        raise ValueError(f"card IDs not in the deck list: {missing}")
    return {"filesz_off": filesz_off, "memsz_off": memsz_off, "sites": sites,
            "relocs": relocs, "donor_va": donor_va, "donor_slots": donor_slots,
            "donor_table": donor_name, "deck": has}


def declared_offsets5(pl: dict) -> set:
    declared = set()
    for off in (pl["filesz_off"], pl["memsz_off"]):
        declared.update(range(off, off + 4))
    for s in pl["sites"]:
        for c in s["cells"]:
            declared.update(range(c["file"], c["file"] + 4))
    return declared


def build_patched5(prx: bytes, hdr: ElfHeader, idx: dict) -> dict:
    pl = plan5(prx, hdr, idx)
    if len(prx) != EXP5_STUB_FILE_OFF:
        raise ValueError(f"base size {len(prx):#x} != append point "
                         f"{EXP5_STUB_FILE_OFF:#x}")
    patched = bytearray(prx) + struct.pack("<5I", *EXP5_STUB_WORDS)
    if len(patched) != EXP5_RESULT_SIZE:
        raise ValueError(f"built image is {len(patched)} bytes, expected "
                         f"{EXP5_RESULT_SIZE:#x}")
    struct.pack_into("<I", patched, pl["filesz_off"], EXP5_PH1_NEW_SIZE)
    struct.pack_into("<I", patched, pl["memsz_off"], EXP5_PH1_NEW_SIZE)
    for s in pl["sites"]:
        for c in s["cells"]:
            if c["new"] != c["old"]:
                struct.pack_into("<I", patched, c["file"], c["new"])
    declared = declared_offsets5(pl)
    changed = [i for i in range(BASE_PRX_SIZE) if prx[i] != patched[i]]
    outside = sorted(set(changed) - declared)
    if outside:
        raise ValueError(f"bytes outside the declared regions changed, first "
                         f"{outside[0]:#x}")
    return {"patched": bytes(patched), "plan": pl, "declared": sorted(declared),
            "changed": changed}


def verify_module5(pristine: bytes, patched: bytes, hdr0: ElfHeader,
                   idx: dict):
    fails = []
    ev = {}
    try:
        assert_base(pristine, "pristine")
    except ValueError as exc:
        return [str(exc)], ev
    try:
        built = build_patched5(pristine, hdr0, idx)
    except ValueError as exc:
        return fails + [str(exc)], ev
    ev["pristine_size"] = len(pristine)
    ev["pristine_sha256"] = sha256(pristine)
    ev["expected_size"] = EXP5_RESULT_SIZE
    ev["expected_sha256"] = sha256(built["patched"])
    ev["plan"] = built["plan"]
    if len(patched) != EXP5_RESULT_SIZE:
        fails.append(f"patched size is {len(patched):#x}, expected "
                     f"{EXP5_RESULT_SIZE:#x}")
        return fails, ev
    if patched != built["patched"]:
        i = next((k for k in range(len(patched))
                  if patched[k] != built["patched"][k]), None)
        fails.append(f"patched image differs from the re-derived image at "
                     f"offset {i:#x}" if i is not None else
                     "patched image differs from the re-derived image")
        return fails, ev
    ev["patched_size"] = len(patched)
    ev["patched_sha256"] = sha256(patched)
    pl = built["plan"]

    # --- stub: DECODE (mnemonic + operands); never re-compare the constant --
    stub = struct.unpack_from("<5I", patched, EXP5_STUB_FILE_OFF)
    decoded = [_decode_stub_word(w) for w in stub]
    ev["stub_file_off"] = EXP5_STUB_FILE_OFF
    ev["stub_vma"] = EXP5_STUB_VMA
    ev["stub_words"] = stub
    ev["stub_decoded"] = decoded
    want = [("lui", (25, 3)),
            ("addiu", (25, 25, 0x2F6C)),
            ("addu", (25, 25, 31)),
            ("jr", (25,)),
            ("nop", ())]
    if decoded != want:
        fails.append(f"stub at file {EXP5_STUB_FILE_OFF:#x} decodes to "
                     f"{decoded}, expected {want}")
    if EXP5_RA_VMA + EXP5_DELTA != EXP5_DONOR_RESOLVER:
        fails.append(f"stub target ra({EXP5_RA_VMA:#x}) + "
                     f"delta({EXP5_DELTA:#x}) != donor resolver "
                     f"{EXP5_DONOR_RESOLVER:#x}")

    # --- donor resolver untouched (base property) ------------------------
    res_words = struct.unpack_from("<11I", patched,
                                   file_offset(EXP5_DONOR_RESOLVER))
    ev["donor_resolver"] = dict(vma=EXP5_DONOR_RESOLVER, words=res_words)
    if res_words != EXP5_RESOLVER_WORDS:
        fails.append("the donor resolver body changed")

    hdr = parse_elf_header(patched)
    phs = parse_ph(patched, hdr)
    ev["patched_ph"] = phs
    want_ph1 = (1, PH1_OFF, PH1_VADDR, PH1_VADDR, EXP5_PH1_NEW_SIZE,
                EXP5_PH1_NEW_SIZE, 7, 16)
    if phs != [PH0_EXPECTED, want_ph1]:
        fails.append(f"patched program headers are {phs}, expected "
                     f"[{PH0_EXPECTED}, {want_ph1}]")
    else:
        if phs[1][4] != EXP5_PH1_NEW_SIZE or phs[1][5] != EXP5_PH1_NEW_SIZE:
            fails.append(f"PH[1] p_filesz/p_memsz are not "
                         f"0x{EXP5_PH1_NEW_SIZE:x}")
        if phs[1][2] + phs[1][5] != EXP5_STUB_VMA + EXP5_STUB_LEN:
            fails.append("PH[1] does not fully cover the stub VMA")

    donor_slots = struct.unpack_from("<5I", patched,
                                     file_offset(pl["donor_va"] + 4))
    ev["donor"] = dict(vma=pl["donor_va"], table=pl["donor_table"],
                       slots=donor_slots)
    if donor_slots != EXP5_DONOR_SLOTS:
        fails.append(f"donor slots changed to {donor_slots}")

    entry_ev = []
    for s in pl["sites"]:
        new_slots = struct.unpack_from("<5I", patched, s["s4"])
        cells = []
        for c in s["cells"]:
            rt = pl["relocs"].get(c["vma"])
            covered = ((c["new"] == 0 and rt is None)
                       or (c["new"] != 0 and rt == 2))
            cells.append(dict(slot=c["slot"], vma=c["vma"], file=c["file"],
                              old=c["old"], new=c["new"], reloc_type=rt,
                              covered=covered, changed=(c["new"] != c["old"])))
            if not covered:
                fails.append(f"CardID {s['card_id']} slot{c['slot']} VMA "
                             f"{c['vma']:#x}: new 0x{c['new']:x}, reloc {rt} "
                             f"(not covered)")
        entry_ev.append(dict(card_id=s["card_id"], entry_vma=s["entry_vma"],
                             slots=new_slots, old_slots=s["old_slots"],
                             cells=cells, label=s["label"]))
    ev["entries"] = entry_ev

    a = next(e for e in entry_ev if e["card_id"] == EXP5_CARD_A)
    b = next(e for e in entry_ev if e["card_id"] == EXP5_CARD_B)
    if a["slots"][0] != EXP5_STUB_VMA:
        fails.append(f"Card A (4844) slot4 is {a['slots'][0]:#x}, expected "
                     f"stub {EXP5_STUB_VMA:#x}")
    if a["slots"][1:] != a["old_slots"][1:]:
        fails.append(f"Card A (4844) slot8/12/16/20 changed: {a['slots'][1:]}")
    if b["slots"][0] != EXP5_DONOR_RESOLVER:
        fails.append(f"Card B (5328) slot4 is {b['slots'][0]:#x}, expected "
                     f"donor resolver {EXP5_DONOR_RESOLVER:#x}")
    if b["slots"][1:] != b["old_slots"][1:]:
        fails.append(f"Card B (5328) slot8/12/16/20 changed: {b['slots'][1:]}")

    declared = set(built["declared"])
    changed = [i for i in range(BASE_PRX_SIZE) if pristine[i] != patched[i]]
    outside = sorted(set(changed) - declared)
    ev["changed_count"] = len(changed)
    ev["changed_ranges"] = byte_ranges(changed)
    ev["declared_count"] = len(declared)
    if outside:
        fails.append(f"{len(outside)} byte(s) outside the declared regions "
                     f"changed, first {outside[0]:#x}")
    payload_ok = (patched[PH1_OFF:EXP5_STUB_FILE_OFF]
                  == pristine[PH1_OFF:EXP5_STUB_FILE_OFF])
    ev["payload_len"] = EXP5_STUB_FILE_OFF - PH1_OFF
    ev["payload_ok"] = payload_ok
    if not payload_ok:
        fails.append(f"the {ev['payload_len']}-byte recipe payload changed")
    rel_ok = (patched[REL_DATA_OFF:REL_DATA_OFF + REL_DATA_SIZE]
              == pristine[REL_DATA_OFF:REL_DATA_OFF + REL_DATA_SIZE])
    ev["rel_data_ok"] = rel_ok
    if not rel_ok:
        fails.append(".rel.data changed (a relocation was added or altered)")
    relt_ok = (patched[REL_TEXT_OFF:REL_TEXT_OFF + REL_TEXT_SIZE]
               == pristine[REL_TEXT_OFF:REL_TEXT_OFF + REL_TEXT_SIZE])
    ev["rel_text_ok"] = relt_ok
    if not relt_ok:
        fails.append(".rel.text changed")
    sl = E_SHNUM * E_SHENTSIZE
    sec_ok = patched[E_SHOFF:E_SHOFF + sl] == pristine[E_SHOFF:E_SHOFF + sl]
    ev["section_table_ok"] = sec_ok
    if not sec_ok:
        fails.append("the section header table bytes changed")
    if (hdr.e_shoff, hdr.e_shnum, hdr.e_shentsize) != (E_SHOFF, E_SHNUM,
                                                       E_SHENTSIZE):
        fails.append("section table header changed")
    if patched[BASE_PRX_SIZE:] != struct.pack("<5I", *EXP5_STUB_WORDS):
        fails.append("the appended range is not exactly the 20 stub bytes")
    return fails, ev


def cmd_dump5(args) -> int:
    prx, hdr, idx, _order = load_base(args.prx)
    pl = plan5(prx, hdr, idx)
    print(f"EXP5 base `{args.prx}`: {len(prx)} bytes, sha256 {sha256(prx)}")
    print(f"  donor {EXP5_DONOR_CARD} {pl['donor_table']}@0x{pl['donor_va']:x}: "
          f"slots {[hex(x) for x in pl['donor_slots']]}")
    print(f"  donor resolver 0x{EXP5_DONOR_RESOLVER:x} (non-owner draws 2)")
    print(f"  delta = 0x{EXP5_DELTA:x} (ra 0x{EXP5_RA_VMA:x}); "
          f"hi={EXP5_HI:#x} lo={EXP5_LO:#x}")
    print(f"  stub words: {[hex(x) for x in EXP5_STUB_WORDS]}")
    for s in pl["sites"]:
        print(f"  CardID {s['card_id']} {s['table']}@0x{s['entry_vma']:x}: "
              f"{s['label']}")
        for c in s["cells"]:
            print(f"    slot{c['slot']} VMA 0x{c['vma']:x} file 0x{c['file']:x} "
                  f"reloc={c['reloc_type']} 0x{c['old']:08x} -> 0x{c['new']:08x}")
    print(f"  decks: {pl['deck']}")
    print(f"  PH[1] 0x{PH1_OLD_SIZE:x} -> 0x{EXP5_PH1_NEW_SIZE:x}; "
          f"result size 0x{EXP5_RESULT_SIZE:x}")
    return 0


def cmd_build5(args) -> int:
    prx, hdr, idx, _order = load_base(args.prx)
    print(f"EXP5 base `{args.prx}`: {len(prx)} bytes, sha256 {sha256(prx)}")
    if os.path.exists(args.out):
        print(f"STOP: refusing to overwrite {args.out}")
        return 1
    for inp in (args.prx, BASE_ISO):
        if os.path.realpath(args.out) == os.path.realpath(inp):
            print(f"STOP: --out is an input file ({inp})")
            return 1
    built = build_patched5(prx, hdr, idx)
    fails, ev = verify_module5(prx, built["patched"], hdr, idx)
    if fails:
        print(f"EXP5 SELF-VERIFY FAILED ({len(fails)}):")
        for x in fails:
            print(f"  FAIL: {x}")
        return 1
    with open(args.out, "wb") as f:
        f.write(built["patched"])
    print(f"wrote {args.out}")
    print(f"  {len(built['patched'])} bytes, sha256 {sha256(built['patched'])}")
    print("  self-verify: OK")
    return 0


def cmd_verify5(args) -> int:
    with open(args.pristine, "rb") as f:
        pristine = f.read()
    with open(args.patched, "rb") as f:
        patched = f.read()
    hdr0 = parse_elf_header(pristine)
    idx, _order = locate_entries(args.prx)
    print(f"EXP5 pristine: {args.pristine} ({len(pristine)} bytes, sha256 "
          f"{sha256(pristine)})")
    print(f"EXP5 patched : {args.patched} ({len(patched)} bytes, sha256 "
          f"{sha256(patched)})")
    fails, ev = verify_module5(pristine, patched, hdr0, idx)
    if fails:
        print(f"EXP5 VERIFICATION FAILED ({len(fails)}):")
        for x in fails:
            print(f"  FAIL: {x}")
        return 1
    print(f"--- 1. re-derived size/sha256")
    print(f"    {ev['expected_size']} bytes, sha256 {ev['expected_sha256']}")
    print(f"--- 2. stub (decoded)")
    print(f"    file {ev['stub_file_off']:#x} = VMA {ev['stub_vma']:#x}: "
          f"{ev['stub_decoded']}")
    print(f"--- 3. PH[1]")
    for i, ph in enumerate(ev["patched_ph"]):
        t, off, va, pa, fs, ms, fl, al = ph
        print(f"    PH{i}: type={t} p_offset={off:#x} p_vaddr={va:#x} "
              f"p_filesz={fs:#x} p_memsz={ms:#x} p_flags={fl}")
    print(f"--- 4. donor")
    print(f"    {EXP5_DONOR_CARD} @0x{ev['donor']['vma']:x} "
          f"({ev['donor']['table']}): {[hex(x) for x in ev['donor']['slots']]}")
    print(f"    resolver 0x{EXP5_DONOR_RESOLVER:x} pinned words "
          f"{[hex(x) for x in ev['donor_resolver']['words']]}")
    print(f"--- 5. entries and per-cell reloc table")
    for e in ev["entries"]:
        print(f"    CardID {e['card_id']} entry VMA 0x{e['entry_vma']:x}: "
              f"{[hex(x) for x in e['slots']]}")
        for c in e["cells"]:
            print(f"      slot{c['slot']} VMA 0x{c['vma']:x} file 0x{c['file']:x} "
                  f"old 0x{c['old']:08x} new 0x{c['new']:08x} "
                  f"reloc={c['reloc_type']} covered={c['covered']} "
                  f"changed={c['changed']}")
    print(f"--- 6. original part [0, 0x{EXP5_STUB_FILE_OFF:x})")
    print(f"    differing bytes: {ev['changed_count']} of the declared "
          f"{ev['declared_count']}")
    for start, end in ev["changed_ranges"]:
        print(f"    changed range [0x{start:x}, 0x{end:x}) ({end - start} B)")
    print(f"    recipe payload ({ev['payload_len']} B) byte-identical: "
          f"{ev['payload_ok']}")
    print(f"    .rel.data byte-identical: {ev['rel_data_ok']}")
    print(f"    .rel.text byte-identical: {ev['rel_text_ok']}")
    print(f"    section header table byte-identical: {ev['section_table_ok']}")
    print(f"--- 7. appended range [0x{BASE_PRX_SIZE:x}, "
          f"0x{EXP5_RESULT_SIZE:x}) is exactly the 20 stub bytes")
    print(f"EXP5 verification: OK - {ev['patched_size']} bytes, sha256 "
          f"{ev['patched_sha256']}")
    return 0


def cmd_iso5(args) -> int:
    with open(args.patched_prx, "rb") as f:
        patched_prx = f.read()
    prx, hdr, idx, _order = load_base(args.prx)
    print(f"EXP5 base module `{args.prx}`: {len(prx)} bytes, sha256 "
          f"{sha256(prx)}")
    print(f"EXP5 patched module `{args.patched_prx}`: {len(patched_prx)} bytes, "
          f"sha256 {sha256(patched_prx)}")
    fails, ev = verify_module5(prx, patched_prx, hdr, idx)
    if fails:
        print(f"STOP: the patched module does not verify ({len(fails)}):")
        for x in fails:
            print(f"  FAIL: {x}")
        return 1
    print(f"    OK: stub 20 B decoded, PH[1] 0x{EXP5_PH1_NEW_SIZE:x}, A/B "
          f"slot4, donor; payload/.rel.data/.rel.text/section table untouched")
    if os.path.exists(args.out):
        print(f"STOP: refusing to overwrite {args.out}")
        return 1
    if os.path.realpath(args.out) in {os.path.realpath(args.src),
                                      os.path.realpath(args.prx),
                                      os.path.realpath(args.patched_prx)}:
        print("STOP: --out is an input file")
        return 1
    got = sha256_file(args.src)
    if got != BASE_ISO_SHA256:
        print(f"STOP: source ISO sha256 {got} differs from the pinned F4 "
              f"{BASE_ISO_SHA256}")
        return 1
    src_size = os.path.getsize(args.src)
    if src_size != BASE_ISO_SIZE:
        print(f"STOP: source ISO size {src_size} != {BASE_ISO_SIZE}")
        return 1
    iso = Iso9660(args.src)
    try:
        entry = iso.resolve(PRX_IN_ISO)
        rec_off, rec = iso_replace.find_record(iso, PRX_IN_ISO)
        mgr_lba = iso.resolve(NEXT_MODULE_IN_ISO).extent
        in_iso = iso.read_file(PRX_IN_ISO)
    finally:
        iso.close()
    print(f"    sha256 {got} (pinned), size {src_size} B")
    print(f"    module extent LBA {entry.extent} size {entry.size:#x}, "
          f"allocation {iso_replace.allocated_bytes(entry.size)} B")
    print(f"    directory record at file {rec_off:#x} (sector {rec_off // SECTOR})")
    print(f"    next module {NEXT_MODULE_IN_ISO} at LBA {mgr_lba}")
    if (entry.extent != ISO_PRX_EXTENT or entry.size != BASE_PRX_SIZE
            or mgr_lba != MGR_LBA_EXPECTED):
        print("STOP: source ISO geometry differs from the pinned values")
        return 1
    if in_iso != prx:
        print("STOP: the module inside the source ISO != the pinned F4 module")
        return 1
    if len(patched_prx) > iso_replace.allocated_bytes(entry.size):
        print("STOP: the patched module does not fit the allocated extent")
        return 1
    report = iso_replace.replace_file(args.src, args.out, PRX_IN_ISO,
                                      patched_prx, label="B1-EXP5")
    print(f"    old size {report['old_size']:#x} -> new {report['new_size']:#x} "
          f"(ceiling {report['ceiling']:#x}); dir data-length updated; "
          f"roundtrip {report['roundtrip']}")
    back = iso_replace.read_iso_file(args.out, PRX_IN_ISO)
    errs = []
    if back != patched_prx:
        errs.append("the module read back from the ISO differs from the "
                    "artifact")
    if len(back) != EXP5_RESULT_SIZE:
        errs.append(f"module size read back is {len(back):#x}, expected "
                    f"{EXP5_RESULT_SIZE:#x}")
    diff = changed_sectors(args.src, args.out)
    expected, mod_changed = expected_iso_sectors(args.src, patched_prx, rec_off)
    if diff != expected:
        errs.append(f"changed sectors are {sorted(diff)}, expected "
                    f"{sorted(expected)}")
    out_size = os.path.getsize(args.out)
    if out_size != src_size or out_size != BASE_ISO_SIZE:
        errs.append(f"ISO size {out_size} != source {src_size} != "
                    f"{BASE_ISO_SIZE}")
    iso2 = Iso9660(args.out)
    try:
        mgr_after = iso2.resolve(NEXT_MODULE_IN_ISO).extent
        rec2_off, rec2 = iso_replace.find_record(iso2, PRX_IN_ISO)
    finally:
        iso2.close()
    if mgr_after != mgr_lba:
        errs.append(f"the next module moved from LBA {mgr_lba} to {mgr_after}")
    with open(args.out, "rb") as f:
        f.seek(rec2_off + 10)
        rec_size_le = struct.unpack("<I", f.read(4))[0]
        rec_size_be = struct.unpack(">I", f.read(4))[0]
    if rec_size_le != EXP5_RESULT_SIZE or rec_size_be != EXP5_RESULT_SIZE:
        errs.append(f"directory record size is {rec_size_le:#x}/"
                    f"{rec_size_be:#x}, expected {EXP5_RESULT_SIZE:#x}")
    print(f"    .prx read back equals the patched artifact: "
          f"{back == patched_prx}")
    print(f"    ISO size {out_size} B (source {src_size} B, unchanged)")
    print(f"    directory record size for the module: {rec_size_le:#x} (LE) / "
          f"{rec_size_be:#x} (BE)")
    print(f"    next module still at LBA {mgr_after} (untouched)")
    print(f"    module-extent changed bytes ({len(mod_changed)} runs):")
    for start, end in mod_changed:
        print(f"      extent+0x{start:x}..0x{end:x} ({end - start} B) -> LBA "
              f"{ISO_PRX_EXTENT + start // SECTOR}")
    print(f"    changed sectors: {len(diff)} -> {sorted(diff)} (expected "
          f"{sorted(expected)})")
    if errs:
        print(f"EXP5 ISO VERIFICATION FAILED ({len(errs)}):")
        for x in errs:
            print(f"  FAIL: {x}")
        return 1
    print(f"EXP5 ISO OK -> {args.out}")
    print(f"    size {out_size} bytes, sha256 {sha256_file(args.out)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("dump", help="print the base layout, entries and patch plan")
    d.add_argument("--prx", default=BASE_PRX)
    d.set_defaults(func=cmd_dump)

    b = sub.add_parser("build", help="build the patched module")
    b.add_argument("--prx", default=BASE_PRX)
    b.add_argument("--out", default=DEFAULT_OUT_PRX)
    b.set_defaults(func=cmd_build)

    v = sub.add_parser("verify", help="verify a patched module against the F4 base")
    v.add_argument("--pristine", default=BASE_PRX)
    v.add_argument("--patched", default=DEFAULT_OUT_PRX)
    v.add_argument("--prx", default=BASE_PRX,
                   help="canonical base used to locate entries by CardID")
    v.set_defaults(func=cmd_verify)

    i = sub.add_parser("iso", help="build and verify the probe ISO")
    i.add_argument("--src", default=BASE_ISO)
    i.add_argument("--prx", default=BASE_PRX)
    i.add_argument("--patched-prx", default=DEFAULT_OUT_PRX)
    i.add_argument("--out", default=DEFAULT_OUT_ISO)
    i.set_defaults(func=cmd_iso)

    d4 = sub.add_parser("dump4", help="EXP4: print the base layout and plan")
    d4.add_argument("--prx", default=BASE_PRX)
    d4.set_defaults(func=cmd_dump4)

    b4 = sub.add_parser("build4", help="EXP4: build the patched module")
    b4.add_argument("--prx", default=BASE_PRX)
    b4.add_argument("--out", default=EXP4_OUT_PRX)
    b4.set_defaults(func=cmd_build4)

    v4 = sub.add_parser("verify4", help="EXP4: verify a patched module")
    v4.add_argument("--pristine", default=BASE_PRX)
    v4.add_argument("--patched", default=EXP4_OUT_PRX)
    v4.add_argument("--prx", default=BASE_PRX)
    v4.set_defaults(func=cmd_verify4)

    i4 = sub.add_parser("iso4", help="EXP4: build and verify the probe ISO")
    i4.add_argument("--src", default=BASE_ISO)
    i4.add_argument("--prx", default=BASE_PRX)
    i4.add_argument("--patched-prx", default=EXP4_OUT_PRX)
    i4.add_argument("--out", default=EXP4_OUT_ISO)
    i4.set_defaults(func=cmd_iso4)

    d5 = sub.add_parser("dump5", help="EXP5: print the base layout and plan")
    d5.add_argument("--prx", default=BASE_PRX)
    d5.set_defaults(func=cmd_dump5)

    b5 = sub.add_parser("build5", help="EXP5: build the patched module")
    b5.add_argument("--prx", default=BASE_PRX)
    b5.add_argument("--out", default=EXP5_OUT_PRX)
    b5.set_defaults(func=cmd_build5)

    v5 = sub.add_parser("verify5", help="EXP5: verify a patched module")
    v5.add_argument("--pristine", default=BASE_PRX)
    v5.add_argument("--patched", default=EXP5_OUT_PRX)
    v5.add_argument("--prx", default=BASE_PRX)
    v5.set_defaults(func=cmd_verify5)

    i5 = sub.add_parser("iso5", help="EXP5: build and verify the probe ISO")
    i5.add_argument("--src", default=BASE_ISO)
    i5.add_argument("--prx", default=BASE_PRX)
    i5.add_argument("--patched-prx", default=EXP5_OUT_PRX)
    i5.add_argument("--out", default=EXP5_OUT_ISO)
    i5.set_defaults(func=cmd_iso5)
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

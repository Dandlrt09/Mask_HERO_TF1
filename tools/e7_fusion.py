#!/usr/bin/env python3
"""E7/T10+T11: grow the native fusion recipe table to 151 records and build the
product ISO.

The native engine reads fusion recipes from a `libduel_eng.prx` `.data` table at
VMA `0x10acb4` (94 records of 8 bytes `(result, mat1, mat2, mat3)` + the
`(10,0,0,0)` terminator), through a LINEAR finder at `.text 0xa0454` whose bound
is hardcoded as `sltiu a2,0x5e` (VMA `0xa047c`).  There is no free room in
`.data`/`.bss` for the new recipes (T1-PLAN.md sections 1-3), so this tool uses
the layout the EXP2 probe already booted (T1-PLAN.md section 4, S-A):

  * append a second `PT_LOAD` segment past EOF, inside the ISO's allocated
    extent for the module, so the ISO does not grow and no other file moves;
  * copy the 94 native records verbatim, append the Masked HERO base recipes
    (Dian has three bases: Clayman 6312, Bladedge 6477, Wildheart 6478) and the
    45 unordered pairs for `Contraste Chaos` (CardID 4696), and re-point the
    finder base, its length and the four table-end pointers.

Every count, size, immediate and pointer below is DERIVED from the S2 record
map, so amplifying that map later is a data-only edit.

Measured coordinates (re-asserted by this tool on the pinned pristine file):

  * `trabajo/e1c/gm/libduel_eng.prx` is a plain little-endian ELF32,
    1470794 bytes (0x16714a), sha256
    6867fb17d48479a429cb71b660daa7ebb8e4be90e0a63c2f4c619ceaa54bcf91, and is
    byte-identical to the copy inside `trabajo/e8/TF1-E8-G6.iso`.
  * `e_phoff` file 0x1c = 0x34, `e_phnum` file 0x2c = 1, `e_phentsize` 32.
    Single PH: type 1, p_offset 0x60, p_vaddr 0, p_paddr 0xfc9b0,
    p_filesz 0x10c080, p_memsz 0x112910, flags 7, align 16.  file = VMA + 0x60.
  * section table `e_shoff` 0x10c230, 25 entries, ends 0x10c618; `.comment` is
    the last file-backed section and ends exactly at EOF (0x16714a).
  * the fusion table base `0x10acb4` is materialized exactly ONCE in `.text`
    (file 0xa04c0); the terminator `0x10afa4` exactly FOUR times (file 0xaadc4,
    0xaafb0, 0xab434, 0xab4e4); `sltiu ...,0x5e` exactly once (file 0xa04dc).
    A sweep of every `lui`+`addiu` pair resolving into `0x10ac00..0x10b100`
    finds only the live 4-byte sentinel table at `0x10afac` plus the unrelated
    `{CardID; pad; ptr}` table at `0x10b018`, never the fusion table.

Chosen (approved) layout -- the EXP2 probe proved it in-game and F1 already
verified the whole mechanism end to end:

  * `PH_OFF      = 0x167150`  (16-aligned; 0x16714a..0x167150 zero padded)
    64-byte table: entry 0 = byte copy of the original PH, entry 1 = new segment.
  * entry 1: type 1, p_offset = `PAYLOAD_OFF = 0x167190`, p_vaddr = p_paddr =
    0x112910 (= vaddr end of segment 1), p_filesz = p_memsz = 1216, flags 7,
    align 16.  p_offset % 16 == p_vaddr % 16 == 0.
  * payload: 1216 bytes at 0x167190 = 94 copied records + 12 Masked HERO base
    recipes + 45 `Contraste Chaos` pairs + the `(10,0,0,0)` terminator.
  * code patches (only the low half of each immediate changes; `%hi` is 0x11 at
    every site): finder base -> 0x112910, `sltiu` bound 0x5e -> 0x97, four end
    pointers -> 0x112dc8.
  * `e_phoff = 0x167150`, `e_phnum = 2`; new file size = 0x167650 = 1472080,
    inside the ISO's 1472512-byte allocation for the module (432 B slack).

Subcommands (every one refuses to write when an invariant fails):

  patch  --out FILE [--src ISO] [--prx FILE]
         Validate the pristine module, patch the 6 words, append the 2nd PH +
         table, set the two ELF fields, self-verify and write the `.prx`.

  verify --pristine FILE --patched FILE
         Re-derive the patched image and assert byte equality; print the pristine
         size/sha256, the old word at each of the 6 sites, the old header, the
         single-diff byte layout, the 2-PH re-parse, the section table identity
         and the finder simulation over the new image.

  iso    --patched-prx FILE --out FILE [--src ISO]
         Verify the patched module, copy the source ISO, replace the module in
         place (directory data-length updated), and prove the image differs from
         the source only in the sectors carrying the module's changed bytes plus
         the directory record.  Prints size and sha256.

  dump   --patched FILE [--src ISO] [--prx FILE]
         Decode and print the records of the new table plus its terminator.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
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
NEXT_MODULE_IN_ISO = "PSP_GAME/USRDIR/gmodule/libduel_mgr.prx"
DEFAULT_SRC_ISO = os.path.join(ROOT, "trabajo", "e8", "TF1-E8-G6.iso")
DEFAULT_OUT_PRX = os.path.join(ROOT, "trabajo", "e7", "libduel_eng_f2.prx")
DEFAULT_OUT_ISO = os.path.join(ROOT, "trabajo", "e7", "TF1-E7-F2.iso")

# --- measured constants ------------------------------------------------------
PRX_SIZE = 1470794                        # 0x16714a
PRX_SHA256 = "6867fb17d48479a429cb71b660daa7ebb8e4be90e0a63c2f4c619ceaa54bcf91"
ISO_SIZE = 798787584
ISO_PRX_EXTENT = 12048
ISO_PRX_ALLOC = 1472512                   # 719 * 2048
EL_PHOFF_FIELD = 0x1C                     # u32
EL_PHNUM_FIELD = 0x2C                     # u16
OLD_PHOFF = 0x34
OLD_PHNUM = 1
PHENTSIZE = 32
PH_OFF = 0x167150                         # 16-aligned append offset
PH_TABLE_SIZE = 64
PAYLOAD_OFF = PH_OFF + PH_TABLE_SIZE      # 0x167190
SEG1 = (1, 0x60, 0x0, 0xFC9B0, 0x10C080, 0x112910, 7, 16)
SEG2_VADDR = 0x112910
E_SHOFF = 0x10C230
E_SHNUM = 25
E_SHENTSIZE = 40
SECTION_TABLE_END = E_SHOFF + E_SHNUM * E_SHENTSIZE   # 0x10c618

# --- native table ------------------------------------------------------------
FILE_DELTA = 0x60                         # file = VMA + 0x60
NATIVE_VMA = 0x10ACB4
NATIVE_COUNT = 94
TERMINATOR = (10, 0, 0, 0)

# --- S2 material map (the only data-only edit surface) -----------------------
# Each Masked HERO result maps to the E-HERO bases of its own attribute that the
# deck recipe already owns (L12).  Dian (TIERRA) is the only one with more than
# one base, which is why the value is a tuple.  Every count, size, immediate and
# pointer below is derived from this map: amplifying it is a data-only change.
MASK_CHANGE = 4704                        # "Cambio de Mascara" / Mask Change
CHAOS = 4696                              # Contraste Chaos: 2 Masked HERO
# (result CardID, (base E-HERO CardIDs...)) in S2 listed order
MASKED_HEROES = (
    (4661, (6393,)),          # Acid        / Bubbleman
    (4665, (6527,)),          # Anki        / Necroshade
    (4671, (6310,)),          # Blast       / Avian
    (4672, (6527,)),          # Dark Law    / Necroshade
    (4673, (6312, 6477, 6478)),   # Dian    / Clayman, Bladedge, Wildheart
    (4681, (6310,)),          # Divine Wind / Avian
    (4684, (6311,)),          # Goka        / Burstinatrix
    (4686, (6313,)),          # Koga        / Sparkman
    (4689, (6393,)),          # Vapor       / Bubbleman
    (4690, (6311,)),          # Atomic      / Burstinatrix
)
NEW_RESULTS = tuple(r for r, _bases in MASKED_HEROES) + (CHAOS,)
S2_BASE_COUNT = sum(len(bases) for _r, bases in MASKED_HEROES)          # 12
CHAOS_COUNT = len(list(itertools.combinations(NEW_RESULTS[:-1], 2)))    # 45
S2_COUNT = S2_BASE_COUNT + CHAOS_COUNT                                  # 57
TABLE_COUNT = NATIVE_COUNT + S2_COUNT                                   # 151
PAYLOAD_SIZE = TABLE_COUNT * 8 + 8                                      # 1216
NEW_SIZE = PAYLOAD_OFF + PAYLOAD_SIZE                                   # 0x167650
SEG2 = (1, PAYLOAD_OFF, SEG2_VADDR, SEG2_VADDR, PAYLOAD_SIZE, PAYLOAD_SIZE,
        7, 16)
TABLE_END_VMA = SEG2_VADDR + TABLE_COUNT * 8                            # 0x112dc8


# --- code patch plan (file offset, old word, new word, label) ----------------
def _low_half(old: int, value: int) -> int:
    """Rewrite only the low 16-bit immediate, keeping the instruction's %hi."""
    return (old & 0xFFFF0000) | (value & 0xFFFF)


PATCH_SITES = (
    (0x0A04C0, 0x24A5ACB4, _low_half(0x24A5ACB4, SEG2_VADDR),
     "finder base   -> VMA 0x112910"),
    (0x0A04DC, 0x2CC2005E, _low_half(0x2CC2005E, TABLE_COUNT),
     f"finder length -> {TABLE_COUNT} (sltiu 0x{TABLE_COUNT:x})"),
    (0x0AADC4, 0x24A5AFA4, _low_half(0x24A5AFA4, TABLE_END_VMA),
     f"end pointer   -> VMA {TABLE_END_VMA:#x}"),
    (0x0AAFB0, 0x24A5AFA4, _low_half(0x24A5AFA4, TABLE_END_VMA),
     f"end pointer   -> VMA {TABLE_END_VMA:#x}"),
    (0x0AB434, 0x24A5AFA4, _low_half(0x24A5AFA4, TABLE_END_VMA),
     f"end pointer   -> VMA {TABLE_END_VMA:#x}"),
    (0x0AB4E4, 0x24A5AFA4, _low_half(0x24A5AFA4, TABLE_END_VMA),
     f"end pointer   -> VMA {TABLE_END_VMA:#x}"),
)

PH_FMT = "<IIIIIIII"


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


def byte_ranges(indices: list[int]) -> list[tuple[int, int]]:
    """Contiguous [start, end) runs of an ascending list of byte offsets."""
    runs: list[tuple[int, int]] = []
    for i in indices:
        if runs and i == runs[-1][1]:
            runs[-1] = (runs[-1][0], i + 1)
        else:
            runs.append((i, i + 1))
    return runs


def file_offset(vma: int) -> int:
    return vma + FILE_DELTA


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
    (_type, _machine, _version, _entry, e_phoff, e_shoff, _flags, _ehsize,
     e_phentsize, e_phnum, e_shentsize, e_shnum, _shstrndx) = \
        struct.unpack_from("<HHIIIIIHHHHHH", prx, 16)
    return ElfHeader(e_phoff, e_phnum, e_phentsize, e_shoff, e_shnum,
                     e_shentsize)


def parse_ph(prx: bytes, hdr: ElfHeader) -> list[tuple]:
    return [struct.unpack_from(PH_FMT, prx, hdr.e_phoff + i * hdr.e_phentsize)
            for i in range(hdr.e_phnum)]


@dataclass
class Section:
    index: int
    name: str
    offset: int
    size: int
    typ: int


def parse_sections(prx: bytes, hdr: ElfHeader) -> list[Section]:
    secs = []
    for i in range(hdr.e_shnum):
        off = hdr.e_shoff + i * hdr.e_shentsize
        (name, typ, _flags, _addr, offset, size, _link, _info, _align,
         _entsize) = struct.unpack_from("<IIIIIIIIII", prx, off)
        secs.append(Section(i, name, offset, size, typ))
    strtab = secs[1].offset if len(secs) > 1 else 0

    def nm(nameoff: int) -> str:
        end = prx.index(b"\0", strtab + nameoff)
        return prx[strtab + nameoff:end].decode("latin1")
    for s in secs:
        s.name = nm(s.name)
    return secs


def native_records(prx: bytes) -> list[tuple]:
    """The 94 pristine records at VMA 0x10acb4, in file order."""
    base = file_offset(NATIVE_VMA)
    return [struct.unpack_from("<4H", prx, base + i * 8)
            for i in range(NATIVE_COUNT)]


def s2_records() -> list[tuple]:
    """The Masked HERO base recipes plus the 45 unordered pairs."""
    masked = [(result, base, MASK_CHANGE, 0)
              for result, bases in MASKED_HEROES for base in bases]
    chaos = [(CHAOS, a, b, 0)
             for a, b in itertools.combinations(NEW_RESULTS[:-1], 2)]
    return masked + chaos


def build_records(prx: bytes) -> tuple[list[tuple], list[tuple], list[tuple]]:
    """(all records, the NATIVE_COUNT native ones, the S2_COUNT S2 ones)."""
    nat = native_records(prx)
    new = s2_records()
    if len(nat) != NATIVE_COUNT:
        raise ValueError(f"native table has {len(nat)} records, expected "
                         f"{NATIVE_COUNT}")
    if len(new) != S2_COUNT:
        raise ValueError(f"S2 table has {len(new)} records, expected {S2_COUNT}")
    recs = nat + new
    if len(recs) != TABLE_COUNT:
        raise ValueError(f"new table has {len(recs)} records, expected "
                         f"{TABLE_COUNT}")
    return recs, nat, new


def build_payload(prx: bytes) -> bytes:
    recs, _nat, _new = build_records(prx)
    payload = b"".join(struct.pack("<4H", *r) for r in recs)
    payload += struct.pack("<4H", *TERMINATOR)
    if len(payload) != PAYLOAD_SIZE:
        raise ValueError(f"payload is {len(payload)} bytes, expected "
                         f"{PAYLOAD_SIZE}")
    return payload


def assert_pristine(prx: bytes, source: str) -> None:
    if len(prx) != PRX_SIZE:
        raise ValueError(f"{source}: {len(prx)} bytes, expected {PRX_SIZE}")
    got = sha256(prx)
    if got != PRX_SHA256:
        raise ValueError(f"{source}: sha256 {got} differs from the pinned "
                         f"pristine {PRX_SHA256}")
    hdr = parse_elf_header(prx)
    if (hdr.e_phoff, hdr.e_phnum, hdr.e_phentsize) != (OLD_PHOFF, OLD_PHNUM,
                                                       PHENTSIZE):
        raise ValueError(f"pristine ELF header is e_phoff {hdr.e_phoff:#x}, "
                         f"e_phnum {hdr.e_phnum}, e_phentsize {hdr.e_phentsize}, "
                         f"expected {OLD_PHOFF:#x}/{OLD_PHNUM}/{PHENTSIZE}")
    if parse_ph(prx, hdr) != [SEG1]:
        raise ValueError(f"pristine program headers are {parse_ph(prx, hdr)}, "
                         f"expected [{SEG1}]")
    if (hdr.e_shoff, hdr.e_shnum, hdr.e_shentsize) != (E_SHOFF, E_SHNUM,
                                                       E_SHENTSIZE):
        raise ValueError(f"pristine section table is e_shoff {hdr.e_shoff:#x}, "
                         f"e_shnum {hdr.e_shnum}, e_shentsize {hdr.e_shentsize}, "
                         f"expected {E_SHOFF:#x}/{E_SHNUM}/{E_SHENTSIZE}")
    for off, old, _new, label in PATCH_SITES:
        actual = struct.unpack_from("<I", prx, off)[0]
        if actual != old:
            raise ValueError(f"pristine word at file {off:#x} ({label}) is "
                             f"0x{actual:08x}, expected 0x{old:08x}")
    if NEW_SIZE > ISO_PRX_ALLOC:
        raise ValueError(f"patched size {NEW_SIZE} exceeds the ISO allocation "
                         f"{ISO_PRX_ALLOC}")
    if PAYLOAD_OFF % 16 != SEG2_VADDR % 16:
        raise ValueError("p_offset and p_vaddr of segment 2 are not congruent "
                         "modulo p_align=16")


def assert_new_words() -> None:
    """The low-half rewrite of every site matches the T1 plan exactly."""
    for off, old, new, label in PATCH_SITES:
        derived = (old & 0xFFFF0000) | (new & 0xFFFF)
        if derived != new:
            raise ValueError(f"patch site {off:#x} ({label}): recomputing the "
                             f"low half of 0x{old:08x} gives 0x{derived:08x}, "
                             f"not 0x{new:08x}")


def build_patched(prx: bytes) -> dict:
    """Return the patched image and the exact patch plan (raising on any doubt)."""
    assert_pristine(prx, "pristine")
    assert_new_words()
    hdr = parse_elf_header(prx)
    ph1_bytes = prx[OLD_PHOFF:OLD_PHOFF + PHENTSIZE]
    if len(ph1_bytes) != PHENTSIZE or \
            struct.unpack(PH_FMT, ph1_bytes) != SEG1:
        raise ValueError("the original PH bytes do not decode to SEG1")
    ph_table = ph1_bytes + struct.pack(PH_FMT, *SEG2)
    pad = b"\0" * (PH_OFF - PRX_SIZE)
    payload = build_payload(prx)

    patched = bytearray(prx) + pad + ph_table + payload
    if len(patched) != NEW_SIZE:
        raise ValueError(f"built image is {len(patched)} bytes, expected "
                         f"{NEW_SIZE}")
    for off, old, new, _label in PATCH_SITES:
        if struct.unpack_from("<I", patched, off)[0] != old:
            raise ValueError(f"patch site {off:#x} moved out from under the diff")
        struct.pack_into("<I", patched, off, new)
    struct.pack_into("<I", patched, EL_PHOFF_FIELD, PH_OFF)
    struct.pack_into("<H", patched, EL_PHNUM_FIELD, 2)

    changed = [i for i in range(PRX_SIZE) if prx[i] != patched[i]]
    declared = set()
    for off, _old, _new, _label in PATCH_SITES:
        declared.update(range(off, off + 4))
    declared.update(range(EL_PHOFF_FIELD, EL_PHOFF_FIELD + 4))
    declared.update(range(EL_PHNUM_FIELD, EL_PHNUM_FIELD + 2))
    outside = sorted(set(changed) - declared)
    if outside:
        raise ValueError(f"bytes outside the declared code/header regions "
                         f"changed, first {outside[0]:#x}")
    return {"patched": bytes(patched), "ph1_bytes": ph1_bytes,
            "ph_table": ph_table, "pad": pad, "payload": payload,
            "records": build_records(prx)[0], "new_records": build_records(prx)[2],
            "changed_original": changed, "declared_original": sorted(declared),
            "append_range": (PRX_SIZE, NEW_SIZE), "ph_off": PH_OFF,
            "payload_off": PAYLOAD_OFF, "new_size": NEW_SIZE,
            "hdr": hdr}


def find_first(records: list[tuple], result: int):
    """The finder semantics: first linear record whose result matches."""
    for i, r in enumerate(records):
        if r[0] == result:
            return i, r
    return None


def verify_pair(pristine: bytes, patched: bytes) -> tuple[list[str], dict]:
    """Independent re-derivation and detailed check of a patched file."""
    fails: list[str] = []
    ev: dict = {}
    try:
        assert_pristine(pristine, "pristine")
    except ValueError as exc:
        return [str(exc)], ev

    # --- 1. pristine evidence -------------------------------------------
    hdr0 = parse_elf_header(pristine)
    ev["pristine_size"] = len(pristine)
    ev["pristine_sha256"] = sha256(pristine)
    ev["old_phoff"] = hdr0.e_phoff
    ev["old_phnum"] = hdr0.e_phnum
    if hdr0.e_phoff != OLD_PHOFF:
        fails.append(f"pristine e_phoff is {hdr0.e_phoff:#x}, expected "
                     f"{OLD_PHOFF:#x}")
    if hdr0.e_phnum != OLD_PHNUM:
        fails.append(f"pristine e_phnum is {hdr0.e_phnum}, expected {OLD_PHNUM}")
    old_words = []
    for off, old, _new, label in PATCH_SITES:
        actual = struct.unpack_from("<I", pristine, off)[0]
        old_words.append((off, old, actual, label))
        if actual != old:
            fails.append(f"pristine word at file {off:#x} ({label}) is "
                         f"0x{actual:08x}, expected 0x{old:08x}")
    ev["old_words"] = old_words

    # --- 2. re-derive the patched image ---------------------------------
    try:
        plan = build_patched(pristine)
    except ValueError as exc:
        return fails + [str(exc)], ev
    ev["expected_sha256"] = sha256(plan["patched"])
    if len(patched) != NEW_SIZE:
        fails.append(f"patched size is {len(patched)}, expected {NEW_SIZE}")
        return fails, ev
    if patched != plan["patched"]:
        i = next((k for k in range(NEW_SIZE) if patched[k] != plan["patched"][k]),
                 None)
        fails.append(f"patched image differs from the re-derived image at "
                     f"offset {i:#x}")
        return fails, ev

    # --- 3. single diff against the pristine ----------------------------
    declared = set(plan["declared_original"])
    changed = [i for i in range(PRX_SIZE) if pristine[i] != patched[i]]
    outside = sorted(set(changed) - declared)
    if outside:
        fails.append(f"diff against the pristine reaches {len(outside)} bytes "
                     f"outside the declared code/header regions, first "
                     f"{outside[0]:#x}")
    per_word = []
    for off, old, new, _label in PATCH_SITES:
        ob = pristine[off:off + 4]
        nb = patched[off:off + 4]
        n = sum(1 for k in range(4) if ob[k] != nb[k])
        per_word.append((off, old, new, ob.hex(), nb.hex(), n))
    ev["changed_original_count"] = len(changed)
    ev["changed_ranges"] = byte_ranges(changed)
    ev["per_word"] = per_word
    phoff_before = pristine[EL_PHOFF_FIELD:EL_PHOFF_FIELD + 4]
    phoff_after = patched[EL_PHOFF_FIELD:EL_PHOFF_FIELD + 4]
    phnum_before = pristine[EL_PHNUM_FIELD:EL_PHNUM_FIELD + 2]
    phnum_after = patched[EL_PHNUM_FIELD:EL_PHNUM_FIELD + 2]
    ev["phoff_bytes"] = (phoff_before.hex(), phoff_after.hex(),
                         sum(1 for k in range(4) if phoff_before[k] != phoff_after[k]))
    ev["phnum_bytes"] = (phnum_before.hex(), phnum_after.hex(),
                         sum(1 for k in range(2) if phnum_before[k] != phnum_after[k]))
    if struct.unpack("<I", phoff_after)[0] != PH_OFF:
        fails.append(f"e_phoff does not hold {PH_OFF:#x}")
    if struct.unpack("<H", phnum_after)[0] != 2:
        fails.append("e_phnum does not hold 2")

    # --- 4. patched ELF re-parses ---------------------------------------
    hdr = parse_elf_header(patched)
    if (hdr.e_phoff, hdr.e_phnum, hdr.e_phentsize) != (PH_OFF, 2, PHENTSIZE):
        fails.append(f"patched header e_phoff {hdr.e_phoff:#x}/e_phnum "
                     f"{hdr.e_phnum}/e_phentsize {hdr.e_phentsize}, expected "
                     f"{PH_OFF:#x}/2/{PHENTSIZE}")
    phs = parse_ph(patched, hdr)
    ev["patched_ph"] = phs
    if phs != [SEG1, SEG2]:
        fails.append(f"patched program headers decode to {phs}, expected "
                     f"[{SEG1}, {SEG2}]")
    else:
        ph1, ph2 = phs
        if ph2[1] % 16 != ph2[2] % 16:
            fails.append(f"PH2 p_offset {ph2[1]:#x} and p_vaddr {ph2[2]:#x} are "
                         f"not congruent modulo 16")
        if not (ph2[2] >= ph1[2] + ph1[5]):
            fails.append(f"segments overlap in memory: seg2.vaddr {ph2[2]:#x} < "
                         f"seg1.vaddr+seg1.memsz {ph1[2] + ph1[5]:#x}")
        if not (ph2[1] >= ph1[1] + ph1[4] or ph1[1] >= ph2[1] + ph2[4]):
            fails.append("segments overlap in the file")
        ev["seg2_vaddr_gap"] = ph2[2] - (ph1[2] + ph1[5])

    # --- 5. section header table and every section header unchanged -----
    sl = E_SHNUM * E_SHENTSIZE
    section_tbl_same = (patched[E_SHOFF:E_SHOFF + sl] ==
                        pristine[E_SHOFF:E_SHOFF + sl])
    ev["section_table_same"] = section_tbl_same
    if not section_tbl_same:
        fails.append("the section header table bytes changed")
    if (hdr.e_shoff, hdr.e_shnum, hdr.e_shentsize) != (E_SHOFF, E_SHNUM,
                                                       E_SHENTSIZE):
        fails.append(f"section table header changed: e_shoff {hdr.e_shoff:#x}/"
                     f"e_shnum {hdr.e_shnum}/e_shentsize {hdr.e_shentsize}")
    for s in parse_sections(patched, hdr):
        if s.offset + s.size > NEW_SIZE:
            fails.append(f"section {s.index} ({s.name}) ends past EOF")

    # --- 6. table content: native prefix, pairs, terminator -------------
    nat = native_records(pristine)
    recs, _nat, _new = build_records(pristine)
    native_bytes = NATIVE_COUNT * 8
    new_table_bytes = patched[PAYLOAD_OFF:PAYLOAD_OFF + native_bytes]
    if new_table_bytes != pristine[file_offset(NATIVE_VMA):
                                   file_offset(NATIVE_VMA) + native_bytes]:
        fails.append(f"records 0..{NATIVE_COUNT - 1} of the new table are not "
                     f"byte-identical to the original {NATIVE_COUNT} records")
    native_results = [r[0] for r in nat]
    distinct = len(set(native_results))
    ev["native_distinct"] = distinct
    if distinct != NATIVE_COUNT:
        fails.append(f"the {NATIVE_COUNT} native results are {distinct} distinct "
                     f"values, expected {NATIVE_COUNT}")
    overlap = sorted(set(native_results) & set(NEW_RESULTS))
    ev["shadow_overlap"] = overlap
    if overlap:
        fails.append(f"native results shadow new results: {overlap}")
    ev["table_count"] = len(recs)
    if len(recs) != TABLE_COUNT:
        fails.append(f"the new table has {len(recs)} records, expected "
                     f"{TABLE_COUNT}")
    ev["duplicate_records"] = len(recs) - len(set(recs))
    if ev["duplicate_records"]:
        dupes = sorted({r for r in recs if recs.count(r) > 1})
        fails.append(f"the new table repeats {len(dupes)} record(s): {dupes}")
    tail = struct.unpack_from("<4H", patched, PAYLOAD_OFF + TABLE_COUNT * 8)
    ev["terminator"] = tail
    if tail != TERMINATOR:
        fails.append(f"word {TABLE_COUNT} is {tail}, expected the terminator "
                     f"{TERMINATOR}")
    # the Masked HERO base records mirror the S2 map exactly, in listed order
    masked_actual = tuple(recs[NATIVE_COUNT:NATIVE_COUNT + S2_BASE_COUNT])
    masked_want = tuple((r, b, MASK_CHANGE, 0)
                        for r, bases in MASKED_HEROES for b in bases)
    ev["masked_records"] = masked_actual
    if masked_actual != masked_want:
        fails.append(f"Masked HERO base records {masked_actual} do not mirror "
                     f"the S2 map {masked_want}")
    dian = tuple(r for r in recs if r[0] == 4673)
    ev["dian_records"] = dian
    want_dian = ((4673, 6312, MASK_CHANGE, 0),
                 (4673, 6477, MASK_CHANGE, 0),
                 (4673, 6478, MASK_CHANGE, 0))
    if dian != want_dian:
        fails.append(f"Dian (4673) records are {dian}, expected {want_dian}")
    chaos = [r for r in recs[NATIVE_COUNT:] if r[0] == CHAOS]
    chaos_pairs = [tuple(sorted((r[1], r[2]))) for r in chaos]
    want_pairs = [tuple(sorted(p))
                  for p in itertools.combinations(NEW_RESULTS[:-1], 2)]
    ev["chaos_pairs"] = len(chaos_pairs)
    if len(chaos_pairs) != CHAOS_COUNT:
        fails.append(f"{len(chaos_pairs)} Contraste Chaos pairs, expected "
                     f"{CHAOS_COUNT}")
    if len(set(chaos_pairs)) != len(chaos_pairs):
        fails.append("Contraste Chaos pairs contain duplicates")
    if sorted(chaos_pairs) != sorted(want_pairs):
        fails.append(f"Contraste Chaos pairs are not exactly the {CHAOS_COUNT} "
                     f"unordered pairs of the {len(NEW_RESULTS) - 1} Masked "
                     f"HERO")

    # --- 7. finder simulation over the new image ------------------------
    first_new = {}
    for t in native_results:
        o = find_first(nat, t)
        n = find_first(recs, t)
        if o != n:
            fails.append(f"native result {t}: first match changed from {o} to {n}")
        first_new[t] = n
    for t in NEW_RESULTS:
        hit = find_first(recs, t)
        if hit is None:
            fails.append(f"new result {t} is not found by the finder")
            continue
        i, r = hit
        own = {rec for rec in recs[NATIVE_COUNT:] if rec[0] == t}
        if i < NATIVE_COUNT or r not in own:
            fails.append(f"new result {t} first matches record {i} {r}, which "
                         f"is not one of its own records")
        first_new[t] = hit
    want_first = {4673: (4673, 6312, MASK_CHANGE, 0),
                  CHAOS: (CHAOS, NEW_RESULTS[0], NEW_RESULTS[1], 0)}
    for t, want in want_first.items():
        got = first_new.get(t)
        if got is None or got[1] != want:
            fails.append(f"result {t} first-matches {got}, expected record {want}")
    ev["first_new"] = first_new

    ev["records"] = recs
    return fails, ev


def print_ph_table(prx: bytes, label: str) -> None:
    hdr = parse_elf_header(prx)
    print(f"{label}: e_phoff {hdr.e_phoff:#x}, e_phnum {hdr.e_phnum}, "
          f"e_phentsize {hdr.e_phentsize}")
    for i, ph in enumerate(parse_ph(prx, hdr)):
        t, off, va, pa, fs, ms, fl, al = ph
        print(f"  PH{i}: type={t} p_offset={off:#x} p_vaddr={va:#x} "
              f"p_paddr={pa:#x} p_filesz={fs:#x} p_memsz={ms:#x} p_flags={fl} "
              f"p_align={al}")


def print_patch_map(plan: dict) -> None:
    print(f"  e_phoff  file {EL_PHOFF_FIELD:#x} (u32): {OLD_PHOFF:#x} -> "
          f"{plan['ph_off']:#x}")
    print(f"  e_phnum  file {EL_PHNUM_FIELD:#x} (u16): {OLD_PHNUM} -> 2")
    print(f"  PH table file {plan['ph_off']:#x}..{plan['ph_off'] + PH_TABLE_SIZE:#x} "
          f"(64 B): entry 0 = byte copy of the original PH, entry 1 = {SEG2}")
    print(f"  payload  file {plan['payload_off']:#x}.."
          f"{plan['payload_off'] + PAYLOAD_SIZE:#x} ({PAYLOAD_SIZE} B): "
          f"{TABLE_COUNT} records + terminator")
    print(f"  pad      file {PRX_SIZE:#x}..{plan['ph_off']:#x} "
          f"({plan['ph_off'] - PRX_SIZE} zero bytes)")
    print(f"  size     {PRX_SIZE} -> {plan['new_size']} "
          f"(+{plan['new_size'] - PRX_SIZE} B, ISO allocation {ISO_PRX_ALLOC})")
    for off, old, new, label in PATCH_SITES:
        print(f"  code     file {off:#08x}: 0x{old:08x} -> 0x{new:08x}   {label}")


def load_pristine(args) -> tuple[bytes, str]:
    if getattr(args, "prx", None):
        with open(args.prx, "rb") as f:
            return f.read(), args.prx
    src = getattr(args, "src", None) or DEFAULT_SRC_ISO
    if not os.path.exists(src):
        raise SystemExit(f"missing input ISO: {src}")
    return iso_replace.read_iso_file(src, PRX_IN_ISO), f"{src}:{PRX_IN_ISO}"


# --------------------------------------------------------------------------- #
# subcommands
# --------------------------------------------------------------------------- #
def cmd_patch(args) -> int:
    prx, source = load_pristine(args)
    print(f"pristine `{source}`: {len(prx)} bytes, sha256 {sha256(prx)}")
    print("--- preconditions")
    plan = build_patched(prx)
    print("    pinned pristine OK; 6 old words match; appended layout and new "
          "table reconstruct")
    print("--- patch map")
    print_patch_map(plan)
    if os.path.exists(args.out):
        print(f"STOP: refusing to overwrite {args.out}")
        return 1
    with open(args.out, "wb") as f:
        f.write(plan["patched"])
    print(f"--- wrote {args.out}")
    print(f"    {len(plan['patched'])} bytes, sha256 {sha256(plan['patched'])}")
    fails, _ = verify_pair(prx, plan["patched"])
    if fails:
        print(f"SELF-VERIFY FAILED ({len(fails)}):")
        for x in fails:
            print(f"  FAIL: {x}")
        return 1
    print("    self-verify: OK")
    return 0


def print_verify_evidence(ev: dict) -> None:
    print("--- 1. pristine")
    print(f"    size {ev['pristine_size']} bytes, sha256 {ev['pristine_sha256']}")
    print(f"    old e_phoff {ev['old_phoff']:#x}, old e_phnum {ev['old_phnum']}")
    for off, old, actual, label in ev["old_words"]:
        print(f"    file {off:#08x}  old word 0x{old:08x}  actual 0x{actual:08x}"
              f"  {label}")

    print("--- 2. patched ELF re-read")
    for i, ph in enumerate(ev["patched_ph"]):
        t, off, va, pa, fs, ms, fl, al = ph
        print(f"    PH{i}: type={t} p_offset={off:#x} p_vaddr={va:#x} "
              f"p_paddr={pa:#x} p_filesz={fs:#x} p_memsz={ms:#x} p_flags={fl} "
              f"p_align={al}")
    print(f"    PH1/PH2 memory gap: {ev.get('seg2_vaddr_gap')} bytes; p_offset % "
          f"16 == p_vaddr % 16")

    print("--- 3. byte diff against the pristine (original part)")
    print(f"    differing bytes in [0, {PRX_SIZE:#x}): "
          f"{ev['changed_original_count']}")
    for start, end in ev["changed_ranges"]:
        print(f"    changed range [{start:#x}, {end:#x}) ({end - start} byte(s))")
    for off, old, new, ob, nb, n in ev["per_word"]:
        print(f"    file {off:#08x}  0x{old:08x} -> 0x{new:08x}  "
              f"{ob} -> {nb}  ({n} byte values)")
    pb, pa, pn = ev["phoff_bytes"]
    print(f"    file {EL_PHOFF_FIELD:#08x}  e_phoff {pb} -> {pa}  ({pn} byte values)")
    hb, ha, hn = ev["phnum_bytes"]
    print(f"    file {EL_PHNUM_FIELD:#08x}  e_phnum {hb} -> {ha}  ({hn} byte values)")
    print(f"    appended range [{PRX_SIZE:#x}, {NEW_SIZE:#x}) is new bytes only")

    print("--- 4. section header table")
    print(f"    e_shoff {E_SHOFF:#x}, {E_SHNUM} entries "
          f"({E_SHOFF:#x}..{SECTION_TABLE_END:#x}); byte-identical to pristine: "
          f"{ev['section_table_same']}")

    print("--- 5. records")
    print(f"    records 0..{NATIVE_COUNT - 1} byte-identical to the "
          f"{NATIVE_COUNT} native records; {ev['native_distinct']} distinct "
          f"native results; native/new result overlap: {ev['shadow_overlap']}")
    print(f"    table records: {ev['table_count']} (expected {TABLE_COUNT}); "
          f"duplicate records: {ev['duplicate_records']}")
    print(f"    word {TABLE_COUNT} (terminator): {ev['terminator']}")
    print(f"    Masked HERO base records: {list(ev['masked_records'])}")
    print(f"    Dian (4673) records: {list(ev['dian_records'])}")
    print(f"    Contraste Chaos (4696) pairs: {ev['chaos_pairs']}/{CHAOS_COUNT}, "
          f"all unique")

    print("--- 6. finder simulation over the new image")
    for t in sorted(ev["first_new"]):
        i, r = ev["first_new"][t]
        role = "native" if t not in NEW_RESULTS else "new"
        print(f"    result {t:5d} ({role:6}) first match record {i:3d}: "
              f"{r}")

    print("--- 7. ISO artefact")
    print(f"    expected final size {NEW_SIZE} B (ISO allocation {ISO_PRX_ALLOC})")


def cmd_verify(args) -> int:
    with open(args.pristine, "rb") as f:
        pristine = f.read()
    with open(args.patched, "rb") as f:
        patched = f.read()
    print(f"pristine: {args.pristine} ({len(pristine)} bytes)")
    print(f"patched : {args.patched} ({len(patched)} bytes, sha256 "
          f"{sha256(patched)})")
    fails, ev = verify_pair(pristine, patched)
    if fails:
        print(f"VERIFICATION FAILED ({len(fails)}):")
        for x in fails:
            print(f"  FAIL: {x}")
        return 1
    print_verify_evidence(ev)
    print(f"verification: OK - the patched file differs from the pristine only "
          f"in the 6 patched words, e_phoff (3 byte values), e_phnum (1 byte "
          f"value) and the appended range; the section header table and every "
          f"section header are unchanged; the ELF re-parses with 2 "
          f"non-overlapping PT_LOAD segments and the new {TABLE_COUNT}-record "
          f"table resolves as planned")
    return 0


def cmd_dump(args) -> int:
    prx, source = load_pristine(args)
    with open(args.patched, "rb") as f:
        patched = f.read()
    fails, ev = verify_pair(prx, patched)
    if fails:
        print(f"STOP: the patched module does not verify ({len(fails)}):")
        for x in fails:
            print(f"  FAIL: {x}")
        return 1
    recs = ev["records"]
    print(f"pristine `{source}` -> {args.patched}")
    print(f"new table: {len(recs)} records + terminator at file {PAYLOAD_OFF:#x} "
          f"(VMA {SEG2_VADDR:#x})")
    print("  idx  result  mat1  mat2  mat3  origin")
    for i, r in enumerate(recs):
        origin = "native" if i < NATIVE_COUNT else \
            ("masked" if i < NATIVE_COUNT + len(MASKED_HEROES) else "chaos")
        print(f"  {i:3d}  {r[0]:6d}  {r[1]:5d}  {r[2]:5d}  {r[3]:5d}  {origin}")
    tail = ev["terminator"]
    print(f"  {len(recs):3d}  {tail[0]:6d}  {tail[1]:5d}  {tail[2]:5d}  "
          f"{tail[3]:5d}  terminator")
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


def expected_iso_sectors(src: str, patched: bytes, rec_off: int) -> set[int]:
    """Sectors the in-place replacement must touch, derived independently."""
    with open(src, "rb") as f:
        f.seek(ISO_PRX_EXTENT * SECTOR)
        before = f.read(ISO_PRX_ALLOC)
    if len(before) != ISO_PRX_ALLOC:
        raise ValueError("could not read the module's allocated extent from the ISO")
    after = patched + before[NEW_SIZE:]
    if len(after) != len(before):
        raise ValueError("extent reconstruction length mismatch")
    out: set[int] = set()
    for i in range(len(before)):
        if before[i] != after[i]:
            out.add(ISO_PRX_EXTENT + i // SECTOR)
    out.add(rec_off // SECTOR)
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
    fails, ev = verify_pair(pristine_prx, patched_prx)
    if fails:
        print(f"STOP: the patched module does not verify ({len(fails)}):")
        for x in fails:
            print(f"  FAIL: {x}")
        return 1
    print(f"    OK: 6 code words + e_phoff/e_phnum + appended {TABLE_COUNT}-"
          f"record table; section table intact; 2 non-overlapping segments")

    iso = Iso9660(args.src)
    try:
        entry = iso.resolve(PRX_IN_ISO)
        rec_off, rec = iso_replace.find_record(iso, PRX_IN_ISO)
        src_size = os.path.getsize(args.src)
        mgr_lba = iso.resolve(NEXT_MODULE_IN_ISO).extent
    finally:
        iso.close()
    if entry.extent != ISO_PRX_EXTENT or entry.size != PRX_SIZE:
        print(f"STOP: source module extent/size is {entry.extent}/{entry.size}, "
              f"expected {ISO_PRX_EXTENT}/{PRX_SIZE}")
        return 1
    if len(patched_prx) > iso_replace.allocated_bytes(entry.size):
        print("STOP: the patched module does not fit the allocated extent")
        return 1
    print(f"--- 2. module extent LBA {entry.extent}, allocation "
          f"{iso_replace.allocated_bytes(entry.size)} B; patched size "
          f"{len(patched_prx)} B (fits); directory record at file {rec_off:#x} "
          f"(sector {rec_off // SECTOR})")
    if os.path.exists(args.out):
        print(f"STOP: refusing to overwrite {args.out}")
        return 1

    print(f"--- 3. copy {args.src} -> {args.out} and replace the module in place")
    report = iso_replace.replace_file(args.src, args.out, PRX_IN_ISO,
                                      patched_prx, label="E7-F2")
    print(f"    old size {report['old_size']} -> new {report['new_size']} "
          f"(ceiling {report['ceiling']}); directory data-length updated; "
          f"roundtrip {report['roundtrip']}")

    print("--- 4. verification from the written ISO")
    back = iso_replace.read_iso_file(args.out, PRX_IN_ISO)
    errs: list[str] = []
    if back != patched_prx:
        errs.append("the module read back from the ISO differs from the artifact")
    if len(back) != NEW_SIZE:
        errs.append(f"module size read back is {len(back)}, expected {NEW_SIZE}")
    diff = changed_sectors(args.src, args.out)
    expected = expected_iso_sectors(args.src, patched_prx, rec_off)
    if diff != expected:
        errs.append(f"changed sectors are {sorted(diff)}, expected "
                    f"{sorted(expected)}")
    out_size = os.path.getsize(args.out)
    if out_size != src_size or out_size != ISO_SIZE:
        errs.append(f"ISO size {out_size} != source {src_size} != expected "
                    f"{ISO_SIZE}")
    iso2 = Iso9660(args.out)
    try:
        mgr_after = iso2.resolve(NEXT_MODULE_IN_ISO).extent
    finally:
        iso2.close()
    if mgr_after != mgr_lba:
        errs.append(f"the next module moved from LBA {mgr_lba} to {mgr_after}")

    print(f"    .prx read back equals the patched artifact: {back == patched_prx}")
    print(f"    changed sectors: {len(diff)} -> {sorted(diff)} (expected "
          f"{sorted(expected)})")
    print(f"    {PRX_IN_ISO} size {NEW_SIZE} B read back; ISO total size "
          f"{out_size} B (unchanged); next module still at LBA {mgr_after}")
    print(f"    every other sector of {out_size} bytes is byte-identical "
          f"(full chunked comparison)")
    if errs:
        print(f"VERIFICATION FAILED ({len(errs)}):")
        for x in errs:
            print(f"  FAIL: {x}")
        return 1
    print(f"OK -> {args.out}")
    print(f"    size {out_size} bytes, sha256 {sha256_file(args.out)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--src", default=DEFAULT_SRC_ISO,
                        help=f"source ISO (default {DEFAULT_SRC_ISO})")
        sp.add_argument("--prx", default=None,
                        help="pristine libduel_eng.prx file (overrides --src)")

    c = sub.add_parser("patch", help="build the patched .prx")
    common(c)
    c.add_argument("--out", default=DEFAULT_OUT_PRX)
    c.set_defaults(func=cmd_patch)

    v = sub.add_parser("verify", help="verify a patched .prx against the pristine")
    v.add_argument("--pristine", required=True)
    v.add_argument("--patched", required=True)
    v.set_defaults(func=cmd_verify)

    i = sub.add_parser("iso", help="build and verify the product ISO")
    i.add_argument("--src", default=DEFAULT_SRC_ISO)
    i.add_argument("--patched-prx", default=DEFAULT_OUT_PRX)
    i.add_argument("--out", default=DEFAULT_OUT_ISO)
    i.set_defaults(func=cmd_iso)

    d = sub.add_parser("dump",
                       help=f"decode and print the {TABLE_COUNT} new records")
    common(d)
    d.add_argument("--patched", default=DEFAULT_OUT_PRX)
    d.set_defaults(func=cmd_dump)
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

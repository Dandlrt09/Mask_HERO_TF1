#!/usr/bin/env python3
"""E7/T9 EXP2: probe whether `libehsys` honours a relocated `e_phoff` and loads
TWO `PT_LOAD` segments -- without changing any game behaviour.

The experiment is a pure ELF-layout probe: it appends a second program header and
an inert 1200-byte payload after the end of `libduel_eng.prx`, points `e_phoff`
at the new 2-entry table and sets `e_phnum = 2`.  Nothing in the module references
the added bytes, and no table, count, immediate, finder or section header is
touched.  If the game boots and plays, the loader accepted the relocated
`e_phoff` and two segments (strategy S-A is viable); if it fails, S-A is dead.

Measured facts (verified by this tool on the pinned pristine file):

  * `libduel_eng.prx` is a plain ELF, 1470794 bytes (0x16714a); the copy in
    `trabajo/e8/TF1-E8-G6.iso` is byte-identical to `trabajo/e1c/gm/`.
  * ELF header: `e_phoff` file 0x1c = 0x34, `e_phnum` file 0x2c = 1,
    `e_phentsize` = 32.  Single PH at 0x34:
    type 1, p_offset 0x60, p_vaddr 0, p_paddr 0xfc9b0, p_filesz 0x10c080,
    p_memsz 0x112910, flags 7, align 16.
  * Section header table: `e_shoff` 0x10c230, `e_shnum` 25, `e_shentsize` 40
    (file 0x10c230..0x10c618).  `.data` ends at file 0x10c0e0; `.comment` is the
    last file-backed section and ends exactly at EOF (0x16714a).
  * There is NO free file region after `.data`: file 0x10c0e0 is `.shstrtab`,
    then the section header table, then `.rel.text`.  (The task brief's original
    "section-free region 0x10c0e0..0x159b48" premise was wrong; writing there
    would corrupt `.shstrtab` and section headers 0..23, including `.rel.text`.)

Chosen (approved) layout -- append past EOF, inside the ISO allocation:

  * `PH_OFF      = 0x167150`  (16-aligned; 0x16714a..0x167150 zero padded)
    64-byte table: entry 0 = byte copy of the original PH; entry 1 = new segment.
  * entry 1: type 1, p_offset = `PAYLOAD_OFF = 0x167190`, p_vaddr = p_paddr =
    0x112910 (= vaddr end of segment 1), p_filesz = p_memsz = 1200, flags 7,
    align 16.  p_offset % 16 == p_vaddr % 16 == 0.
  * payload: 1200 bytes at 0x167190, byte 0..15 = `E7-EXP2-PTLOAD!`, rest zeros.
  * `e_phoff = 0x167150`, `e_phnum = 2`; new file size = 0x167640 = 1472064,
    which is <= the ISO's 1472512-byte allocated extent for the module (1718 B
    slack), so the ISO keeps its total size and no other file moves.
  * The second segment starts exactly where segment 1's `memsz` ends
    (0x112910), so the two load ranges do not overlap.

Subcommands (every one refuses to write when an invariant fails):

  patch  --out FILE [--src ISO] [--prx FILE]
         Validate the pristine module, append the PH table and payload, set the
         two ELF fields, self-verify and write the patched `.prx`.

  verify --pristine FILE --patched FILE
         Re-derive the patched image and assert it is byte-identical; assert the
         diff against the pristine is exactly `e_phoff` + `e_phnum` + the
         appended range; re-parse the ELF (2 PHs, values, non-overlap) and assert
         the section header table and every section header are unchanged.

  iso    --patched-prx FILE --out FILE [--src ISO]
         Verify the patched module on its own, copy the source ISO, replace the
         module in place (directory data-length updated), and prove the image
         differs from the source only in the sectors carrying the module's
         changed bytes plus the directory record.  Prints size and sha256.
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
DEFAULT_OUT_ISO = os.path.join(ROOT, "trabajo", "e7", "TF1-E7-EXP2.iso")
DEFAULT_OUT_PRX = os.path.join(ROOT, "trabajo", "e7", "libduel_eng_exp2.prx")
NEXT_MODULE_IN_ISO = "PSP_GAME/USRDIR/gmodule/libduel_mgr.prx"

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
PAYLOAD_SIZE = 1200                       # 0x4b0
NEW_SIZE = PAYLOAD_OFF + PAYLOAD_SIZE     # 0x167640
SEG1 = (1, 0x60, 0x0, 0xFC9B0, 0x10C080, 0x112910, 7, 16)
SEG2_VADDR = 0x112910
SEG2 = (1, PAYLOAD_OFF, SEG2_VADDR, SEG2_VADDR, PAYLOAD_SIZE, PAYLOAD_SIZE, 7, 16)
MARKER = b"E7-EXP2-PTLOAD!"
E_SHOFF = 0x10C230
E_SHNUM = 25
E_SHENTSIZE = 40
SECTION_TABLE_END = E_SHOFF + E_SHNUM * E_SHENTSIZE   # 0x10c618

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
    out = []
    for i in range(hdr.e_phnum):
        out.append(struct.unpack_from(PH_FMT, prx, hdr.e_phoff + i * hdr.e_phentsize))
    return out


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


def assert_pristine(prx: bytes, source: str) -> None:
    if len(prx) != PRX_SIZE:
        raise ValueError(f"{source}: {len(prx)} bytes, expected {PRX_SIZE}")
    got = sha256(prx)
    if got != PRX_SHA256:
        raise ValueError(f"{source}: sha256 {got} differs from the pinned pristine "
                         f"{PRX_SHA256}")
    hdr = parse_elf_header(prx)
    if (hdr.e_phoff, hdr.e_phnum, hdr.e_phentsize) != (OLD_PHOFF, OLD_PHNUM,
                                                       PHENTSIZE):
        raise ValueError(f"pristine ELF header is e_phoff {hdr.e_phoff:#x}, "
                         f"e_phnum {hdr.e_phnum}, e_phentsize {hdr.e_phentsize}, "
                         f"expected {OLD_PHOFF:#x}/{OLD_PHNUM}/{PHENTSIZE}")
    phs = parse_ph(prx, hdr)
    if phs != [SEG1]:
        raise ValueError(f"pristine program headers are {phs}, expected [{SEG1}]")
    if (hdr.e_shoff, hdr.e_shnum, hdr.e_shentsize) != (E_SHOFF, E_SHNUM,
                                                       E_SHENTSIZE):
        raise ValueError(f"pristine section table is e_shoff {hdr.e_shoff:#x}, "
                         f"e_shnum {hdr.e_shnum}, e_shentsize {hdr.e_shentsize}, "
                         f"expected {E_SHOFF:#x}/{E_SHNUM}/{E_SHENTSIZE}")
    secs = parse_sections(prx, hdr)
    last = max(s.offset + s.size for s in secs)
    if last != PRX_SIZE:
        raise ValueError(f"the last file-backed section ends at {last:#x}, expected "
                         f"EOF {PRX_SIZE:#x} (the append anchor moved)")
    comment = secs[-1]
    if comment.name != ".comment" or comment.offset + comment.size != PRX_SIZE:
        raise ValueError(f"the last section is {comment.name!r} ending at "
                         f"{comment.offset + comment.size:#x}, expected .comment at "
                         f"EOF {PRX_SIZE:#x}")
    if len(prx) + 0 != PRX_SIZE:
        raise ValueError("unreachable")
    if NEW_SIZE > ISO_PRX_ALLOC:
        raise ValueError(f"patched size {NEW_SIZE} exceeds the ISO allocation "
                         f"{ISO_PRX_ALLOC}")
    if PAYLOAD_OFF % 16 != SEG2_VADDR % 16:
        raise ValueError("p_offset and p_vaddr of segment 2 are not congruent "
                         "modulo p_align=16")


def build_patched(prx: bytes) -> dict:
    """Return the patched image and the exact patch plan (raising on any doubt)."""
    assert_pristine(prx, "pristine")
    ph1_bytes = prx[OLD_PHOFF:OLD_PHOFF + PHENTSIZE]
    if len(ph1_bytes) != PHENTSIZE or \
            struct.unpack(PH_FMT, ph1_bytes) != SEG1:
        raise ValueError("the original PH bytes do not decode to SEG1")
    ph_table = ph1_bytes + struct.pack(PH_FMT, *SEG2)
    pad = b"\0" * (PH_OFF - PRX_SIZE)
    payload = MARKER + b"\0" * (PAYLOAD_SIZE - len(MARKER))
    patched = bytearray(prx) + pad + ph_table + payload
    struct.pack_into("<I", patched, EL_PHOFF_FIELD, PH_OFF)
    struct.pack_into("<H", patched, EL_PHNUM_FIELD, 2)
    if len(patched) != NEW_SIZE:
        raise ValueError(f"built image is {len(patched)} bytes, expected {NEW_SIZE}")

    changed = [i for i in range(PRX_SIZE) if prx[i] != patched[i]]
    declared = {EL_PHOFF_FIELD, EL_PHOFF_FIELD + 1, EL_PHOFF_FIELD + 2,
                EL_PHNUM_FIELD}
    outside = sorted(set(changed) - declared)
    if outside:
        raise ValueError(f"bytes outside the declared header fields changed, first "
                         f"{outside[0]:#x}")
    if set(changed) != declared:
        raise ValueError(f"changed header bytes are {sorted(set(changed))}, "
                         f"expected {sorted(declared)}")
    expected_phoff = struct.pack("<I", PH_OFF)
    if bytes(patched[EL_PHOFF_FIELD:EL_PHOFF_FIELD + 4]) != expected_phoff:
        raise ValueError("e_phoff was not written correctly")
    if struct.unpack_from("<H", patched, EL_PHNUM_FIELD)[0] != 2:
        raise ValueError("e_phnum was not written correctly")

    return {"patched": bytes(patched), "ph1_bytes": ph1_bytes,
            "ph_table": ph_table, "pad": pad, "payload": payload,
            "changed_original": changed, "declared_original": sorted(declared),
            "append_range": (PRX_SIZE, NEW_SIZE), "ph_off": PH_OFF,
            "payload_off": PAYLOAD_OFF, "new_size": NEW_SIZE}


def verify_pair(pristine: bytes, patched: bytes) -> tuple[list[str], dict]:
    """Independent check of a patched file against the pinned pristine one."""
    fails: list[str] = []
    plan: dict = {}
    try:
        plan = build_patched(pristine)
    except ValueError as exc:
        return [str(exc)], plan
    if len(patched) != NEW_SIZE:
        fails.append(f"patched size is {len(patched)}, expected {NEW_SIZE}")
        return fails, plan
    if patched != plan["patched"]:
        i = next((k for k in range(NEW_SIZE) if patched[k] != plan["patched"][k]),
                 None)
        fails.append(f"patched image differs from the independently re-derived "
                     f"image at offset {i:#x}" if i is not None else
                     "patched image differs from the re-derived image")
        return fails, plan

    # diff against the pristine: original part only the two ELF fields
    changed = [i for i in range(PRX_SIZE) if pristine[i] != patched[i]]
    if set(changed) != set(plan["declared_original"]):
        fails.append(f"diff against the pristine is {[hex(x) for x in changed]}, "
                     f"expected only e_phoff/e_phnum {[hex(x) for x in plan['declared_original']]}")

    # appended range exact content
    if patched[PRX_SIZE:PH_OFF] != plan["pad"]:
        fails.append("the 0x16714a..0x167150 padding is not zero")
    if patched[PH_OFF:PAYLOAD_OFF] != plan["ph_table"]:
        fails.append("the appended PH table bytes are wrong")
    if patched[PAYLOAD_OFF:PAYLOAD_OFF + len(MARKER)] != MARKER:
        fails.append("the payload marker is wrong")
    if patched[PAYLOAD_OFF + len(MARKER):NEW_SIZE] != \
            b"\0" * (PAYLOAD_SIZE - len(MARKER)):
        fails.append("the payload tail is not zero")

    # re-parse the patched ELF
    try:
        hdr = parse_elf_header(patched)
    except ValueError as exc:
        fails.append(f"the patched file is not a valid ELF: {exc}")
        return fails, plan
    if (hdr.e_phoff, hdr.e_phnum, hdr.e_phentsize) != (PH_OFF, 2, PHENTSIZE):
        fails.append(f"patched header e_phoff {hdr.e_phoff:#x}/e_phnum "
                     f"{hdr.e_phnum}/e_phentsize {hdr.e_phentsize}, expected "
                     f"{PH_OFF:#x}/2/{PHENTSIZE}")
    phs = parse_ph(patched, hdr)
    if phs != [SEG1, SEG2]:
        fails.append(f"patched program headers decode to {phs}, expected "
                     f"[{SEG1}, {SEG2}]")
    else:
        ph1, ph2 = phs
        if not (ph2[2] >= ph1[2] + ph1[5]):
            fails.append(f"segments overlap in memory: seg2.vaddr {ph2[2]:#x} < "
                         f"seg1.vaddr+seg1.memsz {ph1[2] + ph1[5]:#x}")
        if not (ph2[1] >= ph1[1] + ph1[4] or ph1[1] >= ph2[1] + ph2[4]):
            fails.append("segments overlap in the file")

    # section header table and every section header unchanged
    if hdr.e_shoff != E_SHOFF:
        fails.append(f"e_shoff moved to {hdr.e_shoff:#x}, expected {E_SHOFF:#x}")
    sl = E_SHNUM * E_SHENTSIZE
    if patched[E_SHOFF:E_SHOFF + sl] != pristine[E_SHOFF:E_SHOFF + sl]:
        fails.append("the section header table bytes changed")
    if (hdr.e_shnum, hdr.e_shentsize) != (E_SHNUM, E_SHENTSIZE):
        fails.append(f"section count/entsize changed: {hdr.e_shnum}/"
                     f"{hdr.e_shentsize}")
    for s in parse_sections(patched, hdr):
        if s.offset + s.size > NEW_SIZE:
            fails.append(f"section {s.index} ({s.name}) ends at "
                         f"{s.offset + s.size:#x}, past EOF {NEW_SIZE:#x}")
    return fails, plan


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
    print(f"  payload  file {plan['payload_off']:#x}..{plan['payload_off'] + PAYLOAD_SIZE:#x} "
          f"(1200 B): {MARKER!r} + {PAYLOAD_SIZE - len(MARKER)} zero bytes")
    print(f"  pad      file {PRX_SIZE:#x}..{plan['ph_off']:#x} "
          f"({plan['ph_off'] - PRX_SIZE} zero bytes)")
    print(f"  size     {PRX_SIZE} -> {plan['new_size']} "
          f"(+{plan['new_size'] - PRX_SIZE} B, ISO allocation {ISO_PRX_ALLOC})")
    print(f"  untouched original bytes changed: "
          f"{[hex(x) for x in plan['declared_original']]} only")


# --------------------------------------------------------------------------- #
# subcommands
# --------------------------------------------------------------------------- #
def load_pristine(args) -> tuple[bytes, str]:
    if getattr(args, "prx", None):
        with open(args.prx, "rb") as f:
            return f.read(), args.prx
    src = getattr(args, "src", None) or DEFAULT_SRC_ISO
    if not os.path.exists(src):
        raise SystemExit(f"missing input ISO: {src}")
    return iso_replace.read_iso_file(src, PRX_IN_ISO), f"{src}:{PRX_IN_ISO}"


def cmd_patch(args) -> int:
    prx, source = load_pristine(args)
    print(f"pristine `{source}`: {len(prx)} bytes, sha256 {sha256(prx)}")
    print("--- preconditions")
    plan = build_patched(prx)
    print(f"    pinned pristine OK; appended layout reconstructs; declared diff "
          f"is exactly e_phoff/e_phnum")
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


def cmd_verify(args) -> int:
    with open(args.pristine, "rb") as f:
        pristine = f.read()
    with open(args.patched, "rb") as f:
        patched = f.read()
    print(f"pristine: {args.pristine} ({len(pristine)} bytes, sha256 "
          f"{sha256(pristine)})")
    print(f"patched : {args.patched} ({len(patched)} bytes, sha256 "
          f"{sha256(patched)})")
    fails, plan = verify_pair(pristine, patched)
    if fails:
        print(f"VERIFICATION FAILED ({len(fails)}):")
        for x in fails:
            print(f"  FAIL: {x}")
        return 1
    print("--- patch map")
    print_patch_map(plan)
    print("--- patched ELF read back")
    print_ph_table(patched, "patched")
    hdr = parse_elf_header(patched)
    print(f"  e_shoff {hdr.e_shoff:#x} (unchanged), section table "
          f"{E_SHOFF:#x}..{SECTION_TABLE_END:#x} byte-identical to the pristine")
    print("verification: OK - the patched file differs from the pristine only in "
          "e_phoff (3 byte values), e_phnum (1 byte value) and the appended range; "
          "the section header table and every section header are unchanged; the "
          "ELF re-parses with 2 non-overlapping PT_LOAD segments")
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
    fails, plan = verify_pair(pristine_prx, patched_prx)
    if fails:
        print(f"STOP: the patched module does not verify ({len(fails)}):")
        for x in fails:
            print(f"  FAIL: {x}")
        return 1
    print("    OK: only e_phoff/e_phnum plus the appended bytes differ; section "
          "table intact; 2 non-overlapping segments")

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
                                      patched_prx, label="EXP2")
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
    print(f"    {PRX_IN_ISO} read back equals the artifact; size {out_size} B "
          f"(unchanged); next module still at LBA {mgr_after}")
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

    c = sub.add_parser("patch", help="append the 2nd PH + payload into a .prx copy")
    common(c)
    c.add_argument("--out", default=DEFAULT_OUT_PRX)
    c.set_defaults(func=cmd_patch)

    v = sub.add_parser("verify", help="verify a patched .prx against the pristine")
    v.add_argument("--pristine", required=True)
    v.add_argument("--patched", required=True)
    v.set_defaults(func=cmd_verify)

    i = sub.add_parser("iso", help="build and verify the experiment ISO")
    i.add_argument("--src", default=DEFAULT_SRC_ISO)
    i.add_argument("--patched-prx", default=DEFAULT_OUT_PRX)
    i.add_argument("--out", default=DEFAULT_OUT_ISO)
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

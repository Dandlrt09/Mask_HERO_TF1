#!/usr/bin/env python3
"""E5 strategy C, copy 2: the product fix for the TF1 ULES00600 level reader.

Builds `trabajo/e5/TF1-E5-C2.iso` from the same Spanish base ISO that
`tools/e5_patch_iso.py` uses, containing:

  PSP_GAME/USRDIR/duelsys/cardinfo_spa.ehp = trabajo/e1spa/cardinfo_spa_E1.ehp
  PSP_GAME/SYSDIR/BOOT.BIN  = engine ELF with the E5-C2 level-reader patch
  PSP_GAME/SYSDIR/EBOOT.BIN = the same patched engine zero-padded to its
                              original ISO directory size (1104032 B)

The patch
=========

The deck editor's "Forbidden" verdict is produced by the exported wrapper at
VMA 0x478fc (file 0x4795c): it reads the 4-byte record the old `get_limit`
(0x3a43c) computes from `idx = CARD_IntID[CardID-4000]`, where byte 2 is the
level (0 Forbidden, 1 Limited, 2 Semi, 3 Unlimited).  An appended card lives in
an index whose record word was never initialised (all four bytes zero), so the
level reads 0.  The wrapper is rewritten in place (17 words, 0x478fc..0x4793f)
to return 3 when the record pointer is NULL or its whole word is zero, and
byte 2 otherwise.

The old exported `get_limit` body at 0x3a43c becomes dead code:

  * the exported address entry (NID 0xcda3b5c5, index 803, R_MIPS_32 in
    `.rel.rodata.sceResident` at VMA 0x6b6ac / file 0x6b70c) is repointed to
    0x478fc;
  * the two internal `jal 0x3a43c` callers (VMA 0x469cc, 0x46ab0) are
    retargeted to `jal 0x478fc`;
  * the wrapper's own R_MIPS_26 entry at 0x47918 (whose word becomes `nop`) is
    retargeted to 0x3a43c so the loader relocates a dead word instead of a live
    `nop`;
  * the wrapper words at 0x47908 and 0x47928 keep their R_MIPS_26 entries and
    hold the correct module-relative `jal 0x39e3c` / `j 0x47934`.

Nothing else changes: the setter (0x3a3dc), the ban tables and the old body's
own bytes are untouched.

Stdlib only.  Builds and independently verifies; logs under trabajo/e5/.
"""
from __future__ import annotations

import argparse
import os
import shutil
import struct
import sys
import tempfile

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
import ehp            # noqa: E402
import e1_patch_iso   # noqa: E402
import iso_replace    # noqa: E402
import tfcard         # noqa: E402

DEFAULT_SRC = e1_patch_iso.DEFAULT_SRC
DEFAULT_DST = "trabajo/e5/TF1-E5-C2.iso"
DEFAULT_EHP = "trabajo/e1spa/cardinfo_spa_E1.ehp"
DEFAULT_BOOT = "trabajo/e1c/BOOT.BIN"

LANG = "spa"
BOOT_PATH = "PSP_GAME/SYSDIR/BOOT.BIN"
EBOOT_PATH = "PSP_GAME/SYSDIR/EBOOT.BIN"
ELF_MAGIC = b"\x7fELF"

TEXT_FILE_BASE = 0x60              # .text VMA 0 == file 0x60

# --- the 17-word wrapper at VMA 0x478fc (file 0x4795c) ---------------------
WRAPPER_VMA = 0x478FC
WRAPPER_FILE = WRAPPER_VMA + TEXT_FILE_BASE          # 0x4795c
WRAPPER_OLD = (
    0x27BDFFF0,  # addiu sp,sp,-16
    0xAFBF000C,  # sw ra,12(sp)
    0xAFB00008,  # sw s0,8(sp)
    0x0C00E3AA,  # jal 0x38ea8
    0x00808021,  # move s0,a0
    0x50400005,  # beqzl v0,0x47928
    0x3204FFFF,  # andi a0,s0,0xffff
    0x0C00E939,  # jal 0x3a4e4 (scan)
    0x3204FFFF,  # andi a0,s0,0xffff
    0x10000004,  # b 0x47934
    0x8FBF000C,  # lw ra,12(sp)
    0x0C00E90F,  # jal 0x3a43c (old get_limit)
    0x00000000,  # nop
    0x8FBF000C,  # lw ra,12(sp)
    0x8FB00008,  # lw s0,8(sp)
    0x03E00008,  # jr ra
    0x27BD0010,  # addiu sp,sp,16
)
WRAPPER_NEW = (
    0x27BDFFF0,  # addiu sp,sp,-16
    0xAFBF000C,  # sw ra,12(sp)
    0x00000000,  # nop
    0x0C00E78F,  # jal 0x39e3c  (cardid -> record; relocated)
    0x3084FFFF,  # andi a0,a0,0xffff (delay slot)
    0x50400007,  # beqzl v0,0x47930
    0x00000000,  # nop (delay slot)
    0x00000000,  # nop (this word's relocation is retargeted away)
    0x8C430000,  # lw v1,0(v0)
    0x50600003,  # beqzl v1,0x47930
    0x90420002,  # lbu v0,2(v0) (delay slot)
    0x08011E4D,  # j 0x47934 (relocated)
    0x00000000,  # nop (delay slot)
    0x24020003,  # li v0,3
    0x8FBF000C,  # lw ra,12(sp)
    0x03E00008,  # jr ra
    0x27BD0010,  # addiu sp,sp,16 (delay slot)
)

# --- relocations -----------------------------------------------------------
RETARGET_FROM = 0x47918            # wrapper word whose R_MIPS_26 moves away
RETARGET_TO = 0x3A43C              # dead old get_limit body
EXPECTED_WRAPPER_RELOCS = {0x47908: 4, 0x47918: 4, 0x47928: 4}

# --- old get_limit ---------------------------------------------------------
OLD_GET_LIMIT_VMA = 0x3A43C
OLD_GET_LIMIT_WORDS = (
    0x27BDFFF0, 0xAFBF000C, 0x0C00E78F, 0x3084FFFF, 0x50400003, 0x24020003,
    0x90420002, 0x30420003, 0x8FBF000C, 0x03E00008, 0x27BD0010,
)

# --- export table ----------------------------------------------------------
NID_BASE_VMA = 0x696A0
ADDR_BASE_VMA = 0x6AA20
NID_COUNT = 1248
GET_LIMIT_NID = 0xCDA3B5C5
NID_INDEX_EXPECTED = 803
ADDR_ENTRY_VMA = 0x6B6AC
ADDR_ENTRY_FILE = ADDR_ENTRY_VMA + TEXT_FILE_BASE    # 0x6b70c
NEW_EXPORT_VMA = WRAPPER_VMA

# --- internal callers ------------------------------------------------------
CALLER_VMAS = (0x469CC, 0x46AB0)
JAL_OLD = 0x0C00E90F               # jal 0x3a43c
JAL_NEW = (3 << 26) | (WRAPPER_VMA >> 2)   # jal 0x478fc == 0x0c011e3f

# --- card database canaries ------------------------------------------------
APPENDED_INDEX = 2480
APPENDED_CARD_ID = 4661
APPENDED_ATK = 4900
CANARY_CARD_ID = 5759              # GAGAGIGO
CANARY_ATK = 4850
RECORD_WIDTH = {"CARD_Prop.bin": 8, "CARD_IntID.bin": 2, "CARD_Sort_S.bin": 2}


def file_off(vma: int) -> int:
    return vma + TEXT_FILE_BASE


def read_word(blob: bytes, vma: int) -> int:
    return struct.unpack_from("<I", blob, file_off(vma))[0]


def check(cond: bool, msg: str, failures: list[str]) -> None:
    print(f"    [{'OK' if cond else 'FAIL'}] {msg}")
    if not cond:
        failures.append(msg)


def iter_relocations(boot: bytes):
    """Yield (r_offset, r_info, entry_file_offset, section_name) for every
    relocation entry in the engine's `.rel.*` sections (stdlib ELF32 parse)."""
    if boot[:4] != ELF_MAGIC:
        raise ValueError("not an ELF")
    e_shoff = struct.unpack_from("<I", boot, 0x20)[0]
    e_shentsize = struct.unpack_from("<H", boot, 0x2E)[0]
    e_shnum = struct.unpack_from("<H", boot, 0x30)[0]
    e_shstrndx = struct.unpack_from("<H", boot, 0x32)[0]
    secs = [struct.unpack_from("<IIIIIIIIII", boot, e_shoff + i * e_shentsize)
            for i in range(e_shnum)]
    shstr = secs[e_shstrndx]

    def name_of(name_off: int) -> str:
        start = shstr[4] + name_off
        end = boot.index(b"\x00", start)
        return boot[start:end].decode("ascii", "replace")

    for sec in secs:
        name_off, _typ, _flags, _addr, off, size, _link, _info, _align, entsize = sec
        name = name_of(name_off)
        if not name.startswith(".rel"):
            continue
        if entsize not in (0, 8):
            raise ValueError(f"{name}: unexpected relocation entry size {entsize}")
        for j in range(size // 8):
            eo = off + j * 8
            ro, ri = struct.unpack_from("<II", boot, eo)
            yield ro, ri, eo, name


def inspect(boot: bytes) -> tuple[list[str], int | None]:
    """Re-derive every patch-critical fact.

    Returns the failures and, on success, the file offset of the relocation
    entry that must be retargeted from 0x47918 to 0x3a43c.
    """
    failures: list[str] = []
    print("--- 0. patch-critical facts (must all hold) ---")
    got = tuple(struct.unpack_from("<17I", boot, WRAPPER_FILE))
    check(got == WRAPPER_OLD,
          f"wrapper @VMA 0x{WRAPPER_VMA:x} (file 0x{WRAPPER_FILE:x}) is the "
          f"known original 17-word window", failures)

    relocs = list(iter_relocations(boot))
    wrapper_relocs = {ro: ri & 0xFF for ro, ri, _eo, _n in relocs
                      if WRAPPER_VMA <= ro < WRAPPER_VMA + 4 * len(WRAPPER_NEW)}
    retarget_hits = [(ro, ri, eo, n) for ro, ri, eo, n in relocs
                     if ro == RETARGET_FROM]
    targets_3a43c = [n for ro, _ri, _eo, n in relocs if ro == RETARGET_TO]
    check(wrapper_relocs == EXPECTED_WRAPPER_RELOCS,
          f"wrapper relocation entries {[hex(o) for o in sorted(wrapper_relocs)]} "
          f"types { {hex(o): t for o, t in sorted(wrapper_relocs.items())} } "
          f"== expected", failures)
    check(len(retarget_hits) == 1,
          f"exactly one relocation entry with r_offset==0x{RETARGET_FROM:x} "
          f"(got {len(retarget_hits)})", failures)
    check(targets_3a43c == [],
          f"no relocation entry already targets 0x{RETARGET_TO:x} "
          f"(hits: {targets_3a43c})", failures)

    # old get_limit body
    old_body = tuple(struct.unpack_from("<11I", boot, file_off(OLD_GET_LIMIT_VMA)))
    check(old_body == OLD_GET_LIMIT_WORDS,
          f"old get_limit @0x{OLD_GET_LIMIT_VMA:x} is the known 11-word body",
          failures)
    body_relocs = sorted({hex(ro) for ro, _ri, _eo, _n in relocs
                          if OLD_GET_LIMIT_VMA <= ro
                          < OLD_GET_LIMIT_VMA + 4 * len(OLD_GET_LIMIT_WORDS)})
    check(OLD_GET_LIMIT_VMA not in {ro for ro, _ri, _eo, _n in relocs},
          f"0x{OLD_GET_LIMIT_VMA:x} itself carries no relocation entry "
          f"(body relocs: {body_relocs})", failures)

    # export table
    nid_index = None
    for i in range(NID_COUNT):
        if read_word(boot, NID_BASE_VMA + i * 4) == GET_LIMIT_NID:
            nid_index = i
            break
    check(nid_index == NID_INDEX_EXPECTED,
          f"NID 0x{GET_LIMIT_NID:08x} sits at index {nid_index} "
          f"(expected {NID_INDEX_EXPECTED})", failures)
    if nid_index is not None:
        addr_vma = ADDR_BASE_VMA + nid_index * 4
        check(addr_vma == ADDR_ENTRY_VMA,
              f"address entry VMA 0x{addr_vma:x} == 0x{ADDR_ENTRY_VMA:x}",
              failures)
        check(read_word(boot, addr_vma) == OLD_GET_LIMIT_VMA,
              f"address entry value 0x{read_word(boot, addr_vma):x} == "
              f"0x{OLD_GET_LIMIT_VMA:x}", failures)
        addr_rel = sorted({ri & 0xFF for ro, ri, _eo, _n in relocs
                           if ro == addr_vma})
        check(addr_rel == [2],
              f"address entry carries an R_MIPS_32 relocation (got {addr_rel})",
              failures)

    # internal callers
    for vma in CALLER_VMAS:
        check(read_word(boot, vma) == JAL_OLD,
              f"0x{vma:x} holds jal 0x{OLD_GET_LIMIT_VMA:x} "
              f"(0x{read_word(boot, vma):08x})", failures)
        rel = sorted({ri & 0xFF for ro, ri, _eo, _n in relocs if ro == vma})
        check(rel == [4],
              f"0x{vma:x} carries an R_MIPS_26 relocation (got {rel})",
              failures)

    # no other live reference to the old body
    jal_word = struct.pack("<I", JAL_OLD)
    text = boot[TEXT_FILE_BASE:TEXT_FILE_BASE + 0x6894C]
    hits, start = [], 0
    while True:
        i = text.find(jal_word, start)
        if i < 0:
            break
        hits.append(i)
        start = i + 1
    check(sorted(hits) == sorted([0x469CC, 0x46AB0, 0x47928]),
          f"jal 0x{OLD_GET_LIMIT_VMA:x} sites are exactly the two callers and "
          f"the wrapper (got {[hex(h) for h in hits]})", failures)

    if failures or not retarget_hits:
        return failures, None
    ro, _ri, eo, name = retarget_hits[0]
    print(f"    [info] retarget entry @file 0x{eo:x} in {name}: "
          f"r_offset 0x{ro:x} -> 0x{RETARGET_TO:x}")
    return failures, eo


def patch_engine(boot: bytes, retarget_entry: int) -> bytes:
    """Return a copy of the engine with the E5-C2 fix applied."""
    failures, _ = inspect(boot)
    if failures:
        raise ValueError("patch-critical facts do not hold:\n  " +
                         "\n  ".join(failures))
    out = bytearray(boot)
    for i, w in enumerate(WRAPPER_NEW):
        struct.pack_into("<I", out, WRAPPER_FILE + i * 4, w)
    ro, ri = struct.unpack_from("<II", out, retarget_entry)
    assert ro == RETARGET_FROM, (hex(ro), hex(RETARGET_FROM))
    struct.pack_into("<II", out, retarget_entry, RETARGET_TO, ri)
    struct.pack_into("<I", out, ADDR_ENTRY_FILE, NEW_EXPORT_VMA)
    for vma in CALLER_VMAS:
        struct.pack_into("<I", out, file_off(vma), JAL_NEW)
    return bytes(out)


def expected_diff(boot: bytes, patched: bytes, retarget_entry: int) -> set[int]:
    """Every file offset the patch is allowed to change."""
    allowed: set[int] = set()
    ranges = [range(WRAPPER_FILE, WRAPPER_FILE + 4 * len(WRAPPER_NEW)),
              range(retarget_entry, retarget_entry + 4),
              range(ADDR_ENTRY_FILE, ADDR_ENTRY_FILE + 4)]
    ranges += [range(file_off(v), file_off(v) + 4) for v in CALLER_VMAS]
    for rng in ranges:
        for off in rng:
            if boot[off] != patched[off]:
                allowed.add(off)
    return allowed


def build(src: str, dst: str, ehp_src: str, boot_src: str) -> int:
    failures: list[str] = []
    ehp_iso_path, _ = e1_patch_iso.lang_paths(LANG)
    print(f"--- source ISO: {src}")
    print(f"--- language:   {LANG} -> {ehp_iso_path}")

    print(f"--- 1. card database: {ehp_src} -> {dst}")
    new_ehp = open(ehp_src, "rb").read()
    rep = iso_replace.replace_file(src, dst, ehp_iso_path, new_ehp,
                                   label=os.path.basename(ehp_iso_path))
    for k, v in rep.items():
        print(f"    {k}: {v}")
    if not rep["roundtrip"]:
        print("ROUND TRIP MISMATCH after replacing the EHP")
        return 1

    boot = open(boot_src, "rb").read()
    if boot[:4] != ELF_MAGIC:
        raise ValueError(f"{boot_src}: not an ELF ({boot[:4].hex()})")
    fact_failures, retarget_entry = inspect(boot)
    if fact_failures or retarget_entry is None:
        print(f"\nSTOP: patch-critical facts do not hold ({len(fact_failures)}):")
        for f in fact_failures:
            print(f"  FAIL: {f}")
        print("Refusing to build an ISO, per the task's stop rule.")
        return 1

    patched = patch_engine(boot, retarget_entry)
    allowed = expected_diff(boot, patched, retarget_entry)
    print(f"--- 2. engine patch: {len(allowed)} file bytes differ from the artifact")

    print(f"--- 3. engine: pad the patched BOOT.BIN over EBOOT.BIN ---")
    iso_boot = iso_replace.patch_bytes(dst, BOOT_PATH, 0, patched)
    print(f"    {BOOT_PATH}: written {len(patched)} bytes, roundtrip={iso_boot['roundtrip']}")

    from iso9660 import Iso9660
    iso = Iso9660(src)
    try:
        eboot_entry = iso.resolve(EBOOT_PATH)
        boot_entry = iso.resolve(BOOT_PATH)
    finally:
        iso.close()
    boot_original_size, eboot_original_size = boot_entry.size, eboot_entry.size
    if boot_original_size != len(boot):
        raise ValueError(f"{BOOT_PATH}: ISO has {boot_original_size} bytes, "
                         f"artifact has {len(boot)}")
    if eboot_original_size < len(patched):
        raise ValueError(f"{EBOOT_PATH}: {len(patched)} bytes does not fit "
                         f"{eboot_original_size}")
    boot_padded = patched + b"\x00" * (eboot_original_size - len(patched))
    iso_eboot = iso_replace.patch_bytes(dst, EBOOT_PATH, 0, boot_padded)
    print(f"    {EBOOT_PATH}: original size {eboot_original_size} bytes, "
          f"written padded engine {len(boot_padded)} bytes, "
          f"roundtrip={iso_eboot['roundtrip']}")

    print("--- 4. readback verification (independent reader) ---")
    errs = verify(dst, boot, patched, allowed, retarget_entry,
                  boot_original_size, eboot_original_size)
    failures.extend(errs)
    if failures:
        print(f"\nVERIFICATION FAILED ({len(failures)} check(s)):")
        for f in failures:
            print(f"  FAIL: {f}")
        return 1
    print(f"\nOK -> {dst}")
    return 0


def verify(dst: str, boot: bytes, patched: bytes, allowed: set[int],
           retarget_entry: int, boot_size: int, eboot_size: int) -> list[str]:
    failures: list[str] = []
    iso_boot = iso_replace.read_iso_file(dst, BOOT_PATH)
    iso_eboot = iso_replace.read_iso_file(dst, EBOOT_PATH)

    check(iso_boot[:4] == ELF_MAGIC, f"{BOOT_PATH} starts with 7f 45 4c 46", failures)
    check(iso_eboot[:4] == ELF_MAGIC, f"{EBOOT_PATH} starts with 7f 45 4c 46", failures)
    check(len(iso_boot) == boot_size,
          f"{BOOT_PATH} size {len(iso_boot)} == original {boot_size}", failures)
    check(len(iso_eboot) == eboot_size,
          f"{EBOOT_PATH} size {len(iso_eboot)} == original ISO directory size "
          f"{eboot_size}", failures)
    check(iso_boot == patched, f"{BOOT_PATH} equals the patched engine", failures)
    check(iso_eboot == patched + b"\x00" * (eboot_size - len(patched)),
          f"{EBOOT_PATH} equals the patched engine zero-padded", failures)

    # the 17 wrapper words, from BOOT and EBOOT
    print("    wrapper words read back:")
    for label, blob in (("BOOT.BIN ", iso_boot), ("EBOOT.BIN", iso_eboot)):
        words = struct.unpack_from("<17I", blob, WRAPPER_FILE)
        for i in range(0, 17, 4):
            chunk = " ".join(f"0x{w:08x}" for w in words[i:i + 4])
            print(f"      {label} 0x{WRAPPER_VMA + i * 4:05x}: {chunk}")
        check(words == WRAPPER_NEW,
              f"{label.strip()} wrapper == the prescribed 17 words", failures)

    # the retargeted export word
    nid_word = struct.unpack_from("<I", iso_boot, ADDR_ENTRY_FILE)[0]
    print(f"    export address @VMA 0x{ADDR_ENTRY_VMA:x} "
          f"(file 0x{ADDR_ENTRY_FILE:x}) = 0x{nid_word:08x}")
    check(nid_word == WRAPPER_VMA,
          f"export address == 0x{WRAPPER_VMA:x}", failures)

    # the retargeted relocation entry
    old_ro, old_ri = struct.unpack_from("<II", boot, retarget_entry)
    ro, ri = struct.unpack_from("<II", iso_boot, retarget_entry)
    print(f"    relocation entry @file 0x{retarget_entry:x}: "
          f"r_offset 0x{old_ro:x} -> 0x{ro:x}, type={ri & 0xFF} sym={ri >> 8}")
    check(ro == RETARGET_TO and (ri & 0xFF) == 4,
          f"relocation retargeted to 0x{RETARGET_TO:x} (type 4)", failures)

    # the two internal jals
    for vma in CALLER_VMAS:
        word = read_word(iso_boot, vma)
        print(f"    caller 0x{vma:x} @file 0x{file_off(vma):x}: "
              f"0x{JAL_OLD:08x} -> 0x{word:08x}")
        check(word == JAL_NEW, f"0x{vma:x} == jal 0x{WRAPPER_VMA:x}", failures)

    # exact byte diff against the source artifact
    diffs = [i for i in range(len(boot)) if boot[i] != iso_boot[i]]
    extra = [i for i in diffs if i not in allowed]
    missing = [i for i in allowed if i not in diffs]
    print(f"    BOOT.BIN differs from {DEFAULT_BOOT} at {len(diffs)} byte "
          f"offsets; allowed {len(allowed)}")
    check(diffs == sorted(allowed),
          "the byte differences are exactly the wrapper words (minus the "
          "unchanged ones), the relocation entry, the export word and the two "
          "jals", failures)
    for i in range(0, len(diffs), 8):
        print("      diff: " + " ".join(f"0x{o:x}" for o in diffs[i:i + 8]))
    if extra:
        print(f"      UNEXPECTED: {[hex(o) for o in extra]}")
    if missing:
        print(f"      MISSING:    {[hex(o) for o in missing]}")

    # word-level old -> new report
    print("    word-level changes (BOOT.BIN):")
    base = boot
    for i in range(17):
        off = WRAPPER_FILE + i * 4
        o = struct.unpack_from("<I", base, off)[0]
        n = struct.unpack_from("<I", iso_boot, off)[0]
        if o != n:
            print(f"      0x{WRAPPER_VMA + i * 4:05x} (file 0x{off:x}): "
                  f"0x{o:08x} -> 0x{n:08x}")

    # --- card database ------------------------------------------------------
    data = iso_replace.read_iso_file(dst, e1_patch_iso.lang_paths(LANG)[0])
    parsed = ehp.parse(data)
    meta = parsed["meta"]
    files = parsed["files"]
    print(f"    {e1_patch_iso.lang_paths(LANG)[0]}: version={meta['version']} "
          f"marker={meta['marker']!r} count={meta['count']} "
          f"total={meta['declared_total']} (actual {meta['actual_total']})")
    check(meta["declared_total"] == len(data), "EHP declared total == actual size",
          failures)
    for name in meta["order"]:
        n = len(files[name])
        width = RECORD_WIDTH.get(name)
        extra = f"  ({n // width} records of {width} B)" if width and n % width == 0 else ""
        print(f"      {n:>10}  {name}{extra}")

    tmp = tempfile.mkdtemp(prefix="e5_c2_verify_")
    try:
        for name, blob in files.items():
            with open(os.path.join(tmp, name), "wb") as out:
                out.write(blob)
        ci = tfcard.CardInfo(tmp, "_S")
        c = ci.get_by_index(APPENDED_INDEX)
        print(f"    internal index {APPENDED_INDEX}: card_id={c.card_id} "
              f"atk={c.atk} def={c.dfn} level={c.level} exist={c.exist} "
              f"name={c.name!r}")
        check(c.card_id == APPENDED_CARD_ID and c.atk == APPENDED_ATK,
              f"appended record index {APPENDED_INDEX} is CardID "
              f"{APPENDED_CARD_ID} ATK {APPENDED_ATK}", failures)
        g = ci.get(CANARY_CARD_ID)
        print(f"    canary GAGAGIGO {CANARY_CARD_ID}: internal index "
              f"{ci.internal_id(CANARY_CARD_ID)}, ATK {g.atk}, DEF {g.dfn}")
        check(g.atk == CANARY_ATK,
              f"GAGAGIGO {CANARY_CARD_ID} ATK == {CANARY_ATK}", failures)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    return failures


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--src", default=DEFAULT_SRC, help="source ISO (read only)")
    ap.add_argument("--dst", default=DEFAULT_DST, help="output ISO (a copy)")
    ap.add_argument("--ehp", default=DEFAULT_EHP, help="E1 card database artifact")
    ap.add_argument("--boot", default=DEFAULT_BOOT, help="unpatched engine ELF artifact")
    args = ap.parse_args(argv[1:])
    for path in (args.src, args.ehp, args.boot):
        if not os.path.exists(path):
            raise SystemExit(f"missing input: {path}")
    os.makedirs(os.path.dirname(os.path.abspath(args.dst)), exist_ok=True)
    return build(args.src, args.dst, args.ehp, args.boot)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

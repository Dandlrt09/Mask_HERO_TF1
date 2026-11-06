#!/usr/bin/env python3
"""E5 strategy C, copy 1: build a test ISO with a patched engine + E1 card data.

Everything happens on a COPY (`--dst`); the source ISO is only ever read.

  1. copy the source ISO to `--dst` and replace the Spanish card database
     (PSP_GAME/USRDIR/duelsys/cardinfo_spa.ehp) with the already-built E1
     artifact `trabajo/e1spa/cardinfo_spa_E1.ehp`. That container holds the
     appended record at internal index 2480 and repoints IntID[4453] -> 2480,
     which is what makes the new record observable in the deck editor.
  2. in-place patch of PSP_GAME/SYSDIR/BOOT.BIN (the unencrypted engine ELF),
     overwriting the two words of `get_limit`:
       VMA 0x3a454 / file 0x3a4b4:  02 00 42 90  (lbu v0,2(v0))  -> 03 00 02 24 (li v0,3)
       VMA 0x3a458 / file 0x3a4b8:  03 00 42 30  (andi v0,v0,3)  -> 00 00 00 00 (nop)
     so `get_limit(cardid)` always returns 3 (Unlimited). This is a deliberate
     diagnostic that temporarily disables the ban list; its visible canary is
     that cards known to be Forbidden become useable in a deck.
  3. PSP_GAME/SYSDIR/EBOOT.BIN (the same module encrypted, 1104032 bytes) is
     overwritten with the patched BOOT.BIN (1103694 bytes) zero-padded to the
     original EBOOT.BIN size, so any loader path gets the patched engine while
     the ISO directory record size stays valid. The `~PSP` bytes are not
     touched/decrypted.
  4. offline verification re-opens the produced image and checks step 2/3 and
     the card database contents (see `verify`).

Stdlib only (the EHP/CardInfo helpers under tools/ are local, also stdlib).
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
import ehp          # noqa: E402
import e1_patch_iso  # noqa: E402  (language -> ISO paths, source ISO default)
import iso_replace  # noqa: E402
import tfcard       # noqa: E402

DEFAULT_SRC = e1_patch_iso.DEFAULT_SRC
DEFAULT_DST = "trabajo/e5/TF1-E5-C1.iso"
DEFAULT_EHP = "trabajo/e1spa/cardinfo_spa_E1.ehp"
DEFAULT_BOOT = "trabajo/e1c/BOOT.BIN"

LANG = "spa"
BOOT_PATH = "PSP_GAME/SYSDIR/BOOT.BIN"
EBOOT_PATH = "PSP_GAME/SYSDIR/EBOOT.BIN"
ELF_MAGIC = b"\x7fELF"

# The two words to overwrite, at the file offsets the parent task fixed.
WORD_OFFSETS = (0x3A4B4, 0x3A4B8)
WORD_OLD = (bytes.fromhex("02004290"), bytes.fromhex("03004230"))
WORD_NEW = (bytes.fromhex("03000224"), bytes.fromhex("00000000"))

# CARD_IntID is a table of uint16 indexed by (CardID - CARD_ID_BASE); the other
# arrays are indexed by internal index.
INTID_SLOTS = {"4661-4000": 4661, "4453-4000": 4453}
CANARY_CARD_ID = 5759  # GAGAGIGO
PROBE_INDICES = (2479, 2480, 2481)
RECORD_WIDTH = {"CARD_Prop.bin": 8, "CARD_IntID.bin": 2, "CARD_Sort_S.bin": 2}


def patch_boot_words(boot: bytes) -> bytes:
    """Return `boot` with the two `get_limit` words replaced (size unchanged)."""
    for off, old, new in zip(WORD_OFFSETS, WORD_OLD, WORD_NEW):
        found = boot[off:off + len(old)]
        if found != old:
            raise ValueError(
                f"BOOT.BIN+0x{off:x}: expected {old.hex()}, found {found.hex()} "
                "(refusing to patch an unexpected engine)")
    out = bytearray(boot)
    for off, new in zip(WORD_OFFSETS, WORD_NEW):
        out[off:off + len(new)] = new
    return bytes(out)


def build(src: str, dst: str, ehp_src: str, boot_src: str) -> int:
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

    print(f"--- 2/3. engine: pad the patched BOOT.BIN over EBOOT.BIN ---")
    boot = open(boot_src, "rb").read()
    if boot[:4] != ELF_MAGIC:
        raise ValueError(f"{boot_src}: not an ELF ({boot[:4].hex()})")
    boot_patched = patch_boot_words(boot)
    print(f"    {BOOT_PATH}: {len(boot)} bytes, patched {WORD_OLD[0].hex()}->{WORD_NEW[0].hex()}, "
          f"{WORD_OLD[1].hex()}->{WORD_NEW[1].hex()}")

    iso_boot = iso_replace.patch_bytes(dst, BOOT_PATH, 0, boot_patched)
    print(f"    {BOOT_PATH}: written {len(boot_patched)} bytes, roundtrip={iso_boot['roundtrip']}")

    # EBOOT.BIN must stay the same directory size: pad the patched engine.
    from iso9660 import Iso9660
    iso = Iso9660(src)
    try:
        eboot_entry = iso.resolve(EBOOT_PATH)
        boot_entry = iso.resolve(BOOT_PATH)
    finally:
        iso.close()
    boot_original_size, eboot_original_size = boot_entry.size, eboot_entry.size
    if boot_original_size != len(boot):
        raise ValueError(f"{BOOT_PATH}: ISO has {boot_original_size} bytes, artifact has {len(boot)}")
    if eboot_original_size < len(boot_patched):
        raise ValueError(f"{EBOOT_PATH}: {len(boot_patched)} bytes does not fit {eboot_original_size}")
    boot_padded = boot_patched + b"\x00" * (eboot_original_size - len(boot_patched))
    iso_eboot = iso_replace.patch_bytes(dst, EBOOT_PATH, 0, boot_padded)
    print(f"    {EBOOT_PATH}: original size {eboot_original_size} bytes, "
          f"written padded engine {len(boot_padded)} bytes, roundtrip={iso_eboot['roundtrip']}")

    print("--- 4. readback verification ---")
    failures = verify(dst, boot_original_size, eboot_original_size, boot_patched)
    if failures:
        print(f"\nVERIFICATION FAILED ({len(failures)} check(s)):")
        for f in failures:
            print(f"  FAIL: {f}")
        return 1
    print(f"\nOK -> {dst}")
    return 0


def verify(dst: str, boot_size: int, eboot_size: int, boot_patched: bytes) -> list[str]:
    failures: list[str] = []

    def check(cond: bool, msg: str) -> None:
        print(f"    [{'OK' if cond else 'FAIL'}] {msg}")
        if not cond:
            failures.append(msg)

    iso_boot = iso_replace.read_iso_file(dst, BOOT_PATH)
    iso_eboot = iso_replace.read_iso_file(dst, EBOOT_PATH)

    check(iso_boot[:4] == ELF_MAGIC, f"{BOOT_PATH} starts with 7f 45 4c 46")
    check(iso_eboot[:4] == ELF_MAGIC, f"{EBOOT_PATH} starts with 7f 45 4c 46")
    check(len(iso_boot) == boot_size,
          f"{BOOT_PATH} size {len(iso_boot)} == original {boot_size}")
    check(len(iso_eboot) == eboot_size,
          f"{EBOOT_PATH} size {len(iso_eboot)} == original ISO directory size {eboot_size}")
    check(iso_boot == boot_patched,
          f"{BOOT_PATH} equals the patched engine artifact")
    check(iso_eboot == boot_patched + b"\x00" * (eboot_size - len(boot_patched)),
          f"{EBOOT_PATH} equals the patched engine artifact zero-padded")

    for off, new in zip(WORD_OFFSETS, WORD_NEW):
        check(iso_boot[off:off + 4] == new,
              f"{BOOT_PATH}+0x{off:x} == {new.hex()}")
        check(iso_eboot[off:off + 4] == new,
              f"{EBOOT_PATH}+0x{off:x} == {new.hex()}")

    print(f"    patched words read back from the ISO:")
    for label, blob in (("BOOT.BIN", iso_boot), ("EBOOT.BIN", iso_eboot)):
        print(f"      {label} @0x{WORD_OFFSETS[0]:x} = {blob[WORD_OFFSETS[0]:WORD_OFFSETS[0] + 4].hex()}  "
              f"@0x{WORD_OFFSETS[1]:x} = {blob[WORD_OFFSETS[1]:WORD_OFFSETS[1] + 4].hex()}")

    # --- card database ------------------------------------------------------
    ehp_iso_path, _ = e1_patch_iso.lang_paths(LANG)
    data = iso_replace.read_iso_file(dst, ehp_iso_path)
    parsed = ehp.parse(data)
    meta = parsed["meta"]
    files = parsed["files"]
    print(f"    {ehp_iso_path}: version={meta['version']} marker={meta['marker']!r} "
          f"count={meta['count']} total={meta['declared_total']} (actual {meta['actual_total']})")
    check(meta["declared_total"] == len(data), "EHP declared total == actual size")
    for name in meta["order"]:
        n = len(files[name])
        width = RECORD_WIDTH.get(name)
        extra = f"  ({n // width} records of {width} B)" if width and n % width == 0 else ""
        print(f"      {n:>10}  {name}{extra}")

    for name, width in RECORD_WIDTH.items():
        if name not in files:
            check(False, f"{name} present in the container")
            continue
        n = len(files[name])
        check(n % width == 0, f"{name}: {n} bytes is a whole number of {width}-byte records")
        print(f"    record count {name}: {n // width}")

    # --- per-index records, via tools/tfcard.py -----------------------------
    tmp = tempfile.mkdtemp(prefix="e5_verify_")
    try:
        for name, blob in files.items():
            with open(os.path.join(tmp, name), "wb") as out:
                out.write(blob)
        ci = tfcard.CardInfo(tmp, "_S")
        print(f"    CardInfo: {ci.count} internal indices "
              f"(0..{ci.count - 1}), IntID entries {len(ci.intid) // 2}")
        for i in PROBE_INDICES:
            if i >= ci.count:
                print(f"    internal index {i}: no CARD_Prop record (out of range 0..{ci.count - 1})")
                continue
            c = ci.get_by_index(i)
            print(f"    internal index {i}: card_id={c.card_id} atk={c.atk} def={c.dfn} "
                  f"level={c.level} exist={c.exist} name={c.name!r}")

        for label, cid in INTID_SLOTS.items():
            idx = ci.internal_id(cid)
            n = len(ci.intid) // 2
            kind = "zero" if idx == 0 else f"real index {idx}"
            print(f"    CARD_IntID.bin[{label}] = {idx} ({kind}; {n} u16 entries)")
            check(0 <= idx < n, f"CARD_IntID[{label}] = {idx} is inside the table")

        g = ci.get(CANARY_CARD_ID)
        expected = 4850
        print(f"    canary GAGAGIGO {CANARY_CARD_ID}: internal index {ci.internal_id(CANARY_CARD_ID)}, "
              f"ATK {g.atk} (expected {expected} if the E1 canary is present), DEF {g.dfn}")
        check(g.atk == expected, f"GAGAGIGO {CANARY_CARD_ID} ATK == {expected}")
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
    dst_dir = os.path.dirname(os.path.abspath(args.dst))
    os.makedirs(dst_dir, exist_ok=True)
    return build(args.src, args.dst, args.ehp, args.boot)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

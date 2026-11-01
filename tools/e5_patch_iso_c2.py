#!/usr/bin/env python3
"""E5 strategy C, copy 2 -- product level-reader patch (BLOCKED by code space).

Intended product rule
---------------------
Make the level reader return 3 (Unlimited) when the record's whole 4-byte word
is zero (a slot no save/ban data ever initialised, i.e. an appended card), and
otherwise behave exactly as before: `level = byte2 & 3`, or 3 when the record
pointer is NULL.  The real ban list must stay intact.

This script was meant to build `trabajo/e5/TF1-E5-C2.iso` by rewriting the
exported wrapper at VMA 0x478fc (file 0x4795c) and retargeting the exported
`get_limit` NID + every internal `jal 0x3a43c` to it.

What the script does instead
----------------------------
It verifies, from `trabajo/e1c/BOOT.BIN`, every fact the patch relies on and
then prints why the prescribed rewrite cannot be assembled inside the wrapper's
17-word window.  It exits non-zero without touching any ISO, because the task's
own rule says to STOP when the window size blocks the change.

Run:  python3 tools/e5_patch_iso_c2.py
"""
from __future__ import annotations

import os
import struct
import sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOLS)
DEFAULT_BOOT = os.path.join(ROOT, "trabajo", "e1c", "BOOT.BIN")

TEXT_FILE_BASE = 0x60           # .text VMA 0 == file 0x60
WRAPPER_VMA = 0x478FC
WRAPPER_WORDS = 17              # 0x478fc..0x4793f inclusive
EPILOGUE_VMA = 0x47934
REL_TEXT_OFF, REL_TEXT_SIZE = 0xEBAAC, 0x1CD00

NID_BASE_VMA = 0x696A0          # .rodata.sceResident NID array
ADDR_BASE_VMA = 0x6AA20         # parallel export-address array
NID_COUNT = 1248
GET_LIMIT_NID = 0xCDA3B5C5
OLD_GET_LIMIT_VMA = 0x3A43C

EXPECTED_WRAPPER = bytes.fromhex(
    "f0ffbd27" "0c00bfaf" "0800b0af" "aae3000c" "21808000" "05004050"
    "ffff0432" "39e9000c" "ffff0432" "04000010" "0c00bf8f" "0fe9000c"
    "00000000" "0c00bf8f" "0800b08f" "0800e003" "1000bd27")


def file_off(vma: int) -> int:
    return vma + TEXT_FILE_BASE


def read_word(boot: bytes, vma: int) -> int:
    return struct.unpack_from("<I", boot, file_off(vma))[0]


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BOOT
    boot = open(path, "rb").read()
    print(f"engine: {path} ({len(boot)} bytes)")

    # --- ELF sanity --------------------------------------------------------
    if boot[:4] != b"\x7fELF" or boot[4] != 1 or boot[5] != 1:
        print("not a 32-bit little-endian ELF")
        return 2
    print("ELF 32-bit LE: OK")

    # --- wrapper bytes -----------------------------------------------------
    got = boot[file_off(WRAPPER_VMA):file_off(WRAPPER_VMA) + WRAPPER_WORDS * 4]
    print(f"wrapper @VMA 0x{WRAPPER_VMA:x} (file 0x{file_off(WRAPPER_VMA):x}): "
          f"{'matches original' if got == EXPECTED_WRAPPER else 'UNEXPECTED BYTES'}")
    for i, w in enumerate(struct.unpack_from("<" + "I" * WRAPPER_WORDS, got)):
        print(f"  0x{WRAPPER_VMA + i * 4:05x}: 0x{w:08x}")

    # --- relocation slots in the window -----------------------------------
    relocs = []
    for i in range(REL_TEXT_SIZE // 8):
        ro, ri = struct.unpack_from("<II", boot, REL_TEXT_OFF + i * 8)
        if WRAPPER_VMA <= ro < WRAPPER_VMA + WRAPPER_WORDS * 4:
            relocs.append((ro, ri & 0xFF, ri >> 8))
    print(f"relocation entries inside the wrapper window: "
          f"{[(hex(o), t) for o, t, _ in relocs]}")

    # --- exported get_limit NID + address entry ---------------------------
    idx = None
    for i in range(NID_COUNT):
        if read_word(boot, NID_BASE_VMA + i * 4) == GET_LIMIT_NID:
            idx = i
            break
    if idx is None:
        print("get_limit NID not found")
        return 2
    addr_vma = ADDR_BASE_VMA + idx * 4
    print(f"NID 0x{GET_LIMIT_NID:08x} -> index {idx}; "
          f"address entry VMA 0x{addr_vma:x} (file 0x{file_off(addr_vma):x}) = "
          f"0x{read_word(boot, addr_vma):x}")

    # --- internal jal 0x3a43c ---------------------------------------------
    jal_word = (3 << 26) | (OLD_GET_LIMIT_VMA >> 2)
    jb = struct.pack("<I", jal_word)
    text = boot[TEXT_FILE_BASE:TEXT_FILE_BASE + 0x6894C]
    hits, s = [], 0
    while True:
        i = text.find(jb, s)
        if i < 0:
            break
        hits.append(i)
        s = i + 1
    print(f"internal 'jal 0x{OLD_GET_LIMIT_VMA:x}' sites: "
          f"{[hex(h) for h in hits]}")

    # --- why the prescribed rewrite does not fit --------------------------
    print()
    print("=" * 72)
    print("BLOCKED: the wrapper window is too small for the prescribed logic")
    print("=" * 72)
    print(
        "The wrapper is exactly 17 words (0x478fc..0x4793f) and the function\n"
        "at 0x47940 is a live exported function (NID 0xab8bd7ca, index 1034,\n"
        "called from 0x55920), so the window cannot grow.\n"
        "\n"
        "With the prescribed layout the three relocated slots are used by\n"
        "get_flag (0x47908), scan (0x47918) and cardid_to_rec (0x47928), and\n"
        "the epilogue must stay at 0x47934..0x4793f.  The cardid_to_rec path\n"
        "(flag == 0) therefore has only\n"
        "  0x4792c (the jal delay slot) and 0x47930 (~1 usable word)\n"
        "before the epilogue.  The prescribed checks\n"
        "  if (v0 == 0) return 3; w = lw v0; if (w == 0) return 3;\n"
        "  else return (w >> 16) & 3\n"
        "need, at the very least, two conditional branches with their delay\n"
        "slots, the word load, the shift, the mask and two 'return 3' sites,\n"
        "i.e. >= 6-10 words of straight-line code plus its own return plumbing.\n"
        "\n"
        "Placing cardid_to_rec at 0x47918 instead would still collide with the\n"
        "mandated scan jal at 0x47928, and even the shortest correct layout\n"
        "(flag dispatch + scan + rec + null/zero/level checks + epilogue) needs\n"
        "~24 words; a wrapper with the flag/scan path removed entirely still\n"
        "needs 16 words for the rec rule alone.\n"
        "\n"
        "The old get_limit body (0x3a43c..0x3a467, 11 words) is also too small\n"
        "to host the rule (it must call cardid_to_rec and therefore save/restore\n"
        "ra); using it would additionally violate 'leave the old get_limit code\n"
        "untouched'.\n"
        "\n"
        "Per the task rule, no alternative semantic was improvised and no ISO\n"
        "was written.\n")
    return 3


if __name__ == "__main__":
    raise SystemExit(main())

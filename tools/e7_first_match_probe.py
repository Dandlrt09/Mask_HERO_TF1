#!/usr/bin/env python3
"""E7/F4 regression probe: pin the engine's first-match fusion semantics and the
F4 artifact shape.

MANUAL battery, deliberately NOT a framework test: it reads the gitignored
binaries in `trabajo/` (the 800 MB ISOs and the `.prx`), so it cannot run in a
clean clone.  Run from the repo root:

    python3 tools/e7_first_match_probe.py

It is READ-ONLY -- every artifact is opened in binary mode and nothing is
written -- and it uses only the Python standard library; it does NOT import
`tools/e7_fusion.py`.

What it pins (ESTADO-E7.md L15/L16):

  * the pristine sha256 and the pristine finder words: `lui a1,0x11` (file
    0xa04b4), `addiu a1,a1,0xacb4` -> base VMA 0x10acb4 (file 0xa04c0) and the
    bound `sltiu a2,v0,0x5e` -> 94 records (file 0xa04dc);
  * the F4 `.prx` (1471712 B, sha256 pinned): the 6 patched words (finder base,
    `sltiu` = 105, and the four table-end pointers), plus `e_phoff`/`e_phnum`;
  * the caller census over the scanned `.text` range (file 0x60..0x60+0xfa218):
    the finder at VMA 0xa0454 has EXACTLY two `jal` callers (VMA 0xa055c and
    0xa05e4, both result-keyed), none into its interior, and the pristine domain
    word `0x2cc2005e` occurs EXACTLY once;
  * a first-match scan over the F4 table at file 0x167190: 105 records, the
    `(10,0,0,0)` terminator, EXACTLY ONE record per result (the property that
    makes every recipe reachable), and the new results resolving as expected
    (4673 -> (4673, 6312, 4704, 0); 4696 -> (4696, 4697, 4701, 0)).

Prints one final `OK: ...` line and exits non-zero on any failure.
"""
import hashlib
import os
import struct
import sys

PRISTINE = "trabajo/e1c/gm/libduel_eng.prx"
PATCHED = "trabajo/e7/libduel_eng_f4.prx"

PRISTINE_SIZE = 1470794
PRISTINE_SHA = "6867fb17d48479a429cb71b660daa7ebb8e4be90e0a63c2f4c619ceaa54bcf91"
PATCHED_SIZE = 1471712
PATCHED_SHA = "c2873ad9680e66d07d2fbda51b858d0affc783db868e4810e11e661a330aa650"

FILE_DELTA = 0x60                      # file = VMA + 0x60
TEXT_LO = 0x60
TEXT_HI = 0x60 + 0xFA218               # the `.text` scan range used earlier

FINDER_VMA = 0xA0454
FINDER_INTERIOR = range(0xA0458, 0xA0494)   # after the entry, before the next fn
# file offset -> pristine word
FINDER_WORDS = (
    (0xA04B4, 0x3C050011, "lui a1, 0x11"),
    (0xA04C0, 0x24A5ACB4, "addiu a1, a1, 0xacb4 (base VMA 0x10acb4)"),
    (0xA04DC, 0x2CC2005E, "sltiu a2, v0, 0x5e (bound 94 records)"),
)
BOUND_WORD = 0x2CC2005E
# (file offset, pristine word, F4 word, label)
PATCHED_WORDS = (
    (0x0A04C0, 0x24A5ACB4, 0x24A52910, "finder base   -> VMA 0x112910"),
    (0x0A04DC, 0x2CC2005E, 0x2CC20069, "finder length -> 105 (sltiu 0x69)"),
    (0x0AADC4, 0x24A5AFA4, 0x24A52C58, "end pointer   -> VMA 0x112c58"),
    (0x0AAFB0, 0x24A5AFA4, 0x24A52C58, "end pointer   -> VMA 0x112c58"),
    (0x0AB434, 0x24A5AFA4, 0x24A52C58, "end pointer   -> VMA 0x112c58"),
    (0x0AB4E4, 0x24A5AFA4, 0x24A52C58, "end pointer   -> VMA 0x112c58"),
)
NEW_PHOFF = 0x167150
CALLER_VMAS = (0xA055C, 0xA05E4)

TABLE_OFF = 0x167190
TABLE_COUNT = 105
NATIVE_COUNT = 94
TERMINATOR = (10, 0, 0, 0)
# the 11 F4 records (indices 94..104), in the order this round emits them
EXPECTED_NEW = (
    (4661, 6393, 4704, 0), (4665, 6527, 4704, 0), (4671, 6310, 4704, 0),
    (4672, 6527, 4704, 0), (4673, 6312, 4704, 0), (4681, 6310, 4704, 0),
    (4684, 6311, 4704, 0), (4686, 6313, 4704, 0), (4689, 6393, 4704, 0),
    (4690, 6311, 4704, 0), (4696, 4697, 4701, 0),
)
NEW_EXPECT = {
    4673: (4673, 6312, 4704, 0),
    4696: (4696, 4697, 4701, 0),
}

FAILS = []


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 23), b""):
            h.update(chunk)
    return h.hexdigest()


def u32(buf, off):
    return struct.unpack_from("<I", buf, off)[0] if off + 4 <= len(buf) else None


def u16(buf, off):
    return struct.unpack_from("<H", buf, off)[0] if off + 2 <= len(buf) else None


def check(cond, msg):
    if cond:
        print(f"  ok   {msg}")
    else:
        print(f"  FAIL {msg}")
        FAILS.append(msg)


def find_first(records, bound, result):
    """The engine's finder, simulated: linear scan, FIRST result match wins."""
    for i in range(min(bound, len(records))):
        if records[i][0] == result:
            return i, records[i]
    return None


def main():
    for path in (PRISTINE, PATCHED):
        if not os.path.exists(path):
            print(f"STOP: missing {path}; this manual probe needs the gitignored "
                  f"trabajo/ tree (build it with tools/e7_fusion.py)")
            return 1
    pristine = open(PRISTINE, "rb").read()
    patched = open(PATCHED, "rb").read()

    print("--- 1. pristine finder words + pin")
    check(len(pristine) == PRISTINE_SIZE,
          f"pristine size {len(pristine)} == {PRISTINE_SIZE}")
    got_sha = sha256(PRISTINE)
    check(got_sha == PRISTINE_SHA, f"pristine sha256 == {PRISTINE_SHA}")
    for off, want, label in FINDER_WORDS:
        got = u32(pristine, off)
        check(got == want, f"pristine file {off:#x} = {got:#010x} "
                           f"== {want:#010x}  ({label})")

    print("--- 2. F4 module words, header fields and size")
    check(len(patched) == PATCHED_SIZE,
          f"patched size {len(patched)} == {PATCHED_SIZE}")
    check(sha256(PATCHED) == PATCHED_SHA, f"patched sha256 == {PATCHED_SHA}")
    for off, old, new, label in PATCHED_WORDS:
        old_got = u32(pristine, off)
        new_got = u32(patched, off)
        check(old_got == old, f"pristine file {off:#x} == {old:#010x}  ({label})")
        check(new_got == new, f"patched  file {off:#x} = {new_got:#010x} "
                              f"== {new:#010x}  ({label})")
    check(u16(pristine, 0x1C) is not None and u32(pristine, 0x1C) == 0x34,
          "pristine e_phoff (file 0x1c) == 0x34")
    check(u16(pristine, 0x2C) == 1, "pristine e_phnum (file 0x2c) == 1")
    check(u32(patched, 0x1C) == NEW_PHOFF,
          f"patched e_phoff (file 0x1c) == {NEW_PHOFF:#x}")
    check(u16(patched, 0x2C) == 2, "patched e_phnum (file 0x2c) == 2")

    print("--- 3. caller census over the scanned .text range")
    callers = []
    interior = []
    bound_offsets = []
    for off in range(TEXT_LO, TEXT_HI, 4):
        word = u32(pristine, off)
        if word is None:
            break
        if (word >> 26) == 3:                       # jal
            target = (word & 0x03FFFFFF) << 2
            if target == FINDER_VMA:
                callers.append(off - FILE_DELTA)
            if target in FINDER_INTERIOR:
                interior.append((off - FILE_DELTA, target))
        if word == BOUND_WORD:
            bound_offsets.append(off)
    check(tuple(callers) == CALLER_VMAS,
          f"exactly the two result-keyed jal callers to {FINDER_VMA:#x}: "
          f"{[hex(v) for v in callers]} == {[hex(v) for v in CALLER_VMAS]}")
    check(interior == [],
          f"no jal targets the finder interior {FINDER_INTERIOR.start:#x}.."
          f"{FINDER_INTERIOR.stop:#x} (got {interior})")
    check(bound_offsets == [0x0A04DC],
          f"the pristine bound word {BOUND_WORD:#010x} occurs exactly once in "
          f"the range: {[hex(o) for o in bound_offsets]}")

    print("--- 4. first-match scan over the F4 table")
    end = TABLE_OFF + (TABLE_COUNT + 1) * 8
    if end > len(patched):
        check(False, f"patched file too short to hold the table "
                     f"(needs {end}, has {len(patched)})")
        records = []
        terminator = None
    else:
        records = [struct.unpack_from("<4H", patched, TABLE_OFF + 8 * i)
                   for i in range(TABLE_COUNT)]
        terminator = struct.unpack_from("<4H", patched, TABLE_OFF + TABLE_COUNT * 8)
    check(len(records) == TABLE_COUNT, f"table has {TABLE_COUNT} records")
    check(terminator == TERMINATOR,
          f"word {TABLE_COUNT} is the terminator {TERMINATOR} (got {terminator})")
    check(end == len(patched),
          f"table + terminator ends exactly at EOF ({end:#x})")

    by_result = {}
    for r in records:
        by_result.setdefault(r[0], []).append(r)
    multi = sorted(t for t, rs in by_result.items() if len(rs) > 1)
    check(multi == [],
          f"EXACTLY ONE record per result (results with >1: {multi})")
    check(len(by_result) == TABLE_COUNT,
          f"{len(by_result)} distinct results == {TABLE_COUNT} records")

    check(tuple(records[NATIVE_COUNT:]) == EXPECTED_NEW,
          f"the {len(EXPECTED_NEW)} new records == the F4 map "
          f"(got {records[NATIVE_COUNT:]})")
    for result, want in NEW_EXPECT.items():
        idx = NATIVE_COUNT + EXPECTED_NEW.index(want)
        got = find_first(records, TABLE_COUNT, result)
        check(got == (idx, want),
              f"finder: {result} -> record {idx} {want} (got {got})")

    if FAILS:
        print(f"FAILED: {len(FAILS)} check(s)")
        return 1
    print("OK: first-match semantics pinned (2 jal callers at 0xa055c/0xa05e4, "
          "no interior call, the 0x2cc2005e bound word once) and the F4 shape "
          "pinned (6 patched words, e_phoff 0x167150, e_phnum 2, "
          f"{PATCHED_SIZE} B); the table has {TABLE_COUNT} records + the "
          f"(10,0,0,0) terminator with exactly one record per result; new "
          f"results resolve as expected: 4673 -> (4673, 6312, 4704, 0), "
          f"4696 -> (4696, 4697, 4701, 0)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

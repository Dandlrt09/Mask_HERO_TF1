#!/usr/bin/env python3
"""E9 / route B: swap the *script-code* slot of "Cambio de Mascara" and
"Cambio de Forma" inside TFSP's rel_DuelEng.prx.

Corrected facts (see trabajo/e9/E9-TFSP-REFERENCIA.md §9):
  * the engine card id is `CARD_Prop.prop1 & 0x3fff` (14 bits), so
    "Cambio de Mascara" = 9066 and "Cambio de Forma" = 9068 (not 4853/4855);
  * rel_DuelEng.prx lives in the TFSP ISO at file offset 441311232 (LBA 215484);
  * their 24-byte effect records differ ONLY in the last slot, a thunk
    `j 0x16FCA8` carrying a script code in the delay slot:
        Cambio de Mascara  @ prx 0x495E60: {0x236a, 134dac, 9a4f0, c2918, 0, 0x16FFE0}  (code 58)
        Cambio de Forma    @ prx 0x495E78: {0x236c, 134dac, 9a4f0, c2918, 0, 0x170000}  (code 79)

This profile swaps those two thunks (all other slots are already identical), which
is the minimal probe of "does the record's script code drive the effect?".

  dump   ISO                      print both records as they are in the ISO
  build  BASE_ISO OUT_ISO         stream-copy + patch + verify (one pass)
  verify BASE_ISO OUT_ISO         re-read both records and report the diff
"""
from __future__ import annotations

import os
import struct
import sys

PRX_ISO_OFF = 441311232
PRX_SIZE = 6851733

MC_OFF = 0x495E60      # engine id 9066, "Cambio de Mascara"
FC_OFF = 0x495E78      # engine id 9068, "Cambio de Forma"

MC_KEY, FC_KEY = 0x236A, 0x236C
MC_PAYLOAD = (0x00134DAC, 0x0009A4F0, 0x000C2918, 0, 0x0016FFE0)   # code 58
FC_PAYLOAD = (0x00134DAC, 0x0009A4F0, 0x000C2918, 0, 0x00170000)   # code 79

CHUNK = 1 << 22


def read_records(f, base_iso_off: int) -> dict[str, tuple[int, ...]]:
    out = {}
    for name, off in (("MC", MC_OFF), ("FC", FC_OFF)):
        f.seek(base_iso_off + off)
        out[name] = struct.unpack("<6I", f.read(24))
    return out


def cmd_dump(iso: str) -> int:
    with open(iso, "rb") as f:
        recs = read_records(f, PRX_ISO_OFF)
        f.seek(PRX_ISO_OFF)
        magic = f.read(4)
    print(f"ISO {iso}: size={os.path.getsize(iso)} prx magic={magic!r}")
    for k, v in recs.items():
        print(f"  {k}: " + " ".join(f"{w:#010x}" for w in v))
    assert magic == b"\x7fELF", "rel_DuelEng.prx not at the expected ISO offset"
    assert recs["MC"][0] == MC_KEY and recs["MC"][1:] == MC_PAYLOAD, "MC record mismatch"
    assert recs["FC"][0] == FC_KEY and recs["FC"][1:] == FC_PAYLOAD, "FC record mismatch"
    print("  base records match the expected baseline")
    return 0


def cmd_build(base: str, out: str) -> int:
    assert not os.path.exists(out), f"{out} already exists"
    total = os.path.getsize(base)
    with open(base, "rb") as src, open(out, "wb") as dst:
        left = total
        while left:
            buf = src.read(min(CHUNK, left))
            if not buf:
                raise IOError("short read while copying")
            dst.write(buf)
            left -= len(buf)
        # patch: MC gets FC's payload, FC gets MC's payload (keys untouched)
        for off, payload in ((MC_OFF, FC_PAYLOAD), (FC_OFF, MC_PAYLOAD)):
            dst.seek(PRX_ISO_OFF + off + 4)
            dst.write(struct.pack("<5I", *payload))
        dst.flush()
        os.fsync(dst.fileno())
    print(f"wrote {out} ({os.path.getsize(out)} bytes)")
    return 0


def expected_diff_bytes() -> set[int]:
    """Byte offsets (relative to the prx) that must differ after the swap."""
    out: set[int] = set()
    for off, old, new in ((MC_OFF, MC_PAYLOAD, FC_PAYLOAD), (FC_OFF, FC_PAYLOAD, MC_PAYLOAD)):
        old_b = struct.pack("<6I", MC_KEY if off == MC_OFF else FC_KEY, *old)
        new_b = struct.pack("<6I", MC_KEY if off == MC_OFF else FC_KEY, *new)
        out |= {off + i for i in range(24) if old_b[i] != new_b[i]}
    return out


def cmd_verify(base: str, out: str) -> int:
    assert os.path.getsize(base) == os.path.getsize(out), "size differs"
    with open(base, "rb") as fb, open(out, "rb") as fo:
        b = read_records(fb, PRX_ISO_OFF)
        o = read_records(fo, PRX_ISO_OFF)
        print("base:", {k: tuple(hex(x) for x in v) for k, v in b.items()})
        print("out :", {k: tuple(hex(x) for x in v) for k, v in o.items()})
        assert o["MC"][0] == MC_KEY and o["MC"][1:] == FC_PAYLOAD, "MC not patched"
        assert o["FC"][0] == FC_KEY and o["FC"][1:] == MC_PAYLOAD, "FC not patched"
        # full prx byte diff, to prove nothing else moved
        fb.seek(PRX_ISO_OFF)
        fo.seek(PRX_ISO_OFF)
        diff = []
        for i in range(0, PRX_SIZE, CHUNK):
            n = min(CHUNK, PRX_SIZE - i)
            x, y = fb.read(n), fo.read(n)
            if x != y:
                diff += [i + j for j in range(n) if x[j] != y[j]]
        want = expected_diff_bytes()
        print(f"differing bytes inside rel_DuelEng.prx: {len(diff)} (expected {len(want)})")
        assert set(diff) == want, (
            f"unexpected diff: extra={sorted(set(diff) - want)} missing={sorted(want - set(diff))}")
    print("verify OK")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2
    cmd = argv[1]
    if cmd == "dump":
        return cmd_dump(argv[2])
    if cmd == "build":
        return cmd_build(argv[2], argv[3])
    if cmd == "verify":
        return cmd_verify(argv[2], argv[3])
    print(f"unknown command {cmd!r}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

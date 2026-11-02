#!/usr/bin/env python3
"""E6: build the 18-card Masked HERO card database (and the ISO that carries it).

`container` subcommand
----------------------
Reads the pristine `cardinfo_spa.ehp` (from the Spanish base ISO or from a file
already extracted) and appends the 18 records described by `datos/cartas_18.tsv`
at the internal indices 2480..2497, in TSV order.  Every field of every record is
written explicitly from the TSV: no field is inherited from the art donor except
the album sort key (`CARD_Sort_S`), which is a presentation hint.

Record layout (measured; see ESTADO-E0.md §2 and tools/tfcard.py):

  Prop1 (u32)  CardID 0..12 | ATK/10 13..21 | DEF/10 22..30 | CardExistFlag 31
  Prop2 (u32)  kind 0..3 | attr 4..7 | level 8..11 | icon 12..14 |
               ctype 15..19 | rarity 20..22 | bits 23..31 unused (written 0)
  Genre 6 B/index (bit flags; byte4 bit0 = "Special Summon")
  Pass  4 B/index (password; 0 for these 18, the chosen acquisition route is the
                   save, not the in-game password machine)
  Sort  2 B/index (album sort key, kept from the art donor)
  Indx  8 B/index (name offset, description offset) + two trailing placeholders
  Name/Desc      UTF-16-LE string buffers, appended at the end
  IntID 2 B/slot, indexed by CardID - 4000

Verification is a first-class part of the build: it re-reads the rebuilt
container with the independent reader (`tools/tfcard.py`) and asserts every TSV
field of all 18 records, that the 2480 pristine records are byte-identical in
every parallel array, and that CARD_IntID changed in exactly the 18 new slots.

Usage:
  python3 tools/e6_build_18.py container [--ehp FILE] [--src ISO] [--out FILE]
  python3 tools/e6_build_18.py verify-artifact FILE
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import struct
import sys
import tempfile

TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
import cardinfo_add as cia      # noqa: E402
import e1_patch_iso             # noqa: E402
import e5_c2_patch              # noqa: E402
import e6_iso_space             # noqa: E402
import ehp                      # noqa: E402
import iso_replace              # noqa: E402
import tfcard                   # noqa: E402
from iso9660 import SECTOR, Iso9660  # noqa: E402

DEFAULT_SRC = "Yu-Gi-Oh! GX - Tag Force 1 [JP Voice enabled].iso"
DEFAULT_TSV = os.path.join(ROOT, "datos", "cartas_18.tsv")
DEFAULT_PRISTINE = os.path.join(ROOT, "trabajo", "e6", "cardinfo_spa_pristine.ehp")
DEFAULT_OUT = os.path.join(ROOT, "trabajo", "e6", "cardinfo_spa_18.ehp")
EHP_IN_ISO = "PSP_GAME/USRDIR/duelsys/cardinfo_spa.ehp"

# measured in this session from the pristine container (see the build log)
PRISTINE_SHA256 = "40f0935f2807733ec07da2c790ae1f1b26c1d093950d4682901197647e37c696"
PRISTINE_RECORDS = 2480
FIRST_NEW_INDEX = 2480

# Prop2 bit fields (Prop2 bit 0..22, bits 23..31 unused)
P2_FIELDS = {
    "kind": (0, 0xF),
    "attr": (4, 0xF),
    "level": (8, 0xF),
    "icon": (12, 0x7),
    "ctype": (15, 0x1F),
    "rarity": (20, 0x7),
}
P2_USED = 0x7FFFFF            # bits 0..22
REGION_WIDTH = {"CARD_Prop": 8, "CARD_Genre": 6, "CARD_Pass": 4,
                "CARD_Sort": 2, "CARD_Indx": 8}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_tsv(path: str) -> list[dict]:
    """Read the 18-card table.

    The header comes from the `# Columnas:` comment line (the file has no data
    header row); every non-comment line is a card.
    """
    rows: list[list[str]] = []
    header: list[str] | None = None
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            if line.lstrip().startswith("#"):
                if "Columnas:" in line and header is None:
                    header = line.split("Columnas:", 1)[1].split()
                continue
            cells = line.split("\t")
            if header is not None and cells[0] == header[0]:
                continue                      # a data header row, if one exists
            rows.append(cells)
    if header is None:
        raise ValueError(f"{path}: no '# Columnas:' comment with the field order")
    out = []
    for cells in rows:
        if len(cells) != len(header):
            raise ValueError(f"{path}: row with {len(cells)} cells, header has "
                             f"{len(header)}")
        out.append(dict(zip(header, cells)))
    text_cols = {"arte_donante", "nombre", "descripcion", "genre_hex"}
    for row in out:
        for h in header:
            if h not in text_cols:
                row[h] = int(row[h], 0)
    return out


def check_rows(rows: list[dict]) -> list[str]:
    problems: list[str] = []
    if len(rows) != 18:
        problems.append(f"expected 18 rows, found {len(rows)}")
    ids = [r["cardid"] for r in rows]
    if len(set(ids)) != len(ids):
        problems.append("duplicate cardid")
    for r in rows:
        for field, (shift, mask) in [("kind", P2_FIELDS["kind"]),
                                     ("attr", P2_FIELDS["attr"]),
                                     ("level", P2_FIELDS["level"]),
                                     ("icon", P2_FIELDS["icon"]),
                                     ("ctype", P2_FIELDS["ctype"]),
                                     ("rarity", P2_FIELDS["rarity"])]:
            value = r[field]
            if not 0 <= value <= mask:
                problems.append(f"cardid {r['cardid']}: {field}={value} does not "
                                f"fit in {mask.bit_length()} bits")
        for field in ("atk", "def"):
            if r[field] % 10:
                problems.append(f"cardid {r['cardid']}: {field}={r[field]} is not "
                                f"a multiple of 10 (the field stores /10)")
            if r[field] // 10 > 0x1FF:
                problems.append(f"cardid {r['cardid']}: {field}={r[field]} overflows")
        if len(r["genre_hex"]) != 12:
            problems.append(f"cardid {r['cardid']}: genre {r['genre_hex']!r} is not "
                            f"6 bytes of hex")
        if not r["nombre"] or not r["descripcion"]:
            problems.append(f"cardid {r['cardid']}: empty name or description")
    return problems


def donor_index(intid: bytes, card_id: int) -> int:
    idx = cia.internal_id(intid, card_id)
    if idx == 0:
        raise ValueError(f"art donor CardID {card_id} maps to internal index 0 "
                         f"(the null card): it is not a real card")
    return idx


def resolve_donors(rows: list[dict], pristine: bytes) -> None:
    """Resolve each row's `arte_donante` (an exact Spanish card name) into the
    donor's internal index and CardID.  Raises if a name does not exist."""
    _, entries = cia.parse(pristine)
    bodies = {e.name: e.body for e in entries}
    tmp = tempfile.mkdtemp(prefix="e6_donors_")
    try:
        for name, blob in bodies.items():
            with open(os.path.join(tmp, name), "wb") as out:
                out.write(blob)
        ci = tfcard.CardInfo(tmp, "_S")
        names = {}
        for i in range(1, ci.count):
            off = struct.unpack_from("<i", ci.index, i * 8)[0]
            names.setdefault(ci._string(ci.names, off), i)
        for r in rows:
            key = r["arte_donante"]
            if key not in names:
                raise ValueError(f"CardID {r['cardid']}: art donor {key!r} does not "
                                 f"exist in the Spanish card database")
            di = names[key]
            r["_donor_index"] = di
            r["_donor_card_id"] = ci.get_by_index(di).card_id
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def build_container(pristine: bytes, rows: list[dict]) -> tuple[bytes, dict]:
    """Append the 18 records and return (container, report)."""
    header, entries = cia.parse(pristine)
    bodies = {e.name: e.body for e in entries}
    prop = bytearray(bodies[cia.region(entries, "CARD_Prop").name])
    intid = bytearray(bodies[cia.region(entries, "CARD_IntID").name])
    report: dict = {"pristine_size": len(pristine), "pristine_sha256": sha256(pristine),
                    "records": []}

    # --- 1. preconditions on the pristine container -------------------------
    if len(prop) // 8 != PRISTINE_RECORDS:
        raise ValueError(f"pristine CARD_Prop has {len(prop)//8} records, expected "
                         f"{PRISTINE_RECORDS}")
    seen = {}
    for i in range(1, PRISTINE_RECORDS):
        cid = struct.unpack_from("<I", prop, i * 8)[0] & 0x1FFF
        seen.setdefault(cid, i)
    for r in rows:
        cid = r["cardid"]
        if cia.internal_id(bytes(intid), cid) != 0:
            raise ValueError(f"CardID {cid} is not free: CARD_IntID points at "
                             f"index {cia.internal_id(bytes(intid), cid)}")
        if cid in seen:
            raise ValueError(f"CardID {cid} already exists at internal index "
                             f"{seen[cid]}")

    # --- 2. the donor of each card's artwork, by exact Spanish name ----------
    resolve_donors(rows, pristine)

    # --- 3. append the 18 records -------------------------------------------
    genre_e = cia.region(entries, "CARD_Genre")
    pass_e = cia.region(entries, "CARD_Pass")
    sort_e = cia.region(entries, "CARD_Sort")
    indx_e = cia.region(entries, "CARD_Indx")
    name_e = cia.region(entries, "CARD_Name")
    desc_e = cia.region(entries, "CARD_Desc")

    genre = bytearray(bodies[genre_e.name])
    passw = bytearray(bodies[pass_e.name])
    sort = bytearray(bodies[sort_e.name])
    names_buf = bytearray(bodies[name_e.name])
    descs_buf = bytearray(bodies[desc_e.name])
    pristine_indx = bodies[indx_e.name]

    if len(pristine_indx) != PRISTINE_RECORDS * 8 + 16:
        raise ValueError(f"CARD_Indx is {len(pristine_indx)} bytes; expected "
                         f"{PRISTINE_RECORDS * 8 + 16} (records + 2 placeholders)")
    # the two placeholder records live after the real ones and stay at the end
    indx = bytearray(pristine_indx[:PRISTINE_RECORDS * 8])
    indx_tail = bytes(pristine_indx[PRISTINE_RECORDS * 8:])

    for i, r in enumerate(rows):
        idx = FIRST_NEW_INDEX + i
        di = r["_donor_index"]

        # Prop1
        p1 = r["cardid"] & 0x1FFF
        p1 |= (r["atk"] // 10) << 13
        p1 |= (r["def"] // 10) << 22
        p1 |= 1 << 31                       # CardExistFlag
        # Prop2
        p2 = 0
        for field, (shift, mask) in P2_FIELDS.items():
            p2 |= (r[field] & mask) << shift
        if p2 & ~P2_USED:
            raise ValueError(f"cardid {r['cardid']}: Prop2 {p2:#x} uses a "
                             f"reserved bit")

        prop += struct.pack("<II", p1, p2)
        genre += bytes.fromhex(r["genre_hex"])
        passw += struct.pack("<I", r["password"])
        sort += bodies[sort_e.name][di * 2:di * 2 + 2]

        name_off = len(names_buf)
        name_bytes = r["nombre"].encode("utf-16-le") + b"\x00\x00"
        names_buf += name_bytes
        desc_off = len(descs_buf)
        desc_bytes = r["descripcion"].encode("utf-16-le") + b"\x00\x00"
        descs_buf += desc_bytes
        indx += struct.pack("<II", name_off, desc_off)

        struct.pack_into("<H", intid, (r["cardid"] - cia.CARD_ID_BASE) * 2, idx)

        report["records"].append({
            "n": r["n"], "cardid": r["cardid"], "internal_index": idx,
            "donor_name": r["arte_donante"], "donor_index": di,
            "donor_card_id": r["_donor_card_id"],
            "prop1": f"0x{p1:08x}", "prop2": f"0x{p2:08x}",
            "name_off": name_off, "desc_off": desc_off,
            "name_bytes": len(name_bytes), "desc_bytes": len(desc_bytes),
        })

    indx += indx_tail
    bodies[genre_e.name] = bytes(genre)
    bodies[pass_e.name] = bytes(passw)
    bodies[sort_e.name] = bytes(sort)
    bodies[indx_e.name] = bytes(indx)
    bodies[name_e.name] = bytes(names_buf)
    bodies[desc_e.name] = bytes(descs_buf)
    bodies[cia.region(entries, "CARD_Prop").name] = bytes(prop)
    bodies[cia.region(entries, "CARD_IntID").name] = bytes(intid)

    out = cia.rebuild(pristine, bodies)
    report["new_size"] = len(out)
    report["growth"] = len(out) - len(pristine)
    report["new_sha256"] = sha256(out)
    report["sectors_needed"] = (len(out) + 2047) // 2048
    return out, report


def verify_container(pristine: bytes, built: bytes, rows: list[dict]) -> list[str]:
    """Independent verification: every TSV field, the pristine prefix, IntID."""
    fails: list[str] = []
    try:
        p_data = cia.parse(pristine)
        b_data = cia.parse(built)
    except ValueError as exc:
        return [f"parse: {exc}"]
    p_files = {e.name: e for e in p_data[1]}
    b_files = {e.name: e for e in b_data[1]}

    if [e.name for e in b_data[1]] != [e.name for e in p_data[1]]:
        fails.append("the region list changed")

    # pristine prefix must be byte-identical in every per-index array
    for prefix in REGION_WIDTH:
        width = REGION_WIDTH[prefix]
        old = p_files[cia.region(p_data[1], prefix).name].body
        new = b_files[cia.region(b_data[1], prefix).name].body
        keep = PRISTINE_RECORDS * width
        if new[:keep] != old[:keep]:
            first = next(i for i in range(keep) if new[i] != old[i])
            fails.append(f"{prefix}: pristine bytes changed at offset {first}")
        if prefix == "CARD_Indx":
            want_len = keep + len(rows) * width + (len(old) - keep)
            if len(new) != want_len:
                fails.append(f"CARD_Indx: {len(new)} bytes, expected {want_len}")
            if new[-16:] != old[-16:]:
                fails.append("CARD_Indx: the two trailing placeholder records "
                             "changed")
    for prefix in ("CARD_Name", "CARD_Desc"):
        old = p_files[cia.region(p_data[1], prefix).name].body
        new = b_files[cia.region(b_data[1], prefix).name].body
        if new[:len(old)] != old:
            fails.append(f"{prefix}: pristine string buffer changed")
    for prefix in ("CARD_SamePict", "CARD_Top", "DLG_Indx", "DLG_Text"):
        old = p_files[cia.region(p_data[1], prefix).name].body
        new = b_files[cia.region(b_data[1], prefix).name].body
        if new != old:
            fails.append(f"{prefix}: untouched region was modified")

    # CARD_IntID: changed in exactly the 18 new slots
    old_i = p_files[cia.region(p_data[1], "CARD_IntID").name].body
    new_i = b_files[cia.region(b_data[1], "CARD_IntID").name].body
    if len(old_i) != len(new_i):
        fails.append("CARD_IntID size changed")
    else:
        changed = {o // 2 + cia.CARD_ID_BASE for o in range(0, len(old_i), 2)
                   if old_i[o:o + 2] != new_i[o:o + 2]}
        want = {r["cardid"] for r in rows}
        if changed != want:
            fails.append(f"CARD_IntID changed in {sorted(changed)}, "
                         f"expected {sorted(want)}")
        for i, r in enumerate(rows):
            got = cia.internal_id(new_i, r["cardid"])
            if got != FIRST_NEW_INDEX + i:
                fails.append(f"CardID {r['cardid']}: IntID={got}, expected "
                             f"{FIRST_NEW_INDEX + i}")

    # independent read-back of all 18 records
    tmp = tempfile.mkdtemp(prefix="e6_verify_")
    try:
        for name, blob in ehp.parse(built)["files"].items():
            with open(os.path.join(tmp, name), "wb") as out:
                out.write(blob)
        ci = tfcard.CardInfo(tmp, "_S")
        if ci.count != PRISTINE_RECORDS + len(rows):
            fails.append(f"record count {ci.count}, expected "
                         f"{PRISTINE_RECORDS + len(rows)}")
        for i, r in enumerate(rows):
            idx = FIRST_NEW_INDEX + i
            c = ci.get_by_index(idx)
            checks = {
                "cardid": (c.card_id, r["cardid"]), "name": (c.name, r["nombre"]),
                "desc": (c.description, r["descripcion"]),
                "atk": (c.atk, r["atk"]), "def": (c.dfn, r["def"]),
                "level": (c.level, r["level"]), "kind": (c.kind, r["kind"]),
                "attr": (c.attr, r["attr"]), "icon": (c.icon, r["icon"]),
                "ctype": (c.ctype, r["ctype"]), "rarity": (c.rarity, r["rarity"]),
                "genre": (c.genre.hex(), r["genre_hex"].lower()),
                "password": (c.password, r["password"]), "exist": (c.exist, True),
            }
            for field, (got, want) in checks.items():
                if got != want:
                    fails.append(f"index {idx} (CardID {r['cardid']}) {field}: "
                                 f"read {got!r}, expected {want!r}")
            if ci.internal_id(r["cardid"]) != idx:
                fails.append(f"CardID {r['cardid']}: IntID read back as "
                             f"{ci.internal_id(r['cardid'])}, expected {idx}")
        # the pristine records keep reading the same way through tfcard
        p_tmp = tempfile.mkdtemp(prefix="e6_pristine_")
        try:
            for name, blob in ehp.parse(pristine)["files"].items():
                with open(os.path.join(p_tmp, name), "wb") as out:
                    out.write(blob)
            pi = tfcard.CardInfo(p_tmp, "_S")
            for i in range(1, PRISTINE_RECORDS):
                a, b = pi.get_by_index(i), ci.get_by_index(i)
                if (a.card_id, a.atk, a.dfn, a.level, a.kind, a.attr, a.ctype,
                        a.icon, a.rarity, a.name, a.description, a.genre,
                        a.password, a.exist) != \
                   (b.card_id, b.atk, b.dfn, b.level, b.kind, b.attr, b.ctype,
                        b.icon, b.rarity, b.name, b.description, b.genre,
                        b.password, b.exist):
                    fails.append(f"internal index {i} (CardID {a.card_id}) reads "
                                 f"differently after the rebuild")
                    break
        finally:
            shutil.rmtree(p_tmp, ignore_errors=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return fails


def cmd_container(args) -> int:
    rows = read_tsv(args.tsv)
    problems = check_rows(rows)
    if problems:
        for p in problems:
            print(f"TSV PROBLEM: {p}")
        return 1
    if args.ehp and os.path.exists(args.ehp):
        pristine = open(args.ehp, "rb").read()
        source = args.ehp
    else:
        if not os.path.exists(args.src):
            raise SystemExit(f"missing input: {args.src}")
        pristine = iso_replace.read_iso_file(args.src, EHP_IN_ISO)
        source = f"{args.src}:{EHP_IN_ISO}"
    print(f"pristine container: {source}")
    print(f"  size {len(pristine)}  sha256 {sha256(pristine)}")
    if PRISTINE_SHA256 and sha256(pristine) != PRISTINE_SHA256:
        print(f"  STOP: sha256 differs from the pinned pristine "
              f"{PRISTINE_SHA256}")
        return 1
    if not args.ehp:
        os.makedirs(os.path.dirname(os.path.abspath(DEFAULT_PRISTINE)), exist_ok=True)
    if args.save_pristine:
        with open(args.save_pristine, "wb") as f:
            f.write(pristine)
        print(f"  saved pristine copy -> {args.save_pristine}")

    built, report = build_container(pristine, rows)
    print(f"built: {len(built)} bytes (+{report['growth']}), "
          f"{report['sectors_needed']} sectors")
    fails = verify_container(pristine, built, rows)
    if fails:
        print(f"\nVERIFICATION FAILED ({len(fails)}):")
        for f in fails:
            print(f"  FAIL: {f}")
        return 1
    print(f"verification: OK — 18 records, 2480 pristine records unchanged")
    for rec in report["records"]:
        print(f"  idx {rec['internal_index']} CardID {rec['cardid']:5} "
              f"donor {rec['donor_name'][:34]:34} "
              f"name+{rec['name_bytes']:4} desc+{rec['desc_bytes']:5}")

    with open(args.out, "wb") as f:
        f.write(built)
    report_path = args.report or os.path.join(os.path.dirname(os.path.abspath(args.out)),
                                              "container_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"wrote {args.out}")
    print(f"wrote {report_path}")
    return 0


# --------------------------------------------------------------------------- #
# ISO build
# --------------------------------------------------------------------------- #
DATA_BIN = "PSP_GAME/SYSDIR/UPDATE/DATA.BIN"
BOOT_PATH = "PSP_GAME/SYSDIR/BOOT.BIN"
EBOOT_PATH = "PSP_GAME/SYSDIR/EBOOT.BIN"
ART_PATHS = ("PSP_GAME/USRDIR/card/cardh_s.cip",
             "PSP_GAME/USRDIR/card/cardm_s.cip")
DEFAULT_BOOT_ARTIFACT = os.path.join(ROOT, "trabajo", "e1c", "BOOT.BIN")
DEFAULT_ISO_OUT = os.path.join(ROOT, "trabajo", "e6", "TF1-E6-18.iso")

# --- game-module patches: let the 18 new internal indices exist -------------
#
# The card database has 2480 records (internal indices 0..2479), all of them
# taken by real cards, so the 18 new cards live at indices 2480..2497.  Three
# places in the game's code still assume 2480:
#
#   * libcardalbum.prx builds the CardID-by-index map in a fixed stack frame:
#     `addiu sp,sp,-6000`, the map is 2480 u16 entries at sp+0x40E, i.e. it ends
#     exactly at sp+0x1770 = the end of the frame (one extra index fits, 2481
#     onwards writes past it, into the caller's frame).  Growing the frame to
#     6048 B (2498 entries end at sp+0x1792 = 6034) makes room; the matching
#     epilogue must grow by the same amount.
#   * the owned-list loop in libcardalbum stops at `slti s1, 2480`.
#   * libduel_draw clamps a card-list cursor with the same `slti s1, 2480`.
#
# Words, verified by searching each module for the exact instruction word and
# requiring exactly one hit:
MODULE_PATCHES = (
    ("PSP_GAME/USRDIR/gmodule/libcardalbum.prx", 0x27BDE890, 0x27BDE860,
     "stack frame 6000 -> 6048 B (room for the 2498-entry CardID map)"),
    ("PSP_GAME/USRDIR/gmodule/libcardalbum.prx", 0x27BD1770, 0x27BD17A0,
     "matching epilogue 6000 -> 6048 B"),
)
# `slti rt,rs,2480` -> `slti rt,rs,2480+len(rows)` (immediate in the low 16 bits)
BOUND_PATCHES = (
    ("PSP_GAME/USRDIR/gmodule/libcardalbum.prx", 0x2A2309B0,
     "owned-list loop bound 2480 -> 2498"),
    ("PSP_GAME/USRDIR/gmodule/libduel_draw.prx", 0x2A2309B0,
     "card-list cursor clamp 2480 -> 2498"),
)


def plan_module_patches(iso, new_indices: int) -> list[dict]:
    """Locate every module word to patch, asserting it is unique in its file."""
    plan: list[dict] = []
    items = list(MODULE_PATCHES)
    for path, old, why in BOUND_PATCHES:
        items.append((path, old, (old & 0xFFFF0000) | (2480 + new_indices), why))
    for path, old, new, why in items:
        blob = iso.read_file(path)
        hits = [off for off in range(0, len(blob) - 3, 4)
                if struct.unpack_from("<I", blob, off)[0] == old]
        if len(hits) != 1:
            raise ValueError(f"{path}: expected exactly one 0x{old:08x}, found "
                             f"{len(hits)} at {[hex(h) for h in hits]}")
        plan.append({"path": path, "offset": hits[0], "old": old, "new": new,
                     "why": why, "extent": iso.resolve(path).extent})
    return plan


def iso_path(path: str) -> str:
    """Path as tools/e6_iso_space.walk() reports it (leading slash)."""
    return "/" + path.lstrip("/")


def set_record_size(path: str, rec_off: int, size: int) -> None:
    """Rewrite only the data-length field of a directory record (both endians)."""
    with open(path, "r+b") as f:
        f.seek(rec_off + 10)
        f.write(struct.pack("<I", size))
        f.write(struct.pack(">I", size))


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
                for i in range(0, len(x), 2048):
                    if x[i:i + 2048] != y[i:i + 2048]:
                        out.add((base + i) // 2048)
            base += len(x)
    return out


def plan_art(iso, rows: list[dict]) -> list[dict]:
    """Copy each art donor's 8-byte CIP/CPM entry into the new CardID's slot.

    Free CardIDs have a zeroed slot today, i.e. they point at block 0 (the
    container header), so the artwork must be aliased explicitly.
    """
    plans = []
    for art in ART_PATHS:
        blob = bytearray(iso.read_file(art))
        extent = iso.resolve(art).extent
        plan = {"path": art, "extent": extent, "slots": [], "skipped": []}
        for r in rows:
            try:
                dslot = e1_patch_iso.cip_slot(bytes(blob), r["_donor_card_id"])
                tslot = e1_patch_iso.cip_slot(bytes(blob), r["cardid"])
            except ValueError as exc:
                plan["skipped"].append({"cardid": r["cardid"], "reason": str(exc)})
                continue
            entry = bytes(blob[dslot:dslot + 8])
            plan["slots"].append({"cardid": r["cardid"], "slot": tslot,
                                  "art_from": r["_donor_card_id"],
                                  "donor_slot": dslot,
                                  "before": bytes(blob[tslot:tslot + 8]).hex(),
                                  "after": entry.hex()})
            blob[tslot:tslot + 8] = entry
        plan["blob"] = bytes(blob)
        plans.append(plan)
    return plans


def cmd_iso(args) -> int:
    rows = read_tsv(args.tsv)
    problems = check_rows(rows)
    if problems:
        for p in problems:
            print(f"TSV PROBLEM: {p}")
        return 1
    pristine = open(args.pristine, "rb").read()
    if PRISTINE_SHA256 and sha256(pristine) != PRISTINE_SHA256:
        print(f"STOP: pristine container sha256 {sha256(pristine)} != pinned")
        return 1
    built = open(args.container, "rb").read()
    print(f"container: {args.container} ({len(built)} bytes, "
          f"sha256 {sha256(built)})")

    print("--- 1. the container artifact verifies on its own")
    fails = verify_container(pristine, built, rows)
    if fails:
        print(f"STOP: the container artifact does not verify ({len(fails)}):")
        for f in fails:
            print(f"  FAIL: {f}")
        return 1
    print("    OK: 18 records, 2480 pristine records unchanged")
    resolve_donors(rows, pristine)

    print("--- 2. plan the relocation")
    iso = Iso9660(args.src)
    try:
        card_rec_off, card_entry = iso_replace.find_record(iso, EHP_IN_ISO)
        data_rec_off, data_entry = iso_replace.find_record(iso, DATA_BIN)
        boot = iso.read_file(BOOT_PATH)
        boot_entry = iso.resolve(BOOT_PATH)
        eboot_entry = iso.resolve(EBOOT_PATH)
        eboot_size = eboot_entry.size
        eboot = iso.read_file(EBOOT_PATH)
        need = (len(built) + SECTOR - 1) // SECTOR
        data_alloc = e6_iso_space.allocated_sectors(data_entry.size)
        vol = e6_iso_space.volume_sectors(iso)
        art_plans = plan_art(iso, rows)
        module_plan = plan_module_patches(iso, len(rows))
        art_sectors = {}
        for plan in art_plans:
            for slot in plan["slots"]:
                off = plan["extent"] * SECTOR + slot["slot"]
                art_sectors.setdefault(plan["path"], set()).add(off // SECTOR)
    finally:
        iso.close()

    print(f"    container needs {need} sectors; it is pinned at LBA "
          f"{card_entry.extent} inside an allocation of "
          f"{e6_iso_space.allocated_sectors(card_entry.size)} sectors")
    if need <= e6_iso_space.allocated_sectors(card_entry.size):
        print("    it would fit in place (no relocation needed)")
    if args.space != "update-bin":
        raise SystemExit(f"--space {args.space}: only 'update-bin' is implemented")
    new_lba = data_entry.extent
    print(f"    --space update-bin: {DATA_BIN} at LBA {new_lba}, "
          f"{data_entry.size} bytes ({data_alloc} sectors)")
    if need > data_alloc:
        print(f"STOP: the container needs {need} sectors, the region has "
              f"{data_alloc}")
        return 1
    if not data_entry.extent + data_alloc <= vol:
        print("STOP: the region runs past the volume")
        return 1
    iso = Iso9660(args.src)
    try:
        hits = e6_iso_space.overlaps_file(iso, new_lba, need, ignore=iso_path(DATA_BIN))
    finally:
        iso.close()
    if hits:
        print(f"STOP: the target region is not free: {hits[:4]}")
        return 1
    print(f"    the target region is free (no other extent intersects it)")

    print("--- 3. the engine patch is the proven E5-C2 one")
    if boot != open(args.boot, "rb").read():
        print(f"STOP: {BOOT_PATH} in the ISO differs from {args.boot}")
        return 1
    fact_failures, retarget_entry = e5_c2_patch.inspect(boot)
    if fact_failures or retarget_entry is None:
        print(f"STOP: the E5-C2 facts do not hold ({len(fact_failures)}):")
        for f in fact_failures:
            print(f"  FAIL: {f}")
        return 1
    patched = e5_c2_patch.patch_engine(boot, retarget_entry)
    allowed_bytes = e5_c2_patch.expected_diff(boot, patched, retarget_entry)
    print(f"    {len(allowed_bytes)} engine bytes change; BOOT.BIN "
          f"{len(boot)} bytes, EBOOT.BIN {eboot_size} bytes in the ISO")
    if len(patched) > eboot_size:
        print(f"STOP: the patched engine does not fit EBOOT.BIN")
        return 1
    padded = patched + b"\x00" * (eboot_size - len(patched))
    src_eboot_encrypted = not eboot.startswith(b"\x7fELF")
    print(f"    source EBOOT.BIN: {'encrypted (~PSP), as on the UMD' if src_eboot_encrypted else 'already a plain ELF'}")
    tail_diff = sum(1 for i in range(len(padded))
                    if i not in allowed_bytes and eboot[i] != padded[i])

    # every sector this build is allowed to touch
    allowed_sectors: dict[int, str] = {}
    def allow(lba: int, why: str) -> None:
        allowed_sectors.setdefault(lba, why)
    for i in range(need):
        allow(new_lba + i, "moved container")
    for off in (card_rec_off, data_rec_off):
        allow(off // SECTOR, "directory record")
    for plan in art_plans:
        for lba in art_sectors.get(plan["path"], ()): 
            allow(lba, f"art alias in {plan['path']}")
    for off in allowed_bytes:
        allow((boot_entry.extent * SECTOR + off) // SECTOR, "engine patch (BOOT.BIN)")
    for patch in module_plan:
        lba = patch["extent"] + patch["offset"] // SECTOR
        allow(lba, f"module patch: {patch['path'].rsplit('/', 1)[1]} @0x{patch['offset']:x}")
        print(f"    module patch: {patch['path'].rsplit('/', 1)[1]} "
              f"@0x{patch['offset']:x} 0x{patch['old']:08x} -> 0x{patch['new']:08x} "
              f"({patch['why']})")
    if src_eboot_encrypted:
        # an encrypted ~PSP EBOOT cannot be patched in place, so the whole file is
        # replaced by the patched engine zero-padded to its directory size, exactly
        # as the E5-C2 build the user already tested in PPSSPP did
        for i in range(e6_iso_space.allocated_sectors(eboot_size)):
            allow(eboot_entry.extent + i,
                  "EBOOT.BIN replaced by the patched ELF")
    else:
        for off in allowed_bytes:
            allow((eboot_entry.extent * SECTOR + off) // SECTOR,
                  "engine patch (EBOOT.BIN)")

    print("--- 4. copy the ISO and apply")
    if os.path.exists(args.dst):
        raise SystemExit(f"refusing to overwrite {args.dst}; remove it first")
    shutil.copyfile(args.src, args.dst)
    print(f"    copied {args.src} -> {args.dst}")
    with open(args.dst, "r+b") as f:
        f.seek(new_lba * SECTOR)
        f.write(built)
    e6_iso_space.relocate_record(args.dst, card_rec_off, new_lba, len(built))
    set_record_size(args.dst, data_rec_off, 0)
    print(f"    container written at LBA {new_lba}; its record updated "
          f"(extent {new_lba}, size {len(built)})")
    print(f"    {DATA_BIN}: record size set to 0 (firmware update payload, "
          f"never read by the game)")
    rep_boot = iso_replace.patch_bytes(args.dst, BOOT_PATH, 0, patched)
    rep_eboot = iso_replace.patch_bytes(args.dst, EBOOT_PATH, 0, padded)
    print(f"    engine: {BOOT_PATH} and {EBOOT_PATH} patched (roundtrip "
          f"{rep_boot['roundtrip']}/{rep_eboot['roundtrip']})")
    for plan in art_plans:
        rep = iso_replace.patch_bytes(args.dst, plan["path"], 0, plan["blob"])
        print(f"    art: {plan['path']}: {len(plan['slots'])} slots aliased, "
              f"skipped {len(plan['skipped'])}, roundtrip={rep['roundtrip']}")
    for patch in module_plan:
        rep = iso_replace.patch_bytes(args.dst, patch["path"], patch["offset"],
                                      struct.pack("<I", patch["new"]),
                                      expected=struct.pack("<I", patch["old"]))
        print(f"    module: {patch['path'].rsplit('/', 1)[1]} @0x{patch['offset']:x} "
              f"0x{patch['old']:08x} -> 0x{patch['new']:08x}")

    print("--- 5. verification from the written ISO")
    errs = verify_iso(args.src, args.dst, pristine, built, rows, boot, patched,
                      padded, allowed_bytes, retarget_entry, new_lba, need,
                      card_entry.extent, card_entry.size, eboot_size,
                      art_plans, allowed_sectors, tail_diff,
                      data_entry.extent, data_alloc, module_plan)
    if errs:
        print(f"VERIFICATION FAILED ({len(errs)}):")
        for e in errs:
            print(f"  FAIL: {e}")
        return 1
    print(f"\nOK -> {args.dst}")
    return 0


def verify_iso(src, dst, pristine, built, rows, boot, patched, padded,
               allowed_bytes, retarget_entry, new_lba, need, old_lba, old_size,
               eboot_size, art_plans, allowed_sectors, tail_diff,
               data_lba, data_alloc, module_plan) -> list[str]:
    errs: list[str] = []
    iso = Iso9660(dst)
    try:
        card_rec_off, card_entry = iso_replace.find_record(iso, EHP_IN_ISO)
        data_rec_off, data_entry = iso_replace.find_record(iso, DATA_BIN)
        back = iso.read_file(EHP_IN_ISO)
        boot_back = iso.read_file(BOOT_PATH)
        eboot_back = iso.read_file(EBOOT_PATH)
        vol = e6_iso_space.volume_sectors(iso)
        gaps = e6_iso_space.free_regions(iso)
        hits = e6_iso_space.overlaps_file(iso, new_lba, need, ignore=iso_path(EHP_IN_ISO))
    finally:
        iso.close()

    if sha256(back) != sha256(built):
        errs.append("the container read back from the ISO differs from the artifact")
    if len(back) != len(built):
        errs.append(f"container size {len(back)} != {len(built)}")
    if card_entry.extent != new_lba:
        errs.append(f"directory record extent {card_entry.extent} != {new_lba}")
    if card_entry.size != len(built):
        errs.append(f"directory record size {card_entry.size} != {len(built)}")
    if data_entry.size != 0:
        errs.append(f"{DATA_BIN} record size {data_entry.size} != 0")
    if boot_back != patched:
        errs.append(f"{BOOT_PATH} read back differs from the patched engine")
    if eboot_back != padded:
        errs.append(f"{EBOOT_PATH} read back differs from the padded engine")
    if vol != 390033:
        errs.append(f"volume space size changed to {vol}")
    expect_gaps = {(0, 22),
                   (old_lba, old_lba + (old_size + SECTOR - 1) // SECTOR),
                   (new_lba + need, data_lba + data_alloc)}
    if set(gaps) != expect_gaps:
        errs.append(f"free regions are {gaps}, expected {sorted(expect_gaps)}")
    if hits:
        errs.append(f"the moved container overlaps {hits[:3]}")

    # the container itself, through the independent reader
    errs.extend(verify_container(pristine, back, rows))

    # artwork entries
    iso = Iso9660(dst)
    try:
        for plan in art_plans:
            blob = iso.read_file(plan["path"])
            for slot in plan["slots"]:
                got = blob[slot["slot"]:slot["slot"] + 8].hex()
                if got != slot["after"]:
                    errs.append(f"{plan['path']} CardID {slot['cardid']}: slot is "
                                f"{got}, expected {slot['after']}")
        for patch in module_plan:
            blob = iso.read_file(patch["path"])
            got, = struct.unpack_from("<I", blob, patch["offset"])
            if got != patch["new"]:
                errs.append(f"{patch['path']} @0x{patch['offset']:x}: 0x{got:08x}, "
                            f"expected 0x{patch['new']:08x}")
    finally:
        iso.close()

    # nothing outside the planned sectors changed
    diff = changed_sectors(src, dst)
    unexpected = sorted(diff - set(allowed_sectors))
    if unexpected:
        errs.append(f"{len(unexpected)} sectors changed outside the plan: "
                    f"{unexpected[:8]}")
    missing = sorted(set(allowed_sectors) - diff)
    print(f"    changed sectors: {len(diff)} (allowed {len(allowed_sectors)})")
    for lba in sorted(diff)[:6]:
        print(f"      LBA {lba}: {allowed_sectors.get(lba, 'UNEXPECTED')}")
    if missing:
        print(f"    allowed sectors with no change: {missing[:8]}")
    if tail_diff:
        print(f"    note: {tail_diff} bytes inside EBOOT.BIN outside the engine "
              f"patch differ from the source image (EBOOT is rewritten "
              f"zero-padded, as in the E5-C2 build)")
    print(f"    {len(errs)} verification failure(s)" if errs else
          "    all checks passed")
    return errs


def cmd_verify_artifact(args) -> int:
    rows = read_tsv(args.tsv)
    pristine = open(args.ehp, "rb").read()
    built = open(args.artifact, "rb").read()
    print(f"artifact: {args.artifact} ({len(built)} bytes, sha256 {sha256(built)})")
    fails = verify_container(pristine, built, rows)
    if fails:
        print(f"VERIFICATION FAILED ({len(fails)}):")
        for f in fails:
            print(f"  FAIL: {f}")
        return 1
    print("verification: OK")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("container", help="build the 18-card cardinfo container")
    c.add_argument("--src", default=DEFAULT_SRC)
    c.add_argument("--ehp", help="use this extracted container instead of the ISO")
    c.add_argument("--tsv", default=DEFAULT_TSV)
    c.add_argument("--out", default=DEFAULT_OUT)
    c.add_argument("--report", help="JSON report path")
    c.add_argument("--save-pristine", help="also save the pristine container here")
    c.set_defaults(func=cmd_container)

    v = sub.add_parser("verify-artifact", help="re-verify a built container")
    v.add_argument("artifact")
    v.add_argument("--ehp", default=DEFAULT_PRISTINE)
    v.add_argument("--tsv", default=DEFAULT_TSV)
    v.set_defaults(func=cmd_verify_artifact)

    i = sub.add_parser("iso", help="build the test ISO from the container")
    i.add_argument("--src", default=DEFAULT_SRC)
    i.add_argument("--dst", default=DEFAULT_ISO_OUT)
    i.add_argument("--container", default=DEFAULT_OUT)
    i.add_argument("--pristine", default=DEFAULT_PRISTINE)
    i.add_argument("--boot", default=DEFAULT_BOOT_ARTIFACT,
                   help="unpatched engine ELF artifact")
    i.add_argument("--tsv", default=DEFAULT_TSV)
    i.add_argument("--space", default="update-bin",
                   choices=("update-bin",),
                   help="how to free the contiguous region the container needs")
    i.set_defaults(func=cmd_iso)

    args = ap.parse_args(argv[1:])
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

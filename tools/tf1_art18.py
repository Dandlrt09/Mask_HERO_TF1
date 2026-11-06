#!/usr/bin/env python3
"""tf1_art18.py - E8-4: prepare, inject and relocate the art of the 18 cards.

The 18 Masked HERO / Mask Change cards that E6 added share the art slot of a
donor CardID.  E8-4 gives each one its **own** slot (S7) and writes the grown
containers into a new ISO, without touching the E6 ISO or the game ISO (S5, S8).

Subcommands
-----------
``preview``  comparison sheet: 3 real cropped arts at the two cardh candidates
             (64x56/76 colours and 64x48/204 colours), zoomed, so a human can
             pick ``p`` by looking (S6, T2/T6).
``build``    append one private region per card to ``cardh_s.cip`` and
             ``cardm_s.cip``, rewrite the 18 table entries and ``total_size``
             (T7).  Canvas, palette, format, per-card region size and the
             codecs are CLI flags.  ``--cardm-codec gim`` (the default) writes
             a paletted GIM and reproduces E8-4b byte for byte; ``dxt1`` writes
             the native 64x64 BC1 body (``encode_dxt1_swapped``, 2048 B), which
             is what the field/duel renderer actually reads (ESTADO-E8.md 9.8).
             ``--cardh-codec gim`` (the default) keeps the old paletted GIM;
             ``native-dxt1`` writes a real 4096 B native slot: the 128-byte GIM
             template copied verbatim from a native slot plus a 128x62 swapped
             BC1 body, with the native green chroma-key mask applied when it can
             be located reliably (ESTADO-E8.md 9.9, E8-9).  A region is a
             2048-byte-slot multiple, so a GIM larger than one slot can span
             several consecutive slots.

``fetch-full`` download the full card renders (ygoprodeck ``image_url``) as
             JPGs into ``art_full/`` for the E8-9 cardm full-card source; the
             JPG->PNG conversion is the PowerShell ``System.Drawing`` script
             ``_conv_all.ps1``.
``iso``      copy the read-only E6 ISO to the destination ISO and write the two
             grown containers at the LBAs of ESTADO-E8.md 9.2, updating both
             ISO9660 directory records (extent + size) (T8).  The E8-4b/E8-4c
             ISOs, the frozen user-tested ISO and the E6 ISO are never written.
``accept``   T9 hard assertions: ``arts()`` resolves each card to its new slot,
             every cardh GIM decodes back pixel-identical, every cardm slot
             decodes back as a recognisable 64x64 thumbnail through the
             reference DXT1 decoder (or pixel-identically when the codec is
             gim), ``verify`` exits 0 on both containers, the header regions
             differ from the source only at the 18 entries + ``total_size``, and
             the ISO sector diff is confined to exactly the two new extents.

The binding parameters are ESTADO-E8.md sections 9.1-9.3 (S6, S7, S8); this tool
does not re-derive them.  Only the standard library is used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
E8 = os.path.join(ROOT, "trabajo", "e8")
sys.path.insert(0, HERE)
sys.path.insert(0, E8)

import tf1_art as t  # noqa: E402
from cardm_decode import decode_cardm  # noqa: E402  (reference E8-5 decoder)
from iso9660 import Iso9660, SECTOR  # noqa: E402
from iso_replace import find_record  # noqa: E402
from e6_iso_space import (allocated_sectors, free_regions,
                          relocate_record, walk)  # noqa: E402

E6_ISO = os.path.join(ROOT, "trabajo", "e6", "TF1-E6-18.iso")
ART_SRC = os.path.join(E8, "art_src")
ART_FULL = os.path.join(E8, "art_full")      # full card renders (cardm)
MASK_MANIFEST = os.path.join(ART_SRC, "manifest.tsv")
CARDS_TSV = os.path.join(ROOT, "datos", "cartas_18.tsv")
INNER_H = "PSP_GAME/USRDIR/card/cardh_s.cip"
INNER_M = "PSP_GAME/USRDIR/card/cardm_s.cip"
DEFAULT_CARDH_OUT = os.path.join(E8, "cardh_art.cip")
DEFAULT_CARDM_OUT = os.path.join(E8, "cardm_art.cip")
DEFAULT_ISO = os.path.join(E8, "TF1-E8-FINAL.iso")
MANIFEST = os.path.join(E8, "art_manifest.json")
# E8-11: the language-alias build.  FINAL-B is the user-validated variant B
# (native-dxt1 cardh + full DXT1 cardm); FINAL-C starts from it and points the
# four non-``_s`` records per size at the ``_s`` extent/size (ESTADO-E8.md
# 9.12).  Both are read-only for every other command.
FINAL_B_ISO = os.path.join(E8, "TF1-E8-FINAL-B.iso")
FINAL_C_ISO = os.path.join(E8, "TF1-E8-FINAL-C.iso")
# The card-art sizes and the languages actually present in the Spanish image
# (``j`` Japanese is absent): five files per size, ``_s`` the grown one.
ART_SIZES = "hm"
ART_LANGS = "efgis"
ART_OTHER_LANGS = "efgi"
# The E8-4b / E8-4c / frozen user-tested ISOs and the E6 source are read-only
# inputs: ``iso`` refuses to write any of them.
PROTECTED_ISOS = {
    os.path.abspath(os.path.join(E8, "TF1-E8-ART.iso")),
    os.path.abspath(os.path.join(E8, "TF1-E8-ART2.iso")),
    os.path.abspath(os.path.join(E8, "TF1-E8-FINAL-128x56-f4-16.iso")),
    os.path.abspath(FINAL_B_ISO),
    os.path.abspath(E6_ISO),
}
# DXT1 is lossy; ``accept`` requires the decode-back within this mean RGB error.
DXT1_ACCEPT_MAE = 18.0
# ESTADO-E8.md 9.9: the native cardh texture carries a flat green chroma-key
# (0,97,0).  Mask tolerance and the deterministic sample used to locate the
# stable key region.  48 evenly spaced native cards, seated by CardID.
GREEN_TOL = 6
MASK_SAMPLE_N = 48
MASK_REF_CARDS = (6477, 6312, 6310)   # the cards proven in 9.9 / WINNER_*
# ``accept``/``build`` reject a native cardh decode-back above this MAE.
CARDH_ACCEPT_MAE = 18.0
# 1 byte per pixel: 1 where the 128x62 cardh canvas is actually stored (the
# bottom-right 64x2 corner is beyond the 496 stored blocks, exactly as native).
CARDH_STORED = bytes(
    1 if ((y // 4) * t.CARDH_BLOCKS_PER_ROW + x // 4)
    < t.CARDH_BODY_SIZE // 8 else 0
    for y in range(t.CARDH_H) for x in range(t.CARDH_W))


def masked_mean_rgb_error(a: bytes, b: bytes, mask: bytes) -> float:
    """Mean absolute RGB error over the pixels where ``mask`` is 1."""
    total = n = 0
    for i in range(len(mask)):
        if not mask[i]:
            continue
        o = i * 4
        total += (abs(a[o] - b[o]) + abs(a[o + 1] - b[o + 1])
                  + abs(a[o + 2] - b[o + 2]))
        n += 3
    return total / max(n, 1)

# --- parameters fixed by ESTADO-E8.md 9.1/9.2/9.3 --------------------------
CARDH_W, CARDH_H, CARDH_COLORS = 64, 56, 76      # 4096 B exactly
CARDM_W, CARDM_H, CARDM_COLORS = 32, 24, 256     # 2000 B in 2048
# Per-container GIM pixel format.  The historical default is format 5 (INDEX8).
CARDH_FMT, CARDM_FMT = t.FMT_INDEX8, t.FMT_INDEX8
# Private region (bytes) reserved per card, always a multiple of the 2048-byte
# table-slot unit.  A GIM larger than one slot spans several consecutive slots:
# the table entry points at the region start and the next card's region begins
# ``region // SLOT_UNIT`` slot ids later.  Defaults reproduce the E8-4b layout
# (cardh 4096 = 2 slots, cardm 2048 = 1 slot).
SLOT_UNIT = 1 << t.SLOT_SHIFT  # 2048 B per table-slot id
CARDH_REGION, CARDM_REGION = 4096, 2048
CARDH_SLOT0, CARDM_SLOT0 = 5066, 2539
CARDH_LBA = 3646                                 # free region start
CARDM_LBA = 251955                               # old cardh_s.cip extent
E6_CARDH_SHA = ("c0e0fd9b5ba3d2e038ac8801624187f39dd3000197b88510"
                "358f9c196a4d1836")
E6_CARDM_SHA = ("d2b2d2b0fd168c2c593d43fa390d29259b5061250fb693dc"
                "f1693867513ec95b")
PREVIEW_CARDS = [4661, 4665, 4671]
PREVIEW_VARIANTS = [(64, 56, 76, t.FMT_INDEX8),
                    (64, 48, 204, t.FMT_INDEX8)]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Card list and source containers
# ---------------------------------------------------------------------------
def read_cardids(path: str = CARDS_TSV) -> list[int]:
    """CardIDs in the order of ``datos/cartas_18.tsv`` (the E8-4 order)."""
    ids: list[int] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            ids.append(int(line.split("\t")[1]))
    if len(ids) != 18:
        raise ValueError(f"{path}: expected 18 CardIDs, found {len(ids)}")
    return ids


def read_card_names(path: str = os.path.join(ART_SRC, "manifest.tsv")) -> dict:
    """``{cardid: nombre_es}`` from ``art_src/manifest.tsv``."""
    names = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            cols = line.split("\t")
            names[int(cols[0])] = cols[1]
    return names


def assign_cardh_place(cardids: list[int], spec: str = "cover") -> dict:
    """Map each CardID to its cardh placement mode.

    ``spec`` is one of ``PLACE_MODES`` (applied to all cards) or ``"abc"`` (the
    deterministic groups of 6 in ``cards_tsv`` order: first 6 cover, next 6
    left, last 6 contain).
    """
    if spec in PLACE_MODES:
        return {cid: spec for cid in cardids}
    if spec == PLACE_SOURCE:
        if len(cardids) % len(PLACE_MODES):
            raise ValueError(f"abc needs a CardID count divisible by "
                             f"{len(PLACE_MODES)}, got {len(cardids)}")
        per = len(cardids) // len(PLACE_MODES)
        out: dict[int, str] = {}
        for g, mode in enumerate(PLACE_MODES):
            for cid in cardids[g * per:(g + 1) * per]:
                out[cid] = mode
        return out
    raise ValueError(f"unknown cardh placement {spec!r} (use "
                     f"{'|'.join(PLACE_MODES)}|{PLACE_SOURCE})")


def print_cardh_place(place_by_cid: dict, spec: str, ref: int) -> None:
    """Plain-language line naming the CardIDs and names of each A/B/C group."""
    names = read_card_names()
    print(f"cardh placement spec {spec!r}, native reference CardID {ref}")
    for mode in PLACE_MODES:
        ids = [cid for cid in place_by_cid if place_by_cid[cid] == mode]
        if not ids:
            continue
        print(f"  group {mode}: " + ", ".join(
            f"CardID {cid} = {names.get(cid, '?')}" for cid in ids))


def source_container(explicit: str | None, inner: str):
    """Bytes of a container: an explicit file, or read out of the E6 ISO."""
    if explicit:
        with open(explicit, "rb") as fh:
            return fh.read()
    iso = Iso9660(E6_ISO)
    try:
        return iso.read_file(inner)
    finally:
        iso.close()


# ---------------------------------------------------------------------------
# Art preparation (shared by build, preview and accept)
# ---------------------------------------------------------------------------
def prepare_art(cardid: int, w: int, h: int, colors: int, fmt: int,
                resample: str = "area", dither: bool = False,
                art_src: str = ART_SRC) -> dict:
    """PNG -> the exact canvas + indexed GIM that ``build``/``inject`` emit.

    ``fmt`` is the GIM pixel format (``t.FMT_INDEX4`` or ``t.FMT_INDEX8``) and
    is threaded from the ``--cardh-format``/``--cardm-format`` CLI flags.
    """
    png_path = os.path.join(art_src, f"{cardid}.png")
    png_w, png_h, rgba = t.read_png(png_path)
    cw, ch, cropped = t.cover_crop(rgba, png_w, png_h, w, h)
    if resample == "area":
        scaled = t.resize_area(cropped, cw, ch, w, h)
    elif resample == "nearest":
        scaled = t.resize_nearest(cropped, cw, ch, w, h)
    else:
        raise ValueError(f"unknown resample mode {resample!r}")
    palette, indices, n_colours = t.quantise_palette(
        scaled, colors, dither=dither, width=w, height=h)
    palette = palette[:colors * 4]
    canvas = bytearray(w * h * 4)
    for i, idx in enumerate(indices):
        canvas[i * 4:i * 4 + 4] = palette[idx * 4:idx * 4 + 4]
    gim = t.build_gim_indexed(w, h, fmt, palette, indices, colors)
    return {"gim": gim, "canvas": bytes(canvas), "colors": n_colours,
            "fmt": fmt, "w": w, "h": h, "crop": (cw, ch),
            "png": (png_w, png_h)}


def decode_gim(gim: bytes) -> tuple[int, int, bytes]:
    tex = t.GimTexture(gim)
    w, h, rgba = tex.to_pixels()
    return w, h, rgba


def prepare_dxt1_art(cardid: int, w: int, h: int, resample: str = "area",
                     art_src: str = ART_SRC, fit: str = "cover") -> dict:
    """PNG -> the native cardm DXT1 body plus the truecolour canvas it encodes.

    DXT1 is full colour, so ``colors`` and ``dither`` do not apply; the canvas
    is pixel-identical to ``prepare_art``'s input before quantisation.  ``w``
    and ``h`` must be multiples of 4 (64x64 emits 2048 bytes exactly).

    ``fit`` selects how the source maps to the w x h canvas: ``"cover"`` (the
    historical default) centre-crops to the canvas aspect before resampling,
    which is right for the square cropped illustrations; ``"stretch"`` scales
    the whole source directly, so a portrait full-card render keeps its frame,
    name and text when squashed into the 64x64 mini-card (as native does).
    """
    png_path = os.path.join(art_src, f"{cardid}.png")
    png_w, png_h, rgba = t.read_png(png_path)
    if fit == "stretch":
        cw, ch, cropped = png_w, png_h, rgba
    elif fit == "cover":
        cw, ch, cropped = t.cover_crop(rgba, png_w, png_h, w, h)
    else:
        raise ValueError(f"unknown fit mode {fit!r}")
    if resample == "area":
        scaled = t.resize_area(cropped, cw, ch, w, h)
    elif resample == "nearest":
        scaled = t.resize_nearest(cropped, cw, ch, w, h)
    else:
        raise ValueError(f"unknown resample mode {resample!r}")
    payload = t.encode_dxt1_swapped(scaled, w, h)
    return {"payload": payload, "canvas": scaled, "codec": "dxt1",
            "w": w, "h": h, "crop": (cw, ch), "png": (png_w, png_h),
            "fit": fit}


# ---------------------------------------------------------------------------
# Native cardh codec (E8-9 / ESTADO-E8.md 9.9)
# ---------------------------------------------------------------------------
def native_cardh_header(src_h: bytes) -> bytes:
    """The 128-byte GIM template copied verbatim from a native cardh slot.

    Hard-asserts the header is identical across every reference card, so the
    "constant template" claim cannot silently drift.
    """
    c = t.Container.from_bytes(src_h)
    ref = None
    for cid in MASK_REF_CARDS:
        arts = c.arts(cid)
        if not arts:
            raise ValueError(f"reference CardID {cid} has no art in the source")
        hdr = c.payload(arts[0])[:t.CARDH_HEADER_SIZE]
        if hdr[:len(t.GIM_MAGIC)] != t.GIM_MAGIC:
            raise ValueError(f"CardID {cid} slot is not a GIM template: "
                             f"{hdr[:16]!r}")
        if ref is None:
            ref = hdr
        elif hdr != ref:
            raise ValueError(f"CardID {cid} header differs from "
                             f"{MASK_REF_CARDS[0]}'s")
    return ref


def native_green_mask(src_h: bytes):
    """Locate the flat green chroma-key from native cardh decodes.

    Returns ``(mask_or_None, evidence)``.  The applied mask is the pixel set
    that is green in *every* one of ``MASK_SAMPLE_N`` evenly spaced native
    cards (a fixed template).  It is only accepted as "reliable" when it is
    non-empty, fully contained in each reference card's mask, and the
    intersections of two disjoint halves of the sample differ by at most 1% of
    the card area.  Otherwise the caller builds WITHOUT the mask.
    """
    c = t.Container.from_bytes(src_h)
    candidates = [cid for cid in range(c.min_card, c.max_card + 1)
                  if c.arts(cid) and cid not in read_cardids()]
    step = max(1, len(candidates) // MASK_SAMPLE_N)
    sample = candidates[::step][:MASK_SAMPLE_N]
    masks = []
    for cid in sample:
        slot = t.decode_cardh_slot(c.payload(c.arts(cid)[0]))
        masks.append(t.green_key_mask(slot, t.CARDH_W, t.CARDH_H, GREEN_TOL))
    area = t.CARDH_W * t.CARDH_H
    quorum = max(1, (95 * len(masks) + 99) // 100)   # green in >=95% of cards

    def majority(ms):
        return bytes(1 if sum(m[i] for m in ms) >= quorum else 0 for i in range(area))

    core = majority(masks)
    half = len(masks) // 2
    ia = majority(masks[:half]) if masks[:half] else core
    ib = majority(masks[half:]) if masks[half:] else core
    ref_missing = []
    for cid in MASK_REF_CARDS:
        slot = t.decode_cardh_slot(c.payload(c.arts(cid)[0]))
        r = t.green_key_mask(slot, t.CARDH_W, t.CARDH_H, GREEN_TOL)
        ref_missing.append(sum(1 for i in range(area) if core[i] and not r[i]))
    pixels = sum(core)
    missing_limit = max(2, (2 * pixels + 99) // 100)   # 2% of the mask
    instability = sum(1 for i in range(area) if ia[i] != ib[i])
    ref_ok = all(m <= missing_limit for m in ref_missing)
    evidence = {
        "sample": sample, "sample_count": len(masks), "quorum": quorum,
        "core_pixels": pixels, "reference_missing": ref_missing,
        "reference_missing_limit": missing_limit,
        "reference_contained": ref_ok, "half_disagreement": instability,
        "half_disagreement_limit": area // 50,
    }
    reliable = (pixels > 0 and ref_ok and instability <= area // 50)
    return (core if reliable else None), evidence


# --- cardh placement modes (E8-10 A/B/C) ---------------------------------
# The native cardh texture is not the illustration alone: the illustration
# occupies the left ~78 px of the 128-wide frame and the rest is the flat green
# chroma-key plus the game's name-band / box pieces.  These three modes isolate
# the placement so one in-game look can pick it (ESTADO-E8.md 9.11).
PLACE_MODES = ("cover", "left", "contain")
PLACE_LEFT_W = 78                       # illustration width for "left"
PLACE_SOURCE = "abc"                    # grouped spec: 6 cover, 6 left, 6 contain
PLACE_REF_CARD = MASK_REF_CARDS[0]      # native slot the native bytes come from


def native_cardh_reference(src_h: bytes, ref_cid: int = PLACE_REF_CARD) -> bytes:
    """Decode the 128x62 RGBA frame of a reference *native* cardh slot.

    ``left`` and ``contain`` keep this frame as their background so the green
    chroma-key and the game's UI pieces stay byte-for-byte as native expects.
    """
    c = t.Container.from_bytes(src_h)
    arts = c.arts(ref_cid)
    if not arts:
        raise ValueError(f"reference CardID {ref_cid} has no art in the source")
    slot = c.payload(arts[0])
    if len(slot) < t.CARDH_SLOT_SIZE:
        raise ValueError(f"reference CardID {ref_cid} slot is {len(slot)} B, "
                         f"need {t.CARDH_SLOT_SIZE}")
    return t.decode_cardh_slot(slot)


def _fit_size(sw: int, sh: int, dw: int, dh: int) -> tuple[int, int]:
    """Largest ``sw:sh`` fit inside ``dw x dh`` (contain), never upscaling."""
    if sw * dh >= sh * dw:
        w, h = dw, max(1, sh * dw // sw)
    else:
        w, h = max(1, sw * dh // sh), dh
    return min(w, dw), min(h, dh)


def _sub_mask(mask: bytes | None, x: int, y: int, w: int, h: int):
    """The ``w x h`` window of a 128x62 one-byte-per-pixel mask at (x, y)."""
    if mask is None:
        return None
    out = bytearray(w * h)
    for r in range(h):
        row = (y + r) * t.CARDH_W + x
        out[r * w:(r + 1) * w] = mask[row:row + w]
    return bytes(out)


def compose_cardh_canvas(rgba: bytes, png_w: int, png_h: int, place: str,
                         ref_canvas: bytes | None, mask: bytes | None,
                         resample: str = "area") -> dict:
    """Compose the 128x62 cardh RGBA canvas for one placement mode.

    ``cover``   centre-crops the illustration to the whole 128x62 frame (the
                historical E8-9 output; no native background is used).
    ``left``    centre-crops the illustration to 78x62 and writes it at x=0;
                x=78..127 is the reference native frame, verbatim.
    ``contain`` fits the whole illustration (no crop) inside 128x62, centred;
                every remaining pixel is the reference native frame, verbatim.

    The green chroma-key ``mask`` is applied to the illustration tile only, so
    the native background is never repainted.  Returns the canvas plus the tile
    geometry and crop for the manifest/evidence.
    """
    if place not in PLACE_MODES:
        raise ValueError(f"unknown cardh placement {place!r}")
    if place == "cover":
        cw, ch, cropped = t.cover_crop(rgba, png_w, png_h, t.CARDH_W,
                                       t.CARDH_H)
        tw, th = t.CARDH_W, t.CARDH_H
        x0 = y0 = 0
        base = None
    else:
        if ref_canvas is None or len(ref_canvas) != t.CARDH_W * t.CARDH_H * 4:
            raise ValueError(f"cardh placement {place!r} needs the reference "
                             f"native frame")
        base = bytearray(ref_canvas)
        if place == "left":
            tw, th = PLACE_LEFT_W, t.CARDH_H
            cw, ch, cropped = t.cover_crop(rgba, png_w, png_h, tw, th)
            x0 = y0 = 0
        else:                                 # contain
            tw, th = _fit_size(png_w, png_h, t.CARDH_W, t.CARDH_H)
            cw, ch, cropped = png_w, png_h, rgba
            x0 = (t.CARDH_W - tw) // 2
            y0 = (t.CARDH_H - th) // 2
    if resample == "area":
        scaled = t.resize_area(cropped, cw, ch, tw, th)
    elif resample == "nearest":
        scaled = t.resize_nearest(cropped, cw, ch, tw, th)
    else:
        raise ValueError(f"unknown resample mode {resample!r}")
    if mask is not None:
        scaled = t.apply_green_mask(scaled, tw, th,
                                    _sub_mask(mask, x0, y0, tw, th))
    if base is None:
        canvas = bytearray(scaled)
    else:
        canvas = base
        _blit(canvas, t.CARDH_W, scaled, tw, th, x0, y0)
        # Hard assertion: every pixel the illustration does not cover must be
        # the reference native frame, byte for byte.
        for r in range(t.CARDH_H):
            for c in range(t.CARDH_W):
                if x0 <= c < x0 + tw and y0 <= r < y0 + th:
                    continue
                o = (r * t.CARDH_W + c) * 4
                if canvas[o:o + 4] != ref_canvas[o:o + 4]:
                    raise ValueError(f"cardh {place}: native pixel {c},{r} "
                                     f"was not preserved verbatim")
    return {"canvas": bytes(canvas), "tile": (tw, th), "pos": (x0, y0),
            "crop": (cw, ch), "place": place}


def prepare_cardh_native(cardid: int, header: bytes, mask,
                         resample: str = "area", art_src: str = ART_SRC,
                         place: str = "cover",
                         ref_canvas: bytes | None = None) -> dict:
    """PNG -> native cardh slot bytes (header + 128x62 swapped DXT1 body)."""
    png_path = os.path.join(art_src, f"{cardid}.png")
    png_w, png_h, rgba = t.read_png(png_path)
    comp = compose_cardh_canvas(rgba, png_w, png_h, place,
                                ref_canvas if place != "cover" else None,
                                mask, resample)
    slot = t.encode_cardh_native(header, comp["canvas"])
    return {"slot": slot, "canvas": comp["canvas"], "codec": "native-dxt1",
            "w": t.CARDH_W, "h": t.CARDH_H, "crop": comp["crop"],
            "png": (png_w, png_h), "masked": mask is not None,
            "place": place, "tile": comp["tile"], "pos": comp["pos"]}


def mean_rgb_error(a: bytes, b: bytes) -> float:
    """Mean absolute RGB error between two RGBA8 buffers (alpha ignored)."""
    if len(a) != len(b):
        raise ValueError(f"size mismatch {len(a)} != {len(b)}")
    total = 0
    n = 0
    for i in range(0, len(a), 4):
        total += (abs(a[i] - b[i]) + abs(a[i + 1] - b[i + 1])
                  + abs(a[i + 2] - b[i + 2]))
        n += 3
    return total / max(n, 1)


def region_mean_rgb_error(a: bytes, b: bytes, stride: int, x0: int,
                          x1: int) -> float:
    """Mean abs RGB error over columns ``[x0, x1)`` of a width-``stride``
    RGBA frame.  Used to show, on the decoded cardh frame, that the left
    illustration columns were replaced while the right native columns were
    preserved by the DXT1 round-trip (E8-10 left placement)."""
    total = n = 0
    height = len(a) // (stride * 4)
    for y in range(height):
        base = y * stride * 4
        for x in range(x0, x1):
            o = base + x * 4
            total += (abs(a[o] - b[o]) + abs(a[o + 1] - b[o + 1])
                      + abs(a[o + 2] - b[o + 2]))
            n += 3
    return total / max(n, 1)


# ---------------------------------------------------------------------------
# Container growth (T7)
# ---------------------------------------------------------------------------
def assert_regions_exclusive(blob: bytes, regions) -> None:
    """Hard assertion: no CardID resolves to a point inside a foreign region.

    ``regions`` is a list of ``(cardid, slot, region_bytes)`` for the freshly
    appended private regions.  Every art slot of every CardID in the container
    that falls inside one of those ranges must be exactly that region's start
    and must belong to that region's own CardID.  This is what makes a
    multi-slot region safe: no donor table entry may point inside it.
    """
    c = t.Container.from_bytes(blob)
    starts = {}
    for cid, slot, region in regions:
        start = slot << t.SLOT_SHIFT
        starts[start] = (cid, start + region)
    for cid in range(c.min_card, c.max_card + 1):
        for slot in c.arts(cid):
            off = slot << t.SLOT_SHIFT
            for start, (owner, end) in starts.items():
                if start <= off < end and (off != start or owner != cid):
                    raise ValueError(
                        f"CardID {cid} slot {slot} (offset {off}) points "
                        f"inside CardID {owner}'s region [{start}, {end})")


def build_container(src_blob: bytes, cardids: list[int], preps: dict,
                    base_slot: int, region: int, fmt: int,
                    codec: str = "gim"):
    """Append one private ``region``-byte area per CardID, rewrite the entries.

    ``codec`` selects the payload each card carries: ``"gim"`` (default) reads
    ``preps[cid]["gim"]`` and validates its pixel format against ``fmt``;
    ``"dxt1"`` reads ``preps[cid]["payload"]`` and requires it to fill the
    region exactly (64x64 BC1 == 2048 B).

    ``region`` is the per-card reservation in bytes and must be a multiple of
    the 2048-byte table-slot unit (``SLOT_UNIT``).  Card N's GIM is written at
    the start of its own region, the next card's slot id advances by
    ``region // SLOT_UNIT``, and the file grows by exactly ``region`` bytes per
    card.  Hard-asserts that each GIM fits its region and that no CardID's
    table entry points inside another card's region.  With ``region == stride``
    this is byte-identical to the old single-slot build.

    ``fmt`` is the GIM format the prepared payloads must carry; it is verified
    against each payload so a mismatched CLI flag cannot silently ship the
    wrong format.  Returns ``(blob, {cardid: slot}, container)``.
    """
    if region <= 0 or region % SLOT_UNIT:
        raise ValueError(f"region {region} B is not a positive multiple of "
                         f"{SLOT_UNIT} B")
    c = t.Container.from_bytes(src_blob)
    if (base_slot << t.SLOT_SHIFT) != len(src_blob):
        raise ValueError(f"base_slot {base_slot} starts at "
                         f"{base_slot << t.SLOT_SHIFT} but the source is "
                         f"{len(src_blob)} B")
    step = region // SLOT_UNIT
    blob = bytearray(src_blob)
    entries: dict[int, int] = {}
    slot = base_slot
    for cid in cardids:
        if codec == "native-dxt1":
            gim = preps[cid]["slot"]
            if len(gim) != region:
                raise ValueError(f"CardID {cid}: native cardh slot {len(gim)} B "
                                 f"does not fill its {region} B region")
            if gim[:len(t.GIM_MAGIC)] != t.GIM_MAGIC:
                raise ValueError(f"CardID {cid}: native cardh slot does not "
                                 f"start with the GIM template")
        elif codec == "dxt1":
            gim = preps[cid]["payload"]
            if len(gim) != region:
                raise ValueError(f"CardID {cid}: DXT1 payload {len(gim)} B "
                                 f"does not fill its {region} B region")
        else:
            gim = preps[cid]["gim"]
            got_fmt = t.GimTexture(gim).fmt
            if got_fmt != fmt:
                raise ValueError(f"CardID {cid}: prepared GIM is format "
                                 f"{got_fmt}, expected {fmt}")
            if len(gim) > region:
                raise ValueError(f"CardID {cid}: GIM {len(gim)} B does not fit "
                                 f"its {region} B region")
        off = slot << t.SLOT_SHIFT
        if off != len(blob):
            raise ValueError(f"CardID {cid}: slot {slot} starts at {off} but "
                             f"the file ends at {len(blob)}")
        blob += gim + b"\x00" * (region - len(gim))
        entries[cid] = slot
        slot += step
    for cid, s in entries.items():
        entry_off = c.table_top + (cid - c.min_card) * t.ENTRY_SIZE
        struct.pack_into("<II", blob, entry_off, s, 0)
    struct.pack_into("<I", blob, 0x04, len(blob))
    assert_regions_exclusive(bytes(blob),
                             [(cid, entries[cid], region) for cid in cardids])
    return bytes(blob), entries, c


# ---------------------------------------------------------------------------
# preview (T6)
# ---------------------------------------------------------------------------
def _blit(dst: bytearray, dw: int, tile: bytes, tw: int, th: int,
          x: int, y: int) -> None:
    for r in range(th):
        so = r * tw * 4
        do = ((y + r) * dw + x) * 4
        dst[do:do + tw * 4] = tile[so:so + tw * 4]


def _frame(dst: bytearray, dw: int, x: int, y: int, w: int, h: int,
           colour=(255, 255, 255, 255)) -> None:
    for r in (y, y + h - 1):
        for c in range(x, x + w):
            o = (r * dw + c) * 4
            dst[o:o + 4] = bytes(colour)
    for r in range(y, y + h):
        for c in (x, x + w - 1):
            o = (r * dw + c) * 4
            dst[o:o + 4] = bytes(colour)


def parse_variants(spec: str) -> list:
    """``"WxH/COLORS/FMT,..."`` -> ``[(w, h, colors, fmt), ...]``."""
    variants = []
    for part in spec.split(","):
        w_h, colors, fmt = part.strip().split("/")
        w, h = w_h.split("x")
        variants.append((int(w), int(h), int(colors), int(fmt)))
    return variants


def _source_tile(cid: int, w: int, h: int, zoom: int, resample: str,
                 art_src: str) -> bytes:
    """The truecolour source illustration, cover-cropped/resized to w x h."""
    png_path = os.path.join(art_src, f"{cid}.png")
    png_w, png_h, rgba = t.read_png(png_path)
    cw, ch, cropped = t.cover_crop(rgba, png_w, png_h, w, h)
    if resample == "area":
        scaled = t.resize_area(cropped, cw, ch, w, h)
    elif resample == "nearest":
        scaled = t.resize_nearest(cropped, cw, ch, w, h)
    else:
        raise ValueError(f"unknown resample mode {resample!r}")
    return t.resize_nearest(scaled, w, h, w * zoom, h * zoom)


def cmd_preview(args) -> int:
    cards = [int(x) for x in args.cards.split(",")] if args.cards else PREVIEW_CARDS
    variants = parse_variants(args.variants) if args.variants else PREVIEW_VARIANTS
    zoom = args.zoom
    margin, gap, inner = 8, 8, 12
    col_w, col_h, col_x = [], [], []
    x = margin
    for w, h, _colors, _fmt in variants:
        cw = 2 * w * zoom + inner if args.source else w * zoom
        col_w.append(cw)
        col_h.append(h * zoom)
        col_x.append(x)
        x += cw + 2 + gap
    sheet_w = x - gap + margin
    row_h = max(col_h)
    sheet_h = margin * 2 + len(cards) * (row_h + 2) + (len(cards) - 1) * gap
    sheet = bytearray(bytes((40, 40, 40, 255)) * (sheet_w * sheet_h))
    print(f"preview sheet {sheet_w}x{sheet_h}, zoom {zoom}; columns = "
          f"{[f'{w}x{h}/{c}/f{f}' for w, h, c, f in variants]}"
          f"{' (+ source)' if args.source else ''}")
    ok = True
    for row, cid in enumerate(cards):
        for col, (w, h, colors, fmt) in enumerate(variants):
            prep = prepare_art(cid, w, h, colors, fmt, resample=args.resample,
                               dither=args.dither, art_src=args.art_src)
            dw, dh, rgba = decode_gim(prep["gim"])
            same = (dw, dh) == (w, h) and rgba == prep["canvas"]
            ok = ok and same
            tile_w, tile_h = w * zoom, h * zoom
            zoomed = t.resize_nearest(rgba, w, h, tile_w, tile_h)
            tile_png = os.path.join(
                E8, f"art_prev_{cid}_{w}x{h}_{colors}.png")
            t.write_png(tile_png, tile_w, tile_h, zoomed)
            x0 = col_x[col]
            y0 = margin + row * (row_h + 2 + gap)
            if args.source:
                src = _source_tile(cid, w, h, zoom, args.resample, args.art_src)
                _blit(sheet, sheet_w, src, tile_w, tile_h, x0 + 2, y0 + 2)
                _frame(sheet, sheet_w, x0, y0, tile_w + 4, tile_h + 4)
                rx = x0 + tile_w + 4 + inner
            else:
                rx = x0
            _blit(sheet, sheet_w, zoomed, tile_w, tile_h, rx + 2, y0 + 2)
            _frame(sheet, sheet_w, rx, y0, tile_w + 4, tile_h + 4)
            print(f"  CardID {cid} {w}x{h}/{colors}/f{fmt}: crop "
                  f"{prep['crop'][0]}x{prep['crop'][1]}, GIM "
                  f"{len(prep['gim'])} B, {prep['colors']} colours, "
                  f"decode-back identical: {same} -> {os.path.basename(tile_png)}")
    out = args.out
    t.write_png(out, sheet_w, sheet_h, bytes(sheet))
    print(f"wrote {out}")
    return 0 if ok else 1


# ---------------------------------------------------------------------------
# build (T7)
# ---------------------------------------------------------------------------
def cmd_build(args) -> int:
    cardids = read_cardids(args.cards_tsv)
    src_h = source_container(args.cardh_in, INNER_H)
    src_m = source_container(args.cardm_in, INNER_M)
    print(f"source cardh: {len(src_h)} B sha256 {sha256(src_h)[:16]}")
    print(f"source cardm: {len(src_m)} B sha256 {sha256(src_m)[:16]}")

    cardh_native = args.cardh_codec == "native-dxt1"
    header = None
    mask = None
    mask_evidence = None
    place_by_cid = None
    ref_canvas = None
    if cardh_native:
        if args.cardh_region != t.CARDH_SLOT_SIZE:
            raise SystemExit(f"native cardh needs --cardh-region "
                             f"{t.CARDH_SLOT_SIZE} (one 4096 B slot)")
        header = native_cardh_header(src_h)
        mask, mask_evidence = native_green_mask(src_h)
        print(f"cardh native codec: header {t.CARDH_HEADER_SIZE} B from "
              f"native slot copied verbatim {header[:12]!r}")
        print(f"green chroma-key: sample {mask_evidence['sample_count']} "
              f"cards, quorum {mask_evidence['quorum']}, stable core "
              f"{mask_evidence['core_pixels']} px, reference missing "
              f"{mask_evidence['reference_missing']}/"
              f"{mask_evidence['reference_missing_limit']}, half-disagreement "
              f"{mask_evidence['half_disagreement']}/"
              f"{mask_evidence['half_disagreement_limit']} -> "
              f"{'APPLIED' if mask is not None else 'NOT APPLIED (unreliable)'}")
        try:
            place_by_cid = assign_cardh_place(cardids, args.cardh_place)
        except ValueError as exc:
            raise SystemExit(str(exc))
        if any(m != "cover" for m in place_by_cid.values()):
            ref_canvas = native_cardh_reference(src_h, args.cardh_place_ref)
        print_cardh_place(place_by_cid, args.cardh_place, args.cardh_place_ref)

    preps_h, preps_m = {}, {}
    for cid in cardids:
        if cardh_native:
            preps_h[cid] = prepare_cardh_native(
                cid, header, mask, args.resample, args.art_src,
                place_by_cid[cid], ref_canvas)
        else:
            preps_h[cid] = prepare_art(cid, args.cardh_w, args.cardh_h,
                                       args.cardh_colors, args.cardh_format,
                                       args.resample, args.dither, args.art_src)
        if args.cardm_codec == "dxt1":
            preps_m[cid] = prepare_dxt1_art(cid, args.cardm_w, args.cardm_h,
                                            args.resample, args.cardm_art_src,
                                            args.cardm_fit)
        else:
            preps_m[cid] = prepare_art(cid, args.cardm_w, args.cardm_h,
                                       args.cardm_colors, args.cardm_format,
                                       args.resample, args.dither, args.art_src)

    new_h, slots_h, c_h = build_container(src_h, cardids, preps_h,
                                          CARDH_SLOT0, args.cardh_region,
                                          args.cardh_format, args.cardh_codec)
    new_m, slots_m, c_m = build_container(src_m, cardids, preps_m,
                                          CARDM_SLOT0, args.cardm_region,
                                          args.cardm_format, args.cardm_codec)
    print(f"cardh region {args.cardh_region} B = "
          f"{args.cardh_region // SLOT_UNIT} slots -> step "
          f"{args.cardh_region // SLOT_UNIT}")
    print(f"cardm region {args.cardm_region} B = "
          f"{args.cardm_region // SLOT_UNIT} slots -> step "
          f"{args.cardm_region // SLOT_UNIT}")

    with open(args.out_cardh, "wb") as fh:
        fh.write(new_h)
    with open(args.out_cardm, "wb") as fh:
        fh.write(new_m)

    manifest = {"params": {"cardh": [args.cardh_w, args.cardh_h,
                                      args.cardh_colors, args.cardh_format],
                           "cardm": [args.cardm_w, args.cardm_h,
                                      args.cardm_colors, args.cardm_format],
                           "cardh_codec": args.cardh_codec,
                           "cardh_place": args.cardh_place,
                           "cardh_place_ref": args.cardh_place_ref,
                           "cardh_place_groups": ({
                               m: [cid for cid in cardids
                                   if place_by_cid.get(cid) == m]
                               for m in PLACE_MODES} if place_by_cid else None),
                           "cardm_codec": args.cardm_codec,
                           "cardm_art_src": os.path.relpath(args.cardm_art_src,
                                                            ROOT),
                           "cardm_fit": args.cardm_fit,
                           "cardh_region": args.cardh_region,
                           "cardm_region": args.cardm_region,
                           "resample": args.resample, "dither": args.dither,
                           "green_mask": mask_evidence},
                "containers": {}, "cards": []}
    for key, path, blob, src in (("cardh", args.out_cardh, new_h, src_h),
                                 ("cardm", args.out_cardm, new_m, src_m)):
        manifest["containers"][key] = {
            "path": os.path.relpath(path, ROOT), "old_size": len(src),
            "new_size": len(blob), "old_sha256": sha256(src),
            "new_sha256": sha256(blob),
            "sectors": (len(blob) + SECTOR - 1) // SECTOR}
        print(f"== {key} ==")
        print(f"  {os.path.basename(path)}: {len(src)} B -> {len(blob)} B "
              f"({(len(blob) + SECTOR - 1) // SECTOR} sectors), sha256 "
              f"{sha256(blob)[:16]}")
        print(f"  table_top {c_h.table_top}, entry width {t.ENTRY_SIZE}; "
              f"total_size @0x04 = {struct.unpack_from('<I', blob, 0x04)[0]}")

    for cid in cardids:
        if args.cardm_codec == "dxt1":
            cardm_bytes = len(preps_m[cid]["payload"])
            cardm_colors = -1
        else:
            cardm_bytes = len(preps_m[cid]["gim"])
            cardm_colors = preps_m[cid]["colors"]
        if cardh_native:
            cardh_bytes = len(preps_h[cid]["slot"])
            cardh_colors = -1
        else:
            cardh_bytes = len(preps_h[cid]["gim"])
            cardh_colors = preps_h[cid]["colors"]
        rec = {"cardid": cid, "cardh_slot": slots_h[cid],
               "cardm_slot": slots_m[cid],
               "cardh_place": place_by_cid[cid] if place_by_cid else None,
               "cardh_bytes": cardh_bytes,
               "cardh_codec": args.cardh_codec,
               "cardm_bytes": cardm_bytes,
               "cardm_codec": args.cardm_codec,
               "cardh_colors": cardh_colors,
               "cardh_masked": preps_h[cid].get("masked"),
               "cardm_colors": cardm_colors}
        manifest["cards"].append(rec)
        print(f"  CardID {cid}: cardh slot {slots_h[cid]} ({cardh_bytes} B, "
              f"{args.cardh_codec}) · cardm slot {slots_m[cid]} "
              f"({cardm_bytes} B, {args.cardm_codec}, {cardm_colors} col)")
    with open(args.manifest, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
    print(f"wrote {args.manifest}")
    return 0


# ---------------------------------------------------------------------------
# iso (T8)
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# iso (T8)
# ---------------------------------------------------------------------------
def _assert_placement(iso_path: str, path_h: str, lba_h: int, alloc_h: int,
                      old_h, path_m: str, lba_m: int, alloc_m: int) -> None:
    """Hard fit + non-overlap assertions for the two relocated containers.

    ``cardh`` must land inside a genuinely free region; ``cardm`` must fit the
    extent ``cardh`` vacates; and neither new extent may intersect any other
    referenced extent (file or directory) of the image.  Sizes come from the
    actual built containers, so a grown region cannot silently overrun.
    """
    iso = Iso9660(iso_path)
    try:
        gaps = free_regions(iso)
        spans = [(iso.root.extent,
                  iso.root.extent + allocated_sectors(iso.root.size),
                  "<root dir>")]
        for path, e, _off in walk(iso):
            if path.lstrip("/") in (path_h, path_m):
                continue
            spans.append((e.extent, e.extent + allocated_sectors(e.size),
                          path))
    finally:
        iso.close()
    if not any(s <= lba_h and lba_h + alloc_h <= e for s, e in gaps):
        raise ValueError(f"{path_h}: LBA {lba_h}+{alloc_h} is not inside a "
                         f"free region of {iso_path}")
    old_end = old_h.extent + allocated_sectors(old_h.size)
    if not (old_h.extent <= lba_m and lba_m + alloc_m <= old_end):
        raise ValueError(f"{path_m}: LBA {lba_m}+{alloc_m} does not fit the "
                         f"vacated {path_h} extent [{old_h.extent}, {old_end})")
    for label, lba, alloc in (("cardh", lba_h, alloc_h),
                              ("cardm", lba_m, alloc_m)):
        for s, e, path in spans:
            if lba < e and s < lba + alloc:
                raise ValueError(f"{label} extent [{lba}, {lba + alloc}) "
                                 f"overlaps {path} [{s}, {e})")
    if lba_h < lba_m + alloc_m and lba_m < lba_h + alloc_h:
        raise ValueError(f"cardh [{lba_h}, {lba_h + alloc_h}) and cardm "
                         f"[{lba_m}, {lba_m + alloc_m}) overlap each other")


def cmd_iso(args) -> int:
    src, dst = args.src_iso, args.dst_iso
    if os.path.abspath(dst) == os.path.abspath(src):
        raise SystemExit("refusing to overwrite the source ISO")
    if not os.path.abspath(dst).startswith(os.path.abspath(E8) + os.sep):
        raise SystemExit(f"refusing to write outside {E8}")
    if os.path.abspath(dst) in PROTECTED_ISOS:
        raise SystemExit(f"refusing to overwrite the frozen ISO {dst}")
    with open(args.cardh, "rb") as fh:
        cardh = fh.read()
    with open(args.cardm, "rb") as fh:
        cardm = fh.read()
    print(f"copying {src} -> {dst} ({os.path.getsize(src)} B)")
    shutil.copyfile(src, dst)
    iso = Iso9660(dst)
    try:
        rec_h, e_h = find_record(iso, INNER_H)
        rec_m, e_m = find_record(iso, INNER_M)
    finally:
        iso.close()
    print(f"  {INNER_H}: old extent {e_h.extent} size {e_h.size} "
          f"record @ {rec_h}")
    print(f"  {INNER_M}: old extent {e_m.extent} size {e_m.size} "
          f"record @ {rec_m}")
    alloc_h = allocated_sectors(len(cardh))
    alloc_m = allocated_sectors(len(cardm))
    _assert_placement(dst, INNER_H, CARDH_LBA, alloc_h, e_h,
                      INNER_M, CARDM_LBA, alloc_m)
    print(f"  cardh -> LBA {CARDH_LBA} ({alloc_h} sectors) · cardm -> LBA "
          f"{CARDM_LBA} ({alloc_m} sectors): fit + non-overlap hard-asserted")
    with open(dst, "r+b") as fh:
        fh.seek(CARDH_LBA * SECTOR)
        fh.write(cardh)
        fh.seek(CARDM_LBA * SECTOR)
        fh.write(cardm)
    relocate_record(dst, rec_h, CARDH_LBA, len(cardh))
    relocate_record(dst, rec_m, CARDM_LBA, len(cardm))
    iso = Iso9660(dst)
    try:
        back_h = iso.read_file(INNER_H)
        back_m = iso.read_file(INNER_M)
        _r, e_h2 = find_record(iso, INNER_H)
        _r, e_m2 = find_record(iso, INNER_M)
    finally:
        iso.close()
    ok_h = back_h == cardh and e_h2.extent == CARDH_LBA and e_h2.size == len(cardh)
    ok_m = back_m == cardm and e_m2.extent == CARDM_LBA and e_m2.size == len(cardm)
    print(f"  new {INNER_H}: extent {e_h2.extent} size {e_h2.size} "
          f"readback identical: {ok_h}")
    print(f"  new {INNER_M}: extent {e_m2.extent} size {e_m2.size} "
          f"readback identical: {ok_m}")
    if not (ok_h and ok_m):
        raise SystemExit("ISO relocation round-trip FAILED")
    print(f"wrote {dst}")
    return 0


# ---------------------------------------------------------------------------
# language alias (E8-11 / FINAL-C)
# ---------------------------------------------------------------------------
def _art_path(size: str, lang: str) -> str:
    return f"PSP_GAME/USRDIR/card/card{size}_{lang}.cip"


def check_alias_iso(iso_path: str, ref_iso: str | None = None,
                    cardids: list[int] | None = None) -> int:
    """Read-only hard assertions for the language-alias build (FINAL-C).

    Every check prints its evidence and any violation raises ``AssertionError``.
    Pointed at FINAL-B this deliberately fails (the five languages are not yet
    one container); pointed at FINAL-C it passes.  ``ref_iso`` supplies the
    pre-alias records used to prove the vacated extents are unreferenced and to
    prove the ``_s`` containers are byte-identical.
    """
    if cardids is None:
        cardids = read_cardids()
    iso = Iso9660(iso_path)
    try:
        print("== (a) every size shares one extent + size across languages ==")
        target = {}
        for size in ART_SIZES:
            ref_path = _art_path(size, "s")
            _off, e = find_record(iso, ref_path)
            target[size] = (e.extent, e.size)
            print(f"  {size}: reference {ref_path} extent {e.extent} "
                  f"size {e.size}")
        for size in ART_SIZES:
            tgt_extent, tgt_size = target[size]
            for lang in ART_LANGS:
                path = _art_path(size, lang)
                off, e = find_record(iso, path)
                assert (e.extent, e.size) == (tgt_extent, tgt_size), (
                    f"{path}: extent/size ({e.extent}, {e.size}) != the _s "
                    f"record ({tgt_extent}, {tgt_size}); record sector "
                    f"{off // SECTOR}")

        print("== (b) all ten paths read one byte-identical container per size ==")
        for size in ART_SIZES:
            shas = {}
            for lang in ART_LANGS:
                data = iso.read_file(_art_path(size, lang))
                shas[lang] = (len(data), sha256(data))
            uniq = set(shas.values())
            assert len(uniq) == 1, (
                f"{size}: the five languages are NOT one container: {shas}")
            n, sh = next(iter(uniq))
            print(f"  {size}: {ART_LANGS} -> one {n} B container sha256 {sh}")

        if ref_iso:
            print("== (c) _s containers byte-identical to the reference ISO ==")
            ref = Iso9660(ref_iso)
            try:
                for size in ART_SIZES:
                    path = _art_path(size, "s")
                    a = iso.read_file(path)
                    b = ref.read_file(path)
                    assert a == b, f"{path}: _s container differs from {ref_iso}"
                    print(f"  {size}: {path} byte-identical to "
                          f"{os.path.basename(ref_iso)} (sha256 {sha256(a)})")
            finally:
                ref.close()

        print("== (d) the 18 CardIDs resolve to their own _s slots ==")
        c_h = t.Container.from_bytes(iso.read_file(INNER_H))
        c_m = t.Container.from_bytes(iso.read_file(INNER_M))
        step_h = CARDH_REGION // SLOT_UNIT
        step_m = CARDM_REGION // SLOT_UNIT
        for i, cid in enumerate(cardids):
            want_h = CARDH_SLOT0 + i * step_h
            want_m = CARDM_SLOT0 + i * step_m
            got_h, got_m = c_h.arts(cid), c_m.arts(cid)
            assert got_h == [want_h], (
                f"CardID {cid}: cardh arts {got_h} != [{want_h}]")
            assert got_m == [want_m], (
                f"CardID {cid}: cardm arts {got_m} != [{want_m}]")
        last_h = CARDH_SLOT0 + (len(cardids) - 1) * step_h
        last_m = CARDM_SLOT0 + (len(cardids) - 1) * step_m
        print(f"  {len(cardids)} CardIDs resolve to cardh "
              f"{CARDH_SLOT0}..{last_h} / cardm {CARDM_SLOT0}..{last_m}")

        if ref_iso:
            print("== (e) vacated extents of the eight records are unreferenced ==")
            vacated = []
            ref = Iso9660(ref_iso)
            try:
                for size in ART_SIZES:
                    for lang in ART_OTHER_LANGS:
                        path = _art_path(size, lang)
                        _o, e = find_record(ref, path)
                        vacated.append((path, e.extent,
                                        e.extent + allocated_sectors(e.size)))
            finally:
                ref.close()
            occupied = [(e.extent,
                         e.extent + allocated_sectors(e.size), p)
                        for p, e, _o in walk(iso)]
            occupied.append((iso.root.extent,
                             iso.root.extent + allocated_sectors(iso.root.size),
                             "<root>"))
            for path, s, end in vacated:
                hits = [(p, a, b) for a, b, p in occupied if a < end and s < b]
                assert not hits, (f"vacated extent of {path} [{s}, {end}) is "
                                  f"still referenced by {hits}")
                print(f"  vacated {path} [{s}, {end}) = {end - s} sectors "
                      f"unreferenced")
    finally:
        iso.close()
    return 0


def cmd_check(args) -> int:
    print(f"CHECK {args.iso} (reference {args.ref_iso})")
    check_alias_iso(args.iso, args.ref_iso)
    print("CHECK OK: language alias assertions all hold.")
    return 0


def cmd_alias(args) -> int:
    """Copy FINAL-B and alias the eight non-_s directory records to _s."""
    src, dst = args.src_iso, args.dst_iso
    if os.path.abspath(dst) == os.path.abspath(src):
        raise SystemExit("refusing to overwrite the source ISO")
    if not os.path.abspath(dst).startswith(os.path.abspath(E8) + os.sep):
        raise SystemExit(f"refusing to write outside {E8}")
    if os.path.abspath(dst) in PROTECTED_ISOS:
        raise SystemExit(f"refusing to overwrite {dst}")
    print(f"copying {src} -> {dst} ({os.path.getsize(src)} B)")
    shutil.copyfile(src, dst)
    iso = Iso9660(dst)
    try:
        aliases = []
        for size in ART_SIZES:
            ref_path = _art_path(size, "s")
            ref_off, ref_e = find_record(iso, ref_path)
            print(f"  {ref_path}: extent {ref_e.extent} size {ref_e.size} "
                  f"record @ {ref_off} (sector {ref_off // SECTOR})")
            for lang in ART_OTHER_LANGS:
                path = _art_path(size, lang)
                off, e = find_record(iso, path)
                old_end = e.extent + allocated_sectors(e.size)
                aliases.append((path, off, ref_e.extent, ref_e.size,
                                (e.extent, e.size)))
                print(f"  {path}: [{e.extent}, {old_end}) {e.size} B -> "
                      f"aliased to {ref_path} extent {ref_e.extent} size "
                      f"{ref_e.size}, record @ {off} (sector {off // SECTOR})")
    finally:
        iso.close()
    for path, off, extent, size, _old in aliases:
        relocate_record(dst, off, extent, size)
    print(f"rewrote {len(aliases)} directory records (extent + size, LE+BE)")

    changed = sector_diff(src, dst)
    rec_sectors = sorted({off // SECTOR for _p, off, _e, _s, _o in aliases})
    outside = [s for s in changed if s not in rec_sectors]
    print(f"  sectors changed vs {os.path.basename(src)}: {changed}")
    print(f"  directory-record sectors: {rec_sectors}")
    print(f"  changed outside the directory-record sectors: {len(outside)}")
    assert changed and set(changed) == set(rec_sectors), (
        f"changed sectors {changed} != the eight directory-record sectors "
        f"{rec_sectors}")

    check_alias_iso(dst, src)
    print(f"wrote {dst}")
    return 0


# ---------------------------------------------------------------------------
# accept (T9)
# ---------------------------------------------------------------------------
def entry_offsets(c: "t.Container", cardids: list[int]) -> set:
    allowed: set[int] = set()
    for cid in cardids:
        base = c.table_top + (cid - c.min_card) * t.ENTRY_SIZE
        allowed.update(range(base, base + t.ENTRY_SIZE))
    return allowed


def header_diff(src: bytes, built: bytes, c: "t.Container",
                cardids: list[int]) -> list[int]:
    diffs = [i for i in range(c.blob_base) if src[i] != built[i]]
    allowed = entry_offsets(c, cardids) | {4, 5, 6, 7}
    outside = [i for i in diffs if i not in allowed]
    return outside


def sector_diff(a_path: str, b_path: str,
                chunk_sectors: int = 8192) -> list[int]:
    """Sector indices whose 2048-byte contents differ (streamed)."""
    assert os.path.getsize(a_path) == os.path.getsize(b_path)
    changed: list[int] = []
    nsec = os.path.getsize(a_path) // SECTOR
    with open(a_path, "rb") as fa, open(b_path, "rb") as fb:
        idx = 0
        while idx < nsec:
            n = min(chunk_sectors, nsec - idx)
            fa.seek(idx * SECTOR)
            fb.seek(idx * SECTOR)
            ba = fa.read(n * SECTOR)
            bb = fb.read(n * SECTOR)
            for i in range(n):
                if ba[i * SECTOR:(i + 1) * SECTOR] != bb[i * SECTOR:(i + 1) * SECTOR]:
                    changed.append(idx + i)
            idx += n
    return changed


def cmd_selftest(args) -> int:
    """Deterministic regression checks for the T5 primitives."""
    # resize_area: 2x2 -> 1x1 box average, and identity when sizes match.
    src = bytes([10, 20, 30, 255, 30, 40, 50, 255,
                 50, 60, 70, 255, 70, 80, 90, 255])
    assert t.resize_area(src, 2, 2, 1, 1) == bytes([40, 50, 60, 255])
    assert t.resize_area(src, 2, 2, 2, 2) == src
    # cover_crop: identity at equal aspect, height crop for a wider target.
    assert t.cover_crop(src, 2, 2, 2, 2)[0:2] == (2, 2)
    assert t.cover_crop(src, 2, 2, 16, 8)[0:2] == (2, 1)
    # median-cut index alignment (regression: the first box split used to sort
    # the caller's pixel list in place, scrambling the output indices).
    grad = bytearray()
    for y in range(8):
        for x in range(8):
            grad += bytes([x * 31 % 256, y * 31 % 256,
                           (x * 7 + y * 11) % 256, 255])
    pal, idx, n = t.quantise_palette(bytes(grad), 8, width=8, height=8)
    centers = [pal[i * 4:i * 4 + 4] for i in range(n)]
    for i in range(64):
        px = grad[i * 4:i * 4 + 4]
        assert idx[i] == t._nearest_center(px, centers), (
            f"index {i} is {idx[i]}, nearest is {t._nearest_center(px, centers)}")
    # dither: still one valid index per pixel.
    _pal, idx2, n2 = t.quantise_palette(bytes(grad), 8, dither=True,
                                        width=8, height=8)
    assert len(idx2) == 64 and max(idx2) < n2
    # format-5 GIM round-trip.
    gim = t.build_gim_indexed(16, 8, t.FMT_INDEX8, bytes(256 * 4),
                              bytes(16 * 8), 256)
    gw, gh, _rgba = t.GimTexture(gim).to_pixels()
    assert (gw, gh) == (16, 8)
    # format-4 (INDEX4) GIM at the native cardh geometry 128x56, 16 colours.
    gim4 = t.build_gim_indexed(128, 56, t.FMT_INDEX4, bytes(16 * 4),
                               bytes(128 * 56), 16)
    want4 = 128 * 56 // 2 + t.slot_overhead(t.FMT_INDEX4, 16)
    assert len(gim4) == want4, f"format-4 GIM {len(gim4)} B != {want4}"
    gw4, gh4, rgba4 = t.GimTexture(gim4).to_pixels()
    assert (gw4, gh4) == (128, 56) and rgba4 == bytes(128 * 56 * 4)

    # --- region-size parameterisation (E8-4c) --------------------------
    # A GIM larger than one 2048-byte table slot may span several consecutive
    # slots: the table entry keeps pointing at the region *start* and the next
    # card's region begins region_bytes later.
    def mini_cip(min_card, max_card, body_slots=1):
        blob = bytearray(2048)                 # blob_base (HeaderSize -> 0x800)
        blob[0:4] = t.CIP_MAGIC
        struct.pack_into("<I", blob, 0x04, 2048)
        struct.pack_into("<I", blob, 0x10, 48)      # HeaderSize
        struct.pack_into("<I", blob, 0x14, min_card)
        struct.pack_into("<I", blob, 0x18, max_card)
        struct.pack_into("<I", blob, 0x1C, 48)      # OffsetTableTop
        struct.pack_into("<I", blob, 0x20, 1)       # bitshift 1 -> stride 2048
        blob += b"\x00" * (body_slots * 2048)
        struct.pack_into("<I", blob, 0x04, len(blob))
        return bytes(blob)

    gim = t.build_gim_indexed(16, 8, t.FMT_INDEX8, bytes(256 * 4),
                              bytes(16 * 8), 256)
    src = mini_cip(4007, 4008, body_slots=1)            # len 4096, slot 1
    assert len(src) == 4096 and len(gim) <= 2048
    new, entries, _c = build_container(
        src, [4007, 4008], {4007: {"gim": gim}, 4008: {"gim": gim}},
        base_slot=2, region=6144, fmt=t.FMT_INDEX8)
    assert len(new) == 4096 + 2 * 6144, len(new)
    assert entries == {4007: 2, 4008: 5}, entries   # 6144 // 2048 = 3 slots
    nc = t.Container.from_bytes(new)
    assert nc.entry(4007) == (2, 0) and nc.entry(4008) == (5, 0)
    assert nc.offset_of_slot(2) == 4096 and nc.offset_of_slot(5) == 10240
    assert struct.unpack_from("<I", new, 0x04)[0] == len(new)
    # The legacy region reproduces the old unit-step behaviour.
    new1, e1, _c = build_container(src, [4007], {4007: {"gim": gim}},
                                   base_slot=2, region=2048, fmt=t.FMT_INDEX8)
    assert len(new1) == 4096 + 2048 and e1 == {4007: 2}
    # Hard assertions: GIM must fit its region, region must be a 2048-multiple.
    for bad_region in (3072, 2048 + 1024, 0):
        try:
            build_container(src, [4007], {4007: {"gim": gim}},
                            base_slot=2, region=bad_region, fmt=t.FMT_INDEX8)
        except ValueError:
            pass
        else:
            raise AssertionError(f"region {bad_region} was accepted")
    big = t.build_gim_indexed(128, 8, t.FMT_INDEX8, bytes(256 * 4),
                              bytes(128 * 8), 256)
    assert len(big) > 2048
    try:
        build_container(src, [4007], {4007: {"gim": big}},
                        base_slot=2, region=2048, fmt=t.FMT_INDEX8)
    except ValueError:
        pass
    else:
        raise AssertionError("a GIM larger than its region was accepted")
    # No card may point inside another card's region (nor off its own start).
    bad = bytearray(new)
    struct.pack_into("<II", bad, nc.table_top + (4008 - nc.min_card)
                     * t.ENTRY_SIZE, 3, 0)          # 4008 -> inside 4007 region
    try:
        assert_regions_exclusive(bytes(bad), [(4007, 2, 6144),
                                              (4008, 5, 6144)])
    except ValueError:
        pass
    else:
        raise AssertionError("a foreign region pointer was accepted")
    assert_regions_exclusive(new, [(4007, 2, 6144), (4008, 5, 6144)])

    # --- native cardm DXT1 encoder (E8-5 / ESTADO-E8.md 9.8) -----------
    # A 64x64 image emits exactly 2048 B; a solid block round-trips through
    # the reference decoder in trabajo/e8/cardm_decode.py, and the swapped
    # word layout puts the index word first and the endpoints at bytes 4..7.
    solid = bytes((200, 50, 60, 255)) * (64 * 64)
    body = t.encode_dxt1_swapped(solid, 64, 64)
    assert len(body) == 2048, len(body)
    cv = t.rgb565_unpack(t.rgb565_pack(200, 50, 60))
    dec = decode_cardm(body, 64, 64)
    assert len(dec) == 64 * 64 * 4
    assert dec == bytes((cv[0], cv[1], cv[2], 255)) * (64 * 64), "solid DXT1"
    block = t.encode_dxt1_block([(200, 50, 60, 255)] * 16)
    v = t.rgb565_pack(200, 50, 60)
    assert block[0:4] == b"\x00\x00\x00\x00", block
    assert block[4:8] == struct.pack("<HH", v, v), block
    grad = bytearray()
    for y in range(64):
        for x in range(64):
            grad += bytes(((x * 4) % 256, (y * 4) % 256,
                           ((x + y) * 2) % 256, 255))
    gbody = t.encode_dxt1_swapped(bytes(grad), 64, 64)
    assert len(gbody) == 2048
    gdec = decode_cardm(gbody, 64, 64)
    gmae = sum(abs(gdec[i + k] - grad[i + k])
               for i in range(0, len(grad), 4) for k in range(3))
    gmae /= 64 * 64 * 3
    assert gmae < 20, gmae
    for bad in ((63, 64), (64, 63)):
        try:
            t.encode_dxt1_swapped(solid, bad[0], bad[1])
        except ValueError:
            pass
        else:
            raise AssertionError(f"DXT1 accepted {bad[0]}x{bad[1]}")

    # --- native cardh DXT1 codec (E8-9 / ESTADO-E8.md 9.9) --------------
    # A cardh slot is 4096 B: 128 constant template-header bytes + 3968 B of
    # the same swapped-word BC1 stream as cardm, 32 blocks (128 px) per row,
    # plain row-major.  496 blocks = 128x62 (last block row half width).
    header = t.GIM_MAGIC + bytes(t.CARDH_HEADER_SIZE - len(t.GIM_MAGIC))
    solid = bytes((10, 120, 200, 255)) * (t.CARDH_W * t.CARDH_H)
    slot = t.encode_cardh_native(header, solid)
    assert len(slot) == t.CARDH_SLOT_SIZE, len(slot)
    assert slot[:t.CARDH_HEADER_SIZE] == header, "header not verbatim"
    dec = t.decode_cardh_slot(slot)
    assert len(dec) == t.CARDH_W * t.CARDH_H * 4, len(dec)
    cv = t.rgb565_unpack(t.rgb565_pack(10, 120, 200))
    # The last half block row (64x2 bottom-right corner) is not stored: 496
    # blocks cover rows 0..59 at full width and rows 60..61 at half width.
    nblocks = t.CARDH_BODY_SIZE // 8
    for y in range(t.CARDH_H):
        for x in range(t.CARDH_W):
            b = (y // 4) * t.CARDH_BLOCKS_PER_ROW + x // 4
            o = (y * t.CARDH_W + x) * 4
            if b < nblocks:
                assert dec[o:o + 4] == bytes((cv[0], cv[1], cv[2], 255)), \
                    f"solid native cardh mismatch at {x},{y}"
            else:
                assert dec[o:o + 3] == b"\x00\x00\x00", \
                    f"unstored pixel {x},{y} is not black"
    assert nblocks == 15 * t.CARDH_BLOCKS_PER_ROW + 16, nblocks
    # A native header that is not a GIM template must be rejected.
    for bad in (b"XXXX" * 32, header[:64]):
        try:
            t.encode_cardh_native(bad, solid)
        except ValueError:
            pass
        else:
            raise AssertionError(f"bad cardh header of {len(bad)} B accepted")
    # Green chroma-key detection and masking.
    gm = t.green_key_mask(bytes((0, 97, 0, 255)) + bytes((1, 2, 3, 255)), 2, 1)
    assert gm == b"\x01\x00", gm
    painted = t.apply_green_mask(bytes((9, 9, 9, 255)) + bytes((0, 0, 0, 255)),
                                 2, 1, b"\x01\x00")
    assert painted == bytes((0, 97, 0, 255)) + bytes((0, 0, 0, 255)), painted
    # A 128x62 canvas whose last block row is half width must decode clean.
    grad = bytearray()
    for y in range(t.CARDH_H):
        for x in range(t.CARDH_W):
            grad += bytes(((x * 2) % 256, (y * 4) % 256, 128, 255))
    gslot = t.encode_cardh_native(header, bytes(grad))
    gdec = t.decode_cardh_slot(gslot)
    tot = 0
    for y in range(t.CARDH_H):
        for x in range(t.CARDH_W):
            b = (y // 4) * t.CARDH_BLOCKS_PER_ROW + x // 4
            if b >= nblocks:
                continue
            o = (y * t.CARDH_W + x) * 4
            tot += sum(abs(gdec[o + k] - grad[o + k]) for k in range(3))
    gmae = tot / (t.CARDH_W * t.CARDH_H * 3)
    assert gmae < 20, gmae

    # --- cardh placement modes (E8-10 A/B/C) ---------------------------
    assert _fit_size(624, 624, t.CARDH_W, t.CARDH_H) == (62, 62)
    assert _fit_size(200, 40, t.CARDH_W, t.CARDH_H) == (128, 25)
    assert _fit_size(128, 62, t.CARDH_W, t.CARDH_H) == (128, 62)
    ids18 = list(range(4007, 4007 + 18))
    assert assign_cardh_place(ids18, "cover") == {c: "cover" for c in ids18}
    abc = assign_cardh_place(ids18, "abc")
    assert [abc[c] for c in ids18] == ["cover"] * 6 + ["left"] * 6 \
        + ["contain"] * 6
    for bad in ("bogus", "abcabc"):
        try:
            assign_cardh_place(ids18, bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"place spec {bad!r} accepted")
    ref = bytes((7, 8, 9, 255)) * (t.CARDH_W * t.CARDH_H)
    ill = bytes((200, 10, 10, 255)) * (624 * 624)
    cov = compose_cardh_canvas(ill, 624, 624, "cover", None, None)
    assert len(cov["canvas"]) == t.CARDH_W * t.CARDH_H * 4
    assert cov["tile"] == (t.CARDH_W, t.CARDH_H)
    lef = compose_cardh_canvas(ill, 624, 624, "left", ref, None)
    assert lef["tile"] == (PLACE_LEFT_W, t.CARDH_H) and lef["pos"] == (0, 0)
    for r in range(t.CARDH_H):
        for c in range(t.CARDH_W):
            o = (r * t.CARDH_W + c) * 4
            want = ill[:4] if c < PLACE_LEFT_W else ref[o:o + 4]
            assert lef["canvas"][o:o + 4] == want, (c, r)
    con = compose_cardh_canvas(ill, 624, 624, "contain", ref, None)
    assert con["tile"] == (62, 62) and con["pos"] == (33, 0)
    for r in range(t.CARDH_H):
        for c in range(t.CARDH_W):
            o = (r * t.CARDH_W + c) * 4
            inside = 33 <= c < 33 + 62 and 0 <= r < 62
            want = ill[:4] if inside else ref[o:o + 4]
            assert con["canvas"][o:o + 4] == want, (c, r)
    # A masked illustration only repaints its own tile, never the native frame.
    mmask = bytes([1]) * (t.CARDH_W * t.CARDH_H)
    lem = compose_cardh_canvas(ill, 624, 624, "left", ref, mmask)
    for r in range(t.CARDH_H):
        for c in range(PLACE_LEFT_W, t.CARDH_W):
            o = (r * t.CARDH_W + c) * 4
            assert lem["canvas"][o:o + 4] == ref[o:o + 4], (c, r)
        for c in range(PLACE_LEFT_W):
            o = (r * t.CARDH_W + c) * 4
            assert lem["canvas"][o:o + 4] == bytes(t.GREEN_KEY) + b"\xff", (c, r)
    print("  placement: cover/left/contain compose + abc grouping OK")

    print("SELFTEST OK: resize_area, cover_crop, median-cut alignment, "
          "dither, format-5 GIM round-trip, format-4 128x56 GIM round-trip, "
          "region-based slot advance, native DXT1 encoder (2048 B, swapped "
          "word layout, reference-decoder round-trip), native cardh DXT1 "
          "codec (4096 B slot, verbatim header, 128x62 round-trip), green "
          "chroma-key mask, cardh placement cover/left/contain + abc groups")
    return 0


def cmd_accept(args) -> int:
    cardids = read_cardids(args.cards_tsv)
    for label, region in (("cardh", args.cardh_region),
                          ("cardm", args.cardm_region)):
        assert region > 0 and region % SLOT_UNIT == 0, (
            f"{label} region {region} B is not a positive multiple of "
            f"{SLOT_UNIT} B")
    with open(args.cardh, "rb") as fh:
        built_h = fh.read()
    with open(args.cardm, "rb") as fh:
        built_m = fh.read()
    c_h = t.Container.from_bytes(built_h)
    c_m = t.Container.from_bytes(built_m)
    src_h = source_container(args.cardh_in, INNER_H)
    src_m = source_container(args.cardm_in, INNER_M)

    print("== T9.1 arts() resolves each of the 18 to its own region start ==")
    step_h = args.cardh_region // SLOT_UNIT
    step_m = args.cardm_region // SLOT_UNIT
    for i, cid in enumerate(cardids):
        want_h = CARDH_SLOT0 + i * step_h
        want_m = CARDM_SLOT0 + i * step_m
        got_h, got_m = c_h.arts(cid), c_m.arts(cid)
        assert got_h == [want_h], f"CardID {cid}: cardh arts {got_h} != [{want_h}]"
        assert got_m == [want_m], f"CardID {cid}: cardm arts {got_m} != [{want_m}]"
        print(f"  CardID {cid}: cardh {got_h} · cardm {got_m}")

    print("== T9.2 every injected payload decodes back correctly ==")
    dxt1_previews = []
    cardh_previews = []
    cardh_native = args.cardh_codec == "native-dxt1"
    header = mask = ref_canvas = None
    place_by_cid = None
    if cardh_native:
        header = native_cardh_header(src_h)
        mask, _ev = native_green_mask(src_h)   # same deterministic result
        try:
            place_by_cid = assign_cardh_place(cardids, args.cardh_place)
        except ValueError as exc:
            raise SystemExit(str(exc))
        if any(m != "cover" for m in place_by_cid.values()):
            ref_canvas = native_cardh_reference(src_h, args.cardh_place_ref)
        print_cardh_place(place_by_cid, args.cardh_place, args.cardh_place_ref)
    for i, cid in enumerate(cardids):
        slot_h = CARDH_SLOT0 + i * step_h
        off_h = c_h.offset_of_slot(slot_h)
        payload_h = c_h.blob[off_h:off_h + args.cardh_region]
        if cardh_native:
            prep_h = prepare_cardh_native(cid, header, mask, args.resample,
                                          args.art_src, place_by_cid[cid],
                                          ref_canvas)
            assert len(payload_h) == t.CARDH_SLOT_SIZE, len(payload_h)
            assert payload_h[:t.CARDH_HEADER_SIZE] == header, (
                f"CardID {cid} cardh slot {slot_h}: header not verbatim")
            assert payload_h == prep_h["slot"], (
                f"CardID {cid} cardh slot {slot_h}: slot bytes != the encoded "
                f"native cardh slot")
            dec = t.decode_cardh_slot(payload_h)
            err = masked_mean_rgb_error(dec, prep_h["canvas"], CARDH_STORED)
            assert err <= CARDH_ACCEPT_MAE, (
                f"CardID {cid} cardh slot {slot_h}: native DXT1 decode-back "
                f"MAE {err:.2f} > {CARDH_ACCEPT_MAE}")
            if prep_h["place"] == "left" and ref_canvas is not None:
                assert prep_h["tile"] == (PLACE_LEFT_W, t.CARDH_H), (
                    f"CardID {cid}: left tile {prep_h['tile']} != "
                    f"({PLACE_LEFT_W}, {t.CARDH_H})")
                assert prep_h["pos"] == (0, 0), (
                    f"CardID {cid}: left pos {prep_h['pos']} != (0, 0)")
                mae_left = region_mean_rgb_error(dec, ref_canvas, t.CARDH_W,
                                                 0, PLACE_LEFT_W)
                mae_native = region_mean_rgb_error(dec, ref_canvas, t.CARDH_W,
                                                   PLACE_LEFT_W, t.CARDH_W)
                assert mae_native <= CARDH_ACCEPT_MAE, (
                    f"CardID {cid}: decoded native columns "
                    f"[{PLACE_LEFT_W}, {t.CARDH_W}) MAE {mae_native:.2f} > "
                    f"{CARDH_ACCEPT_MAE} (reference not preserved)")
                assert mae_left > mae_native, (
                    f"CardID {cid}: decoded left columns [0, {PLACE_LEFT_W}) "
                    f"MAE {mae_left:.2f} is not more distant from the native "
                    f"reference than the native columns ({mae_native:.2f})")
                print(f"    left placement: decoded x0..{PLACE_LEFT_W - 1} "
                      f"illustration (MAE vs native {mae_left:.2f}), "
                      f"x{PLACE_LEFT_W}..{t.CARDH_W - 1} native "
                      f"(MAE {mae_native:.2f} <= {CARDH_ACCEPT_MAE})")
            cardh_previews.append((cid, dec))
            print(f"  CardID {cid}: cardh native DXT1 {t.CARDH_W}x{t.CARDH_H} "
                  f"placement {prep_h['place']} tile {prep_h['tile']} at "
                  f"{prep_h['pos']} MAE {err:.2f} RGB (stored px), header "
                  f"verbatim, slot {len(payload_h)} B · cardm below")
        else:
            tex_h = t.GimTexture(payload_h)
            dw, dh, rgba = tex_h.to_pixels()
            prep_h = prepare_art(cid, args.cardh_w, args.cardh_h,
                                 args.cardh_colors, args.cardh_format,
                                 args.resample, args.dither, args.art_src)
            assert tex_h.fmt == args.cardh_format, (
                f"CardID {cid} cardh slot {slot_h}: GIM format {tex_h.fmt} != "
                f"{args.cardh_format}")
            assert (dw, dh) == (args.cardh_w, args.cardh_h), (
                f"CardID {cid} cardh slot {slot_h}: decoded {dw}x{dh}")
            assert rgba == prep_h["canvas"], (
                f"CardID {cid} cardh slot {slot_h}: decode-back is not "
                f"pixel-identical to the prepared canvas")
        slot_m = CARDM_SLOT0 + i * step_m
        off_m = c_m.offset_of_slot(slot_m)
        payload_m = c_m.blob[off_m:off_m + args.cardm_region]
        if args.cardm_codec == "dxt1":
            prep_m = prepare_dxt1_art(cid, args.cardm_w, args.cardm_h,
                                      args.resample, args.cardm_art_src,
                                      args.cardm_fit)
            assert len(payload_m) == args.cardm_region, (
                f"CardID {cid} cardm slot {slot_m}: {len(payload_m)} B != "
                f"region {args.cardm_region} B")
            assert payload_m == prep_m["payload"], (
                f"CardID {cid} cardm slot {slot_m}: slot bytes != the encoded "
                f"DXT1 body")
            dec_m = decode_cardm(payload_m, args.cardm_w, args.cardm_h)
            err = mean_rgb_error(dec_m, prep_m["canvas"])
            distinct = t.distinct_colours(dec_m)
            assert distinct >= 16, (
                f"CardID {cid} cardm slot {slot_m}: only {distinct} distinct "
                f"colours in the DXT1 thumbnail")
            assert err <= DXT1_ACCEPT_MAE, (
                f"CardID {cid} cardm slot {slot_m}: DXT1 decode-back MAE "
                f"{err:.2f} > {DXT1_ACCEPT_MAE}")
            dxt1_previews.append((cid, dec_m))
            if not cardh_native:
                print(f"  CardID {cid}: cardh decode-back identical: True · "
                      f"cardm DXT1 {args.cardm_w}x{args.cardm_h} MAE "
                      f"{err:.2f} RGB, {distinct} distinct colours")
            else:
                print(f"    cardm DXT1 {args.cardm_w}x{args.cardm_h} MAE "
                      f"{err:.2f} RGB, {distinct} distinct colours")
        else:
            tex_m = t.GimTexture(payload_m)
            dwm, dhm, rgbam = tex_m.to_pixels()
            prep_m = prepare_art(cid, args.cardm_w, args.cardm_h,
                                 args.cardm_colors, args.cardm_format,
                                 args.resample, args.dither, args.art_src)
            assert tex_m.fmt == args.cardm_format, (
                f"CardID {cid} cardm slot {slot_m}: GIM format {tex_m.fmt} != "
                f"{args.cardm_format}")
            assert (dwm, dhm) == (args.cardm_w, args.cardm_h), (
                f"CardID {cid} cardm slot {slot_m}: decoded {dwm}x{dhm}")
            assert rgbam == prep_m["canvas"], (
                f"CardID {cid} cardm slot {slot_m}: decode-back is not "
                f"pixel-identical to the prepared canvas")
            if not cardh_native:
                print(f"  CardID {cid}: cardh + cardm decode-back identical: "
                      f"True")

    if cardh_native:
        picks = [p for p in cardh_previews if p[0] in (4661, 4665, 4671)]
        picks = picks or cardh_previews[:3]
        for cid, dec in picks:
            path = os.path.join(E8, f"cardh_native_{args.preview_stem}_{cid}.png")
            t.write_png(path, t.CARDH_W, t.CARDH_H, dec)
            big = t.resize_nearest(dec, t.CARDH_W, t.CARDH_H,
                                   t.CARDH_W * 4, t.CARDH_H * 4)
            path4 = os.path.join(E8, f"cardh_native_{args.preview_stem}_{cid}_4x.png")
            t.write_png(path4, t.CARDH_W * 4, t.CARDH_H * 4, big)
            print(f"  wrote {os.path.relpath(path, ROOT)} and "
                  f"{os.path.relpath(path4, ROOT)}")

    if cardh_native and place_by_cid is not None:
        # One upscaled cardh PNG per A/B/C group so the three placements can be
        # compared side by side (E8-10).
        by_place = {}
        for cid, dec in cardh_previews:
            by_place.setdefault(place_by_cid[cid], (cid, dec))
        for mode in PLACE_MODES:
            if mode not in by_place:
                continue
            cid, dec = by_place[mode]
            path = os.path.join(E8, f"TF1-E8-{args.preview_tag}_cardh_{mode}_{cid}.png")
            t.write_png(path, t.CARDH_W, t.CARDH_H, dec)
            big = t.resize_nearest(dec, t.CARDH_W, t.CARDH_H,
                                   t.CARDH_W * 4, t.CARDH_H * 4)
            path4 = os.path.join(E8, f"TF1-E8-{args.preview_tag}_cardh_{mode}_{cid}_4x.png")
            t.write_png(path4, t.CARDH_W * 4, t.CARDH_H * 4, big)
            print(f"  wrote {os.path.relpath(path, ROOT)} and "
                  f"{os.path.relpath(path4, ROOT)}")
        print("  A/B/C preview: " + ", ".join(
            f"{m} -> CardID {by_place[m][0]}" for m in PLACE_MODES
            if m in by_place))
        picks = [p for p in dxt1_previews if p[0] in (4661, 4665, 4671)]
        picks = picks or dxt1_previews[:3]
        for cid, dec in picks:
            path = os.path.join(E8, f"cardm_{args.preview_stem}_{cid}.png")
            t.write_png(path, args.cardm_w, args.cardm_h, dec)
            big = t.resize_nearest(dec, args.cardm_w, args.cardm_h,
                                   args.cardm_w * 4, args.cardm_h * 4)
            path4 = os.path.join(E8, f"cardm_{args.preview_stem}_{cid}_4x.png")
            t.write_png(path4, args.cardm_w * 4, args.cardm_h * 4, big)
            print(f"  wrote {os.path.relpath(path, ROOT)} and "
                  f"{os.path.relpath(path4, ROOT)}")

    print("== T9.3 verify exits 0 on both new containers ==")
    for path in (args.cardh, args.cardm):
        rc = t.main(["verify", "--container", path])
        assert rc == 0, f"verify failed ({rc}) on {path}"
        print(f"  verify {os.path.basename(path)}: exit {rc}")

    print("== T9.4 header regions differ only at the 18 entries + total_size ==")
    for label, src, built, c in (("cardh", src_h, built_h, c_h),
                                 ("cardm", src_m, built_m, c_m)):
        outside = header_diff(src, built, c, cardids)
        total = struct.unpack_from("<I", built, 0x04)[0]
        assert not outside, (f"{label}: bytes changed outside the 18 entries / "
                             f"total_size: {outside[:12]}")
        assert total == len(built), f"{label}: total_size {total} != {len(built)}"
        print(f"  {label}: blob_base {c.blob_base}, no foreign header byte "
              f"changed, total_size {total} == {len(built)}")

    print("== T9.5 ISO sector diff confined to the two new extents ==")
    changed = sector_diff(args.src_iso, args.iso)
    alloc_h = (len(built_h) + SECTOR - 1) // SECTOR
    alloc_m = (len(built_m) + SECTOR - 1) // SECTOR
    allowed = set(range(CARDH_LBA, CARDH_LBA + alloc_h))
    allowed |= set(range(CARDM_LBA, CARDM_LBA + alloc_m))
    # T8 rewrites the two ISO9660 directory records, which live in a metadata
    # sector outside both extents.  Those record sectors are the only allowed
    # extra: the assertion below still rejects any other changed sector.
    iso0 = Iso9660(args.src_iso)
    try:
        rec_h0, _ = find_record(iso0, INNER_H)
        rec_m0, _ = find_record(iso0, INNER_M)
    finally:
        iso0.close()
    rec_sectors = {rec_h0 // SECTOR, rec_m0 // SECTOR}
    outside = [s for s in changed
               if s not in allowed and s not in rec_sectors]
    print(f"  {len(changed)} sectors changed of "
          f"{os.path.getsize(args.iso) // SECTOR}")
    print(f"  cardh extent [{CARDH_LBA}, {CARDH_LBA + alloc_h}) "
          f"({alloc_h} sec) · cardm extent [{CARDM_LBA}, "
          f"{CARDM_LBA + alloc_m}) ({alloc_m} sec)")
    print(f"  ISO9660 directory-record sector(s) updated by T8: "
          f"{sorted(rec_sectors)}")
    print(f"  changed outside the extents and record sectors: {len(outside)}")
    assert changed, "the new ISO is byte-identical to the E6 ISO"
    assert not outside, (f"sectors changed outside the new extents and the "
                         f"directory-record sectors: {outside[:20]}")
    assert rec_sectors <= set(changed), (
        f"the directory-record sector(s) {sorted(rec_sectors)} did not "
        f"change, so T8 did not update the records")

    print("== T9.6 ISO reads back the built containers; E6 source untouched ==")
    iso = Iso9660(args.iso)
    try:
        got_h = iso.read_file(INNER_H)
        got_m = iso.read_file(INNER_M)
    finally:
        iso.close()
    assert got_h == built_h and got_m == built_m, "ISO readback mismatch"
    e6_h = source_container(None, INNER_H)
    e6_m = source_container(None, INNER_M)
    assert sha256(e6_h) == E6_CARDH_SHA, "E6 cardh_s.cip changed!"
    assert sha256(e6_m) == E6_CARDM_SHA, "E6 cardm_s.cip changed!"
    print(f"  new ISO cardh/cardm readback identical to the build: True")
    print(f"  E6 ISO cardh sha256 {sha256(e6_h)} (expected {E6_CARDH_SHA})")
    print(f"  E6 ISO cardm sha256 {sha256(e6_m)} (expected {E6_CARDM_SHA})")

    print()
    print("ACCEPT OK: T9.1 .. T9.6 all hold.")
    return 0


# ---------------------------------------------------------------------------
# full card download (E8-9)
# ---------------------------------------------------------------------------
def read_manifest_rows(path: str = MASK_MANIFEST) -> list:
    """``(cardid, passcode)`` rows from ``art_src/manifest.tsv``."""
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            cols = line.split("\t")
            rows.append((int(cols[0]), cols[3]))
    return rows


def cmd_fetch_full(args) -> int:
    """Download the full card renders (ygoprodeck ``image_url``) as JPGs.

    The JPG->PNG step is the PowerShell ``System.Drawing`` converter used for
    the cropped sources (``trabajo/e8/_conv_all.ps1``); this command only
    fetches the JPEGs into ``art_full/``.
    """
    import urllib.request
    os.makedirs(args.out_dir, exist_ok=True)
    rows = read_manifest_rows(args.manifest)
    got = skipped = 0
    for cardid, passcode in rows:
        url = args.url_template.format(passcode=passcode)
        dst = os.path.join(args.out_dir, f"{cardid}.jpg")
        if os.path.exists(dst) and not args.force:
            print(f"  CardID {cardid}: {dst} exists, skip")
            skipped += 1
            continue
        req = urllib.request.Request(url, headers={"User-Agent": "tf1_art18"})
        with urllib.request.urlopen(req, timeout=args.timeout) as resp:
            data = resp.read()
        with open(dst, "wb") as fh:
            fh.write(data)
        print(f"  CardID {cardid} passcode {passcode}: {len(data)} B <- {url}")
        got += 1
    print(f"full card JPGs: {got} downloaded, {skipped} skipped, into "
          f"{os.path.relpath(args.out_dir, ROOT)}")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="tf1_art18.py",
        description="E8-4: prepare and inject the art of the 18 cards.")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_art_flags(sp):
        sp.add_argument("--art-src", default=ART_SRC)
        sp.add_argument("--resample", choices=("area", "nearest"),
                        default="area")
        sp.add_argument("--dither", action="store_true")

    pv = sub.add_parser("preview", help="comparison sheet for the palette")
    pv.add_argument("--out", default=os.path.join(E8, "art_preview.png"))
    pv.add_argument("--cards", help="comma-separated CardIDs (default 3)")
    pv.add_argument("--zoom", type=int, default=5)
    pv.add_argument("--variants",
                    help="comma-separated WxH/COLORS/FMT (default: the two "
                         "legacy 76/204-colour variants)")
    pv.add_argument("--source", action="store_true",
                    help="draw the truecolour source tile next to each result")
    add_art_flags(pv)
    pv.set_defaults(func=cmd_preview)

    pb = sub.add_parser("build", help="append own slots and rewrite the entries")
    pb.add_argument("--cards-tsv", default=CARDS_TSV)
    pb.add_argument("--cardh-in", help="source cardh_s.cip (default: E6 ISO)")
    pb.add_argument("--cardm-in", help="source cardm_s.cip (default: E6 ISO)")
    pb.add_argument("--out-cardh", default=DEFAULT_CARDH_OUT)
    pb.add_argument("--out-cardm", default=DEFAULT_CARDM_OUT)
    pb.add_argument("--manifest", default=MANIFEST,
                    help="where to write the build manifest JSON")
    pb.add_argument("--cardh-w", type=int, default=CARDH_W)
    pb.add_argument("--cardh-h", type=int, default=CARDH_H)
    pb.add_argument("--cardh-colors", type=int, default=CARDH_COLORS)
    pb.add_argument("--cardh-format", type=int,
                    choices=(t.FMT_INDEX4, t.FMT_INDEX8), default=CARDH_FMT,
                    help="cardh GIM format: 4 = INDEX4, 5 = INDEX8 (default 5)")
    pb.add_argument("--cardh-region", type=int, default=CARDH_REGION,
                    help="private bytes reserved per cardh (multiple of 2048; "
                         "default 4096 = the E8-4b single slot)")
    pb.add_argument("--cardh-codec", choices=("gim", "native-dxt1"),
                    default="gim",
                    help="cardh payload: gim (paletted GIM, default, "
                         "byte-for-byte reproducible) or native-dxt1 (the "
                         "native 4096 B slot: verbatim GIM template header + "
                         "128x62 swapped DXT1 body)")
    pb.add_argument("--cardh-place",
                    choices=PLACE_MODES + (PLACE_SOURCE,), default="cover",
                    help="cardh placement for native-dxt1: cover (whole "
                         "128x62), left (illustration 78x62 at x=0, native "
                         "elsewhere), contain (whole illustration fit "
                         "inside, native elsewhere) or abc (6 cover / 6 left "
                         "/ 6 contain in cards_tsv order)")
    pb.add_argument("--cardh-place-ref", type=int, default=PLACE_REF_CARD,
                    help="reference native cardh slot for the native bytes")
    pb.add_argument("--cardm-art-src", default=ART_SRC,
                    help="cardm PNG source dir (default art_src; use art_full "
                         "for the full card render)")
    pb.add_argument("--cardm-fit", choices=("cover", "stretch"),
                    default="cover",
                    help="cover (crop to canvas aspect, default) or stretch "
                         "(scale the whole source; keeps the full card frame)")
    pb.add_argument("--cardm-w", type=int, default=CARDM_W)
    pb.add_argument("--cardm-h", type=int, default=CARDM_H)
    pb.add_argument("--cardm-colors", type=int, default=CARDM_COLORS)
    pb.add_argument("--cardm-format", type=int,
                    choices=(t.FMT_INDEX4, t.FMT_INDEX8), default=CARDM_FMT,
                    help="cardm GIM format: 4 = INDEX4, 5 = INDEX8 (default 5)")
    pb.add_argument("--cardm-region", type=int, default=CARDM_REGION,
                    help="private bytes reserved per cardm (multiple of 2048; "
                         "default 2048 = the E8-4b single slot)")
    pb.add_argument("--cardm-codec", choices=("gim", "dxt1"), default="gim",
                    help="cardm payload: gim (paletted GIM, default) or dxt1 "
                         "(native 64x64 BC1; ignores --cardm-colors/format)")
    add_art_flags(pb)
    pb.set_defaults(func=cmd_build)

    pi = sub.add_parser("iso", help="write the grown containers into a new ISO")
    pi.add_argument("--src-iso", default=E6_ISO)
    pi.add_argument("--dst-iso", default=DEFAULT_ISO)
    pi.add_argument("--cardh", default=DEFAULT_CARDH_OUT)
    pi.add_argument("--cardm", default=DEFAULT_CARDM_OUT)
    pi.set_defaults(func=cmd_iso)

    pal = sub.add_parser(
        "alias", help="alias the four non-_s card-art records per size to "
        "the _s extent/size (E8-11 / FINAL-C)")
    pal.add_argument("--src-iso", default=FINAL_B_ISO)
    pal.add_argument("--dst-iso", default=FINAL_C_ISO)
    pal.set_defaults(func=cmd_alias)

    pc = sub.add_parser(
        "check", help="read-only language-alias assertions on an ISO")
    pc.add_argument("--iso", default=FINAL_C_ISO)
    pc.add_argument("--ref-iso", default=FINAL_B_ISO)
    pc.set_defaults(func=cmd_check)

    pa = sub.add_parser("accept", help="T9 hard assertions + evidence")
    pa.add_argument("--cards-tsv", default=CARDS_TSV)
    pa.add_argument("--cardh", default=DEFAULT_CARDH_OUT)
    pa.add_argument("--cardm", default=DEFAULT_CARDM_OUT)
    pa.add_argument("--iso", default=DEFAULT_ISO)
    pa.add_argument("--src-iso", default=E6_ISO)
    pa.add_argument("--cardh-in", help="source cardh_s.cip (default: E6 ISO)")
    pa.add_argument("--cardm-in", help="source cardm_s.cip (default: E6 ISO)")
    pa.add_argument("--cardh-w", type=int, default=CARDH_W)
    pa.add_argument("--cardh-h", type=int, default=CARDH_H)
    pa.add_argument("--cardh-colors", type=int, default=CARDH_COLORS)
    pa.add_argument("--cardh-format", type=int,
                    choices=(t.FMT_INDEX4, t.FMT_INDEX8), default=CARDH_FMT,
                    help="cardh GIM format: 4 = INDEX4, 5 = INDEX8 (default 5)")
    pa.add_argument("--cardh-region", type=int, default=CARDH_REGION,
                    help="private bytes reserved per cardh (multiple of 2048; "
                         "default 4096 = the E8-4b single slot)")
    pa.add_argument("--cardh-codec", choices=("gim", "native-dxt1"),
                    default="gim",
                    help="cardh payload written by the matching build")
    pa.add_argument("--cardh-place",
                    choices=PLACE_MODES + (PLACE_SOURCE,), default="cover",
                    help="cardh placement written by the matching build")
    pa.add_argument("--cardh-place-ref", type=int, default=PLACE_REF_CARD,
                    help="reference native cardh slot written by the build")
    pa.add_argument("--cardm-art-src", default=ART_SRC,
                    help="cardm PNG source dir (must match the build)")
    pa.add_argument("--cardm-fit", choices=("cover", "stretch"),
                    default="cover",
                    help="cardm fit mode written by the matching build")
    pa.add_argument("--cardm-w", type=int, default=CARDM_W)
    pa.add_argument("--cardm-h", type=int, default=CARDM_H)
    pa.add_argument("--cardm-colors", type=int, default=CARDM_COLORS)
    pa.add_argument("--cardm-format", type=int,
                    choices=(t.FMT_INDEX4, t.FMT_INDEX8), default=CARDM_FMT,
                    help="cardm GIM format: 4 = INDEX4, 5 = INDEX8 (default 5)")
    pa.add_argument("--cardm-region", type=int, default=CARDM_REGION,
                    help="private bytes reserved per cardm (multiple of 2048; "
                         "default 2048 = the E8-4b single slot)")
    pa.add_argument("--cardm-codec", choices=("gim", "dxt1"), default="gim",
                    help="cardm payload written by the matching build")
    pa.add_argument("--preview-tag", default="ABC",
                    help="tag in the per-placement preview filename "
                         "(default ABC; set FINAL-B so it does not overwrite "
                         "the E8-10 A/B/C evidence)")
    pa.add_argument("--preview-stem", default="final",
                    help="stem in the cardh/cardm per-card preview filename "
                         "(default final)")
    add_art_flags(pa)
    pa.set_defaults(func=cmd_accept)

    pf = sub.add_parser("fetch-full",
                        help="download full card renders (cardm source)")
    pf.add_argument("--manifest", default=MASK_MANIFEST)
    pf.add_argument("--out-dir", default=ART_FULL)
    pf.add_argument("--url-template",
                    default="https://images.ygoprodeck.com/images/cards/{passcode}.jpg",
                    help="ygoprodeck image_url template (full card)")
    pf.add_argument("--timeout", type=float, default=30.0)
    pf.add_argument("--force", action="store_true")
    pf.set_defaults(func=cmd_fetch_full)

    ps = sub.add_parser("selftest",
                        help="regression checks for the T5 primitives")
    ps.set_defaults(func=cmd_selftest)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

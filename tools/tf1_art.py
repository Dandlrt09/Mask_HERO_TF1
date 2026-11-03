#!/usr/bin/env python3
"""tf1_art.py - reader/writer for Yu-Gi-Oh! GX Tag Force 1 (PSP) card art.

This tool reads the card-art containers shipped in the ISO.  It also carries
an ``inject`` command used only by the E8 format-5 canary experiment: it can
write a self-built, structurally valid INDEX8 (format 5) GIM into one card's
fixed-size art slot, leaving every byte outside that slot untouched.

  * ``card/cardh_<lang>.cip`` - album / large card, magic ``CIP\\x1a``
  * ``card/cardm_<lang>.cip`` - field / small card, magic ``CPM\\x1a``

Container layout (little-endian u32 unless stated otherwise)
------------------------------------------------------------
  @0x00  magic               ``CIP\\x1a`` or ``CPM\\x1a``
  @0x04  total file size
  @0x10  HeaderSize          0x5F18 = 24344 (where the offset table area ends)
  @0x14  MinCardNumber       4007
  @0x18  MaxCardNumber       6957
  @0x1C  OffsetTableTop      48
  @0x20  BitshiftSize        2 for cardh, 1 for cardm

The offset table holds one 8-byte entry per CardID at
``OffsetTableTop + (card_id - MinCardNumber) * 8``:

  * first u32 = ``slot``.  ``0`` means "no art".
    ``slot & 0x80000000`` is an **alternate-art pointer**: its low 24 bits
    are a byte offset inside the header where a list of ``(slot, pad)``
    pairs lives (the list ends on the entry with the high bit set).
    Otherwise the image lives at ``slot << 11``.
  * second u32 = padding, always 0.

Payload
-------
A cardh slot is a 128-byte constant GIM template (``MIG.00.1PSP\\x00``) truncated to the
container's 4096-byte window (the prefix is vestigial); a cardm slot is
**not** a GIM either: each 2048-byte slot is a native 64x64 DXT1 (BC1) image
whose 8-byte blocks store their two 32-bit words swapped (the 4 index bytes
first, then the RGB565 endpoints).  The cardh texture body after that prefix is
the same swapped DXT1, 128x62.  The ``CPM_GIMHEADER`` prefix CIPTool shows is
only the constant the game prepends before reading the raw pixels.  See
``encode_dxt1_swapped``, ``decode_cardh_slot`` and ESTADO-E8.md 9.8/9.9.

GIM block structure (verified against TF1's own files)
------------------------------------------------------
The file is ``MIG.00.1PSP\\x00`` (16 bytes) followed by a chain of blocks.
Each block starts with a 16-byte header::

  +0x00  u16 type      2 wrapper, 3 wrapper, 4 image, 5 palette
  +0x02  u16 pad
  +0x04  u32 size      span of this block
  +0x08  u32 next      offset to the next block, relative to this block
                       (last block: points past itself / past the window)
  +0x0C  u32 data      0x10 (data follows the 16-byte header)

An image (type 4) and a palette (type 5) block each carry a 0x40-byte
image header at ``block + 0x10``::

  +0x00  u16 header_size   0x30
  +0x02  u16 pad
  +0x04  u16 format        3 = RGBA8888, 4 = INDEX4, 5 = INDEX8, 8 = the
                           (undecoded) cardh/cardm default, bpp 4 (see below)
  +0x06  u16 flags
  +0x08  u16 width
  +0x0A  u16 height
  +0x0C  u16 bpp           32 / 8 / 4
  +0x0E..u16 pad / alignment hints
  +0x18  u32 = 0x30, +0x1C u32 = 0x40
  +0x20  u32 = 0x40 + payload length (padding included)
  +0x28  u32 = 0x40

Texture bytes start at ``image_header + 0x40``.  ``0x1070``/``0x1060``/
``0x1050``/``0x1040`` in the cardh slot prefix are a constant template copied
from a larger GIM (they appear verbatim in ``referencia/CIPTool/CIPTool.h``'s
``CPM_GIMHEADER``), so they are not per-image sizes.

Pixel storage: the PSP GE texture swizzle
-----------------------------------------
Texture data is **swizzled**, not linear.  The stream is a sequence of
128-byte units; each unit is one 16-byte block wide and 8 rows tall; units
are stored row-major over the block grid, where ``row_bytes = width*bpp/8``
and ``blocks_per_row = row_bytes/16``::

  stored_offset(unit uy, unit ux, row r, col c) = (uy*bpr + ux)*128 + r*16 + c
  -> display pixel row  = uy*8 + r
  -> display byte column = ux*16 + c

This is proved, not assumed: with it ``window_s0002.gim`` from TF1's own
``limitlist.ehp`` renders as a legible blue "Limitada" banner (red no-entry
icon on the left, white label box on the right, cream body under it), and all
55 ``help*.gim`` files in ``/PSP_GAME/USRDIR/help`` render as coherent
screenshots and diagrams.  Without it they are stripy noise.

THE NATIVE CODEC IS SWAPPED-WORD DXT1 (BC1), NOT A PALETTE.  Every cardh and
cardm slot is BC1 DXT1 whose 8-byte blocks store their two 32-bit words
swapped: the 4 index bytes first (0,1,2,3) then the RGB565 endpoints.  There
is no GE swizzle.  cardm: one 2048-byte 64x64 image.  cardh: a 128-byte
constant GIM template (starts ``MIG.00.1PSP``, declares format 8, 128x64) then
3968 bytes = 496 blocks = 128x62 pixels, 32 blocks per row, row-major.  See
``encode_dxt1_swapped``/``decode_dxt1_swapped`` and the cardh helpers below,
proven in ESTADO-E8.md 9.8/9.9.  The GIM ``displays`` in the format-8 header
are vestigial; ``extract`` still refuses format 8 (use the native decoders).
The ``decode_cardh_slot`` helper also backs the E8-9 inject path in
tf1_art18.py (per-container ``--cardh-codec native-dxt1``).

Usage
-----
  python tools/tf1_art.py list    [--container trabajo/e8/cardh_s.cip]
  python tools/tf1_art.py gim GIMFILE --out trabajo/e8/OUT.png
  python tools/tf1_art.py extract CARDID --out trabajo/e8/CARDID.png
  python tools/tf1_art.py verify  [--container trabajo/e8/cardh_s.cip]
  python tools/tf1_art.py inject  --container IN.cip --cardid 6310 \
      --png preview.png [--format 4|5] [--palette N] \
      [--width 64 --height 40] [--resample nearest|area] [--dither] \
      --out OUT.cip

``inject`` centre-crops the PNG to the target canvas' aspect ratio (cover-crop,
so no letterboxing) and then resamples it.  The native cardh/cardm path lives
in ``tools/tf1_art18.py`` (``--cardh-codec native-dxt1``, ``--cardm-codec
dxt1``); this module supplies its codec primitives.  ``--resample nearest`` (the
default, kept for the E8 canaries) is aliased nearest-neighbour; ``area`` is an
antialiased box average, the right choice for a large source such as the
624x624 EDOPro crops.  ``--dither`` runs Floyd-Steinberg error diffusion while
mapping pixels onto the quantised palette.

Only the standard library is used; no PIL, no numpy.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import struct
import sys
import zlib

TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOLS)
DEFAULT_CARDH = os.path.join(ROOT, "trabajo", "e8", "cardh_s.cip")
DEFAULT_CARDM = os.path.join(ROOT, "trabajo", "e8", "cardm_s.cip")
DEFAULT_LANG = "s"

CIP_MAGIC = b"CIP\x1a"
CPM_MAGIC = b"CPM\x1a"
GIM_MAGIC = b"MIG.00.1PSP\x00"
TABLE_TOP = 48
ENTRY_SIZE = 8
SLOT_SHIFT = 11
GIM_HEADER_SIZE = 128
ALT_MASK = 0x80000000
ALT_PTR_MASK = 0x00FFFFFF

# GIM block chain.
BLOCK_TOP = 0x10
BLOCK_HEADER_SIZE = 16
BLOCK_IMAGE = 4
BLOCK_PALETTE = 5
IMAGE_HEADER_SIZE = 0x40

# Image-header field offsets, relative to ``block + 0x10``.
IH_FORMAT_OFF = 0x04
IH_WIDTH_OFF = 0x08
IH_HEIGHT_OFF = 0x0A
IH_BPP_OFF = 0x0C

# Pixel formats.  4 (INDEX4) and 5 (INDEX8) are both decoded and encoded;
# 8 is what every cardh/cardm slot declares and is still NOT decoded.
FMT_RGBA8888 = 3
FMT_INDEX4 = 4
FMT_INDEX8 = 5
FMT_4BPP = 8

# Uncompressed sprites have no GIM header in CPM containers.
CARDM_WIDTH = 64
CARDM_HEIGHT = 64

# A complete format-5 (INDEX8) GIM is a fixed 1232 bytes of headers plus one
# byte per pixel: 16 magic + 2 wrapper block headers (32) + palette block
# (16 block header + 64 image header + 256 * 4 palette) + image block
# (16 block header + 64 image header).  Measured from window_s0002.gim:
# 5328 bytes total - 128 * 32 texture = 1232.
FORMAT5_WRAPPER_OVERHEAD = 48            # magic + type-2 + type-3 headers
FORMAT5_PALETTE_BLOCK = 1104             # 16 + 64 + 256 * 4
FORMAT5_IMAGE_OVERHEAD = 80              # 16 + 64
FORMAT5_OVERHEAD = (FORMAT5_WRAPPER_OVERHEAD + FORMAT5_PALETTE_BLOCK
                    + FORMAT5_IMAGE_OVERHEAD)   # 1232

SWIZZLE_UNIT = 128
SWIZZLE_ROWS = 8
SWIZZLE_BLOCK = 16


class UnsupportedFormat(Exception):
    """Raised for pixel formats this tool cannot decode yet (format 8)."""


# ---------------------------------------------------------------------------
# Container parsing
# ---------------------------------------------------------------------------
class Container:
    """A read-only CIP/CPM card-art container."""

    def __init__(self, path: str):
        with open(path, "rb") as fh:
            blob = fh.read()
        self._load(blob, path)

    @classmethod
    def from_bytes(cls, blob: bytes, path: str = "<bytes>") -> "Container":
        """Build a container view over an in-memory blob (no file read)."""
        self = cls.__new__(cls)
        self._load(blob, path)
        return self

    def _load(self, blob: bytes, path: str) -> None:
        self.path = path
        self.blob = blob
        magic = self.blob[0:4]
        if magic not in (CIP_MAGIC, CPM_MAGIC):
            raise ValueError(f"{path}: not a CIP/CPM container ({magic!r})")
        self.kind = "cip" if magic == CIP_MAGIC else "cpm"
        (self.total_size, self.header_size, self.min_card, self.max_card,
         self.table_top, self.bitshift) = (
            struct.unpack_from("<I", self.blob, 0x04)[0],
            struct.unpack_from("<I", self.blob, 0x10)[0],
            struct.unpack_from("<I", self.blob, 0x14)[0],
            struct.unpack_from("<I", self.blob, 0x18)[0],
            struct.unpack_from("<I", self.blob, 0x1C)[0],
            struct.unpack_from("<I", self.blob, 0x20)[0],
        )
        self.stride = self.bitshift << SLOT_SHIFT
        # First blob starts at HeaderSize rounded up to the next 0x800 boundary.
        self.blob_base = (self.header_size + 0x7FF) & ~0x7FF
        # Number of fixed-size slots from blob_base to EOF.
        self.slot_count = (len(self.blob) - self.blob_base) // self.stride

    # -- table ------------------------------------------------------------
    def entry(self, card_id: int) -> tuple[int, int]:
        """Raw (slot, pad) 8-byte table entry for a CardID."""
        if not self.min_card <= card_id <= self.max_card:
            raise ValueError(f"CardID {card_id} outside "
                             f"{self.min_card}..{self.max_card}")
        off = self.table_top + (card_id - self.min_card) * ENTRY_SIZE
        return struct.unpack_from("<II", self.blob, off)

    def arts(self, card_id: int) -> list[int]:
        """Resolve a CardID to the list of slots that actually hold art.

        A single slot is returned directly; an alternate-art pointer is walked
        until the terminating entry (high bit set).  Slot 0 yields an empty
        list.
        """
        slot, _pad = self.entry(card_id)
        if slot == 0:
            return []
        if slot & ALT_MASK:
            ptr = slot & ALT_PTR_MASK
            out: list[int] = []
            while True:
                sid, _off = struct.unpack_from("<II", self.blob, ptr)
                out.append(sid & ~ALT_MASK)
                ptr += ENTRY_SIZE
                if sid & ALT_MASK:
                    break
            return out
        return [slot]

    def offset_of_slot(self, slot: int) -> int:
        return slot << SLOT_SHIFT

    def payload(self, slot: int) -> bytes:
        """The fixed-size container window for one slot."""
        off = self.offset_of_slot(slot)
        return self.blob[off:off + self.stride]

    # -- iteration --------------------------------------------------------
    def iter_cards(self):
        """Yield (card_id, slots) for every CardID in range, including empty."""
        for card_id in range(self.min_card, self.max_card + 1):
            yield card_id, self.arts(card_id)

    def stats(self) -> dict:
        zero = sentinel = alt = with_art = total_arts = 0
        for _cid, slots in self.iter_cards():
            if not slots:
                zero += 1
                slot, _pad = self.entry(_cid)
                if slot != 0:
                    sentinel += 1
                continue
            with_art += 1
            total_arts += len(slots)
            if len(slots) > 1:
                alt += 1
        return {"zero": zero, "sentinel": sentinel, "with_art": with_art,
                "alt_cards": alt, "total_arts": total_arts}


# ---------------------------------------------------------------------------
# GIM block chain
# ---------------------------------------------------------------------------
def iter_blocks(raw: bytes):
    """Yield (block_offset, type, size, next, data) for a GIM byte string."""
    if raw[:len(GIM_MAGIC)] != GIM_MAGIC:
        raise ValueError(f"not a GIM: {raw[:12]!r}")
    off = BLOCK_TOP
    for _ in range(16):
        if off + BLOCK_HEADER_SIZE > len(raw):
            break
        typ, _pad, size, nxt, data = struct.unpack_from("<HHIII", raw, off)
        yield off, typ, size, nxt, data
        if nxt == 0:
            break
        off += nxt


class GimTexture:
    """A GIM parsed into its image header + palette + texture bytes."""

    __slots__ = ("raw", "fmt", "width", "height", "bpp", "data_off",
                 "palette")

    def __init__(self, raw: bytes):
        self.raw = raw
        self.fmt = -1
        self.width = self.height = self.bpp = 0
        self.data_off = -1
        self.palette = None
        for off, typ, _size, _nxt, _data in iter_blocks(raw):
            hdr = off + BLOCK_HEADER_SIZE
            if hdr + IMAGE_HEADER_SIZE > len(raw):
                continue
            fmt = struct.unpack_from("<H", raw, hdr + IH_FORMAT_OFF)[0]
            w = struct.unpack_from("<H", raw, hdr + IH_WIDTH_OFF)[0]
            h = struct.unpack_from("<H", raw, hdr + IH_HEIGHT_OFF)[0]
            bpp = struct.unpack_from("<H", raw, hdr + IH_BPP_OFF)[0]
            if typ == BLOCK_PALETTE:
                # The palette image header's width is the entry count (TF1's own
                # format-4 assets declare 16, its format-5 assets 256).
                base = hdr + IMAGE_HEADER_SIZE
                n = w if 1 <= w <= 256 else 256
                self.palette = [raw[base + i * 4: base + i * 4 + 4]
                                for i in range(n)]
            elif typ == BLOCK_IMAGE:
                self.fmt, self.width, self.height, self.bpp = fmt, w, h, bpp
                self.data_off = hdr + IMAGE_HEADER_SIZE
        if self.data_off < 0:
            raise ValueError("GIM has no image block (type 4)")

    @property
    def body(self) -> bytes:
        return self.raw[self.data_off:]

    def to_pixels(self) -> tuple[int, int, bytes]:
        """Decode to RGBA.  Raises UnsupportedFormat for format 8."""
        return decode_texture(self.fmt, self.width, self.height, self.bpp,
                              self.body, self.palette)


# ---------------------------------------------------------------------------
# PSP GE texture swizzle
# ---------------------------------------------------------------------------
def unswizzle(data: bytes, width: int, height: int, bpp: int) -> bytes:
    """Undo the PSP GE texture swizzle (see the module docstring).

    ``height`` is in pixels; for compressed formats pass the block-row count.
    """
    row_bytes = width * bpp // 8
    if row_bytes % SWIZZLE_BLOCK or height % SWIZZLE_ROWS:
        raise ValueError(f"geometry {width}x{height}@{bpp}bpp is not a "
                         f"whole number of 16-byte x 8-row swizzle units")
    blocks_per_row = row_bytes // SWIZZLE_BLOCK
    out = bytearray(len(data))
    for uy in range(height // SWIZZLE_ROWS):
        for ux in range(blocks_per_row):
            base = (uy * blocks_per_row + ux) * SWIZZLE_UNIT
            for r in range(SWIZZLE_ROWS):
                src = base + r * SWIZZLE_BLOCK
                dst = (uy * SWIZZLE_ROWS + r) * row_bytes + ux * SWIZZLE_BLOCK
                out[dst:dst + SWIZZLE_BLOCK] = data[src:src + SWIZZLE_BLOCK]
    return out


def swizzle(data: bytes, width: int, height: int, bpp: int) -> bytes:
    """The exact inverse of :func:`unswizzle` (linear row-major -> swizzled).

    Rejects geometries that are not a whole number of 16-byte x 8-row swizzle
    units, exactly like :func:`unswizzle` (so the two stay symmetric).
    """
    row_bytes = width * bpp // 8
    if row_bytes % SWIZZLE_BLOCK or height % SWIZZLE_ROWS:
        raise ValueError(f"geometry {width}x{height}@{bpp}bpp is not a "
                         f"whole number of 16-byte x 8-row swizzle units")
    blocks_per_row = row_bytes // SWIZZLE_BLOCK
    out = bytearray(len(data))
    for uy in range(height // SWIZZLE_ROWS):
        for ux in range(blocks_per_row):
            base = (uy * blocks_per_row + ux) * SWIZZLE_UNIT
            for r in range(SWIZZLE_ROWS):
                src = (uy * SWIZZLE_ROWS + r) * row_bytes + ux * SWIZZLE_BLOCK
                dst = base + r * SWIZZLE_BLOCK
                out[dst:dst + SWIZZLE_BLOCK] = data[src:src + SWIZZLE_BLOCK]
    return bytes(out)


def decode_texture(fmt: int, width: int, height: int, bpp: int,
                   body: bytes, palette) -> tuple[int, int, bytes]:
    """Decode a GIM texture body to 8-bit RGBA."""
    if fmt == FMT_RGBA8888:
        need = width * height * 4
        return width, height, unswizzle(body[:need], width, height, 32)
    if fmt == FMT_INDEX8:
        need = width * height
        if palette is None:
            raise ValueError("INDEX8 texture without a palette block")
        idx = unswizzle(body[:need], width, height, 8)
        if max(idx, default=0) >= len(palette):
            raise ValueError(f"INDEX8 index exceeds the {len(palette)}-entry "
                             f"palette block")
        return width, height, b"".join(palette[i] for i in idx)
    if fmt == FMT_INDEX4:
        # INDEX4 packs two pixels per byte, first (left) pixel in the low nibble.
        # This order is measured, not assumed: decoding TF1's own format-4
        # ``bg0001.gim`` with high-nibble-first doubles the mean horizontal
        # gradient (16.5 vs 10.1) and shows a vertical comb.
        if palette is None:
            raise ValueError("INDEX4 texture without a palette block")
        n = width * height
        packed = unswizzle(body[:(n + 1) // 2], width, height, 4)
        out = bytearray(n * 4)
        for i in range(n):
            byte = packed[i >> 1]
            idx = (byte & 0x0F) if (i & 1) == 0 else (byte >> 4)
            if idx >= len(palette):
                raise ValueError(f"INDEX4 index {idx} exceeds the "
                                 f"{len(palette)}-entry palette block")
            out[i * 4:i * 4 + 4] = palette[idx]
        return width, height, bytes(out)
    if fmt == FMT_4BPP:
        raise UnsupportedFormat(
            "format 8 (bpp 4) is not decoded: no interpretation tried "
            "(standard DXT1, DXT1 + PSP swizzle, and ~100 alternate "
            "swizzle/tile/block permutations) produces a recognisable card")
    raise UnsupportedFormat(f"unknown GIM pixel format {fmt} (bpp {bpp})")


# ---------------------------------------------------------------------------
# Format-5 GIM encoder
# ---------------------------------------------------------------------------
def _write_image_header(out: bytearray, off: int, fmt: int, flags: int,
                        width: int, height: int, bpp: int,
                        payload: int) -> None:
    """Write the 0x40-byte image/palette header at ``off`` (see window_s0002).

    Everything except formation/size is a constant copied from TF1's own
    format-5 ``window_s0002.gim`` template:
    ``+0x0E = 0x10``, ``+0x10 = 0x00020008`` for indexed (``0x00020001`` for
    RGBA), ``+0x18 = 0x30``, ``+0x1C = 0x40``, ``+0x20 = 0x40 + payload``,
    ``+0x28 = 0x00010001`` indexed / ``0x00010002`` RGBA, ``+0x2C = 0x00010003``,
    ``+0x30 = 0x40``.
    """
    struct.pack_into("<HHHHHHH", out, off, 0x30, 0, fmt, flags, width,
                     height, bpp)
    struct.pack_into("<H", out, off + 0x0E, 0x10)
    indexed = fmt in (FMT_INDEX4, FMT_INDEX8)
    struct.pack_into("<I", out, off + 0x10,
                     0x00020008 if indexed else 0x00020001)
    struct.pack_into("<I", out, off + 0x14, 0)
    struct.pack_into("<I", out, off + 0x18, 0x30)
    struct.pack_into("<I", out, off + 0x1C, 0x40)
    struct.pack_into("<I", out, off + 0x20, 0x40 + payload)
    struct.pack_into("<I", out, off + 0x24, 0)
    struct.pack_into("<I", out, off + 0x28,
                     0x00010001 if indexed else 0x00010002)
    struct.pack_into("<I", out, off + 0x2C, 0x00010003)
    struct.pack_into("<I", out, off + 0x30, 0x40)


def bpp_of(fmt: int) -> int:
    """Bits per pixel of the indexed formats the encoder writes."""
    if fmt == FMT_INDEX8:
        return 8
    if fmt == FMT_INDEX4:
        return 4
    raise ValueError(f"the encoder writes INDEX4 (format 4) and INDEX8 "
                     f"(format 5), not format {fmt}")


def slot_overhead(fmt: int, palette_entries: int) -> int:
    """Bytes a GIM of ``fmt`` needs before its first pixel byte.

    magic (16) + the two wrapper block headers (32) + the palette block (16
    block header + 64 image header + ``palette_entries * 4`` RGBA) + the image
    block header (16 + 64).  The palette block is the only variable part.
    """
    bpp_of(fmt)  # rejects unsupported formats
    if not 1 <= palette_entries <= 256:
        raise ValueError(f"palette_entries {palette_entries} is out of range")
    return (FORMAT5_WRAPPER_OVERHEAD + BLOCK_HEADER_SIZE + IMAGE_HEADER_SIZE
            + palette_entries * 4 + BLOCK_HEADER_SIZE + IMAGE_HEADER_SIZE)


def pack_indices(fmt: int, width: int, height: int, indices: bytes) -> bytes:
    """Linear row-major index plane -> the packed bytes the format stores.

    INDEX8 stores one byte per pixel.  INDEX4 stores two pixels per byte with
    the first (left) pixel in the low nibble.
    """
    n = width * height
    if len(indices) != n:
        raise ValueError(f"indices must be {n} bytes, got {len(indices)}")
    if fmt == FMT_INDEX8:
        return bytes(indices)
    if fmt != FMT_INDEX4:
        raise ValueError(f"cannot pack format {fmt}")
    out = bytearray((n + 1) // 2)
    for i in range(0, n, 2):
        lo = indices[i]
        hi = indices[i + 1] if i + 1 < n else 0
        out[i >> 1] = lo | (hi << 4)
    return bytes(out)


def build_gim_indexed(width: int, height: int, fmt: int, palette_rgba: bytes,
                      indices: bytes,
                      palette_entries: int | None = None) -> bytes:
    """Emit a complete, structurally valid paletted GIM (INDEX4 or INDEX8).

    ``palette_rgba`` holds ``palette_entries`` RGBA8888 entries (default: as
    many as the buffer holds, so a 1024-byte buffer still means 256).  The
    palette block declares exactly that many entries and is sized accordingly,
    which is the variable-size palette an INDEX8 canvas needs to fit its slot.
    ``indices`` is the linear row-major index plane (``width * height`` bytes)
    and is packed and swizzled here.  The block chain, header constants and
    wrapper sizes follow TF1's own files, with every size field recomputed for
    this geometry and palette.
    """
    if width < 16 or width % 16:
        raise ValueError(f"width {width} must be a non-zero multiple of 16")
    if height < 8 or height % 8:
        raise ValueError(f"height {height} must be a non-zero multiple of 8 "
                         f"(PSP swizzle works in 8-row units)")
    bpp = bpp_of(fmt)
    max_entries = 16 if fmt == FMT_INDEX4 else 256
    if palette_entries is None:
        palette_entries = len(palette_rgba) // 4
    if not 1 <= palette_entries <= max_entries:
        raise ValueError(f"format {fmt} allows 1..{max_entries} palette "
                         f"entries, got {palette_entries}")
    if len(palette_rgba) != palette_entries * 4:
        raise ValueError(f"palette_rgba must be {palette_entries} RGBA8888 "
                         f"entries ({palette_entries * 4} B), got "
                         f"{len(palette_rgba)} B")
    if len(indices) != width * height:
        raise ValueError(f"indices must be {width * height} bytes, got "
                         f"{len(indices)}")
    if max(indices, default=0) >= palette_entries:
        raise ValueError(f"index {max(indices)} is outside the "
                         f"{palette_entries}-entry palette")

    texture = swizzle(pack_indices(fmt, width, height, indices), width, height,
                      bpp)
    palette_block = (BLOCK_HEADER_SIZE + IMAGE_HEADER_SIZE
                     + palette_entries * 4)
    image_block = BLOCK_HEADER_SIZE + IMAGE_HEADER_SIZE + len(texture)
    palette_off = BLOCK_TOP + 2 * BLOCK_HEADER_SIZE                  # 0x30
    image_off = palette_off + palette_block
    total = image_off + image_block

    out = bytearray(total)
    out[0:len(GIM_MAGIC)] = GIM_MAGIC
    struct.pack_into("<HHIII", out, 0x10, 2, 0, total - 0x10, 16, 0x10)
    struct.pack_into("<HHIII", out, 0x20, 3, 0, total - 0x20, 16, 0x10)
    struct.pack_into("<HHIII", out, palette_off, BLOCK_PALETTE, 0,
                     palette_block, palette_block, 0x10)
    _write_image_header(out, palette_off + BLOCK_HEADER_SIZE,
                        FMT_RGBA8888, 0, palette_entries, 1, 32,
                        palette_entries * 4)
    pal_data = palette_off + BLOCK_HEADER_SIZE + IMAGE_HEADER_SIZE
    out[pal_data:pal_data + palette_entries * 4] = palette_rgba
    struct.pack_into("<HHIII", out, image_off, BLOCK_IMAGE, 0,
                     image_block, image_block, 0x10)
    _write_image_header(out, image_off + BLOCK_HEADER_SIZE,
                        fmt, 1, width, height, bpp, len(texture))
    tex_off = image_off + BLOCK_HEADER_SIZE + IMAGE_HEADER_SIZE
    out[tex_off:tex_off + len(texture)] = texture
    return bytes(out)


def build_gim_format5(width: int, height: int, palette_rgba: bytes,
                      indices: bytes,
                      palette_entries: int | None = None) -> bytes:
    """Emit a complete, structurally valid INDEX8 (format 5) GIM.

    ``palette_rgba`` is 256 RGBA8888 entries (1024 bytes) by default; pass
    ``palette_entries`` (and a shorter buffer) for a smaller palette block.
    """
    return build_gim_indexed(width, height, FMT_INDEX8, palette_rgba, indices,
                             palette_entries)


def build_gim_format4(width: int, height: int, palette_rgba: bytes,
                      indices: bytes,
                      palette_entries: int | None = None) -> bytes:
    """Emit a complete, structurally valid INDEX4 (format 4) GIM.

    ``palette_rgba`` holds up to 16 RGBA8888 entries (64 bytes).
    """
    return build_gim_indexed(width, height, FMT_INDEX4, palette_rgba, indices,
                             palette_entries)


# ---------------------------------------------------------------------------
# PNG input, scaling and quantisation (stdlib only)
# ---------------------------------------------------------------------------
def _png_sample(row: bytes, index: int, bitdepth: int) -> int:
    if bitdepth == 8:
        return row[index]
    if bitdepth == 16:
        return (row[index * 2] << 8) | row[index * 2 + 1]
    per_byte = 8 // bitdepth
    byte = row[index // per_byte]
    shift = (per_byte - 1 - (index % per_byte)) * bitdepth
    return (byte >> shift) & ((1 << bitdepth) - 1)


def read_png(path: str) -> tuple[int, int, bytes]:
    """Decode a non-interlaced PNG to 8-bit RGBA (standard library only)."""
    with open(path, "rb") as fh:
        data = fh.read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path}: not a PNG file")
    pos = 8
    idat = bytearray()
    plte = None
    trns = None
    width = height = bitdepth = colortype = interlace = 0
    while pos + 12 <= len(data):
        (length,) = struct.unpack_from(">I", data, pos)
        tag = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if tag == b"IHDR":
            (width, height, bitdepth, colortype, _c, _f,
             interlace) = struct.unpack(">IIBBBBB", chunk)
        elif tag == b"PLTE":
            plte = bytes(chunk)
        elif tag == b"tRNS":
            trns = bytes(chunk)
        elif tag == b"IDAT":
            idat += chunk
        elif tag == b"IEND":
            break
    if interlace:
        raise ValueError(f"{path}: interlaced PNG is not supported")
    if colortype not in (0, 2, 3, 4, 6):
        raise ValueError(f"{path}: unsupported PNG colour type {colortype}")
    if bitdepth not in (1, 2, 4, 8, 16):
        raise ValueError(f"{path}: unsupported PNG bit depth {bitdepth}")
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[colortype]
    filter_bpp = max(1, channels * bitdepth // 8)
    stride = (width * channels * bitdepth + 7) // 8
    raw = zlib.decompress(bytes(idat))
    rows = []
    prev = bytearray(stride)
    p = 0
    for _y in range(height):
        if p >= len(raw):
            raise ValueError(f"{path}: truncated PNG data")
        ftype = raw[p]
        p += 1
        row = bytearray(raw[p:p + stride])
        p += stride
        if ftype == 1:
            for i in range(filter_bpp, stride):
                row[i] = (row[i] + row[i - filter_bpp]) & 0xFF
        elif ftype == 2:
            for i in range(stride):
                row[i] = (row[i] + prev[i]) & 0xFF
        elif ftype == 3:
            for i in range(stride):
                a = row[i - filter_bpp] if i >= filter_bpp else 0
                row[i] = (row[i] + ((a + prev[i]) >> 1)) & 0xFF
        elif ftype == 4:
            for i in range(stride):
                a = row[i - filter_bpp] if i >= filter_bpp else 0
                b = prev[i]
                c = prev[i - filter_bpp] if i >= filter_bpp else 0
                pp = a + b - c
                pa, pb, pc = abs(pp - a), abs(pp - b), abs(pp - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                row[i] = (row[i] + pr) & 0xFF
        elif ftype != 0:
            raise ValueError(f"{path}: unsupported PNG filter {ftype}")
        rows.append(row)
        prev = row
    scale_sub = {1: 255, 2: 85, 4: 17}
    out = bytearray(width * height * 4)
    for y in range(height):
        row = rows[y]
        base = y * width * 4
        for x in range(width):
            o = base + x * 4
            if colortype == 3:
                idx = _png_sample(row, x, bitdepth)
                if plte is None or idx * 3 + 2 >= len(plte):
                    raise ValueError(f"{path}: PNG palette index out of range")
                out[o] = plte[idx * 3]
                out[o + 1] = plte[idx * 3 + 1]
                out[o + 2] = plte[idx * 3 + 2]
                out[o + 3] = (trns[idx] if trns is not None
                              and idx < len(trns) else 255)
            elif colortype == 0:
                v = _png_sample(row, x, bitdepth)
                v = (v >> 8) if bitdepth == 16 else (
                    v * scale_sub[bitdepth] if bitdepth in scale_sub else v)
                out[o] = out[o + 1] = out[o + 2] = v
                out[o + 3] = 255
            elif colortype == 4:
                g = _png_sample(row, x * 2, bitdepth)
                a = _png_sample(row, x * 2 + 1, bitdepth)
                if bitdepth == 16:
                    g >>= 8
                    a >>= 8
                out[o] = out[o + 1] = out[o + 2] = g
                out[o + 3] = a
            else:
                r = _png_sample(row, x * channels, bitdepth)
                g = _png_sample(row, x * channels + 1, bitdepth)
                b = _png_sample(row, x * channels + 2, bitdepth)
                if bitdepth == 16:
                    r >>= 8
                    g >>= 8
                    b >>= 8
                out[o] = r
                out[o + 1] = g
                out[o + 2] = b
                if colortype == 6:
                    a = _png_sample(row, x * channels + 3, bitdepth)
                    out[o + 3] = a >> 8 if bitdepth == 16 else a
                else:
                    out[o + 3] = 255
    return width, height, bytes(out)


def resize_nearest(rgba: bytes, sw: int, sh: int, dw: int, dh: int) -> bytes:
    """Nearest-neighbour resample of an RGBA8 buffer."""
    if (sw, sh) == (dw, dh):
        return rgba
    out = bytearray(dw * dh * 4)
    for y in range(dh):
        sy = y * sh // dh
        srow = sy * sw * 4
        drow = y * dw * 4
        for x in range(dw):
            sx = x * sw // dw
            out[drow + x * 4:drow + x * 4 + 4] = rgba[
                srow + sx * 4:srow + sx * 4 + 4]
    return bytes(out)


def resize_area(rgba: bytes, sw: int, sh: int, dw: int, dh: int) -> bytes:
    """Box/area-average resample of an RGBA8 buffer (antialiased downscale).

    Each destination pixel averages the source pixels whose integer span maps
    to it (``[x*sw//dw, (x+1)*sw//dw)``), which is the area filter.  The
    averaging window is at least one source pixel, so upscaling degrades to
    nearest instead of producing empty pixels.
    """
    if (sw, sh) == (dw, dh):
        return rgba
    if sw <= 0 or sh <= 0 or dw <= 0 or dh <= 0:
        raise ValueError("resize_area needs positive dimensions")
    out = bytearray(dw * dh * 4)
    for dy in range(dh):
        y0 = dy * sh // dh
        y1 = max(y0 + 1, (dy + 1) * sh // dh)
        if y1 > sh:
            y1 = sh
        for dx in range(dw):
            x0 = dx * sw // dw
            x1 = max(x0 + 1, (dx + 1) * sw // dw)
            if x1 > sw:
                x1 = sw
            r = g = b = a = n = 0
            for y in range(y0, y1):
                row = y * sw
                for x in range(x0, x1):
                    o = (row + x) * 4
                    r += rgba[o]
                    g += rgba[o + 1]
                    b += rgba[o + 2]
                    a += rgba[o + 3]
                    n += 1
            o = (dy * dw + dx) * 4
            out[o] = r // n
            out[o + 1] = g // n
            out[o + 2] = b // n
            out[o + 3] = a // n
    return bytes(out)


def cover_crop(rgba: bytes, sw: int, sh: int,
               dw: int, dh: int) -> tuple[int, int, bytes]:
    """Centre-crop an RGBA8 buffer to the aspect ratio ``dw:dh`` (cover).

    Returns ``(cw, ch, cropped)``: the largest centred crop of the source that
    matches the target aspect, so scaling it to ``dw x dh`` fills the canvas
    without letterboxing.  When the source already has the target aspect this
    is the identity.  Resampling to exactly ``dw x dh`` is the caller's next
    step (``resize_area`` / ``resize_nearest``).
    """
    if sw <= 0 or sh <= 0 or dw <= 0 or dh <= 0:
        raise ValueError("cover_crop needs positive dimensions")
    if sw * dh > sh * dw:          # source is too wide: cut the sides
        cw, ch = sh * dw // dh, sh
    else:                          # source is too tall: cut top and bottom
        cw, ch = sw, sw * dh // dw
    cw = max(1, min(cw, sw))
    ch = max(1, min(ch, sh))
    if (cw, ch) == (sw, sh):
        return sw, sh, rgba
    x0 = (sw - cw) // 2
    y0 = (sh - ch) // 2
    out = bytearray(cw * ch * 4)
    for y in range(ch):
        src = ((y0 + y) * sw + x0) * 4
        out[y * cw * 4:(y + 1) * cw * 4] = rgba[src:src + cw * 4]
    return cw, ch, bytes(out)


def _nearest_center(px, centers) -> int:
    """Index of the palette centre closest to ``px`` in RGBA space."""
    best, bestd = 0, 1 << 30
    for k, c in enumerate(centers):
        d = ((px[0] - c[0]) ** 2 + (px[1] - c[1]) ** 2
             + (px[2] - c[2]) ** 2 + (px[3] - c[3]) ** 2)
        if d < bestd:
            bestd, best = d, k
    return best


def _floyd_steinberg(rgba: bytes, width: int, height: int, centers):
    """Error-diffuse ``rgba`` onto ``centers`` (Floyd-Steinberg).

    Returns ``(palette, indices, colour_count)`` with the same shape as the
    non-dithered ``_median_cut`` result.  Each pixel is mapped to its nearest
    centre and the residual is distributed 7/16 right, 3/16 down-left,
    5/16 down and 1/16 down-right.  The working buffer is float, so accumulated
    error is not re-quantised between neighbours.
    """
    n = width * height
    buf = [float(v) for v in rgba[:n * 4]]
    indices = bytearray(n)

    def spread(x: int, y: int, factor: float, err) -> None:
        if 0 <= x < width and 0 <= y < height:
            j = (y * width + x) * 4
            buf[j] += err[0] * factor
            buf[j + 1] += err[1] * factor
            buf[j + 2] += err[2] * factor
            buf[j + 3] += err[3] * factor

    for y in range(height):
        for x in range(width):
            i = (y * width + x) * 4
            px = buf[i:i + 4]
            k = _nearest_center(px, centers)
            indices[y * width + x] = k
            c = centers[k]
            err = (px[0] - c[0], px[1] - c[1], px[2] - c[2], px[3] - c[3])
            spread(x + 1, y, 7 / 16, err)
            spread(x - 1, y + 1, 3 / 16, err)
            spread(x, y + 1, 5 / 16, err)
            spread(x + 1, y + 1, 1 / 16, err)

    palette = bytearray(256 * 4)
    for i, colour in enumerate(centers[:256]):
        palette[i * 4:i * 4 + 4] = colour
    return bytes(palette), bytes(indices), min(len(centers), 256)


def _median_cut(rgba: bytes, max_colors: int, dither: bool = False,
                width: int | None = None, height: int | None = None):
    pixels = [rgba[i * 4:i * 4 + 4] for i in range(len(rgba) // 4)]
    # Copy the pixel list: the first split sorts the box in place, and
    # ``pixels`` must keep its row-major order for the index assignment below.
    boxes = [list(pixels)]
    while len(boxes) < max_colors:
        bi = -1
        biggest = -1
        for i, box in enumerate(boxes):
            if len(box) < 2:
                continue
            rng = max(max(p[c] for p in box) - min(p[c] for p in box)
                      for c in range(4))
            if rng > biggest:
                biggest = rng
                bi = i
        if bi < 0:
            break
        box = boxes.pop(bi)
        ch = max(range(4), key=lambda c: max(p[c] for p in box)
                 - min(p[c] for p in box))
        box.sort(key=lambda p: p[ch])
        mid = len(box) // 2
        boxes.append(box[:mid])
        boxes.append(box[mid:])
    centers = [bytes(sum(p[c] for p in box) // len(box) for c in range(4))
               for box in boxes]
    if dither:
        if width is None or height is None or width * height != len(pixels):
            raise ValueError("dithering needs the texture width and height")
        return _floyd_steinberg(rgba, width, height, centers)
    palette = bytearray(256 * 4)
    for i, colour in enumerate(centers[:256]):
        palette[i * 4:i * 4 + 4] = colour
    cache: dict[bytes, int] = {}
    indices = bytearray(len(pixels))
    for i, px in enumerate(pixels):
        j = cache.get(px)
        if j is None:
            best, bestd = 0, 1 << 30
            for k, c in enumerate(centers):
                d = ((px[0] - c[0]) ** 2 + (px[1] - c[1]) ** 2
                     + (px[2] - c[2]) ** 2 + (px[3] - c[3]) ** 2)
                if d < bestd:
                    bestd, best = d, k
            j = best
            cache[px] = j
        indices[i] = j
    return bytes(palette), bytes(indices), min(len(centers), 256)


def quantise_palette(rgba: bytes, max_colors: int = 256, dither: bool = False,
                     width: int | None = None, height: int | None = None):
    """Return (256-entry RGBA palette, one index byte per pixel, colour count).

    Up to ``max_colors`` distinct RGBA values are preserved exactly (so a
    canary round-trips losslessly); a larger set is reduced with a median cut.
    With ``dither`` the reduced palette is applied with Floyd-Steinberg error
    diffusion, which needs the texture ``width`` and ``height``.
    """
    n = len(rgba) // 4
    distinct = set()
    for i in range(n):
        distinct.add(rgba[i * 4:i * 4 + 4])
        if len(distinct) > max_colors:
            break
    if len(distinct) <= max_colors:
        palette = bytearray(256 * 4)
        indices = bytearray(n)
        order: dict[bytes, int] = {}
        for i in range(n):
            key = rgba[i * 4:i * 4 + 4]
            j = order.get(key)
            if j is None:
                j = len(order)
                order[key] = j
                palette[j * 4:j * 4 + 4] = key
            indices[i] = j
        return bytes(palette), bytes(indices), len(order)
    return _median_cut(rgba, max_colors, dither, width, height)


def prepare_gim(png_path: str, w: int, h: int, fmt: int, palette_entries: int,
                resample: str = "area", dither: bool = False):
    """PNG -> a ready-to-inject paletted GIM for a ``w x h`` canvas.

    The PNG is cover-cropped to the canvas aspect and resampled with
    ``resize_area`` (``resample='area'``) or ``resize_nearest``
    (``resample='nearest'``), then quantised.  Returns ``(gim, n_colours)``.
    """
    png_w, png_h, rgba = read_png(png_path)
    cw, ch, cropped = cover_crop(rgba, png_w, png_h, w, h)
    if resample == "area":
        scaled = resize_area(cropped, cw, ch, w, h)
    elif resample == "nearest":
        scaled = resize_nearest(cropped, cw, ch, w, h)
    else:
        raise ValueError(f"unknown resample mode {resample!r}")
    palette, indices, n_colours = quantise_palette(
        scaled, palette_entries, dither=dither, width=w, height=h)
    palette = palette[:palette_entries * 4]
    gim = build_gim_indexed(w, h, fmt, palette, indices, palette_entries)
    return gim, n_colours


# ---------------------------------------------------------------------------
# Payload re-emission (structural round-trip, format agnostic)
# ---------------------------------------------------------------------------
def parse_dxt1_blocks(body: bytes) -> list[tuple[int, int, int]]:
    """Split a body into 8-byte units for the A2 re-emission proof."""
    blocks: list[tuple[int, int, int]] = []
    n = len(body) // 8
    for i in range(n):
        c0, c1, idx = struct.unpack_from("<HHI", body, i * 8)
        blocks.append((c0, c1, idx))
    tail = len(body) - n * 8
    if tail:
        raw = body[n * 8:] + b"\x00" * (8 - tail)
        blocks.append((0, 0, struct.unpack_from("<I", raw, 4)[0]))
    return blocks


def encode_dxt1_blocks(blocks: list[tuple[int, int, int]]) -> bytes:
    """Inverse of ``parse_dxt1_blocks`` (byte-identical)."""
    out = bytearray()
    for c0, c1, idx in blocks:
        out += struct.pack("<HHI", c0, c1, idx)
    return bytes(out)


# ---------------------------------------------------------------------------
# Native cardm DXT1 (BC1) encoder -- ESTADO-E8.md 9.8
# ---------------------------------------------------------------------------
# A cardm slot is a 64x64 BC1 image.  Every 8-byte block stores its two 32-bit
# words swapped: the 4 index bytes first (in order 0,1,2,3) and then the RGB565
# endpoints c0 (LE) then c1 (LE).  There is no GE swizzle and no palette.  The
# layout is proven by ``trabajo/e8/cardm_decode.py`` and the decodable
# thumbnails in ``trabajo/e8/cardm_probe/``; this encoder is its inverse.
DXT1_BLOCK = 4                 # block edge in pixels
DXT1_BLOCK_BYTES = 8


def rgb565_unpack(value: int) -> tuple[int, int, int]:
    """RGB565 -> 8-bit RGB, expansion identical to cardm_decode.py."""
    r = (value >> 11) & 0x1F
    g = (value >> 5) & 0x3F
    b = value & 0x1F
    return ((r * 255 + 15) // 31, (g * 255 + 31) // 63, (b * 255 + 15) // 31)


def rgb565_pack(r: int, g: int, b: int) -> int:
    """8-bit RGB -> RGB565 (rounded and clamped)."""
    r = (r * 31 + 127) // 255
    g = (g * 63 + 127) // 255
    b = (b * 31 + 127) // 255
    r = 0 if r < 0 else 31 if r > 31 else r
    g = 0 if g < 0 else 63 if g > 63 else g
    b = 0 if b < 0 else 31 if b > 31 else b
    return (r << 11) | (g << 5) | b


def _bc1_colours(c0: int, c1: int) -> list[tuple[int, int, int]]:
    """The four RGB colours a BC1 block decodes to, matching cardm_decode.py."""
    a = rgb565_unpack(c0)
    b = rgb565_unpack(c1)
    if c0 > c1:
        return [a, b,
                tuple((2 * a[i] + b[i]) // 3 for i in range(3)),
                tuple((a[i] + 2 * b[i]) // 3 for i in range(3))]
    return [a, b,
            tuple((a[i] + b[i]) // 2 for i in range(3)),
            (0, 0, 0)]


def _bc1_bits(block, c0: int, c1: int) -> tuple[int, int]:
    """(index plane, squared error) for one 16-pixel block and endpoint pair."""
    palette = _bc1_colours(c0, c1)
    bits = 0
    err = 0
    for i, p in enumerate(block):
        best, best_d = 0, 1 << 30
        for k in range(4):
            q = palette[k]
            d = ((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2
                 + (p[2] - q[2]) ** 2)
            if d < best_d:
                best_d, best = d, k
        bits |= best << (2 * i)
        err += best_d
    return bits, err


def _bc1_refit(block, c0: int, c1: int):
    """One least-squares re-fit of the endpoints for the current indices.

    Every decoded colour is a linear combination ``a * wa + b * wb`` of the two
    continuous endpoints, so with the index plane fixed the best endpoints are
    the 2x2 normal-equation solution per channel.  Returns
    ``(err, c0, c1, bits)`` or ``None`` when the block is degenerate.
    """
    bits, _err = _bc1_bits(block, c0, c1)
    weights = ((1.0, 0.0), (0.0, 1.0), (2 / 3, 1 / 3), (1 / 3, 2 / 3))
    sa = sb = sab = 0.0
    pa = [0.0, 0.0, 0.0]
    pb = [0.0, 0.0, 0.0]
    for i, p in enumerate(block):
        wa, wb = weights[(bits >> (2 * i)) & 3]
        sa += wa * wa
        sab += wa * wb
        sb += wb * wb
        for ch in range(3):
            pa[ch] += wa * p[ch]
            pb[ch] += wb * p[ch]
    det = sa * sb - sab * sab
    if det < 1e-9:
        return None
    a = [(pa[ch] * sb - pb[ch] * sab) / det for ch in range(3)]
    b = [(pb[ch] * sa - pa[ch] * sab) / det for ch in range(3)]
    c0n = rgb565_pack(round(a[0]), round(a[1]), round(a[2]))
    c1n = rgb565_pack(round(b[0]), round(b[1]), round(b[2]))
    if c0n < c1n:
        c0n, c1n = c1n, c0n
    bits, err = _bc1_bits(block, c0n, c1n)
    return err, c0n, c1n, bits


def _bc1_candidates(block):
    """Continuous endpoint-pair candidates for a 4x4 block (RGB tuples)."""
    n = len(block)
    out = []
    mn = [min(p[k] for p in block) for k in range(3)]
    mx = [max(p[k] for p in block) for k in range(3)]
    out.append((tuple(mx), tuple(mn)))
    best, pa, pb = -1, block[0], block[0]
    for i in range(n):
        for j in range(i + 1, n):
            d = sum((block[i][k] - block[j][k]) ** 2 for k in range(3))
            if d > best:
                best, pa, pb = d, block[i], block[j]
    out.append((pa, pb))
    mean = [sum(p[k] for p in block) / n for k in range(3)]
    cov = [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]]
    for p in block:
        d = [p[k] - mean[k] for k in range(3)]
        for r in range(3):
            for c in range(3):
                cov[r][c] += d[r] * d[c]
    axis = [1.0, 1.0, 1.0]
    for _ in range(6):
        nxt = [sum(cov[r][c] * axis[c] for c in range(3)) for r in range(3)]
        norm = sum(v * v for v in nxt) ** 0.5
        if norm < 1e-9:
            axis = None
            break
        axis = [v / norm for v in nxt]
    if axis is not None:
        ts = [sum((p[k] - mean[k]) * axis[k] for k in range(3)) for p in block]
        t0, t1 = min(ts), max(ts)
        out.append((tuple(mean[k] + t1 * axis[k] for k in range(3)),
                    tuple(mean[k] + t0 * axis[k] for k in range(3))))
    return out


def encode_dxt1_block(pixels) -> bytes:
    """Encode 16 RGBA ``(r,g,b,a)`` pixels to one swapped-word BC1 block."""
    block = [(p[0], p[1], p[2]) for p in pixels]
    best = None
    for a, b in _bc1_candidates(block):
        c0 = rgb565_pack(round(a[0]), round(a[1]), round(a[2]))
        c1 = rgb565_pack(round(b[0]), round(b[1]), round(b[2]))
        if c0 < c1:
            c0, c1 = c1, c0
        bits, err = _bc1_bits(block, c0, c1)
        if best is None or err < best[0]:
            best = (err, c0, c1, bits)
        refit = _bc1_refit(block, c0, c1)
        if refit is not None and refit[0] < best[0]:
            best = refit
    _err, c0, c1, bits = best
    return struct.pack("<I", bits) + struct.pack("<HH", c0, c1)


# ---------------------------------------------------------------------------
# Native cardh DXT1 (BC1) -- ESTADO-E8.md 9.9
# ---------------------------------------------------------------------------
# A cardh slot is exactly 4096 B: 128 constant template-header bytes followed
# by 3968 B of the same swapped-word BC1 stream as cardm, 32 blocks (128 px)
# per row, plain row-major, no GE swizzle.  3968 B = 496 blocks = 15 full
# block rows + a half (16-block) last row = a 128x62 visible canvas (the
# declared 128x64 needs 4096 B and cannot fit behind the header).
CARDH_W = 128
CARDH_H = 62
CARDH_HEADER_SIZE = GIM_HEADER_SIZE           # 128 B constant GIM template
CARDH_SLOT_SIZE = 4096
CARDH_BODY_SIZE = CARDH_SLOT_SIZE - CARDH_HEADER_SIZE   # 3968 B
CARDH_BLOCKS_PER_ROW = CARDH_W // 4           # 32
GREEN_KEY = (0, 97, 0)                         # flat chroma-key in native art


def decode_dxt1_swapped(data: bytes, width: int, height: int) -> bytes:
    """Decode a swapped-word BC1 stream to RGBA8 (inverse of the encoder).

    Unlike the cardm decoder this tolerates a truncated last block row: the
    cardh body holds 496 blocks for a 128x62 canvas whose 16th block row is
    only half width, so blocks past ``len(data)//8`` are left opaque black.
    """
    if width % DXT1_BLOCK or height <= 0:
        raise ValueError(f"DXT1 needs width a multiple of {DXT1_BLOCK} and a "
                         f"positive height, got {width}x{height}")
    bw, bh = width // DXT1_BLOCK, (height + DXT1_BLOCK - 1) // DXT1_BLOCK
    nblocks = len(data) // DXT1_BLOCK_BYTES
    out = bytearray(width * height * 4)
    for i in range(3, len(out), 4):
        out[i] = 255
    for by in range(bh):
        for bx in range(bw):
            j = by * bw + bx
            if j >= nblocks:
                continue
            b = data[j * 8:j * 8 + 8]
            c0 = b[4] | b[5] << 8
            c1 = b[6] | b[7] << 8
            bits = (b[0] | b[1] << 8 | b[2] << 16 | b[3] << 24)
            cols = _bc1_colours(c0, c1)
            for py in range(DXT1_BLOCK):
                y = by * DXT1_BLOCK + py
                if y >= height:
                    continue
                for px in range(DXT1_BLOCK):
                    x = bx * DXT1_BLOCK + px
                    if x >= width:
                        continue
                    c = cols[(bits >> (2 * (py * 4 + px))) & 3]
                    o = (y * width + x) * 4
                    out[o:o + 3] = bytes(c)
    return bytes(out)


def encode_cardh_native(header: bytes, canvas: bytes) -> bytes:
    """Build one native cardh slot: verbatim ``header`` + encoded body.

    ``header`` must be the 128-byte constant GIM template copied from a native
    slot; ``canvas`` is a 128x62 RGBA8 buffer.  The two missing rows (62..63)
    are padded by repeating row 61 so the encoder can emit full blocks, then
    the 4096-byte block stream is truncated to the 3968-byte body.
    """
    if len(header) != CARDH_HEADER_SIZE:
        raise ValueError(f"cardh header must be {CARDH_HEADER_SIZE} B, got "
                         f"{len(header)}")
    if header[:len(GIM_MAGIC)] != GIM_MAGIC:
        raise ValueError(f"cardh header is not a GIM template: {header[:16]!r}")
    if len(canvas) != CARDH_W * CARDH_H * 4:
        raise ValueError(f"cardh canvas must be {CARDH_W}x{CARDH_H} RGBA, got "
                         f"{len(canvas)} B")
    padded = canvas + canvas[-CARDH_W * 4:] * (64 - CARDH_H)
    body = encode_dxt1_swapped(padded, CARDH_W, 64)[:CARDH_BODY_SIZE]
    slot = bytes(header) + body
    if len(slot) != CARDH_SLOT_SIZE:
        raise ValueError(f"cardh slot is {len(slot)} B, expected "
                         f"{CARDH_SLOT_SIZE}")
    return slot


def decode_cardh_slot(slot: bytes, height: int = CARDH_H) -> bytes:
    """Decode a 4096-byte native cardh slot to a ``CARDH_W`` x height RGBA."""
    if len(slot) < CARDH_SLOT_SIZE:
        raise ValueError(f"cardh slot needs {CARDH_SLOT_SIZE} B, got {len(slot)}")
    return decode_dxt1_swapped(slot[CARDH_HEADER_SIZE:CARDH_SLOT_SIZE],
                               CARDH_W, height)


def green_key_mask(rgba: bytes, width: int, height: int,
                   tolerance: int = 6) -> bytes:
    """One byte per pixel: 1 where the pixel is the flat green chroma-key."""
    mask = bytearray(width * height)
    for i in range(width * height):
        o = i * 4
        if (abs(rgba[o] - GREEN_KEY[0]) + abs(rgba[o + 1] - GREEN_KEY[1])
                + abs(rgba[o + 2] - GREEN_KEY[2]) <= tolerance):
            mask[i] = 1
    return bytes(mask)


def apply_green_mask(canvas: bytes, width: int, height: int,
                     mask: bytes) -> bytes:
    """Paint every masked pixel of ``canvas`` with the flat green chroma-key."""
    if len(canvas) != width * height * 4 or len(mask) != width * height:
        raise ValueError("canvas/mask size mismatch")
    colour = bytes(GREEN_KEY) + b"\xff"
    out = bytearray(canvas)
    for i in range(width * height):
        if mask[i]:
            out[i * 4:i * 4 + 4] = colour
    return bytes(out)


def encode_dxt1_swapped(rgba: bytes, width: int, height: int) -> bytes:
    """Encode an RGBA8 buffer as the native cardm DXT1 body.

    ``width`` and ``height`` must be multiples of 4.  For 64x64 the result is
    exactly 2048 bytes.  Blocks are row-major; alpha is ignored (BC1 is opaque).
    """
    if width % DXT1_BLOCK or height % DXT1_BLOCK:
        raise ValueError(f"DXT1 needs width and height multiples of "
                         f"{DXT1_BLOCK}, got {width}x{height}")
    if len(rgba) < width * height * 4:
        raise ValueError(f"rgba holds {len(rgba)} B, need {width * height * 4}")
    bw, bh = width // DXT1_BLOCK, height // DXT1_BLOCK
    out = bytearray(bw * bh * DXT1_BLOCK_BYTES)
    for by in range(bh):
        for bx in range(bw):
            px = []
            for py in range(DXT1_BLOCK):
                row = (by * DXT1_BLOCK + py) * width + bx * DXT1_BLOCK
                for pxx in range(DXT1_BLOCK):
                    o = (row + pxx) * 4
                    px.append(rgba[o:o + 4])
            o = (by * bw + bx) * DXT1_BLOCK_BYTES
            out[o:o + DXT1_BLOCK_BYTES] = encode_dxt1_block(px)
    return bytes(out)


# ---------------------------------------------------------------------------
# PNG writer (stdlib only)
# ---------------------------------------------------------------------------
def _png_chunk(tag: bytes, data: bytes) -> bytes:
    chunk = tag + data
    return (struct.pack(">I", len(data)) + chunk +
            struct.pack(">I", zlib.crc32(chunk) & 0xFFFFFFFF))


def write_png(path: str, width: int, height: int, rgba: bytes) -> None:
    """Write an 8-bit RGBA PNG.  ``rgba`` is width*height*4 bytes."""
    raw = bytearray()
    stride = width * 4
    for y in range(height):
        raw.append(0)  # filter: none
        raw += rgba[y * stride:(y + 1) * stride]
    png = b"\x89PNG\r\n\x1a\n"
    png += _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
    png += _png_chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += _png_chunk(b"IEND", b"")
    with open(path, "wb") as fh:
        fh.write(png)


def distinct_colours(rgba: bytes) -> int:
    """Number of distinct opaque RGB triples (blank-detection evidence)."""
    seen = set()
    for i in range(0, len(rgba), 4):
        if rgba[i + 3]:
            seen.add(bytes(rgba[i:i + 3]))
    return len(seen)


# ---------------------------------------------------------------------------
# Container rebuild
# --------------------------------------------------------------------------- (A3)
# ---------------------------------------------------------------------------
def rebuild_container(container: Container) -> bytes:
    """Rebuild the file from header region + each slot window, in offset order.

    The header region carries the file header and the (alternate-art) offset
    tables verbatim; the slots are appended in ascending ``slot << 11`` order.
    This is exactly the inverse of how the packer lays the file out.
    """
    out = bytearray(container.blob[:container.blob_base])
    slots = sorted({s for _cid, ss in container.iter_cards() for s in ss})
    pos = container.blob_base
    for slot in slots:
        off = container.offset_of_slot(slot)
        if off != pos:
            # Preserve any gap (there are none in the shipped files, but a
            # rebuild must stay byte-exact if one appears).
            out += container.blob[pos:off]
            pos = off
        out += container.payload(slot)
        pos = off + container.stride
    out += container.blob[pos:]
    return bytes(out)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
def cmd_list(args) -> int:
    c = Container(args.container)
    print(f"container      : {args.container}")
    print(f"magic          : {c.blob[0:4]!r}")
    print(f"size           : {len(c.blob)} B")
    print(f"HeaderSize     : {c.header_size} (0x{c.header_size:X})")
    print(f"CardID range   : {c.min_card}..{c.max_card}")
    print(f"BitshiftSize   : {c.bitshift} -> stride {c.stride} B")
    print(f"blob base      : {c.blob_base} (0x{c.blob_base:X}), "
          f"{c.slot_count} slots")
    print()
    print(f"{'cardid':>6} {'slot':>10} {'offset':>10} {'fmt':>3} {'bpp':>3} "
          f"{'w':>4} {'h':>4}  note")
    exceptions = 0
    for card_id, slots in c.iter_cards():
        if not slots:
            continue
        for slot in slots:
            off = c.offset_of_slot(slot)
            payload = c.payload(slot)
            note = ""
            if payload[:len(GIM_MAGIC)] == GIM_MAGIC:
                try:
                    g = GimTexture(payload)
                    fmt, bpp, w, h = g.fmt, g.bpp, g.width, g.height
                except ValueError as exc:
                    fmt = bpp = w = h = -1
                    note = f"GIM parse error: {exc}"
                    exceptions += 1
            elif c.kind == "cpm":
                fmt, bpp, w, h = FMT_4BPP, 4, CARDM_WIDTH, CARDM_HEIGHT
                note = "bare texture (no GIM header)"
            else:
                fmt = bpp = w = h = -1
                note = "no GIM magic"
                exceptions += 1
            print(f"{card_id:>6} {slot:>10} {off:>10} {fmt:>3} {bpp:>3} "
                  f"{w:>4} {h:>4}  {note}")
    st = c.stats()
    print()
    print(f"summary: {st['with_art']} CardIDs with art "
          f"({st['total_arts']} arts, {st['alt_cards']} with alternates), "
          f"{st['zero'] - st['sentinel']} zero entries, "
          f"{st['sentinel']} sentinels, {exceptions} parse exceptions")
    return 1 if exceptions else 0


def cmd_gim(args) -> int:
    with open(args.gimfile, "rb") as fh:
        raw = fh.read()
    tex = GimTexture(raw)
    try:
        w, h, rgba = tex.to_pixels()
    except UnsupportedFormat as exc:
        print(f"{args.gimfile}: format {tex.fmt} {tex.width}x{tex.height} "
              f"@{tex.bpp}bpp", file=sys.stderr)
        print(f"cannot decode: {exc}", file=sys.stderr)
        return 3
    write_png(args.out, w, h, rgba)
    pal = "yes" if tex.palette is not None else "no"
    print(f"{args.gimfile}: format {tex.fmt}, {w}x{h}, bpp {tex.bpp}, "
          f"palette {pal}, {distinct_colours(rgba)} distinct colours")
    print(f"wrote {args.out}")
    return 0


def cmd_extract(args) -> int:
    c = Container(args.container)
    slots = c.arts(args.cardid)
    if not slots:
        print(f"CardID {args.cardid} has no art (slot 0)", file=sys.stderr)
        return 2
    slot = slots[0]
    payload = c.payload(slot)
    try:
        if payload[:len(GIM_MAGIC)] == GIM_MAGIC:
            tex = GimTexture(payload)
            w, h, rgba = tex.to_pixels()
            fmt, bpp = tex.fmt, tex.bpp
        else:
            raise UnsupportedFormat(
                "cardm slots are bare format-8 (bpp 4) textures with no GIM "
                "header; that format is not decoded")
    except UnsupportedFormat as exc:
        print(f"CardID {args.cardid}: slot {slot}, offset "
              f"{c.offset_of_slot(slot)}", file=sys.stderr)
        print(f"refusing to write {args.out}: {exc}", file=sys.stderr)
        return 3
    write_png(args.out, w, h, rgba)
    print(f"CardID {args.cardid}: slot {slot}, offset {c.offset_of_slot(slot)}, "
          f"{len(slots)} art(s), first art -> {w}x{h}, format {fmt} "
          f"({bpp}bpp), {distinct_colours(rgba)} distinct colours")
    print(f"wrote {args.out}")
    return 0


def fit_canvas(stride: int, png_w: int, png_h: int,
               fmt: int = FMT_INDEX8,
               palette_entries: int = 256) -> tuple[int, int]:
    """Largest swizzle-legal indexed canvas that fits a ``stride`` slot."""
    bpp = bpp_of(fmt)
    overhead = slot_overhead(fmt, palette_entries)
    max_pixels = (stride - overhead) * 8 // bpp
    if max_pixels < 16 * 8:
        raise ValueError(f"slot stride {stride} B is too small for format {fmt} "
                         f"with {palette_entries} palette entries (needs at "
                         f"least {overhead + 128} B)")
    best = (0, 0)
    for w in range(16, max_pixels + 1, 16):
        h = max(8, (png_h * w // png_w // 8) * 8)
        if w * h <= max_pixels and w * h > best[0] * best[1]:
            best = (w, h)
    if best == (0, 0):
        raise ValueError("no swizzle-legal canvas fits the slot")
    return best


def cmd_inject(args) -> int:
    c = Container(args.container)
    slots = c.arts(args.cardid)
    if not slots:
        print(f"CardID {args.cardid} has no art (slot 0)", file=sys.stderr)
        return 2
    if bool(args.width) != bool(args.height):
        print("--width and --height must be supplied together", file=sys.stderr)
        return 2
    fmt = args.format
    bpp = bpp_of(fmt)
    max_pal = 16 if fmt == FMT_INDEX4 else 256
    palette_entries = args.palette if args.palette else max_pal
    if not 1 <= palette_entries <= max_pal:
        print(f"format {fmt} allows 1..{max_pal} palette entries, got "
              f"{palette_entries}", file=sys.stderr)
        return 2
    slot = slots[0]
    png_w, png_h, rgba = read_png(args.png)
    if args.width:
        w, h = args.width, args.height
    else:
        w, h = fit_canvas(c.stride, png_w, png_h, fmt, palette_entries)
    if w % 16 or h % 8:
        print(f"canvas {w}x{h} is not swizzle-legal "
              f"(width must be %16, height %8)", file=sys.stderr)
        return 3
    cw, ch, cropped = cover_crop(rgba, png_w, png_h, w, h)
    if args.resample == "area":
        rgba = resize_area(cropped, cw, ch, w, h)
    else:
        rgba = resize_nearest(cropped, cw, ch, w, h)
    palette, indices, n_colours = quantise_palette(
        rgba, palette_entries, dither=args.dither, width=w, height=h)
    palette = palette[:palette_entries * 4]
    gim = build_gim_indexed(w, h, fmt, palette, indices, palette_entries)
    if len(gim) > c.stride:
        print(f"GIM {len(gim)} B does not fit the {c.stride} B slot",
              file=sys.stderr)
        return 3
    blob = bytearray(c.blob)
    off = c.offset_of_slot(slot)
    blob[off:off + c.stride] = gim + b"\x00" * (c.stride - len(gim))
    with open(args.out, "wb") as fh:
        fh.write(blob)
    print(f"injected CardID {args.cardid}: {len(slots)} art(s), first slot "
          f"{slot} @ {off}; format {fmt} {w}x{h}@{bpp}bpp, palette "
          f"{palette_entries} entries, PNG {png_w}x{png_h} "
          f"(cover-crop {cw}x{ch}), resample {args.resample}"
          f"{' + dither' if args.dither else ''}, {n_colours} "
          f"colours, GIM {len(gim)} B in {c.stride} B slot")
    print(f"wrote {args.out}")
    return 0


def cmd_verify(args) -> int:
    c = Container(args.container)
    is_gim = c.kind == "cip"
    ok = True

    # A1: every art offset must begin with the GIM magic (cardh only).
    print("A1 - every art offset begins with MIG.00.1PSP")
    bad = []
    count = 0
    for card_id, slots in c.iter_cards():
        for slot in slots:
            count += 1
            payload = c.payload(slot)
            if payload[:len(GIM_MAGIC)] != GIM_MAGIC:
                bad.append((card_id, slot, c.offset_of_slot(slot), payload[:12]))
    print(f"    resolved {count} arts; {len(bad)} exception(s)")
    for card_id, slot, off, head in bad[:20]:
        print(f"      CardID {card_id} slot {slot} @ {off}: {head!r}")
    if bad and is_gim:
        ok = False
    if not is_gim:
        print("    (cardm is bare: GIM magic is not expected, A1 is cardh-only)")

    # A2: every payload re-emits byte-identically from its 8-byte units.
    print("A2 - payload re-emits byte-identically (8-byte unit split)")
    fails = []
    checked = 0
    for card_id, slots in c.iter_cards():
        for slot in slots:
            checked += 1
            payload = c.payload(slot)
            body = payload[GIM_HEADER_SIZE:] if is_gim else payload
            if encode_dxt1_blocks(parse_dxt1_blocks(body)) != body:
                fails.append((card_id, slot, "body mismatch"))
    print(f"    round-tripped {checked} payloads; {len(fails)} failure(s)")
    for card_id, slot, why in fails[:20]:
        print(f"      CardID {card_id} slot {slot}: {why}")
    if fails:
        ok = False

    # A3: rebuild the whole container byte-identically.
    print("A3 - full container rebuild matches the original sha256")
    rebuilt = rebuild_container(c)
    orig_hash = hashlib.sha256(c.blob).hexdigest()
    new_hash = hashlib.sha256(rebuilt).hexdigest()
    print(f"    original : {len(c.blob)} B  sha256 {orig_hash}")
    print(f"    rebuilt  : {len(rebuilt)} B  sha256 {new_hash}")
    if orig_hash != new_hash:
        ok = False
        print("    MISMATCH")

    print()
    if ok:
        print("VERIFY OK: A1, A2 and A3 all hold.")
    else:
        print("VERIFY FAILED: do not claim success.")
    print("NOTE: A1/A2/A3 prove the container index and byte layout only.")
    print("They say nothing about the pixel format: formats 3 (RGBA8888) and")
    print("5 (INDEX8) are decoded and visually verified via 'gim'; format 8")
    print("(cardh/cardm, bpp 4) is NOT decoded.")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="tf1_art.py",
        description="Reader/writer for Yu-Gi-Oh! GX Tag Force 1 card art "
                    "(the inject command builds format-5 canary GIMs).")
    sub = p.add_subparsers(dest="cmd", required=True)

    pl = sub.add_parser("list", help="list every CardID's slot and GIM fields")
    pl.add_argument("--container", default=DEFAULT_CARDH)
    pl.set_defaults(func=cmd_list)

    pg = sub.add_parser("gim", help="decode one .gim file to a PNG")
    pg.add_argument("gimfile")
    pg.add_argument("--out", required=True, help="output .png path")
    pg.set_defaults(func=cmd_gim)

    pe = sub.add_parser("extract", help="decode one CardID to a PNG")
    pe.add_argument("cardid", type=int)
    pe.add_argument("--out", required=True, help="output .png path")
    pe.add_argument("--container", default=DEFAULT_CARDH)
    pe.set_defaults(func=cmd_extract)

    pi = sub.add_parser("inject", help="render a PNG into one card's art slot "
                                        "as a format-4/5 GIM")
    pi.add_argument("--container", default=DEFAULT_CARDH)
    pi.add_argument("--cardid", type=int, required=True)
    pi.add_argument("--png", required=True, help="source image")
    pi.add_argument("--out", required=True, help="output container path")
    pi.add_argument("--format", type=int, choices=(FMT_INDEX4, FMT_INDEX8),
                    default=FMT_INDEX8,
                    help="GIM pixel format: 4 = INDEX4, 5 = INDEX8 (default 5)")
    pi.add_argument("--palette", type=int,
                    help="palette block entry count (default: the format max)")
    pi.add_argument("--width", type=int,
                    help="canvas width (multiple of 16); defaults to the "
                         "largest canvas that fits the slot")
    pi.add_argument("--height", type=int,
                    help="canvas height (multiple of 8)")
    pi.add_argument("--resample", choices=("nearest", "area"),
                    default="nearest",
                    help="scaling filter: nearest (default) or area")
    pi.add_argument("--dither", action="store_true",
                    help="Floyd-Steinberg error diffusion onto the palette")
    pi.set_defaults(func=cmd_inject)

    pv = sub.add_parser("verify", help="A1/A2/A3 proofs; refuses false success")
    pv.add_argument("--container", default=DEFAULT_CARDH)
    pv.set_defaults(func=cmd_verify)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
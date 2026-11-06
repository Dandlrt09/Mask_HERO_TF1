#!/usr/bin/env python3
"""E7/T14 battery: independent read-only verification of round F3.

MANUAL battery, deliberately NOT a framework test -- like every other tool here
it reads the gitignored binaries in `trabajo/` (the 800 MB ISOs and the `.prx`),
so it cannot run in a clean clone.  It was written by the T14 verifier, who
re-derived every number from the bytes without importing `tools/e7_fusion.py`
(author-independent), and it is kept so the verdict can be replayed.  The copy
pasted in the verifier's report needed two transcription fixes (the PH0
comparison and the `CARD_Prop` unpack); this file is the version that was re-run
here to PASS.

Run from the repo root:  python3 tools/e7_f3_probe.py

Covers S2 (record map), S3 (module geometry), S4 (native recipes + ISO) and S6
(artifact pins) of `odd/tasks/e7-recetas-fusion.md`, plus the F3 attribute
invariant.  Exits non-zero on any failure.
"""
import hashlib
import struct
from itertools import combinations

PRISTINE = 'trabajo/e1c/gm/libduel_eng.prx'
PATCHED = 'trabajo/e7/libduel_eng_f3.prx'
F3_ISO = 'trabajo/e7/TF1-E7-F3.iso'
G6_ISO = 'trabajo/e8/TF1-E8-G6.iso'
PIN = {'pristine': '6867fb17d48479a429cb71b660daa7ebb8e4be90e0a63c2f4c619ceaa54bcf91',
       'patched': '9b6c1fceb6b13cc7ba99c308a47a636c5967a2651510127508dd22d682dfac15',
       'f3iso': '85ca0409ea1b1fb4a4ba44b60427bac18d9b29119846a1e7d54e0f3473f77974'}
E_HERO = [(4661, 6393), (4665, 6527), (4671, 6310), (4672, 6527), (4673, 6312),
          (4673, 6477), (4673, 6478), (4681, 6310), (4684, 6311), (4686, 6313),
          (4689, 6393), (4690, 6311)]
FUSION = [(4661, 6535), (4671, 6344), (4671, 6487), (4673, 6486), (4673, 6529),
          (4673, 6488), (4681, 6344), (4681, 6487), (4686, 6345), (4689, 6535)]
MASK = [4661, 4665, 4671, 4672, 4673, 4681, 4684, 4686, 4689, 4690]
SEC = 2048


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


P = open(PRISTINE, 'rb').read()
F = open(PATCHED, 'rb').read()
assert (len(P), sha(PRISTINE)) == (1470794, PIN['pristine'])
assert (len(F), sha(PATCHED)) == (1472160, PIN['patched'])
assert sha(F3_ISO) == PIN['f3iso']

# --- S3: ELF geometry ------------------------------------------------------
assert (P[:4] == F[:4] == b'\x7fELF') and P[5] == 1            # 32-bit LE
assert struct.unpack_from('<I', P, 0x1c)[0] == 0x34             # pristine e_phoff
assert struct.unpack_from('<I', F, 0x1c)[0] == 0x167150         # relocated e_phoff
assert struct.unpack_from('<H', P, 0x2c)[0] == 1
assert struct.unpack_from('<H', F, 0x2c)[0] == 2
assert struct.unpack_from('<I', P, 0x20)[0] == struct.unpack_from('<I', F, 0x20)[0] == 0x10c230
assert struct.unpack_from('<H', P, 0x30)[0] == struct.unpack_from('<H', F, 0x30)[0] == 25
assert P[0x10c230:0x10c230 + 25 * 40] == F[0x10c230:0x10c230 + 25 * 40]   # section table
ph0p = struct.unpack_from('<8I', P, 0x34)
ph0f = struct.unpack_from('<8I', F, 0x167150)
ph1f = struct.unpack_from('<8I', F, 0x167150 + 32)
assert struct.pack('<8I', *ph0f) == struct.pack('<8I', *ph0p)  # PH0 byte-identical
assert tuple(ph1f) == (1, 0x167190, 0x112910, 0x112910, 1296, 1296, 7, 16)


def ov(a, b):
    return not (a[1] <= b[0] or b[1] <= a[0])


assert not ov((ph0f[1], ph0f[1] + ph0f[4]), (ph1f[1], ph1f[1] + ph1f[4]))   # file ranges
assert not ov((ph0f[2], ph0f[2] + ph0f[5]), (ph1f[2], ph1f[2] + ph1f[5]))   # VMA ranges
diffs = [i for i in range(len(P)) if P[i] != F[i]]
assert diffs == [0x1c, 0x1d, 0x1e, 0x2c, 0xa04c0, 0xa04c1, 0xa04dc,
                 0xaadc4, 0xaadc5, 0xaafb0, 0xaafb1, 0xab434, 0xab435,
                 0xab4e4, 0xab4e5], diffs


def imm(off, b):
    return struct.unpack_from('<H', b, off)[0]


assert imm(0xa04c0, F) == 0x2910 and imm(0xa04c0, P) == 0xACB4  # base -> 0x112910
assert imm(0xa04dc, F) == 0xA1 and imm(0xa04dc, P) == 0x5E      # sltiu 161
for off in (0xaadc4, 0xaafb0, 0xab434, 0xab4e4):
    assert imm(off, P) == 0xAFA4 and imm(off, F) == 0x2E18      # 4 table-end ptrs

# --- S2: record map --------------------------------------------------------
nat = [struct.unpack_from('<4H', P, 0x10ad14 + 8 * i) for i in range(94)]
assert struct.unpack_from('<4H', P, 0x10ad14 + 752) == (10, 0, 0, 0)
new = [struct.unpack_from('<4H', F, 0x167190 + 8 * i) for i in range(161)]
assert struct.unpack_from('<4H', F, 0x167190 + 1288) == (10, 0, 0, 0)
assert new[:94] == nat
assert new[94:116] == [(r, m, 4704, 0) for r, m in E_HERO + FUSION]
pairs = [(4696, a, b, 0) for a, b in combinations(MASK, 2)]
assert new[116:161] == pairs and set(new[116:161]) == set(pairs)
assert len(set(map(tuple, new))) == 161
natres = {r[0] for r in nat}
assert not ({r[0] for r in new[94:]} & natres)

# --- S4: finder simulation + ISO -------------------------------------------
def first(recs, bound, t):
    for i in range(min(bound, len(recs))):
        if recs[i][0] == t:
            return i


for r in nat:
    assert first(nat, 94, r[0]) == first(new, 94, r[0]) == first(new, 161, r[0])
assert new[first(new, 161, 4696)] == (4696, 4661, 4665, 0)
assert new[first(new, 161, 4673)] == (4673, 6312, 4704, 0)


def walk(f, path):
    """(LBA, size) of a file in an ISO9660 image, walking from the root."""
    f.seek(16 * SEC)
    s = f.read(SEC)
    assert s[0] == 1 and s[1:6] == b'CD001'
    cur = (struct.unpack_from('<I', s, 158)[0], struct.unpack_from('<I', s, 166)[0])
    for part in path.upper().split('/'):
        f.seek(cur[0] * SEC)
        data = f.read(cur[1])
        hit = None
        pos = 0
        while pos < len(data):
            ln = data[pos]
            if ln == 0:
                pos = ((pos // SEC) + 1) * SEC
                continue
            nlen = data[pos + 32]
            raw = data[pos + 33:pos + 33 + nlen]
            if nlen == 1 and raw in (b'\x00', b'\x01'):
                nm = '.' if raw == b'\x00' else '..'
            else:
                nm = raw.decode('ascii', 'replace').split(';')[0]
            if nm.upper() == part:
                hit = (struct.unpack_from('<I', data, pos + 2)[0],
                       struct.unpack_from('<I', data, pos + 10)[0], data[pos + 25])
                break
            pos += ln
        assert hit, part
        cur = (hit[0], hit[1])
        if not (hit[2] & 2):
            return cur
    return cur


f3 = open(F3_ISO, 'rb')
g6 = open(G6_ISO, 'rb')
fl, fs = walk(f3, 'PSP_GAME/USRDIR/gmodule/libduel_eng.prx')
gl, gs = walk(g6, 'PSP_GAME/USRDIR/gmodule/libduel_eng.prx')
assert (fl, fs) == (12048, 1472160) and (gl, gs) == (12048, 1470794)
f3.seek(fl * SEC)
assert f3.read(fs) == F                       # the ISO module == the patched .prx
g6.seek(gl * SEC)
assert g6.read(gs) == P                       # the G6 module == the pristine .prx
ml, ms = walk(f3, 'PSP_GAME/USRDIR/gmodule/libduel_mgr.prx')
mlg, msg = walk(g6, 'PSP_GAME/USRDIR/gmodule/libduel_mgr.prx')
assert (ml, ms) == (mlg, msg) == (12767, 129106)
f3.seek(ml * SEC)
g6.seek(mlg * SEC)
assert f3.read(ms) == g6.read(msg)
n = 798787584 // SEC
diffs = []
i = 0
while i < n:
    k = min(512, n - i)
    f3.seek(i * SEC)
    g6.seek(i * SEC)
    a, b = f3.read(k * SEC), g6.read(k * SEC)
    if a != b:
        diffs += [i + j for j in range(k) if a[j * SEC:(j + 1) * SEC] != b[j * SEC:(j + 1) * SEC]]
    i += k
assert diffs == [38, 12048, 12368, 12389, 12390, 12766], diffs
assert (12767 - 12048) * SEC == 1472512 >= 1472160       # the module allocation

# --- attribute invariant (F3) ----------------------------------------------
tsv = {}
for line in open('datos/cartas_18.tsv', encoding='utf-8'):
    if line.startswith('#') or not line.strip():
        continue
    p = line.rstrip('\n').split('\t')
    try:
        cid = int(p[1])
    except ValueError:
        continue
    tsv[cid] = (int(p[3]), p[13])
prop = open('trabajo/e2/eng/CARD_Prop.bin', 'rb').read()
intid = open('trabajo/e2/eng/CARD_IntID.bin', 'rb').read()
indx = open('trabajo/e2/eng/CARD_Indx_E.bin', 'rb').read()
nm = open('trabajo/e2/eng/CARD_Name_E.bin', 'rb').read()


def cattr(cid):
    idx = struct.unpack_from('<H', intid, (cid - 4000) * 2)[0]
    assert idx
    p2 = struct.unpack_from('<ii', prop, idx * 8)[1]
    no = struct.unpack_from('<i', indx, idx * 8)[0]
    e = nm.index(b'\x00\x00', no)
    e += e % 2
    return (p2 >> 4) & 0xF, nm[no:e].decode('utf-16-le', 'replace')


for r, m in FUSION:
    ra, _ = tsv[r]
    ba, _ = cattr(m)
    assert ra == ba, (r, m, ra, ba)
dian = [rec[1] for rec in new if rec[0] == 4673 and rec[2] == 4704 and rec[3] == 0]
assert dian == [6312, 6477, 6478, 6486, 6529, 6488]
print('T14 F3 battery: PASS (S2, S3, S4, S6, attribute invariant)')

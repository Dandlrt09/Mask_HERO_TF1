# Masked HERO in Tag Force 1

Porting the 18 **Masked HERO** cards to *Yu-Gi-Oh! GX Tag Force 1* (PSP, `ULES00600`).

This repository holds the investigation tooling and the spike handoffs. It contains
**no game data**: the ISO and every extracted asset are ignored (see `.gitignore`)
and can be regenerated with the tools in `tools/`.

## Status

| Spike | Scope | Result |
| --- | --- | --- |
| E0 | CardInfo layout, bit-packing of `CARD_Prop`, free card IDs | Done — 6 internal files, 472 free IDs in `4007..6957` |
| E2 | Decode the EHP v3 container and `CARD_Genre` | Done — 36 real genre bits, mapped and verified against Yugipedia |
| E3 | Does the engine read `CARD_Genre` for the "Cannot perform Normal Summon" rule? | **Negative** — it does not; genre is UI-filter / AI metadata, rules live in ARM code |
| E1-test | Append one new card on a free ID and reuse existing artwork | Done — the engine reads the appended record; the "Forbidden" verdict is positional, not content (`ESTADO-E1-test.md`) |
| E5 | Lift the engine's card-index limit so no real card is lost | Done — strategy C patches the level reader; `BOOT.BIN` is an unencrypted ELF (`ESTADO-E5-limite.md`) |
| E6 | Port the 18 **Masked HERO** cards (data + save) | **Done and validated in game** — 18-card content table, ownership in the save, the 2480-index limit lifted (`ESTADO-E6.md`) |
| E7 | Make the 11 Masked HERO Fusion-summonable from a native recipe table | **Offline verified; in-game round pending** — 161 recipes in a second `PT_LOAD` (round F3); "Mask Change" as a Fusion material already confirmed in game (`ESTADO-E7.md`) |
| E8 | Build and inject the 18 real card arts | Delivered for field/duel, deck editor and name bar; the big-card (`cardh`) geometry is open (`ESTADO-E8.md`) |
| E9 | ARC-V Tag Force Special as a reference for "Mask Change" | Done — TFSP resolves by card id, so no reusable data handler (`ESTADO-E9.md`) |

Two findings worth keeping in mind:

- The engine **does** read `CARD_Prop` from `cardinfo_<lng>.ehp` inside the ISO, so
  card data can be changed without touching `EBOOT.BIN`.
- `EBOOT.BIN` is encrypted (`~PSP`, a signed PRX), so it must be decrypted to an ELF
  before Ghidra. Runtime AR/PPSSPP codes work regardless, and the scene already
  redirects loads to `ms0:/PSP/MODS/TAGFORCE/`.

Read the handoffs in order: `ESTADO-E0.md` -> `ESTADO-E2.md` -> `ESTADO-E3.md` ->
`ESTADO-E1-test.md` -> `ESTADO-E5-limite.md` -> `ESTADO-E6.md` -> `ESTADO-E7.md` ->
`ESTADO-E8.md` -> `ESTADO-E9.md`.

## Layout

```
ESTADO-E0.md         spike E0 handoff: CardInfo layout, scope, risks, plan
ESTADO-E2.md         spike E2 handoff: EHP v3 container and the CARD_Genre map
ESTADO-E3.md         spike E3 handoff: runtime result for the genre rule
ESTADO-E1-test.md    E1-test handoff: append one card and observe it in game
ESTADO-E5-limite.md  E5 handoff: the card-index limit and strategy C
ESTADO-E6.md         E6 handoff: the 18-card port, the save and the test protocol
ESTADO-E7.md         E7 handoff: the fusion recipe table and the second PT_LOAD
ESTADO-E8.md         E8 handoff: the CIP/GIM art pipeline and the cardh geometry
ESTADO-E9.md         E9 reference: how "Mask Change" works in ARC-V TFSP
datos/               content tables (card list, HERO recipe, effect texts)
odd/tasks/           ODD feature documents (specs, tasks, log)
tools/               investigation and patching tooling (python3, stdlib only)
trabajo/             scratch space: extracted game data and test ISOs (ignored)
referencia/          third-party reference sources (git submodules)
```

## Tools

All of them are `python3` with the standard library only.

```bash
# ISO9660 reader: list a directory or extract one file
python3 tools/iso9660.py "<iso>" ls PSP_GAME/USRDIR/duelsys
python3 tools/iso9660.py "<iso>" extract PSP_GAME/USRDIR/duelsys/cardinfo_eng.ehp \
        trabajo/e2/cardinfo_eng.ehp

# EHP v3 container: list the 12 internal files or extract them
python3 tools/ehp.py trabajo/e2/cardinfo_eng.ehp ls
python3 tools/ehp.py trabajo/e2/cardinfo_eng.ehp extract trabajo/e2/eng

# CardInfo library: dump cards by name from an extracted `eng` folder
python3 tools/tfcard.py trabajo/e2/eng _E "Celtic Guardian" "Zoa"

# E3 probe: signature, genre base address and target byte for a card
python3 tools/e3_probe.py trabajo/e2/eng "Celtic Guardian"

# E3 patch: copy the ISO and patch Prop/Genre bytes in all 6 languages
python3 tools/e3_patch_iso.py "<iso>" trabajo/TF1-E3-test.iso

# CardInfo append: rebuild an EHP container with one extra card record
python3 tools/cardinfo_add.py <in.ehp> <out.ehp> --card-id 4661 --name "E1 TEST CARD" \
        --donor 4047 --atk 4900 --level 4 --canary 4047:4850
python3 tools/cardinfo_add.py <in.ehp> --print-card 4661

# ISO replace: swap one file inside an image and update its directory record
python3 tools/iso_replace.py "<iso>" <out.iso> PSP_GAME/USRDIR/duelsys/cardinfo_eng.ehp <new.ehp>

# E1-test: the whole pipeline (ISO copy + new card + artwork alias + readback check)
python3 tools/e1_patch_iso.py

# E6: build the 18-card database, grant it in a save, and swap one file in the ISO
python3 tools/e6_build_18.py
python3 tools/e6_patch_save.py grant --save <DATA0> --out <DATA0.18>

# E7: patch the fusion recipe table and build the product ISO (`verify` re-checks it)
python3 tools/e7_fusion.py patch --out trabajo/e7/libduel_eng_f3.prx
python3 tools/e7_fusion.py verify --pristine <pristine.prx> --patched <patched.prx>
python3 tools/e7_fusion.py iso --out trabajo/e7/TF1-E7-F3.iso

# E7/T14: replay the independent verification battery of the F3 artifacts (manual: reads trabajo/)
python3 tools/e7_f3_probe.py

# E8: build and inject the 18 real card arts
python3 tools/tf1_art18.py
```

## Reference sources

`referencia/` holds read-only upstream clones, pinned as submodules:

- [xan1242/TFCardEdit](https://github.com/xan1242/TFCardEdit) — CardInfo format (C++)
- [xan1242/TFCardEditGUI](https://github.com/xan1242/TFCardEditGUI) — fields and enums (C#)
- [xan1242/EHPScanner](https://github.com/xan1242/EHPScanner) — EHP scanning/extraction
- [xan1242/CIPTool](https://github.com/xan1242/CIPTool) — card art containers (CIP/CPM, DXT1/GIM)
- [DeaTh-G/tagforce-essentials](https://github.com/DeaTh-G/tagforce-essentials) — xdelta patches and AR codes

```bash
git submodule update --init --recursive
```

## Next steps

1. **E7 in-game round** — run `trabajo/e7/TF1-E7-F3.iso` in PPSSPP with two signals:
   Dian with any owned EARTH base (Clayman, Bladedge, Wildheart, Rampart Blaster,
   Mudballman, Wildedge) + "Cambio de Mascara", and a native Fusion (`Flame Wingman`)
   that must still resolve. Closes T5/T12 (`odd/tasks/e7-recetas-fusion.md`).
2. **E8 geometry** — the exact big-card (`cardh`) fold and the Spanish name in the bar
   (`ESTADO-E8.md` §9.16).
3. **Effects front** — write the real "Mask Change" effect as ARM code, using the second
   `PT_LOAD` as the new code space and `ESTADO-E9.md` as the reference.
4. **AI probe** — does a genre bit such as `SpecialSummon` change how the AI evaluates
   and plays a card?

Delivery for this repository is sliced as chained PRs; see
`odd/tasks/delivery-cadena-prs.md`.

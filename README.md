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
| E1-test | Append one new card on a free ID and reuse existing artwork | Test ISO built and verified; **in-game result pending** (`ESTADO-E1-test.md`) |

Two findings worth keeping in mind:

- The engine **does** read `CARD_Prop` from `cardinfo_<lng>.ehp` inside the ISO, so
  card data can be changed without touching `EBOOT.BIN`.
- `EBOOT.BIN` is encrypted (`~PSP`, a signed PRX), so it must be decrypted to an ELF
  before Ghidra. Runtime AR/PPSSPP codes work regardless, and the scene already
  redirects loads to `ms0:/PSP/MODS/TAGFORCE/`.

Read the handoffs in order: `ESTADO-E0.md` -> `ESTADO-E2.md` -> `ESTADO-E3.md`.

## Layout

```
ESTADO-E0.md   spike E0 handoff: CardInfo layout, scope, risks, plan
ESTADO-E2.md   spike E2 handoff: EHP v3 container and the CARD_Genre map
ESTADO-E3.md   spike E3 handoff: runtime result for the genre rule
tools/         read-only investigation tooling (python3, stdlib only)
trabajo/       scratch space: extracted game data and test ISOs (ignored)
referencia/    third-party reference sources (git submodules)
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

1. **E1-test** — add one new card under a free ID (`Prop` + `Genre` + `IntID` + text +
   reused art) and check that it shows up in the album / shop / deck editor. Validates
   the whole data pipeline without a single line of ARM. **Built and verified offline;
   the in-game check is pending** — see `ESTADO-E1-test.md` for the test protocol.
2. **E4** — Mask Change as an AR/PPSSPP code.
3. **AI probe** — does a genre bit such as `SpecialSummon` change how the AI evaluates
   and plays a card?
4. **ARM front** — decrypt the `~PSP` EBOOT to an ELF, then map the Fusion / Extra Deck
   summon paths.

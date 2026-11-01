# ESTADO — E2: contenedor EHP y `CARD_Genre.bin` (TF1, ULES00600)

Fecha: continuación del spike E0. Lee esto junto a `ESTADO-E0.md`.
Estado: **E2 completado.** La pregunta central reabierta en E0 (¿datos o código?)
quedó **resuelta a medias, y en un sentido mejor del que esperaba**: existe una
capa de datos de comportamiento real (`CARD_Genre`), pero es clasificación de
etiquetas, no un motor de efectos.
No se modificó nada del juego. Todo lo de esta sesión es lectura + extracción a `trabajo/`.

---

## 1. Contenedor EHP v3 — formato resuelto

`PSP_GAME/USRDIR/duelsys/cardinfo_eng.ehp` (1.019.616 bytes) se extrajo del ISO con
las herramientas nuevas (`tools/iso9660.py`, `tools/ehp.py`).

Encabezado real, deducido del dump:

| Offset | Tamaño | Campo |
|---|---|---|
| 0x00 | 4 | `"EHP"` + versión `0x03` |
| 0x04 | 4 | tamaño total del contenedor (u32) |
| 0x08 | 4 | marcador `"NOT "` |
| 0x0C | 4 | cantidad de entradas (u32) — 12 acá |
| 0x10 | 8 × N | tabla de entradas: `(name_offset u32, data_offset u32)` |

- `name_offset` es relativo al inicio del contenedor; nombre ASCII terminado en NUL.
- Los datos son contiguos: **el tamaño de cada archivo = `data_offset` del siguiente − el propio**
  (el último usa `total`). No hay campo de tamaño por entrada.
- Verificado: suma de regiones == 1.019.616, las 12 entradas cubren el archivo entero.

No hizo falta compilar `EHPScanner` (C++): el formato se leyó del binario en Python.

## 2. Los 12 archivos internos (extraídos a `trabajo/e2/eng/`)

| Archivo | Tamaño | Registro | Notas |
|---|---|---|---|
| `CARD_Desc_E.bin` | 801.952 | buffer UTF-16LE | descripciones |
| **`CARD_Genre.bin`** | **14.880** | **6 bytes/carta** | **el archivo que `TFCardEdit` no conoce** |
| `CARD_Indx_E.bin` | 19.856 | int32 × 2 | offset de nombre + offset de descripción |
| `CARD_IntID.bin` | 5.920 | uint16 | 2.960 entradas |
| `CARD_Name_E.bin` | 85.792 | buffer UTF-16LE | nombres |
| `CARD_Pass.bin` | 9.920 | uint32 | passwords |
| `CARD_Prop.bin` | 19.840 | 8 bytes/carta | **2.480 registros** |
| `CARD_SamePict_E.bin` | 160 | — | artes alternativos |
| `CARD_Sort_E.bin` | 4.960 | — | orden de clasificación |
| `CARD_Top_E.bin` | 112 | — | índice "top" |
| `DLG_Indx_E.bin` | 2.960 | — | índice de diálogos |
| `DLG_Text_E.bin` | 52.896 | — | textos de diálogo |

Cifras maestras: **2.480 registros** en `CARD_Prop` (índice 0 = carta nula, 2.479 reales),
**6 bytes/carta exactos** en `CARD_Genre` (14.880 / 2.480 = 6,0).

### 2.1 Índice interno (`CARD_IntID`) — corregido

`CARD_IntID` **no** se indexa por `CardID − 4007` sino por **`CardID − 4000`**:
`CARD_IntID[(CardID − 4000) × 2]` devuelve el **índice interno** (0..2479) que indexa
Prop/Genre/Pass/Indx. Las entradas 4001–4006 son inválidas (apuntan a 0).
Esto cierra un detalle de E0 y es la pieza que faltaba para escribir el pipeline de datos.

### 2.2 IDs libres medidos

Rango presente: **4007..6957** = 2.951 slots. Usados: **2.479**. **Libres: 472.**
(La estimación de E0 era 479; la diferencia es el recuento exacto.)
Ejemplos de IDs libres bajos: 4661, 4665, 4671, 4672, 4673, 4681, 4684, 4686…
Los 18 registros entran de sobra.

## 3. `CARD_Genre.bin` — el hallazgo de E2

`CARD_Genre` son **6 bytes por carta, 5 usados** (byte 5 siempre 0), y coinciden
**exactamente** con la taxonomía de "genres" que Yugipedia documenta para TF1
(la lista de filtros del juego). **Mapa de bits completo, verificado contra las
listas oficiales de cartas de cada genre:**

| Byte | Bit | Genre |
|---|---|---|
| 0 | 1 | Remove card from play |
| 0 | 2 | Destroy Spell/Trap |
| 0 | 3 | Destroy monster |
| 0 | 4 | Deck destruction |
| 0 | 5 | Hand destruction |
| 0 | 6 | LV Monsters |
| 0 | 7 | Toon |
| 1 | 0 | Spirit |
| 1 | 1 | Union |
| 1 | 2 | Fusion Material |
| 1 | 3 | Token |
| 1 | 4 | Flip Effect |
| 1 | 5 | Change card position |
| 1 | 6 | Get control |
| 1 | 7 | Cancel out Effect |
| 2 | 0 | Attribute |
| 2 | 1 | Type |
| 2 | 2 | Return card |
| 2 | 3 | Increase draw |
| 2 | 4 | Search Deck |
| 2 | 5 | Recover cards from Graveyard |
| 2 | 6 | Increase/Decrease ATK/DEF |
| 2 | 7 | Pierce |
| 3 | 0 | Cannot be destroyed |
| 3 | 1 | Restrict Attack |
| 3 | 2 | Direct Attack |
| 3 | 3 | Multiple Attack |
| 3 | 4 | Reduce Life Points |
| 3 | 5 | Recover Life Points |
| 3 | 6 | Spell Counter |
| 3 | 7 | Gamble |
| 4 | 0 | **Special Summon** |
| 4 | 1 | **Cannot perform Normal Summon** |
| 4 | 2 | Game Original |
| 4 | 3 | Card with a different artwork |

Pruebas de validación (carta → genre): Toon World `byte0 bit7`; Horus LV8
`byte0 bit6`; Yata-Garasu `byte1 bit0` (Spirit); X-Head Cannon `byte1 bit1` (Union);
Blue-Eyes White Dragon / Elemental Hero Avian `byte1 bit2` (Fusion Material);
Jinzo / Solemn Judgment `byte1 bit7`; Sangan / Witch of the Black Forest
`byte2 bit4` (Search Deck); Rocket Warrior / Marshmallon / Relinquished
`byte3 bit0` (Cannot be destroyed); Cyber-Stein / Monster Reborn / Polymerization
`byte4 bit0` (Special Summon); Dark Sage / Flame Swordsman / Horus LV8
`byte4 bit1` (Cannot perform Normal Summon).

### 3.1 Qué significa esto para el proyecto

- **Es una capa de datos semántica real, no categoría de UI/álbum.** La hipótesis
  de E0 ("quizá sólo categorías de filtro") queda descartada: los valores codifican
  capacidades efectivas (desterrar, buscar, negar, no destruible, invocación especial…).
- **Pero no es el motor de efectos.** Es un conjunto de etiquetas **gruesas**: dice
  "esta carta reduce LP", no *cuánto* ni *cuándo*. Los efectos siguen siendo código ARM.
  La conclusión de E0 ("código por carta") se mantiene para la implementación.
- **La pieza data-driven que sí existe y ahora es concreta:** *"Cannot perform Normal
  Summon"*. Para los monstruos de Fusión / nomi, `CARD_Prop` no tiene ningún campo que
  diga "no se puede invocar normal"; el único lugar donde vive esa regla es este bit de
  genre. Es una **hipótesis fuerte** (no confirmada en runtime) de que **el motor lee
  el genre para aplicar esa regla**. Si se confirma, las 11 fusiones del proyecto
  obtenienen su regla "no invocable normalmente" sin escribir ARM.
- **Consecuencia operativa nueva y obligatoria:** `CARD_Genre` es una **tercera matriz
  paralela** que hay que **extender** al agregar cartas. Una carta nueva con genre = 0
  no aparece en los filtros del juego y probablemente la IA no la evalúe. Por eso el
  pipeline de datos de E1-test debe escribir Prop **y** Genre **e** IntID.
- **Riesgo IA, actualizado (mejor):** existe un sistema de clasificación que
  **probablemente alimenta la evaluación de cartas de la IA** (los "genres" son justo
  lo que el juego expone para filtrar/evaluar). Asignar los bits correctos a las cartas
  nuevas puede darles presencia en la IA sin tocar código. Sigue sin ser un modelo de
  IA completo, pero es la primera vía concreta para ese problema.

### 3.2 Caveat de E0 sobre los 9 bits libres de `CARD_Prop` — actualizado

Medido: **los 2.480 registros tienen los bits 23–31 de Prop2 en 0.** Ninguna carta usa
esos bits, así que no codifican comportamiento observable. El experimento "poner un bit
en 1" sigue siendo barato pero bajó de prioridad: la atención ahora está en el genre.

## 4. Herramientas nuevas (en `tools/`, sólo lectura + extracción)

- `tools/iso9660.py` — lector ISO9660 mínimo: `ls`, `cat`, `extract`.
- `tools/ehp.py` — lector/desempaquetador EHP v3: `ls`, `extract`.
- `tools/tfcard.py` — librería `CardInfo`: carga un set extraído, expone `get(CardID)`,
  `by_name`, `all_cards`, `free_card_ids`, y el mapa `GENRE_BITS` -> `card.genres`.

Nada depende de compiladores ni de .NET; corre con `python3` a secas.

## 5. Plan actualizado

E0 ponía E2 (leer `CARD_Genre`) antes que nada. Hecho. Orden nuevo:

1. ~~E2 — extraer `cardinfo_eng.ehp` y leer `CARD_Genre`~~ **HECHO**.
2. **E1-test — validar el pipeline de datos con UNA carta sin efecto nuevo.**
   Ahora incluye **Prop + Genre + IntID + Name/Desc + arte**, con genre correcto.
   Objetivo: ver la carta en álbum / tienda / editor de deck sin escribir ARM.
   Decisión de diseño pendiente que hay que resolver acá: **¿el motor indexa Prop por
   `CARD_IntID` (se pueden *appendear* registros al final) o asume orden por CardID
   (habría que insertar en su lugar y correr todos los índices)?** Se prueba empíricamente.
3. **E3 — verificar en runtime si el genre gobierna reglas.** Con PPSSPP/código AR:
   tomar una carta invocable normalmente, ponerle `byte4 bit1`, y ver si el juego
   bloquea la invocación normal. Esto convierte la hipótesis 3.1 en hecho (o la mata).
4. **E4 — Cambio de Máscara como código AR** (enviar un HÉROE al GY y traer del Extra).
5. **E5 — efecto real auto-contenido (Ácido)**; luego el resto; y Dark Law / Vapor /
   Divine Wind / Atómico / Contraste Chaos al final.

## 6. Artefactos de esta sesión

Todo bajo `C:\Users\Danieldlrt09\Proyectos\MASK HERO in TF1\`:

- `trabajo/e2/cardinfo_eng.ehp` — el contenedor extraído del ISO.
- `trabajo/e2/eng/` — los 12 archivos internos.
- `trabajo/e2_genre_bits.txt` — volcado de los 48 bits con sus cartas de ejemplo.
- `tools/iso9660.py`, `tools/ehp.py`, `tools/tfcard.py`.
- `ESTADO-E2.md` — este informe.

# ESTADO — Spike E6: portar las 18 cartas HÉROE Enmascarado

Fecha: sesión del cierre de E5 + arranque de E6.
Estado: **decisiones tomadas y tabla de contenido escrita. El build se frena en un bloqueo de layout del ISO (ver §4), que necesita una decisión del usuario.**
Nada del ISO original fue modificado; todo el trabajo vive en copias (`trabajo/`).

Continúa a `ESTADO-E5-limite.md` (estrategia C, cerrada y verificada) y a `ESTADO-E0.md` §1 (alcance).

---

## 1. Decisiones del usuario (verbatim de la sesión)

1. **Textos**: copiar la fuente de verdad al repo → hecho: `datos/efectos_heroes_enmascarados.txt` (sha256 `dacd5aac…` idéntico al original en `OneDrive/Escritorio`).
2. **Arte prestado (S4)**: el agente elige el donante por carta y lo lista. → elegido en `datos/cartas_18.tsv` (ver §3). Ajustable: cambiar un donante es una edición de 8 bytes en las tablas CIP.
3. **Obtención (T10)**: «Editar el save/álbum» → ver T14. Implica reversar el formato del save del jugador (fuera del repo, hay que pedirle una copia).
4. **Alcance**: «Las 18 de una».

## 2. Hechos medidos (esta sesión)

- **Motor**: el veredicto «Forbidden» del editor es el nivel leído por el wrapper exportado en `BOOT.BIN` VMA 0x478fc. C2 (probado por el usuario en PPSSPP: editor + duelo + cartas propias intactas) lo reescribe a: `rec == NULL || palabra_de_4B(rec) == 0 → 3`, si no `byte2`. Lista de prohibidas intacta. Artefacto: `tools/e5_c2_patch.py`; ISO probado: `trabajo/e5/TF1-E5-C2.iso`.
- **Códigos del formato** (derivados de las propias cartas del juego, no adivinados):
  `kind` 0=Normal, 1=Efecto, 3=Fusión, 13=Mágica, 14=Trampa · `attr` 1=LUZ, 2=OSCURIDAD, 3=AGUA, 4=FUEGO, 5=TIERRA, 6=VIENTO, 8=Mágica, 9=Trampa · `ctype` 15=Guerrero, 22=Mágica · `icon` 0=Normal, 3=Equipado, 5=Juego Rápido · `genre` byte4 bit0 = Invocación Especial.
- **CardIDs libres**: 472 en 4007..6957; se usan 18 (4661, 4665, 4671, 4672, 4673, 4681, 4684, 4686, 4689, 4690, 4696, 4697, 4699, 4701, 4704, 4721, 4726, 4730). Índices internos nuevos: 2480..2497 (el relleno de nivel del motor llega hasta 2959 sin pisar el siguiente campo del ctx en 0x265C3C).
- **Donantes de arte**: 48 cartas HÉROE ya existen en TF1 (E-HERO / D-HERO). Se eligió uno por carta en `datos/cartas_18.tsv` (columna `arte_donante`), temáticamente por atributo.
- **Contenedor**: `PSP_GAME/USRDIR/duelsys/cardinfo_spa.ehp` (prístino: 1125216 B, 2480 registros, 12 archivos internos, LBA 331709). `CARD_IntID` tiene 2960 entradas.

## 3. Contenido a portar

`datos/cartas_18.tsv` (18 filas, cabecera comentada). Columnas:
`n · cardid · kind · attr · level · atk · def · ctype · icon · rarity · genre_hex · password · arte_donante · nombre · descripcion`
- 11 fusiones (10 vía Cambio de Máscara + HÉROE del Contraste Chaos, nivel 9, 3000/2600), 3 de Deck Principal (Cuervo del Crepúsculo, Horno, Fuente), 4 Mágicas (3 de Juego Rápido + Carga de Máscara).
- `password = 0` (la vía elegida es el save, no la máquina de contraseñas; se puede completar después).
- `rarity = 4` en todas (valor válido, ajustable).
- Descripciones: los efectos de `datos/efectos_heroes_enmascarados.txt` unidos en un párrafo (se quitaron los guiones de viñeta).

## 4. BLOQUEO: el contenedor no entra en el ISO

Medido con `tools/e6_iso_space.py` (analizador de extents ISO9660, verificado en esta sesión):

- El ISO base está **completamente lleno**: los únicos sectores sin referenciar son los metadatos iniciales (22 sectores = 45 056 B en LBA 0..21: área de sistema + descriptores de volumen + path tables). **No sirven**: hay que preservar el descriptor de volumen, y además un archivo necesita un extent **contiguo**.
- El contenedor ocupa 550 sectores y tiene ~1184 B de holgura interna. Los 18 registros (~470 B) entran en esa holgura, pero **los textos UTF-16 nuevos suman ~8–12 KB** → hay que mover el contenedor a una región contigua libre de 551 sectores, y no existe.
- Archivos grandes presentes (candidatos si hay que liberar espacio): `PSP_GAME/SYSDIR/UPDATE/DATA.BIN` 15 456 416 B (7548 sectores, **datos de actualización de firmware: el juego no los usa**), `movie/staffroll_a.pmf` 56 MB, `movie/opening_a.pmf` 46 MB, `movie/opening_f.pmf` 46 MB (el ISO tiene los pares `_a`/`_f` por el modo «JP Voice enabled»), `snd/psp_snddat.bin` 166 MB.

**Opciones (decisión del usuario, T12b):**
- **(recomendada)** Neutralizar `PSP_GAME/SYSDIR/UPDATE/DATA.BIN` (y `UPDATE/EBOOT.BIN`) y mover el contenedor a la región liberada. El juego nunca lee esos datos; es una práctica estándar de la escena. Costo: cero jugable.
- Sustituir una de las películas duplicadas (`opening_f.pmf`) por un clon corto existente. Riesgo: si el juego reproduce esa, se ve otra cosa.
- Recortar los textos nuevos para entrar en 1184 B: **no alcanza** (18 descripciones cortas ya superan la holgura).

Mover un archivo es legal: su identidad es el registro de directorio; hay que reescribir LBA (bytes 2..9) y tamaño (10..17) en LE y BE. `tools/e6_iso_space.py` ya expone el analizador y un `relocate_record`; **no fue usado todavía** (el build se canceló antes).

## 5. Tareas

| ID | Tarea | Estado |
|---|---|---|
| T11 | Tabla de contenido de las 18 (`datos/cartas_18.tsv`) con códigos derivados y donantes de arte | **hecha** — la verifica el build |
| T12 | Construir el contenedor de 2481+18 registros (Prop/Genre/Pass/Indx/Name/Desc/IntID) y verificar que los 2480 previos no cambian | pendiente |
| T12b | Liberar espacio en el ISO y reubicar el contenedor (ver §4) | **bloqueada — espera decisión del usuario** |
| T12c | ISO final: contenedor reubicado + alias de arte en `cardh_s.cip`/`cardm_s.cip` + motor C2 + verificación offline | pendiente |
| T13 | Prueba del usuario: las 18 visibles en el álbum (nombre, arte, ATK/DEF, nivel) y una en duelo | pendiente |
| T14 | Editar el save/álbum para que el jugador posea las 18 (vía elegida para obtenerlas) | pendiente |

## 6. Plan de build (para no re-derivar; es el spec que se le pasó al worker cancelado)

Herramientas nuevas previstas: `tools/e6_build_18.py` (constructor) y `tools/e6_iso_space.py` (analizador/movedor, ya existe). Reutilizar, sin modificar, `tools/cardinfo_add.py` (agregado de un registro) y `tools/e5_c2_patch.py` (parche del motor: 17 palabras del wrapper en 0x478fc, entrada de reloc repuntada, entrada de dirección del NID `0xcda3b5c5` → 0x478fc, y los dos `jal 0x478fc`; EBOOT.BIN = el ELF parcheado con ceros hasta 1104032 B).

1. Leer `datos/cartas_18.tsv`; **afirmar** que los 18 cardid están libres en el contenedor prístino (`CARD_IntID[cardid-4000] == 0`) y resolver cada `arte_donante` por nombre exacto; si alguno no resuelve, sustituir por el HÉROE existente del mismo `attr` y **reportarlo**.
2. Agregar los 18 registros en 2480..2497 en el orden del TSV, con todos los campos del TSV y `CardExistFlag=1`; `CARD_IntID[cardid-4000] = índice`.
3. Afirmar: 2481 registros; los 18 correctos; **todos los índices 0..2479 idénticos byte a byte** al prístino en Prop/Genre/Pass y en (card_id, nombre, atk, def, nivel) derivados.
4. Ubicar el contenedor (ver §4) y actualizar el registro de directorio.
5. Copiar la entrada CIP del donante al slot nuevo en `cardh_s.cip` y `cardm_s.cip`.
6. ISO final en `trabajo/e6/TF1-E6-18.iso` desde el ISO base español; reabrir y verificar: los 18 registros con sus campos, los 2480 previos sin cambios, las entradas CIP nuevas, y los hechos del motor (palabras del wrapper, export, reloc, llamadores).

## 7. Log

- **L1 (usuario, verbatim).** «En realidad solo tengo una, no tengo 4 de esas. Voy a probar en duelo» — aclaración sobre el «X4» que muestra el juego: es el conteo del registro *aliasado* (CardID 4453), no el álbum.
- **L2 (usuario, verbatim).** «1,2,3 ok. Todo funciono» → **C cerrada**: carta nueva legal en el editor, cartas propias intactas, duelo arranca y la carta se invoca. Con esto E5 T9 queda cerrado y se habilita armar las 18.
- **L3 (usuario, verbatim).** «Guarda sesion, sigamos con esto en la proxima» → cierre de sesión: se guardan notas, memoria y commits.
- **L4 (hallazgo).** El build de las 18 se canceló al detectarse (§4) que el ISO no tiene región contigua libre; el analizador `tools/e6_iso_space.py` quedó escrito y **verificado** (su medición se reprodujo en esta sesión). No se escribió ningún ISO de E6.
- **L5 (nota de continuidad).** Quedan sin trackear y sin commitear a propósito: `tools/e6_iso_space.py` (verificado) y `tools/e5_patch_iso_c2.py` (diagnóstico del camino bloqueado del wrapper). El resto se commitea en esta sesión.

## 8. Entrega (corte de slice)

Rama `spike/e1-test`. Cierre de sesión con cuatro commits para E5 (el slice de la estrategia C queda cerrado y verificado):

- `ac4187b` feat(e5): las tres herramientas (`e5_patch_iso.py`, `e5_patch_iso_c2.py`, `e5_c2_patch.py`)
- `81d8ae6` docs(e5): `ESTADO-E5-limite.md`
- `aebb888` feat(e6): `datos/cartas_18.tsv` + `datos/efectos_heroes_enmascarados.txt`
- `b69bc37` docs(e6): este documento + `tools/e6_iso_space.py`

**El corte de entrega queda acá**: E6 (las 18) es un slice nuevo, que arranca cuando se resuelva §4 (espacio en el ISO) y va con sus propios commits de unidad de trabajo. Los ISO de prueba viven en `trabajo/` y están en `.gitignore`. Push, PR y merge son decisión del usuario: nada se subió.

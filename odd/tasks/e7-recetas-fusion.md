# E7 · Recetas de fusión para las 11 Masked HERO

Fase E7, alcance A (decidido por el usuario). Todo el contexto del motor está medido en
`ESTADO-E7.md` §7 y en `trabajo/e7/recon/E7-RECON-EFFECTS.md`.
ISO de partida: `trabajo/e8/TF1-E8-G6.iso` (arte cerrado). Artefacto de salida: `trabajo/e7/TF1-E7-F1.iso`.

## Specs

- **S1 — Alcance.** Se hacen invocables por Fusión las 11 Masked HERO. **No se escribe código ARM
  nuevo** en esta fase: se usa la tabla de recetas nativa. Fuera de alcance: los efectos de las 4
  Mágicas y los de los monstruos (frentes B y C de `ESTADO-E7.md` §3).
- **S2 — Materiales.** `resultado = base E-HERO del mismo atributo + «Cambio de Máscara» (CardID
  4704)`. Base por atributo (decidida por el usuario):

  | Fusión | CardID | Atributo | Base E-HERO |
  | --- | --- | --- | --- |
  | Ácido | 4661 | AGUA | Bubbleman 6393 |
  | Anki | 4665 | OSCURIDAD | Necroshade 6527 |
  | Blast | 4671 | VIENTO | Avian 6310 |
  | Dark Law | 4672 | OSCURIDAD | Necroshade 6527 |
  | Dian | 4673 | TIERRA | Clayman 6312 |
  | Divine Wind | 4681 | VIENTO | Avian 6310 |
  | Goka | 4684 | FUEGO | Burstinatrix 6311 |
  | Koga | 4686 | LUZ | Sparkman 6313 |
  | Vapor | 4689 | AGUA | Bubbleman 6393 |
  | Atómico | 4690 | FUEGO | Burstinatrix 6311 |

  `Contraste Chaos` (4696) usa los materiales que fija el propio texto del usuario: **2 monstruos
  «HÉROE Enmascarado»** ⇒ se agrega una entrada por cada par no ordenado de las 10 Masked HERO
  anteriores (45 entradas).
- **S3 — La tabla nativa no se puede estirar in situ.** La tabla vive en `gmodule/libduel_eng.prx`
  `.data` VMA `0x10acb4` (94 registros de 8 B, terminador `(10,0,0,0)` en `0x10afa4`). Pegado al
  terminador hay un blob de 108 B (`0x10afac..0x10b018`) y después la tabla de 8 B
  `{u16 CardID; u16 0; u32 handler}` (`0x10b018..`). El largo está hardcodeado en el finder `.text
  0xa0454` (`sltiu ..., 0x5e`). Cualquier extensión debe dejar coherentes: la tabla, el terminador, el
  largo del finder y el puntero de fin de tabla (usado por 4 funciones, p. ej. `0xaad58`).
- **S4 — Nada de lo que funciona se rompe.** Las 94 recetas nativas deben seguir resolviendo en la ISO
  construida, y ninguna región de `libduel_eng.prx` fuera del plan de parches puede cambiar.
- **S5 — Prueba del usuario en PPSSPP.** `Polimerización` + base + «Cambio de Máscara» invoca la
  Masked HERO correspondiente, y una fusión nativa (`Flame Wingman`) se sigue invocando.
- **S6 — Un artefacto ISO por ronda**, sin tocar nunca la ISO original ni la de partida.
- **S7 — Duda abierta, la decide el test.** Si el motor rechaza una Mágica como material de fusión
  (todos los materiales nativos son monstruos), **no se cambia el mapa por cuenta propia**: se vuelve
  al usuario con la medición y las alternativas ya ofrecidas (Rey del Pantano 6044 / materiales del
  donante E-HERO).

## Tasks

| ID | Specs | Qué | Route | Commit |
| --- | --- | --- | --- | --- |
| T1 | S3, S4 | Decidir y documentar dónde viven las 149 recetas (94+55): espacio libre real dentro de `.data` o crecimiento del segmento. Producir el mapa exacto de parches (base, fin, largo, y los 4 sitios de fin de tabla). | worker | — |
| T1b | S3 | **Bloqueo abierto (usuario)**: elegir entre S-A (segundo PT_LOAD, 6 parches, cargador sin precedente) y S-B (desplazar el bss, 11 428 parches). Medición completa en `trabajo/e7/T1-PLAN.md` y `ESTADO-E7.md` §8. | user | — |
| T7 | S3, S4 | **Experimento aprobado por el usuario** (§7.5.1): parchear el puntero de una carta que el usuario pueda jugar en la tabla `{u16 CardID; u16 0; u32 ptr}` (VMA `0x10b018..`) por el handler de `Monster Reborn` (4842, puntero `0xadbcc`) y construir `trabajo/e7/TF1-E7-EXP1.iso` para probar si el despacho `{CardID → ptr}` es vivo y editable. Un round de PPSSPP del usuario decide el frente B. | worker | — |
| T9 | S3 | **EXP2, sonda de layout del cargador**: construir una ISO con el layout exacto de S-A (2º `PT_LOAD` con un payload inocuo de 1200 B en el hueco de archivo `0x10c0e0`, `e_phoff` reubicado, **sin** tocar el finder ni ninguna tabla) para decidir si `libehsys` soporta 2 segmentos. Un round del usuario decide si S-A es viable. | worker | — |
| T2 | S1, S2 | `tools/e7_fusion.py`: construir la tabla nueva y parchear `libduel_eng.prx` en una copia, con verificación de ida y vuelta. | worker | — |
| T3 | S6 | Construir `trabajo/e7/TF1-E7-F1.iso` desde `TF1-E8-G6.iso` con el `.prx` parcheado; verificación por sectores. | worker | — |
| T4 | S4 | Verificación offline: las 94 nativas + las 55 nuevas legibles desde la ISO; nada fuera del plan cambió. | verify | — |
| T5 | S5 | Test del usuario en PPSSPP (una sola varilla de decisión). | user | — |
| T6 | — | Commits por unidad de trabajo, `ESTADO-E7.md` actualizado y cierre de la fase. | inline | — |

## Log

- **L1** (usuario, verbatim): «empieza con un recon read-only corto (localizar recetas de fusión +
  mapear el cableado de efectos) E7».
- **L2** (usuario, verbatim): «Acabo de reiniciar el pc para ver si esta vez no te congelas en lo que
  haces E7, sigue en donde quedaste con eso».
- **L3** (usuario, decisión de alcance, verbatim): «A · Recetas de fusión (mi recomendación)».
- **L4** (usuario, decisión de materiales, verbatim): «Base E-HERO + «Cambio de Máscara» (4704)».
- **E1** (medido, read-only): tabla de fusión nativa = 94 registros de 8 B `(result, mat1, mat2, mat3)`
  en `libduel_eng.prx` `.data` VMA `0x10acb4`, terminador `(10,0,0,0)`, finder `.text 0xa0454` con
  largo `0x5e` hardcodeado, sin relocs; blob de 108 B pegado al terminador. Detalle en `ESTADO-E7.md`
  §7.1.
- **E2** (medido, read-only): los efectos se despachan por tablas de datos `CardID → handler`
  (24 B y 8 B); las 4 Mágicas del port no tienen handler (0 apariciones). `ESTADO-E7.md` §7.2–7.3.
- **E3** (T1, medido por worker, 2026-11-03): **no hay espacio para las recetas nuevas**. Los 108 B
  siguientes al terminador son una tabla viva de 27 palabras con 11 referencias absolutas en `.text`;
  el mayor hueco muerto de `.data` es de 328 B; pisar bss es inseguro (546 referencias en el primer
  1,2 KB) y el módulo tiene **un solo PT_LOAD** (los 22 `.prx` + `BOOT.BIN` también). Quedan S-A
  (2º PT_LOAD, 6 parches, cargador sin precedente) y S-B (desplazar bss, 11 428 parches). Plan y mapa
  en `trabajo/e7/T1-PLAN.md`. Sin solapamiento: ninguno de los 11 resultados está ya en la tabla.
- **E4** (corrección de documento): la afirmación de `ESTADO-E7.md` §7.1 de que `E. Hero Erikshieler
  4696` ya tenía receta nativa era **falsa**; corregida.
- **L5** (usuario, decisión de secuencia, verbatim): «Probar antes el mecanismo de efectos (1 palabra)»
  ⇒ T7, con T2/T3 bloqueadas hasta que el experimento diga si el despacho `{CardID → ptr}` responde.
- **E6** (T7, ejecutado y verificado, 2026-11-03): EXP1 construido. Carta origen **`Rescate` (Salvage,
  5908)**, la única Mágica de la tabla que el usuario ya tiene en el deck (deducido del save, no
  asumido); donante `Monster Reborn` (4842). Parche `libduel_eng.prx` file `0x10b634`:
  `44 28 0b 00` → `cc db 0a 00`. Artefacto `trabajo/e7/TF1-E7-EXP1.iso` (sha256 `aa1376fa…`), con
  **3 bytes** distintos de G6 y **1 sector** (12582) tocado — verificado por el padre con comparación
  byte a byte del archivo completo (la afirmación «exactamente 4 bytes» no se sostiene porque ambos
  punteros comparten el byte alto; la invariante verificada es «todo byte cambiado dentro de la
  palabra declarada»). Herramienta `tools/e7_exp1.py` (subcomandos `table`/`patch`/`verify`/`iso`, se
  niega a escribir si falla una invariante) y volcado completo de la tabla (363 entradas) en
  `trabajo/e7/T7-TABLE.txt`. **Falta el test del usuario en PPSSPP** (T8) para cerrar el frente B.
- **L6** (usuario, resultado del test, verbatim): «Opción B, cumplió su efecto original» ⇒ la tabla de
  8 B no es la palanca del efecto de activación. Registrado en `ESTADO-E7.md` §7.5.1 y como obs. de
  memoria `mask-hero-tf1/e7-exp1-result`. Siguiente: **T9 (EXP2)**, sonda de layout del cargador, que es
  lo que de verdad decide si S-A es viable para el frente de fusión; y sigue abierta la decisión
  S-A vs S-B.
- **E7** (T9, ejecutado y verificado, 2026-11-03): **EXP2**, sonda inocua del layout de S-A. Artefacto
  `trabajo/e7/TF1-E7-EXP2.iso` (sha256 `7ab83647…`, mismo tamaño que G6): `e_phoff=0x167150`,
  `e_phnum=2`, 2ª PH mapeando 1200 B en `VMA 0x112910`, payload con marcador en file `0x167190`,
  módulo 1.470.794 → 1.472.064 B dentro de su asignación (la ISO no crece), 3 sectores distintos.
  Herramienta `tools/e7_exp2.py`; protocolo en `trabajo/e7/T9-EXP2.md`. **Falta el test del usuario
  (T10)**: si el juego arranca y el duelo corre igual que con G6, S-A es viable y T2/T3 desbloquean; si
  falla, no distingue «e_phoff reubicado» de «dos segmentos» y hará falta una sonda más fina.
- **E8** (error del padre, cazado por el worker): el brief de EXP2 declaraba libre la región de archivo
  `0x10c0e0..0x159b48`. Es **falso**: ahí viven `.shstrtab`, la tabla de secciones y `.rel.text`. El
  worker se negó a escribir con esa premisa; se corrigió a un append al final del archivo. Lección: la
  lista de secciones de un `.prx` **no** implica que el resto del archivo esté libre — hay que cruzar
  `sh_offset`/`sh_size` de **todas** las secciones antes de declarar un hueco.
- **L7** (usuario, resultado del test, verbatim): «Duelo completado usando varias fusiones normales de la
  receta de jaiden y partida salvada» ⇒ **EXP2 = A**: el cargador acepta el `e_phoff` reubicado y el
  segundo `PT_LOAD`, así que **S-A es viable** y T2/T3 se desbloquean. Siguiente sesión: T2 (tabla
  extendida de 149 registros en el segmento nuevo + repunte del finder y de los 4 sitios de fin) y T3
  (ISO de producto `trabajo/e7/TF1-E7-F1.iso`).

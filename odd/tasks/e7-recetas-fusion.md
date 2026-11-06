# E7 · Recetas de fusión para las 11 Masked HERO

Fase E7, alcance A (decidido por el usuario). Todo el contexto del motor está medido en
`ESTADO-E7.md` §7 y en `trabajo/e7/recon/E7-RECON-EFFECTS.md`.
ISO de partida: `trabajo/e8/TF1-E8-G6.iso` (arte cerrado). Artefacto de salida: `trabajo/e7/TF1-E7-F3.iso`
(rondas F1 → F2 → F3; el mapa vigente es el de L14).

## Specs

- **S1 — Alcance.** Se hacen invocables por Fusión las 11 Masked HERO. **No se escribe código ARM
  nuevo** en esta fase: se usa la tabla de recetas nativa. Fuera de alcance: los efectos de las 4
  Mágicas y los de los monstruos (frentes B y C de `ESTADO-E7.md` §3).
- **S2 — Materiales.** `resultado = base E-HERO del mismo atributo + «Cambio de Máscara» (CardID
  4704)`. Base por atributo: **todas las bases E-HERO del mismo atributo que la receta del deck ya
  posee** (L12), donde la receta es `datos/receta_hero.tsv`:

  | Fusión | CardID | Atributo | Base(s) E-HERO |
  | --- | --- | --- | --- |
  | Ácido | 4661 | AGUA | Bubbleman 6393 |
  | Anki | 4665 | OSCURIDAD | Necroshade 6527 |
  | Blast | 4671 | VIENTO | Avian 6310 |
  | Dark Law | 4672 | OSCURIDAD | Necroshade 6527 |
  | Dian | 4673 | TIERRA | Clayman 6312, **Bladedge 6477**, **Wildheart 6478** |
  | Divine Wind | 4681 | VIENTO | Avian 6310 |
  | Goka | 4684 | FUEGO | Burstinatrix 6311 |
  | Koga | 4686 | LUZ | Sparkman 6313 |
  | Vapor | 4689 | AGUA | Bubbleman 6393 |
  | Atómico | 4690 | FUEGO | Burstinatrix 6311 |

  Son **12 registros** de base E-HERO (9 de una sola base + 3 de Dian) porque TIERRA es el único
  atributo con más de una base poseída. `Necroshade 6527` **no** está en la receta del deck (Anki y Dark
  Law quedan inalcanzables hasta que tenga esa carta) pero **se mantiene**: quitarla los dejaría sin
  receta alguna.

  **Bases HÉROE de Fusión (L14).** La carta real «Cambio de Máscara» toma **cualquier** monstruo HÉROE,
  así que las 7 Fusiones HÉROE que el deck ya posee son bases con la **misma regla de atributo**. Los
  atributos se **midieron** (contenedor prístino para las bases, `datos/cartas_18.tsv` para los
  resultados), no se recordaron:

  | Fusión poseída | CardID | Atributo | Enmascarados que gana |
  | --- | --- | --- | --- |
  | Flame Wingman | 6344 | VIENTO | Blast 4671, Divine Wind 4681 |
  | Tempest | 6487 | VIENTO | Blast 4671, Divine Wind 4681 |
  | Rampart Blaster | 6486 | TIERRA | Dian 4673 |
  | Mudballman | 6529 | TIERRA | Dian 4673 |
  | Wildedge | 6488 | TIERRA | Dian 4673 |
  | Thunder Giant | 6345 | LUZ | Koga 4686 |
  | Steam Healer | 6535 | AGUA | Ácido 4661, Vapor 4689 |

  ⇒ **+10 registros** (Dian pasa a 6 bases). El deck **no** posee Fusiones HÉROE de OSCURIDAD ni de
  FUEGO, así que Anki, Dark Law, Goka y Atómico no ganan bases nuevas.

  `Contraste Chaos` (4696) usa los materiales que fija el propio texto del usuario: **2 monstruos
  «HÉROE Enmascarado»** ⇒ una entrada por cada par no ordenado de las 10 Masked HERO anteriores
  (45 entradas). **Total: 12 + 10 + 45 = 67 registros nuevos ⇒ 94 + 67 = 161 registros** (F1: 149;
  F2: 151). Holgura: el *extent* ISO del módulo es 1.472.512 B y la tabla de 161 pide 1.472.160 B ⇒
  quedan **352 B** sin hacer crecer la ISO.
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
| T10 | S2, S6 | Ronda **F2**: ampliar el mapa a las bases poseídas (L12) y construir `libduel_eng_f2.prx` + `TF1-E7-F2.iso`. | worker | hecho (E16) |
| T11 | S4 | Verificación independiente de F2 (misma batería que T4). | verify | hecho — PASS (E16) |
| T12 | S5 | Ronda in-game de F2: Dian con Bladedge/Wildheart + una fusión nativa. | user | pendiente |
| T13 | S2, S6 | Ronda **F3**: ampliar el mapa a los HÉROE de Fusión poseídos (L14, edición data-only) y construir `libduel_eng_f3.prx` + `TF1-E7-F3.iso`. | worker | hecho (E19) |
| T14 | S4 | Verificación independiente de F3 (misma batería que T11 + igualdad de atributos de cada base nueva). | verify | hecho — PASS (E21) |
| T15 | S5, S6 | Ronda in-game única sobre `TF1-E7-F3.iso`, higiene de docs (README + entrega) y cierre de la fase. | user + inline | — |

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
- **E9** (entrega, medido por el harness): el corte de unidad de trabajo para E7 es el commit
  **`fb27dca`** (`feat(e7): map the engine dispatch for effects and probe the module layout`, 4 archivos,
  1 566 líneas). La rama `spike/e1-test` está en **28 commits / ~9 710 líneas** sobre `main`: antes del
  próximo commit hay que aplicar la estrategia de entrega (PRs encadenados; corte sugerido E0..E6 / E7 /
  E8) y actualizar el README. **Decisión del usuario**, no del agente. Por eso T2/T3 no se commitearon y
  esta anotación queda en el árbol de trabajo.
- **Estado al cerrar la sesión**: sin commitear `ESTADO-E6.md`, `ESTADO-E8.md`, `tools/e6_patch_save.py`,
  `datos/receta_hero.tsv` (unidad de trabajo de la fase E6, anterior y separada) y esta anotación.
- **L8** (usuario, verbatim): «Sigamos con E7 ahora que ya tenemos referencias de Tag force special»
  (la referencia es la de E9: `ESTADO-E9.md`, «Cambio de Máscara» en ARC-V Tag Force Special).
- **L9** (usuario, decisión de secuencia, verbatim): «A ahora y B después, en rondas separadas» ⇒ esta
  ronda cierra **T2/T3 (frente A: recetas)** y el **frente B** (el efecto real de «Cambio de Máscara»
  como código ARM, con la spec de E9) queda como **fase propia**, no como parte de E7.
- **L10** (usuario, decisión de entrega, verbatim): «Cortar PRs al cerrar E7» ⇒ los PRs encadenados
  (corte E0..E6 / E7 / E8 / E9) + README se hacen **con E7 cerrado y validado in-game**, no antes.
- **E10** (medido por el padre, 2026-11, read-only sobre `trabajo/e1c/gm/libduel_eng.prx`):
  (a) **el finder es un escaneo lineal por resultado, sin orden que preservar**: `0xa0454` materializa
  la base, y el bucle compara `lhu 0(entry)` contra el argumento y devuelve el puntero de la **primera**
  coincidencia, con `sltiu a2,0x5e` (VMA `0xa047c`, file `0xa04dc`) ⇒ **agregar al final es seguro**
  (no hay búsqueda binaria ni clave ordenada).
  (b) **Completitud del mapa de parches, verificada por barrido**: la base `0x10acb4` se materializa
  **una sola vez** en todo `.text` (VMA `0xa0460`, file `0xa04c0`); el terminador `0x10afa4`
  **exactamente cuatro veces** (VMA `0xaad64`, `0xaaf50`, `0xab3d4`, `0xab484`; file `0xaadc4`,
  `0xaafb0`, `0xab434`, `0xab4e4`); `sltiu …,0x5e` una sola vez. Barrido de todos los pares
  `lui+addiu` que resuelven a `0x10ac00..0x10b100`: 10 sitios, y **ninguno más sobre la tabla de
  fusión** (los demás son la tabla de 27 palabras de `0x10afac` y `0x10ac80`/`0x10ac9c`/`0x10b01c`).
  Los 4 sitios de fin pasan el terminador como **argumento** a un import de `libehsys`
  (stub VMA `0xfbe00`, NID `0xed7a3401`, vía el wrapper `0xf7698`, que resuelve el puntero contra la
  base del módulo) ⇒ lectura de T1 **confirmada**: es un **límite de tabla**, no una base.
  (c) La carga útil nueva son **1200 B exactos** (94 copiados + 55 nuevos + terminador = 149×8+8),
  **el mismo tamaño que la sonda EXP2** ⇒ el layout ya validado in-game por T10 se reusa sin cambios
  (mismo `PH_OFF=0x167150`, mismo `PAYLOAD_OFF=0x167190`, mismo archivo final `0x167640`).
- **Riesgo abierto de esta ronda (S7)**: que el motor rechace una **Mágica** como material de fusión
  (todos los materiales nativos son monstruos). Si la selección de materiales del duelo no deja elegir
  «Cambio de Máscara», **no se cambia el mapa por cuenta propia**: se vuelve al usuario con la medición
  y las alternativas ya ofrecidas (Rey del Pantano 6044 / materiales del donante E-HERO). Lo decide T5.
- **E11** (T2/T3, ejecutados, 2026-11): construidos `trabajo/e7/libduel_eng_f1.prx` (1.472.064 B =
  `0x167640`, sha256 `5dfb9b7e…0a8e7e1`) y `trabajo/e7/TF1-E7-F1.iso` (798.787.584 B, **mismo tamaño
  que G6**, sha256 `135c8881…36362d7`) con la herramienta nueva `tools/e7_fusion.py`
  (`patch`/`verify`/`iso`/`dump`; se niega a escribir si una invariante falla). Informe del escritor:
  `trabajo/e7/T2-T3.md`.
- **E12** (T4, verificación independiente, 2026-11): un verificador read-only **re-derivó todo desde los
  bytes, sin usar la herramienta del escritor**. PASS en **S2, S3, S4 y S6**: `e_phnum=2` con PH2 =
  `(1, 0x167190, 0x112910, 0x112910, 1200, 1200, 7, 16)`; **15 bytes distintos** en `[0, 0x16714a)`
  (los 6 sitios declarados + `e_phoff` + `e_phnum`) y nada más; tabla de secciones byte-idéntica;
  registros 0..93 byte-idénticos a los nativos; 10 recetas exactas según S2 y los 45 pares exactos
  (`itertools.combinations`) sin duplicados; 149 registros y terminador `(10,0,0,0)`; las 94 nativas
  resuelven en el **mismo índice** que en la tabla original y las 11 nuevas a su receta (4696 → primer
  par `(4661,4665)`); en la ISO solo difieren los sectores `{38, 12048, 12368, 12389, 12390, 12766}`
  (registro de directorio + el módulo) y `libduel_mgr.prx` (LBA 12767+) está intacto.
- **E13** (corrección de cifra del padre): el «barrido = 10 sitios» de E10(b) contaba solo pares
  `lui`+`addiu` **adyacentes y en el mismo registro**; un barrido más amplio (ventana de 8
  instrucciones / guiado por relocs) encuentra más candidatos, pero **las cifras sustantivas se
  reproducen exactas**: `0x10acb4` se materializa **una vez**, `0x10afa4` **cuatro veces**, y ningún otro
  sitio toca la tabla de fusión. La cifra de 10 era un artefacto del criterio de barrido, no un hecho.
- **Cobertura offline de esta unidad**: el subcomando `verify` de `tools/e7_fusion.py` (verificación
  estructural ida y vuelta, reproducible desde el módulo prístino). **No** se agrega un test con
  framework: los artefactos binarios viven en `trabajo/` (gitignored: 800 MB de ISO + módulo), así que
  un test commiteado que dependa de ellos no correría en un clon limpio; sería un falso test. El
  comportamiento en el juego lo decide T5.
- **L11** (usuario, resultado del test, verbatim): «funcionó, burstinatrix se fusiono con la magia
  cambio de mascara para invocar a atomic pero es raro ya que de las opciones no me salio Dian sabiendo
  que tengo a Bladedge que es tierra no me permitio fusionarlo con el, probablemente porqué esta
  invocado y quiza solo funcione si esta en la mano».
- **E14** (T5, primera varilla — **observada**): «Polimerización» + **Burstinatrix** (6311) + **«Cambio de
  Máscara»** (4704, una Mágica) resolvió e invocó **HÉROE Enmascarado Atómico** (4690) ⇒ (a) la receta
  nueva del frente A funciona in-game; (b) **S7 queda contestada: el motor NO rechaza una Mágica como
  material de fusión**; (c) el segundo `PT_LOAD` no sólo «no rompe la carga» (EXP2): **se usa** — el
  finder repuntado a `0x112910` con largo 149 está leyendo la tabla nueva.
- **Sobre Dian / Bladedge (medido, no es un fallo)**: Bladedge (6477) **no es material de ninguna de las
  55 recetas**: S2 fija **una base por atributo** y para TIERRA la base es **Clayman (6312)**. Dian sólo
  se ofrece con `Clayman + «Cambio de Máscara»` (y con Clayman disponible en mano o campo). Si se quiere
  «cualquier HÉROE del mismo atributo», hay que **ampliar S2** (decisión de producto del usuario).
  **Restricción medida de esa ampliación**: el módulo ocupa 1.472.064 B dentro de un *extent* ISO de
  1.472.512 B ⇒ **448 B = 56 registros** de holgura (`8 B` cada uno) **sin** hacer crecer la ISO; más que
  eso pide un layout nuevo (mover el módulo siguiente del image).
- **T5 sigue abierta**: falta la **segunda varilla de S5** (que una fusión **nativa**, p. ej. Avian +
  Burstinatrix → Flame Wingman, siga resolviendo). Sin esa señal no se cierra T5 ni se commitea la unidad.
- **L12** (usuario, decisión de producto, 2026-11): ante la ausencia de Dian en la lista de fusiones
  («de las opciones no me salio Dian sabiendo que tengo a Bladedge que es tierra»), eligió **«Ampliar
  sólo las bases que ya tenés»** ⇒ **S2 se reescribe** a «todas las bases E-HERO del mismo atributo que
  la receta del deck ya posee». En la misma ronda respondió dos cosas más: **la fusión nativa todavía no
  la probó** (T5 sigue abierta) y **Burstinatrix estaba en la mano** al fusionar (su hipótesis de que un
  monstruo **en el campo** no cuenta como material queda **sin confirmar**, ni probada ni descartada).
- **E15** (medido, consecuencia de L12): las bases poseídas por atributo salen de `datos/receta_hero.tsv`
  y dan **sólo Dian con más de una**: TIERRA = Clayman 6312 + **Bladedge 6477** + **Wildheart 6478**;
  los otros ocho atributos del mapa tienen **una sola** base poseída cada uno. Por eso la ampliación son
  **+2 registros** (S2: 57; tabla: **151**). Holgura: el *extent* ISO del módulo es 1.472.512 B y la
  tabla nueva pide 1.472.080 B ⇒ quedan **432 B = 54 registros**; los 7 HÉROE de Fusión de la receta
  pedirían 10 registros más, así que también entrarían (queda como decisión aparte, ver S2).
- **T10/T11** (reabren T2/T3/T4 sobre un artefacto nuevo `F2`): el mismo mecanismo, con el mapa ampliado.
- **E16** (T10/T11, ejecutados y verificados, 2026-11): ronda **F2** construida y verificada —
  `trabajo/e7/libduel_eng_f2.prx` (1.472.080 B = `0x167650`, sha256 `38c44953…ad59a`) y
  `trabajo/e7/TF1-E7-F2.iso` (798.787.584 B, sha256 `e3d9ea35…742fbf`). La herramienta ahora **deriva
  del mapa** los contadores, el tamaño de la carga útil, el inmediato del largo y el puntero de fin ⇒ el
  próximo cambio de mapa es **edición de datos**. Verificación independiente (T11): **PASS en S2, S3, S4
  y S6** — 151 registros sin duplicados, triplete de Dian exacto `(4673, 6312/6477/6478, 4704, 0)`, los 45
  pares exactos, las 94 nativas resuelven en el **mismo índice**, `4673 → (4673,6312,4704,0)` y
  `4696 → (4696,4661,4665,0)`, y **todos** los bytes que difieren en la ISO explicados por el plan;
  G6 y los artefactos de F1 quedaron byte-idénticos. Nota: `trabajo/e7/T10-F2.md` etiqueta «PH1» al
  segmento nuevo; es **PH2** (los valores medidos son correctos).
- **Pendiente de la ronda (una sola varilla, T5+T12)**: Dian con **Bladedge** o **Wildheart** + «Cambio
  de Máscara», y una **fusión nativa** (Avian + Burstinatrix → Flame Wingman) para cerrar S4 in-game.
  **Decisión abierta**: incluir los **7 HÉROE de Fusión** poseídos como bases (+10 registros; entran en
  la holgura de 432 B).
- **Estado al cerrar la sesión (2026-11, a pedido del usuario: «haré esto mañana, guarda y cierra
  sesion»)**: rondas **F1** y **F2** construidas y verificadas offline (PASS independiente en S2, S3, S4
  y S6); **T5/T12 esperan la ronda in-game de mañana sobre `TF1-E7-F2.iso`** (dos señales: Dian con
  Bladedge/Wildheart, y una fusión nativa). Sin commitear: `tools/e7_fusion.py` (nuevo) y los cambios de
  `ESTADO-E7.md` (§8.4/§8.5) y de este documento (L8-L12, E10-E16, S2 reescrito). **No se commiteó a
  propósito**: L10 fija que el commit de la unidad de E7 va **después** de la validación in-game, y el
  corte de PRs al cerrar la fase. Los artefactos binarios (`trabajo/e7/*.prx`, `*.iso`) son gitignored y
  quedan en disco.
- **L13** (usuario, decisión de entrega, 2026-11, verbatim): «Vamos a ordenar todo lo relacionado con el
  repo y hacer los commits y push correspondientes a lo trabajado». Decisiones de entrega tomadas en el
  cuestionario de esa ronda: **cadena stacked a `main`** (`chain_strategy=stacked-to-main`), **un corte
  por fase** (E1-test / E5 / E6 / E7 / E8 / E9 + README) y **PRs simples, sin issues ni labels** (el repo
  destino no tiene esa política). Esto **adelanta el commit de la unidad de E7 y el corte de PRs**
  respecto de L10, que los ataba al cierre validado in-game: **T5/T12 siguen abiertos** y quedan
  declarados como pendientes en el corte de E7.
- **E17** (T6, ejecutado, 2026-11): commit de la unidad de E7 en `spike/e1-test` —
  `feat(e7): add the data-driven fusion recipe patcher for TF1` (`tools/e7_fusion.py`) y
  `docs(e7): record the F1/F2 rounds and the delivery decision` (`ESTADO-E7.md` §8.4/§8.5 y este
  documento con L8-L13 y E10-E17). Entrega cortada en **7 ramas stacked desde `main`**, una por fase:
  `feat/e1-test-card-db-probe` → `feat/e5-level-reader-limit` → `feat/e6-port-18-cards` →
  `feat/e7-fusion-recipes` → `feat/e8-card-art` → `feat/e9-tfsp-reference` → `docs/readme-and-delivery`.
  El corte de E7 lleva la ronda **F2** verificada offline (PASS independiente en S2, S3, S4 y S6) con la
  validación in-game **todavía pendiente**; cada corte supera el presupuesto de revisión de 400 líneas y
  no hay split más fino que no rompa la cohesión (el detalle está en `odd/tasks/delivery-cadena-prs.md`).
- **E17b** (entrega, ejecutada por el usuario, 2026-11): los 7 cortes y un PR de integración quedaron
  **mergeados en `main`** (`42af335`). Corrección de convención del usuario (L2 de la entrega): con
  bases fijas el merge va **descendente** (tip primero, PR sobre `main` último). `main` es la rama
  canónica; `spike/e1-test` queda como registro de la historia original.
- **L14** (usuario, decisiones de esta ronda, verbatim: «Sigamos con los masked hero, en que nos
  quedamos?»): del cuestionario, **«Cerrar E7 (higiene de docs + dejar la ISO lista)»** y **«Sí,
  incluirlos (mapa 161)»** ⇒ S2 se amplía con los **7 HÉROE de Fusión poseídos** como bases (misma
  regla de atributo de L12) y la ronda cierra dejando la ISO lista para la ronda in-game.
- **E18** (medido, no recordado): atributos de los 7 HÉROE de Fusión leídos del contenedor **prístino**
  (`trabajo/e2/eng`, campo `attr`: 1 LUZ, 3 AGUA, 5 TIERRA, 6 VIENTO) y de los 11 Enmascarados en
  `datos/cartas_18.tsv`. La medición **corrigió el supuesto del padre**: Flame Wingman (6344) es
  **VIENTO**, no FUEGO, y Tempest (6487) también VIENTO ⇒ los resultados de VIENTO (Blast, Divine Wind)
  ganan **dos** bases y los de FUEGO (Goka, Atómico) **ninguna**. Mapa: **161 registros** (12 E-HERO +
  10 Fusión + 45 pares), carga útil **1296 B**, holgura **352 B**.
- **E19** (T13, ejecutado): ronda **F3** construida con la herramienta *data-driven*: el cambio fue
  **edición de datos** (una tupla nueva + contadores derivados) y los derivados salieron solos — tabla
  **161** (`sltiu 0xa1`), payload **1296 B**, fin de tabla VMA `0x112e18`, archivo `0x1676a0` =
  1.472.160 B. Artefactos: `trabajo/e7/libduel_eng_f3.prx` (sha256 `9b6c1fce…`) y
  `trabajo/e7/TF1-E7-F3.iso` (798.787.584 B, sha256 `85ca0409ea1b1fb4a4ba44b60427bac18d9b29119846a1e7d54e0f3473f77974`);
  auto-`verify` **OK** y chequeo por sectores del subcomando `iso` **OK** (6 sectores:
  `38, 12048, 12368, 12389, 12390, 12766`).
- **E20** (T15, higiene de docs): README (fila E7 y próximos pasos) y
  `odd/tasks/delivery-cadena-prs.md` (S1 con el orden de merge **descendente** de L2 y D4 marcado como
  ejecutado).
- **E21** (T14, ejecutado): verificación **independiente** de F3 por un verificador read-only que
  re-derivó todo de los bytes **sin usar** `tools/e7_fusion.py` (usó `tools/tfcard.py` sólo como lector
  de contraste y no modificó ningún archivo): **PASS en S2, S3, S4 y S6** más la **invariante de
  atributo** (10/10 pares iguales; Dian con sus 6 bases en el orden declarado). Números medidos: PH2
  exacto `(1, 0x167190, 0x112910, 0x112910, 1296, 1296, 7, 16)` con rangos de archivo y VMA disjuntos;
  tabla de secciones y PH0 byte-idénticos; **15 bytes** distintos en `[0, 0x16714a)` exactamente los
  declarados; 161 registros únicos, primeros 94 byte-idénticos a los nativos, los 22 de base exactos,
  los 45 pares exactos; las 94 nativas resuelven en el **mismo índice** y `4696 → (4696,4661,4665,0)`,
  `4673 → (4673,6312,4704,0)`; en la ISO el módulo es byte-idéntico al `.prx` y difieren exactamente
  los **6 sectores** `{38, 12048, 12368, 12389, 12390, 12766}` con `libduel_mgr.prx` (LBA 12767)
  intacto y G6/F1/F2 en sus pins. La batería del verificador quedó como herramienta reproducible:
  **`tools/e7_f3_probe.py`** (`python3 tools/e7_f3_probe.py`; manual, depende de `trabajo/`).
  Re-ejecutada acá para dejarla en verde: **PASS** (exit 0); el pegado del informe traía **dos errores de
  transcripción** (la comparación de PH0 y el `unpack` de `CARD_Prop`) que se corrigieron — la versión
  commiteada es la que se ejecutó, no la transcripción.

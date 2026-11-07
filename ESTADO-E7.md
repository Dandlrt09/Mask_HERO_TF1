# ESTADO — Fase E7: efectos de las 18 cartas (motor)

Estado: **recon read-only EJECUTADO** (§7). Nada del juego modificado todavía: falta la decisión de
alcance (§8).
Continúa a `ESTADO-E6.md` (§11.2) y a `ESTADO-E8.md` (§9.16.10, cierre de arte).
ISO base: `trabajo/e8/TF1-E8-G6.iso` (arte validado). Save con la receta HÉROE:
`trabajo/e6/DATA0.hero`.

---

## 1. Qué falta

El port (E6/E8) es de **datos**: nombre, arte, ATK/DEF, tipo/atributo/nivel, texto. Los **efectos NO
se ejecutan**. En duelo, hoy:

- Las **4 Mágicas** nuevas (**Cambio de Máscara**, **Cambio de Máscara II**, **Cambio de Forma**,
  **Carga de Máscara**) no ejecutan su efecto.
- Las **11 Fusiones** HÉROE Enmascarado **no tienen receta de fusión** ⇒ no son invocables (y como
  «Cambio de Máscara» tampoco ejecuta, quedan inalcanzables en duelo).
- Los **10 monstruos** tampoco aplican sus efectos.

## 2. Hechos conocidos (heredados de E6 §11.2)

- TF1 mantiene los **efectos de carta como código de motor**, no como datos.
- Módulos candidatos: `libduel_eng.prx`, `libduel_mgr.prx` — **ELF sin cifrar** (abordables).
- Posible que las **recetas de fusión** sí vivan como **datos** en `duelsys/*.ehp` (a verificar).
- El motor ya fue tocado con éxito en E5 (parche C2 del wrapper de límites en `BOOT.BIN`) y en E6
  (parche de límites + parche del motor), así que hay precedente de parchear código con verificación
  offline (diff de sectores) y test del usuario en PPSSPP.

## 3. Pregunta de alcance (decidir ANTES de empezar)

¿Qué priorizamos y en qué orden?

- **A. Recetas de Fusión** — que las 11 Fusiones se puedan invocar (Polimerización / «Cambio de
  Máscara»). Probablemente la vía más barata **si** las recetas son datos.
- **B. Efectos de las 4 Mágicas** — sobre todo las de «Cambio de Máscara», que son la receta
  concesionada del usuario.
- **C. Efectos de los 10 monstruos** — la parte más pesada (código por carta).
- **D. Todo**, por partes.

## 4. Plan sugerido (a validar con el usuario)

1. **Recon read-only (spike chico):**
   - Localizar las **recetas de fusión**: ¿existen en `duelsys/*.ehp`? ¿cómo se indexan por CardID?
     Contrastar con una fusión nativa conocida.
   - Mapear cómo se cablea un **efecto de Mágica** por carta en `libduel_eng.prx` / `libduel_mgr.prx`
     (tabla de handlers por CardID o por código interno).
2. **Decidir alcance** con el usuario a partir del recon.
3. **Atacar primero lo más barato/verificable** (muy probablemente las recetas, si son datos).
4. Cada paso con **verificación offline** (diff de sectores dentro del extent tocado) y **test del
   usuario en PPSSPP** (una sola varilla de decisión por ronda).

## 5. Riesgo

Fase **grande y de alto riesgo** (código de motor). Empezar con un **spike chico y verificable**, sin
prometer resultados, y con un artefacto ISO por ronda para que el usuario pruebe.

## 6. Referencia rápida (artefactos de fases previas)

- Parches de motor ya aplicados: `tools/e5_c2_patch.py` (wrapper de límites en `BOOT.BIN`),
  `tools/e6_build_18.py` (motor + datos de E6).
- Herramientas: `tools/ehp.py` (contenedores `.ehp`), `tools/iso_replace.py`, `tools/iso9660.py`,
  `tools/tfcard.py` (passcode→CardID), `tools/e6_iso_space.py`.
- Receta del usuario: `datos/receta_hero.tsv` (37 cartas ⇒ 53 copias concedidas en
  `trabajo/e6/DATA0.hero`).

---

## 7. Recon E7: resultados medidos (2026-11-03, read-only)

Artefactos: `trabajo/e7/recon/` (scripts `find_recipe{,2,3,5}.py`, `E7-RECON-EFFECTS.md`,
`find_recipe*.txt`, `filelist.txt`). ISO de trabajo: `trabajo/e8/TF1-E8-G6.iso` (solo lectura).
Nunca se escribió una ISO ni un archivo del juego.

### 7.1 Las recetas de fusión SON datos (hallazgo central)

En `PSP_GAME/USRDIR/gmodule/libduel_eng.prx` (ELF plano), sección `.data`:

| hecho | valor |
| --- | --- |
| inicio de la tabla | VMA `0x10acb4` = file offset `0x10ad14` |
| entrada | **8 B = (result, mat1, mat2, mat3) u16 little-endian, espacio CardID** |
| cantidad | **94 entradas** (`0x10acb4`..`0x10afa4`) |
| terminador | `(10, 0, 0, 0)` en VMA `0x10afa4` |
| relocs | **ninguna** sobre la tabla (`rel.data` empieza en `0x10ac80`, 4 punteros a `.text`) |

Estructura de la entrada: `mat3 == 0` ⇒ fusión de 2 materiales; `mat3 != 0` ⇒ tercer material
(`Blue-Eyes Ultimate Dragon` = 4007×3, `Cyber End Dragon` = 6390×3, `Alkana Knight Joker`,
`E. Hero Tempest` = Avian + Sparkman + Bubbleman). `mat1`/`mat2` pueden ser además un **token de
tipo**, no un CardID: `15` = Guerrero (`UFOroid Fighter` = UFOroid + Guerrero) y `7` = Máquina
(`Chimeratech Overdragon` = Cyber Dragon + Máquina).

Verificación con recetas reales (muestra): idx 0 `Flame Swordsman` = Flame Manipulator + Masaki;
idx 12 `B. Skull Dragon` = Summoned Skull + Red-Eyes; idx 66 `E. Hero Flame Wingman` = Avian +
Burstinatrix; idx 71 `Shining Flare Wingman` = Flame Wingman + Sparkman; idx 84 `Blue-Eyes Ultimate
Dragon` = Blue-Eyes ×3.

**Corrección (2026-11-03, medida):** los 94 resultados son 94 distintos y **ninguno de los 11 objetivos de
E7 aparece como resultado**, ni tampoco 4696 ni 6639. Una versión anterior de esta sección afirmaba que
`E. Hero Erikshieler 4696` ya tenía receta nativa: era **falso** (venía de confundir la salida del
clasificador `0xa0530` con una entrada de la tabla). No hay solapamiento: las 11 fusiones nuevas no
sombran ninguna componente nativa.

**Consumidor (medido)**: finder en `libduel_eng.prx` `.text` **`0xa0454`**, que materializa la base
con el par `lui $a1,0x11` + `addiu $a1,$a1,-0x534c` (= `0x10acb4`, en el delay slot) y recorre con
`sltiu ..., 0x5e` ⇒ **el largo 94 está hardcodeado en el código**, no se deriva del terminador. Por eso
una búsqueda ingenua de inmediatos no lo encuentra. El clasificador `0xa0530` devuelve 4/5 para las
recetas de 2 materiales y 2/3 según `mat3`. Cuatro funciones (p. ej. `0xaad58`) materializan el final
`0x10afa4`.

**Consecuencias para parchear (a decidir)**: agregar N recetas exige (a) `0x5e → 0x5e+N` en `0xa0454`,
(b) lugar para 8·N bytes, y (c) NO pisar el blob contiguo `0x10afac..0x10b018` (27 palabras pegadas al
terminador). Las 11 fusiones del port necesitan además decidir materiales (su invocación real es por
«Cambio de Máscara», que no ejecuta: ver §7.2).

### 7.2 El despacho de efectos es por tablas de datos keyed por CardID

En `libduel_eng.prx` `.data`: **4 tablas de entradas de 24 B `{u32 CardID; 5×u32 slots}`**, ordenadas
ascendentes y dispersas (solo cartas con handler): `0x100644` (764 entradas, ids 4078–6824),
`0x104dfc` (454), `0x1078a4` (175), `0x108924` (213) = **1606 entradas**. El despachador está en
`.text 0x48d74`: elige tabla con los bits 2–3 del byte 3 de la carta, lee la clave u16 en `carta+0` y
hace **búsqueda binaria** (stride 24: `sll 1; addu; sll 3`). 18 sitios hacen `jal 0x48d74`; el llamador
típico (`0x49138`) ejecuta `lw handler, entry+8; jalr`.

También hay tablas menores de 8 B `{u16 CardID; u16 0x0000; u32 handler_ptr}`: `0xfec98+`,
`0xffc28+` y la de `0x10b018..` (verificada palabra a palabra). Esta última lista cartas de
*búsqueda/revelado* con su puntero de handler: 4022 Time Wizard, 4054 Sangan, 4108 Mask of Darkness,
4177 Big Eye, 4324 Elegant Egotist, 4408 Monster Eye, 4426 Cyber-Stein, 4431 Thunder Dragon, 4434
Magician of Faith, 4512 Gale Dogra, 4580 Witch of the Black Forest, 4658 Magical Labyrinth, 4755,
4756, 4772, 4775, 4810, 4830, 4837 Polimerización, 4842 Monster Reborn, 4845, 4852 Ancient Telescope,
4857 Soul Release, 4867, 4872, 4885, 4911, … Varias comparten puntero (Time Wizard y Elegant Egotist
→ `0xacefc`; Thunder Dragon, Berfomet y 4872 → `0xad4a0`) ⇒ handler genérico compartido.
**Anomalía abierta**: aparecen CardIDs *libres* en TF1 (4867, 4872, 4885) con handler asignado, así que
la semántica exacta de esta tabla (efecto de la carta vs. comportamiento de búsqueda/revelado) queda
como **hipótesis a probar**, no como hecho. Layout medido de una entrada:
`v10b0b0` = `ea 12 | 00 00 | cc db 0a 00` ⇒ (4842 Monster Reborn, 0, ptr `0xadbcc`);
`v10b0c0` = `f4 12 | 00 00 | 30 dd 0a 00` ⇒ (4852 Ancient Telescope, 0, ptr `0xadd30`).

También hay arrays de punteros puros (349 en `0x10a578`, 180 en `0x100374`). **No existe ninguna tabla
de largo ≈2480** en los 4 binarios: el 2480 de E5/E6 era solo el clamp de UI.

### 7.3 Las 4 Mágicas del port NO tienen handler (medido)

`Cambio de Máscara 4704`, `Cambio de Máscara II 4721`, `Cambio de Forma 4726`, `Carga de Máscara 4730`:
**0 apariciones** en las tablas y **0 inmediatos reales** en el código de los 4 binarios. Todos los
hits crudos son branch-offsets, NIDs o ruido. Conclusión: no ejecutan nada porque el motor no las
conoce.

Controles con efecto implementado (para calibrar): `Toon Summoned Skull 4735` → 8 inmediatos reales
en `.text` (`0x1c368, 0x24200, 0x33ccc, 0xe56b0, 0xe5bdc, 0xe6478, 0xe69a8, 0xe6ee8`) en cadenas con
4734/4773, sin entrada en tablas; `Polimerización 4837` → 14 inmediatos + 3 entradas de datos
(`0xffc28`, tabla 1 `0x1010c4` con handlers `0xa10c4`/`0xa1020`, `0x10b0a8`).

### 7.4 Módulos y exports

`BOOT.BIN` (módulo `modehsys`) exporta **libehsys** (~1253 relocs de export); `libduel_eng` importa
1246 NIDs de ella y exporta ~144 como `libduel_eng` (que importan `mgr` y `draw`). **No hay un export
«get card effect» identificable**: el despacho es interno de `libduel_eng`.

### 7.5 Formas de tocar el motor, de barata a cara

1. **Barata (a probar primero)**: sobrescribir **una sola palabra** en una copia scratch — en
   `libduel_eng.prx` file offset `0x10b124` (campo puntero de la entrada 4852 `Ancient Telescope`, VMA
   `0x10b0c4`, hoy `0x000add30`, con su `R_MIPS_32` en `.rel.data`) escribir `0x000adbcc` (puntero de
   la entrada 4842 `Monster Reborn`). Coordenadas confirmadas palabra a palabra por el padre sobre la
   ISO vigente (`libduel_eng.prx` de `trabajo/e8/TF1-E8-G6.iso` es byte-idéntico al extraído en
   `trabajo/e1c/gm/`). Si en PPSSPP `Ancient Telescope` revive un monstruo, queda probado el mecanismo
   `{CardID → ptr}`; si no cambia nada, la tabla no es lo que parece y hay que re-planificar (§7.6).
   `BOOT.BIN` **sí difiere** del extraído de `e1c` (48 bytes, parches E5/E6) ⇒ usar siempre el de la ISO.

   **Ejecutado (EXP1, T7)**: en vez de `Ancient Telescope` (que el usuario no posee) se parcheó
   **`Rescate` (Salvage, CardID 5908)** — es la única Mágica de la tabla que el usuario ya tiene en el
   deck según el save `trabajo/e6/DATA0.hero` (tabla de propiedad en `0x155C`, 72 registros hoy; deck en
   `0x4824`: 42 cartas, 35 distintas). Parche: `libduel_eng.prx` file `0x10b634` (VMA `0x10b5d4`, entrada
   `Rescate` en `0x10b5d0`) `44 28 0b 00` → `cc db 0a 00` (de `0xb2844` al puntero de `Monster Reborn`
   `0xadbcc`). Solo cambian 3 bytes porque ambos punteros comparten el byte alto `0x00`. Artefacto:
   `trabajo/e7/TF1-E7-EXP1.iso`, sha256 `aa1376fa292ccb0ff4283cbdd16d20af05d82c49a8581c1e7360af7c8060b3ac`,
   1 solo sector distinto (12582) y 3 bytes respecto de G6 (`571d3f78…`) — verificado por el padre con
   comparación byte a byte de todo el archivo. Herramienta: `tools/e7_exp1.py`; protocolo en
   `trabajo/e7/T7-EXP1.md`. **Resultado del test del usuario: B** — «Rescate» cumplió su efecto
   original, sin rastro del efecto del donante. Conclusión acotada: la tabla de 8 B **no es la palanca**
   del efecto de activación. No refuta que el motor despache por datos: queda la tabla de 24 B con el
   despachador `0x48d74` y las comparaciones de CardID en código. Hipótesis viva: la tabla de 8 B es de
   *filtros/pickers* (todas sus cartas son de búsqueda/revelado/recuperación), y un cambio de filtro no
   se habría visto con la preparación del test. **Costo nuevo medido**: el frente de efectos necesita
   también espacio para código nuevo (`.text` termina en `0xfa218` y `.sceStub.text` arranca ahí mismo),
   el mismo problema de layout que la tabla de fusión.
2. **Recetas de fusión**: `0x5e → 0x5e+N` + 8·N bytes libres (probablemente reubicar la tabla y
   repuntar el finder, o usar el hueco tras la última tabla antes de `0x10b018`).
3. **Las 4 Mágicas**: insertar entradas `{CardID → handler}` — pero **no hay handler nativo** que haga
   «manda el HERO al cementerio y trae el Masked HERO del mismo atributo»; habría que escribir código
   ARM nuevo o componerlo con handlers existentes (la vía más cara).
4. **Tabla de 24 B (efectos completos)**: exige desplazar `.data` y reparar todos los `lui/addiu`
   posteriores ⇒ fase grande.

### 7.6 Desconocido

Semántica de los otros 4 slots de la entrada de 24 B y del selector «byte3 bits 2–3» (hipótesis: clase
de carta); contenido y dueño del blob `0x10afac..0x10b018`; si las 11 fusiones del port pueden usar
la tabla de 8 B de `0x10b018` en vez de la de fusión.

---

## 8. Estado del alcance A y bloqueo de espacio

Alcance **decidido por el usuario**: A (recetas de fusión), con materiales «base E-HERO del mismo
atributo + «Cambio de Máscara» (4704)» y `Contraste Chaos` = 2 monstruos «HÉROE Enmascarado». Specs
detalladas en `odd/tasks/e7-recetas-fusion.md` (S1-S7) y plan de inserción en `trabajo/e7/T1-PLAN.md`.

### 8.1 El bloqueo medido: no hay dónde poner las recetas nuevas

Agregar `N` recetas exige `8·N` bytes **contiguos inmediatamente después del terminador** (el finder
`0xa0454` recorre `base..fin` con un `sltiu` de largo fijo). Medido por T1:

- **Los 108 B siguientes al terminador (`0x10afac..0x10b018`) NO están libres**: son una tabla viva
de 27 palabras (26 no nulas y un 0 en `0x10b014`) con **11 referencias absolutas** en `.text`
  (`0xab63c, 0xab6c0, 0xab984, 0xac0ac, 0xac178, 0xac470, 0xac610, 0xac738, 0xac778, 0xacb10,
  0xacbdc`). Tampoco hay ninguna región muerta ≥ 448 B en `.data`: el mayor hueco sin relocs es de
  **328 B** (`0x10a430..0x10a578`) y las tablas de punteros de `0x10a578` (349 relocs) y `0x100374`
  (180 relocs) están vivas.
- **Pisar el arranque del bss es inseguro**: el primer 1,2 KB de bss (`0x10c080..0x10c530`) tiene 546
  referencias (12 absolutas medidas por el padre; incluye un array de índice dinámico en `0x10c088`).
- **El módulo tiene UN solo PT_LOAD** (`p_offset 0x60`, `p_filesz 0x10c080`, `p_memsz 0x112910`,
  flags 7) y **los 22 `.prx` del juego y el `BOOT.BIN` también tienen `e_phnum == 1`**.

### 8.2 Estrategias con su costo medido

| # | Estrategia | Parches | Riesgo |
| --- | --- | --- | --- |
| S-A | Segundo PT_LOAD al final del archivo, tabla de 1200 B en `VMA 0x112910` (encima del `memsz` actual) + `e_phoff` reubicado a `0x167150` | **6 palabras** | El cargador del juego (`libehsys`) podría no soportar 2 segmentos: ninguno de los 23 ejecutables del juego los usa. Se resuelve con una ronda de PPSSPP. |
| S-B | Crecer el `.data` existente: insertar 1200 B en el file `0x10c0e0`, desplazar todo el bss y reparchar sus referencias | **11 428** (`11 427` LO16 + 1 HI16) + mover `.shstrtab` y la tabla de secciones | Determinista pero enorme y difícil de revisar. |
| S-11 | Recortar a 11 recetas (10 + 1 par para Chaos) y meterlas en un espacio libre | — | **También bloqueado**: el hueco de 108 B está vivo y ningún hueco muerto alcanza los 840 B que pediría reubicar la tabla de 105 registros. Además viola S2. |

**Estado**: T2/T3 bloqueadas a la espera del resultado de la sonda EXP2 (o de la elección de S-B).
Nada del juego original fue modificado; los artefactos viven en `trabajo/e7/`.

### 8.3 Sonda EXP2 (T9): ¿el cargador soporta el layout de S-A?

Un round de PPSSPP decide entre S-A y S-B. La sonda es **inocua**: cambia solo el `e_phoff` y el
`e_phnum` del módulo y agrega 1200 B que **ningún código referencia**; ninguna tabla, contador,
inmediato ni finder fue tocado. Artefacto `trabajo/e7/TF1-E7-EXP2.iso`, sha256
`7ab83647b8ea0108f28c99b0292b8146814e3351f14fd1b9693c0353420dd9fb`, mismo tamaño que G6
(798.787.584 B). Cambios medidos: `libduel_eng.prx` pasa de 1.470.794 a 1.472.064 B (dentro de los
1.472.512 B ya asignados a su extent, así que la ISO no crece y el módulo siguiente sigue en LBA
12767); tabla de PH de 2 entradas en file `0x167150` (la 1ª es copia byte a byte de la original, la 2ª
mapea 1200 B en `VMA 0x112910`, justo por encima del `memsz` de la 1ª); payload con marcador
`E7-EXP2-PTLOAD!` en file `0x167190`; 3 sectores distintos (`38` = registro del directorio con el nuevo
largo, `12048`, `12766`). Verificado por el padre re-parseando el ELF desde la ISO: `e_phnum=2`, sin
solapamiento de segmentos, tabla de secciones byte-idéntica, solo `0x1c,0x1d,0x1e,0x2c` distintos en el
prefijo común. Herramienta `tools/e7_exp2.py`; detalle en `trabajo/e7/T9-EXP2.md`.

**Resultado del test del usuario (T10): A.** Duelo completo usando **varias fusiones nativas de la
receta de Jaden** y partida guardada, sin ninguna anomalía. Conclusión: el cargador acepta el `e_phoff`
reubicado y un segundo `PT_LOAD` ⇒ **S-A es viable** y T2/T3 quedan desbloqueadas. Límite honesto del
resultado: prueba que el layout **no rompe** la carga; que el segundo segmento se **use** de verdad se
confirma con la ISO de producto (si las 11 recetas nuevas funcionan, se usa; si las 94 nativas se
rompen, se ignora).

**Nota de método**: el brief del padre declaró «libre» la región de archivo `0x10c0e0..0x159b48`; es
**falso** (ahí están `.shstrtab`, la tabla de secciones y `.rel.text`). El worker se negó a escribir y
pidió la corrección: se pasó a un append al final del archivo. Sin esa negativa, la sonda habría
corrompido la tabla de secciones y un fallo se habría atribuido a la pregunta equivocada.

### 8.4 Artefacto de producto (T2/T3) y verificación independiente (T4) — 2026-11

| hecho | valor |
| --- | --- |
| ISO de producto | `trabajo/e7/TF1-E7-F1.iso`, **798.787.584 B** (mismo tamaño que G6), sha256 `135c8881c0038995a3055470311e8a64ebae2c232e7d8eff9336da4cd36362d7` |
| módulo parcheado | `trabajo/e7/libduel_eng_f1.prx`, **1.472.064 B** (`0x167640`), sha256 `5dfb9b7e11f4d1d5753bc2c2cb65188d97148fbfe0a1a95c45714537a0a8e7e1` |
| herramienta | `tools/e7_fusion.py` (`patch`/`verify`/`iso`/`dump`; se niega a escribir si falla una invariante) + informe `trabajo/e7/T2-T3.md` |
| tabla nueva | 149 registros + terminador = **1200 B exactos** (94 nativos copiados byte a byte + 10 recetas Masked HERO + 45 pares de Contraste Chaos) en el 2º `PT_LOAD` (`VMA 0x112910`, file `0x167190`) |
| parches de código | 6 palabras: base del finder `0x10acb4 → 0x112910`, `sltiu 0x5e → 0x95` (149) y los 4 sitios de fin `0x10afa4 → 0x112db8`; más `e_phoff=0x167150` y `e_phnum=2` |
| huella | **15 bytes** distintos en `[0, 0x16714a)` + 1270 bytes agregados; tabla de secciones intacta; **6 sectores** distintos en la ISO (`38, 12048, 12368, 12389, 12390, 12766`), ninguno fuera del módulo y su registro de directorio; `libduel_mgr.prx` (LBA 12767+) intacto |

**T4 — verificación independiente (PASS en S2, S3, S4 y S6)**: un verificador read-only re-derivó todo
desde los bytes **sin usar la herramienta del escritor**. Reproducido: `e_phnum=2` con PH2 =
`(1, 0x167190, 0x112910, 0x112910, 1200, 1200, 7, 16)` y rangos de carga disjuntos; los 15 bytes
cambiados son exactamente los declarados y nada más; la tabla de secciones y las 25 entradas son
byte-idénticas; los registros 0..93 son byte-idénticos a los nativos; las 10 recetas y los 45 pares
coinciden con S2 sin duplicados; 149 registros y terminador `(10,0,0,0)`; **las 94 nativas resuelven en
el mismo índice** que en la tabla original (búsqueda lineal por `result`) y las 11 nuevas a su receta
(4696 → primer par `(4661,4665)`); en la ISO solo difieren los sectores declarados.

**Riesgo residual que decide T5 (in-game, una sola varilla)**: (a) que el motor acepte una **Mágica**
(`Cambio de Máscara` 4704) como material de fusión — si la pantalla de fusión no deja elegirla, aplica
S7 y se vuelve al usuario sin tocar el mapa; (b) la semántica en runtime del helper de `libehsys`
(NID `0xed7a3401`, stub VMA `0xfbe00`) que recibe el puntero de fin de tabla. El soporte del cargador
para dos `PT_LOAD` ya está probado in-game (EXP2/T10, §8.3).

**Cobertura offline declarada**: el subcomando `verify` de `tools/e7_fusion.py`. **No** se agrega un test
con framework: los artefactos binarios viven en `trabajo/` (gitignored: ISO de 800 MB + módulo), así que
un test commiteado que dependa de ellos no correría en un clon limpio.

### 8.5 Ronda F2 (L12: mapa ampliado) — 2026-11

**Motivo**: en el test in-game de F1 el usuario vio que **Dian** no aparecía entre las opciones aunque
tenía HÉROE de TIERRA. Causa medida: **Bladedge (6477) no era material de ninguna de las 55 recetas**
(S2 fijaba **una base por atributo**: TIERRA ⇒ Clayman 6312). Decisión del usuario (L12): ampliar sólo a
**las bases que su deck ya posee**.

| hecho | valor |
| --- | --- |
| mapa | **151 registros** = 94 nativos + **12** de base + **45** de Contraste Chaos; Dian acepta **Clayman 6312 + Bladedge 6477 + Wildheart 6478** (TIERRA es el único atributo con más de una base poseída) |
| módulo | `trabajo/e7/libduel_eng_f2.prx`, **1.472.080 B** (`0x167650`), sha256 `38c44953b4afac5989e931d22275fcadb4bed453f3743d844492ff080a7ad59a` |
| ISO | `trabajo/e7/TF1-E7-F2.iso`, **798.787.584 B** (mismo tamaño que G6), sha256 `e3d9ea359285f980a7e08236fc81a1c967335936028a853df074ef9731742fbf` |
| geometría | igual que F1, con la carga útil en **1216 B** (`0x4c0`): 2º `PT_LOAD` en `VMA 0x112910`, finder con largo **151** (`sltiu 0x97` en file `0xa04dc`) y fin en `VMA 0x112dc8` (los 4 sitios) |
| huella | los mismos **15 bytes** distintos dentro de `[0,0x16714a)` + 1286 bytes agregados; **6 sectores** distintos en la ISO; G6 y los artefactos de F1 byte-idénticos (pins re-verificados) |
| herramienta | `tools/e7_fusion.py` ahora **deriva del mapa** contadores, tamaño de carga útil, inmediato del largo y puntero de fin ⇒ el próximo cambio de mapa es una edición de datos |
| verificación (T11) | verificador read-only **independiente**: **PASS en S2, S3, S4 y S6**; 151 registros sin duplicados; triplete de Dian exacto; 45 pares exactos; las 94 nativas resuelven en el **mismo índice**; `4673 → (4673,6312,4704,0)` y `4696 → (4696,4661,4665,0)`; **todos** los bytes que difieren en la ISO quedan explicados por el plan |

**Nota de etiqueta**: el informe `trabajo/e7/T10-F2.md` §2 llama «PH1» al segundo segmento nuevo; el
nombre correcto es **PH2** (PH1 en `0x167150` es la copia byte a byte del header original). Los valores
medidos son correctos, sólo la etiqueta difiere.

**Pendiente (una sola ronda del usuario, T5+T12)**: (a) Dian con **Bladedge** o **Wildheart** + «Cambio
de Máscara»; (b) una fusión **nativa** (Avian + Burstinatrix → Flame Wingman) para cerrar S4 in-game.
**Decisión abierta**: incluir los 7 HÉROE de Fusión poseídos (+10 registros; entran en la holgura) —
**resuelta en L14** (ronda F3, §8.6).

### 8.6 Ronda F3 (L14: bases HÉROE de Fusión) — 2026-11

**Motivo**: la carta real «Cambio de Máscara» toma **cualquier** monstruo HÉROE, así que las Fusiones
HÉROE que el deck ya posee son bases válidas. El usuario aprobó incluirlas (L14), con la **misma regla
de atributo** de L12.

**Los atributos se midieron, no se recordaron** — y la medición corrigió el supuesto del padre:
**Flame Wingman (6344) es VIENTO**, no FUEGO, y Tempest (6487) también. Fuentes: `trabajo/e2/eng`
(contenedor prístino, campo `attr`) para las bases y `datos/cartas_18.tsv` para los resultados.

| Fusión poseída | CardID | Atributo | Enmascarados que gana |
| --- | --- | --- | --- |
| Flame Wingman | 6344 | VIENTO | Blast 4671, Divine Wind 4681 |
| Tempest | 6487 | VIENTO | Blast 4671, Divine Wind 4681 |
| Rampart Blaster | 6486 | TIERRA | Dian 4673 |
| Mudballman | 6529 | TIERRA | Dian 4673 |
| Wildedge | 6488 | TIERRA | Dian 4673 |
| Thunder Giant | 6345 | LUZ | Koga 4686 |
| Steam Healer | 6535 | AGUA | Ácido 4661, Vapor 4689 |

⇒ **+10 registros** (Dian pasa a 6 bases: Clayman, Bladedge, Wildheart, Rampart Blaster, Mudballman,
Wildedge). El deck no posee Fusiones HÉROE de OSCURIDAD ni de FUEGO ⇒ Anki, Dark Law, Goka y Atómico no
ganan bases. **Mapa: 94 + 12 + 10 + 45 = 161 registros.**

| hecho | valor |
| --- | --- |
| mapa | **161 registros** (94 nativos + 22 de base + 45 pares de Contraste Chaos) |
| módulo | `trabajo/e7/libduel_eng_f3.prx`, **1.472.160 B** (`0x1676a0`), sha256 `9b6c1fceb6b13cc7ba99c308a47a636c5967a2651510127508dd22d682dfac15` |
| ISO | `trabajo/e7/TF1-E7-F3.iso`, **798.787.584 B** (mismo tamaño que G6), sha256 `85ca0409ea1b1fb4a4ba44b60427bac18d9b29119846a1e7d54e0f3473f77974` |
| geometría | igual que F1/F2, con la carga útil en **1296 B** (`0x510`): 2º `PT_LOAD` en `VMA 0x112910`, finder con largo **161** (`sltiu 0xa1` en file `0xa04dc`) y fin en `VMA 0x112e18` (los 4 sitios) |
| huella | los mismos **15 bytes** distintos dentro de `[0,0x16714a)` + 1366 bytes agregados; **6 sectores** distintos en la ISO; G6, F1 y F2 byte-idénticos (pins re-verificados) |
| herramienta | la ampliación fue **edición de datos**: tupla nueva `FUSION_HERO_BASES` + contadores y punteros **derivados** (largo del finder, tamaño de carga útil, fin de tabla) y el pin de producto `DIAN_BASES` en el `verify`. Corregido el rótulo del `dump` (contaba entradas de mapa, no registros) |
| auto-verificación | subcomandos `verify` e `iso`: **OK** — 6 palabras + `e_phoff`/`e_phnum` + el rango agregado; tabla de secciones intacta; 2 segmentos sin solape; la tabla de 161 resuelve; en la ISO difieren exactamente los **6 sectores** esperados y el resto de los 798.787.584 B es byte-idéntico |
| verificación (T14) | verificador read-only **independiente** (sin usar la herramienta del escritor, `tfcard.py` sólo como lector de contraste): **PASS en S2, S3, S4 y S6** + **igualdad de atributo 10/10**. Medido: PH2 exacto y rangos disjuntos; tabla de secciones byte-idéntica; **15 bytes** distintos exactamente los declarados; 161 registros únicos con los primeros 94 byte-idénticos, los 22 de base exactos y los 45 pares exactos; las 94 nativas resuelven en el **mismo índice**; en la ISO el módulo es byte-idéntico y difieren exactamente los **6 sectores** con `libduel_mgr.prx` intacto; Dian con sus 6 bases en orden. La batería quedó como herramienta reproducible: **`tools/e7_f3_probe.py`** (manual: depende de `trabajo/`) |

**Pendiente (una sola ronda in-game, T5/T12/T15)**: sobre `trabajo/e7/TF1-E7-F3.iso`, (a) Dian con
cualquiera de sus 6 bases de TIERRA + «Cambio de Máscara»; (b) una fusión **nativa** (Flame Wingman) que
siga resolviendo. — **Contestada en §8.7**: el intento in-game del usuario falló con **Wildheart** y
funcionó con **Clayman**, y la causa medida es el límite del motor, no el mapa.

### 8.7 Ronda F4 (reconciliación: una receta alcanzable por resultado) — 2026-11

**Motivo**: el usuario probó F3 en PPSSPP — «No funcionó, pude hacer una fusion normal pero para traer a
Dian con filo salvaje y cambio de mascara no funciono» — con «Cambio de Máscara» **en la mano** y la base
primero en la mano y después invocada al campo. La medición estática explicó el fallo por completo.

**El límite del motor (medido por dos analistas read-only independientes)**: la tabla de recetas se lee
**solo** por el finder `.text 0xa0454`, que devuelve el **primer** registro de cada `result`; sus únicos
dos llamadores son `classifier` (`0xa0530`, jal en `0xa055c`) y `get_material(result, slot)` (`0xa0590`,
jal en `0xa05e4`), ambos indexados por resultado; los **94 resultados nativos son todos distintos** ⇒ el
motor nunca necesitó elegir entre dos recetas del mismo resultado, y **ningún camino lee un registro
posterior al primero**. Consecuencia sobre F3: **56 de sus 161 registros eran inertes** (Bladedge idx 99,
Wildheart idx 100, los tres HÉROE de Fusión de TIERRA y 44 de los 45 pares de Chaos).

**Pools de materiales (medidos)**: struct por jugador `0x10e4ec + jugador·4012`; **mano** en `+288+slot·4`
(count `+12`, código de ubicación 11) **primero**, después las **5 zonas de monstruo** `+48+zona·20`
(0..4); el resolutor es `0xa10c4`/`0xa0d2c` con el localizador `0xa0c60`. La **oferta del menú 12**
(`0xb4058`) mira **solo zonas de monstruo**, la del menú 14 (`0xb440c`) solo el cementerio. Una **Mágica**
—como «Cambio de Máscara» 4704— **solo puede venir de la mano**. Esto explica por qué la pantalla de
fusión no listaba a Dian ni siquiera con el registro alcanzable, y por qué la vía que sí funciona es la
**activación/resolución** (así se invocó 4690 en F1 y Dian en F3).

**Reconciliación F4 (decisión del usuario)**: **una receta alcanzable por resultado**, 94 + 10 + 1 =
**105 registros**; Dian con **Clayman** (lo confirmado in-game) y Contraste Chaos con **Cuervo del
Crepúsculo 4697 + Fuente 4701**. Revertidas la ampliación de L12/L14 (bases extra del mismo atributo) y
los 45 pares.

| hecho | valor |
| --- | --- |
| mapa | **105 registros** = 94 nativos + 10 de base + 1 de Chaos; **0 resultados con más de un registro** |
| módulo | `trabajo/e7/libduel_eng_f4.prx`, **1.471.712 B** (`0x1674e0`), sha256 `c2873ad9680e66d07d2fbda51b858d0affc783db868e4810e11e661a330aa650` |
| ISO | `trabajo/e7/TF1-E7-F4.iso`, **798.787.584 B**, sha256 `4323b0aa2ded8753230159d6a5517bf1a2f8f6747fd145ade1f70f6e37462b96` |
| geometría | 2º `PT_LOAD` en `VMA 0x112910`, carga útil **848 B** (`0x350`), finder con largo **105** (`sltiu 0x69`), fin de tabla `VMA 0x112c58`; holgura **800 B** |
| huella | **15 bytes** distintos en `[0,0x16714a)` + 918 agregados; **6 sectores** (`38, 12048, 12368, 12389, 12390, 12766`); G6, F1, F2 y F3 byte-idénticos |
| herramienta | la reconciliación fue **edición de datos** (una tupla borrada, `CHAOS_PAIR` explícito) + un `verify` nuevo que exige **una receta por resultado** |
| verificación (T17) | **independiente: PASS en las 6 afirmaciones** — tabla y orden de los 11 nuevos exactos; 105 resultados con **count 1 y 0 tapados**; PH1 `(1,0x167190,0x112910,0x112910,848,848,7,16)` y las 94 nativas en el **mismo índice**; ISO con exactamente los 6 sectores y `libduel_mgr.prx` intacto; **10/10** atributos base↔resultado y el par de Chaos con `kind 1` (baraja principal); pins de F1/F2/F3 intactos. Sonda `tools/e7_first_match_probe.py` (manual) en verde |

**El sustituto: la vía práctica para «cualquier HÉROE» (L17)**. «Rey del Pantano» **6044** está en la
lista **hardcodeada** de sustitutos de material del motor — `BOOT.BIN` VMA `0x4a4d8` `is_substitute`,
lista `{6258, 6257, 6256, 6044, 4648, 4275, 4264, 4115}` — y la rama del sustituto (`libduel_eng`
`0xa0754`/`0xa091c`) llena el primer slot real sin cubrir, **incluida la base** de nuestros registros.
Permite **un** sustituto por fusión (bandera en `0x10D08C`, `xori v1,v0,1` en `0xa0dbc`) y su lista de
exclusión (`BOOT.BIN 0x4a54c`) **no** contiene ningún Enmascarado. Resultado práctico:
`Polimerización + Rey del Pantano + «Cambio de Máscara»` (los tres en la mano) invoca **cualquiera de los
10**; y `Rey del Pantano + Fuente + Polimerización` invoca Contraste Chaos. Es **ciego al atributo**
(aplana la regla de S2/L12) y **King solo no alcanza** (no puede llenar dos slots). No hay bit de
`CARD_Prop`/`CARD_Genre` que marque al sustituto: es solo la lista de ids en código.

**Pendiente (una sola ronda in-game, T18)**: sobre `trabajo/e7/TF1-E7-F4.iso`: (a) Dian con **Clayman** +
«Cambio de Máscara» (re-confirmación de F4); (b) **Rey del Pantano + «Cambio de Máscara»** ⇒ cualquier
Enmascarado; (c) Contraste Chaos con **Cuervo + Fuente**.

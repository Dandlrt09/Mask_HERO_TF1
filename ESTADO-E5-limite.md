# ESTADO — E5: estrategia C (subir el límite de la base de cartas)

> Experimento para resolver el bloqueo T9 de E1-test: el validador de deck marca
> «Forbidden Card» toda carta cuyo registro vive en un índice interno **no canónico**
> (probado con planD vs planF). C busca **subir el límite por código** para no perder
> ninguna carta real, en vez de reciclar las 23 ranuras prohibidas (estrategia A).
>
> Estado: **en investigación**. Hallazgo mayor de esta sesión: `PSP_GAME/SYSDIR/BOOT.BIN`
> es un **ELF MIPS sin cifrar** con el motor completo (`mod ehsys`), así que el frente ARM
> ya no depende de desencriptar `EBOOT.BIN` (que es el mismo módulo cifrado, `~PSP`).

Objetivo (algorítmico): que una carta nueva en un índice interno **> 2479** pase el
validador de deck del juego (sin ícono rojo, se pueda sacar al baúl y volver a poner), con
una copia parcheada del ISO y sin tocar el original.

---

## Specs

- **S1 — Ir primero por C.** (L18 de E1-test, textual): «La C es la mas complicada? me
  gustaria ir por ella y sino pues reemplazar aunque pensaba en reemplazar quiza prohibidas
  sabiendo que no son usadas por los npc y luego desprohibirlas. Por ahora vamos a cerrar
  sesión y guardar. Mañana seguimos» → orden: **primero C**.
- **S2 — Fallback A.** Si C no es viable, reemplazar las **23 ranuras prohibidas** (CardID de
  la lista de prohibidas) y después desprohibirlas. Ya verificado que los recipes las
  referencian (`deck/all_s.ehp` 858 refs, `duelsys/recipe_npc.ehp` 27): el jugador no pierde
  nada, pero algunos mazos de NPC mostrarían las cartas nuevas.
- **S3 — No se pierde ninguna carta.** Motivo explícito de elegir C sobre A/B.
- **S4 — No tocar el original.** Se trabaja sobre copias en `trabajo/` (autorización de E1-test).
- **S5 — Canaria visible.** Lección metodológica de E3: cada copia de prueba lleva una
  canaria distinguible (p. ej. GAGAGIGO ATK 1850 → 4850) para separar «el parche no se cargó»
  de «el parche no tiene efecto».
- **S6 — Continuidad de esta sesión** (usuario, textual): «Sigamos con el proyecto, empieza
  con la C».

## Hechos medidos (evidencia, no suposiciones)

| Hecho | Evidencia |
|---|---|
| `PSP_GAME/SYSDIR/BOOT.BIN` es **ELF 32-bit LSB MIPS** (`7f 45 4c 46`), sin cifrar, contiene `modehsys`/`libehsys` y la tabla de prohibidas en claro | `head -c 16`, `strings`, escaneo de CardID |
| `PSP_GAME/SYSDIR/EBOOT.BIN` es el **mismo módulo cifrado** (`~PSP`, 1104032 B vs 1103694 B = +0x152 de cabecera/padding) | `head -c 16` de ambos |
| Los `gmodule/*.prx` son ELF sin cifrar (22 módulos); `libehsys` **no** es un archivo del ISO → vive dentro del `EBOOT`/`BOOT` | `find`/`ls` del ISO completo (714 archivos) |
| La tabla real de prohibidas/limitadas está en **`liblimitlist.prx` `.data` file 0x91cc** (vaddr 0x916c): 93 entradas de 4 B = (u16 CardID, u16 nivel); **0=Prohibida (28), 1=Limitada (53), 2=Semi (12)** | lectura de la tabla + nombres por CardID |
| Hay una **copia** de esa tabla en `BOOT.BIN` (`.data` vaddr 0x6f080, file 0x6f0e0) | escaneo de clústeres de CardID conocidos |
| La pantalla «Lista de Cartas Prohibidas/Limitadas» y `limitlist.ehp` son UI; `liblimitlist.prx` es el módulo que **carga** la lista: `li s0,4007` → bucle `jal 0x6eec(card_id, 3)` hasta 6957 (nivel 3 = sin límite), y si el preset es 1 recorre las 93 entradas del `.data` (`sltiu v0,s0,186`, `s1 += 4`) | desarme vaddr 0x5428..0x5514 |
| `jal 0x6eec` / `jal 0x6edc` caen en `.sceStub.text` de `liblimitlist.prx` → son **imports de `libehsys`** (set/get del límite por carta), no código propio | desarme vaddr 0x6e80..0x6f80 |
| La única constante **2480** en el `.text` de los módulos de deck/álbum está en `libcardalbum.prx` vaddr 0x3e6c (`slti v1,s1,2480`), dentro del bucle que arma la lista de **cartas poseídas** desde la pila (array de u16, frame de 6000 B) | escaneo de inmediatos + desarme 0x3d80..0x3f60 |
| `libdeck.prx` **no importa** `liblimitlist` (sí `libehsys`, `librecipe_viewer`, `libdeck_tutorial`); los que importan `liblimitlist` son `liblabo`, `libstory`, `libtitle` | strings de nombres de módulo por PRX |
| El texto del mensaje vive en `deck/all_<lng>.ehp` (`strTbl.bin`): «This is a Forbidden Card, so it cannot be added to the Deck.» y «Since "$CA%s$C0" is a Forbidden Card, it cannot be added to your Deck.» (UTF-16LE, file +0x262214 y +0x263318 en `all_s.ehp`) | búsqueda de textos en el ISO |
| En el `.text` de `BOOT.BIN` **no hay** el inmediato 2480 (ni 2479/2481/2960) | escaneo de inmediatos 0x60..0x689ac |
| `sameCardTbl.dat` (208 B) es un archivo interno de `deck/all_<lng>.ehp` (no está suelto en el ISO) | listado del contenedor + búsqueda en el ISO |
| Herramienta de análisis disponible: `mipsel-linux-gnu-objdump` obtenido sin root con `apt-get download binutils-mipsel-linux-gnu` + `dpkg-deb -x` en `/tmp/mipsbin`, `LD_LIBRARY_PATH=/tmp/mipsbin/root/usr/lib/x86_64-linux-gnu` | instalación local en `/tmp` (fuera del repo) |

## Pregunta abierta (lo que falta)

**¿Dónde decide el motor que un índice interno ≥ 2480 es «Forbidden»?** Hipótesis en pie:

1. **H1 — array por índice con default 0.** `libehsys` mantiene un array por carta; el
   default es 3 (sin límite) para CardID 4007..6957, pero si el juego lo indexa o lo
   **valida por índice interno** y el índice 2480 queda fuera de la zona inicializada, lee 0
   = Prohibida. Explica planD (índice 2480, contenido idéntico a una carta legal → igual
   prohibida) y planF (índice canónico 447 → legal).
2. **H2 — posesión.** La lista de cartas poseídas se arma con tope 2480
   (`libcardalbum.prx` 0x3e6c): una carta en índice 2480 no está en la lista y el editor la
   trata como no utilizable (mensaje «Forbidden»).
3. **H3 — otra tabla por índice** en el motor (p. ej. la copia de la lista de prohibidas de
   `BOOT.BIN` expandida por índice) desalineada por el append.

## Tareas

| ID | Tarea | Estado |
|---|---|---|
| T1 | Documentar E5 y los hechos medidos | hecho — este documento |
| T2 | Relevar los módulos: extraer `gmodule/*.prx` + `BOOT.BIN`/`EBOOT.BIN` y montar el desarmador MIPS | hecho — `/tmp/mipsbin` + `trabajo/e1c/` |
| T3 | Ubicar la tabla de prohibidas real y su consumo en `liblimitlist.prx` | hecho — 93 entradas + bucle 0x5428..0x5514 |
| T4 | Trazar en `BOOT.BIN` qué camino produce «Forbidden» para el índice 2480 (H1/H2/H3) | **hecho (L6)** — veredicto = `get_limit` (BOOT 0x3a43c); `libehsys` lo provee **sólo** `BOOT.BIN`; el patch propuesto por el relevamiento tenía 2 defectos (L7) |
| T5 | Diseñar el parche mínimo según T4 (subir el tope/el default, o arreglar el lookup) | **hecho (L8)** — sonda reloc-safe de 2 palabras dentro del cuerpo de `get_limit` (file 0x3a4b4 / 0x3a4b8) |
| T6 | Construir la copia de prueba: cardinfo + parche del motor + canaria | **hecho** — `tools/e5_patch_iso.py` → `trabajo/e5/TF1-E5-C1.iso` |
| T7 | Verificación sin emulador (relectura del ISO + parche aplicado) | **hecho (L10)** — relectura independiente con `tools/iso9660.py` |
| T8 | Prueba en PPSSPP (usuario): la carta se agrega al deck sin ícono rojo | **bloqueado — espera al usuario**: probar `trabajo/e5/TF1-E5-C2.iso` (parche de producto) y reportar: (1) la carta nueva entra al deck sin ícono rojo, (2) las cartas propias del jugador siguen usables como antes, (3) una partida con la carta nueva en el deck |
| T9 | Si C funciona: pipeline de las 18 cartas. Si no: decidir A | **pendiente** — con el resultado de T8: cerrar C (fix de producto verificado) o pasar a A (23 ranuras prohibidas) |

## Log

- **L1** (usuario, textual): «Sigamos con el proyecto, empieza con la C» → arranca E5 con la
  estrategia C del cierre de E1-test (L18).
- **L2** (evidencia): `BOOT.BIN` (el «otro» boot del ISO) es un ELF sin cifrar con el motor
  `modehsys`/`libehsys`. Es el hallazgo que hace viable C: el frente ARM deja de depender de
  desencriptar el `~PSP`.
- **L3** (evidencia): la tabla de prohibidas/limitadas real está en `liblimitlist.prx` `.data`
  0x91cc (93 entradas (CardID, nivel): 28/53/12) y tiene copia en `BOOT.BIN` `.data`
  0x6f080.
- **L4** (evidencia): `liblimitlist.prx` inicializa el límite con `jal 0x6eec(card_id, 3)`
  para 4007..6957 y luego aplica las 93 entradas; `0x6edc`/`0x6eec` son **stubs de imports
  de `libehsys`** ⇒ la estructura de límites es del motor (dentro de `BOOT.BIN`), no del
  módulo de UI.
- **L5** (evidencia): en el `.text` de `BOOT.BIN` no aparece el inmediato 2480 ⇒ la decisión
  no es un `slti ...,2480` en el motor (descarta la variante trivial de H1; quedan el
  lookup por índice y H2/H3).

## Log — continuación (spike E5, estrategia C)

- **L6 (relevamiento del motor, subagente read-only + verificación propia).** El veredicto «Forbidden» sale de `get_limit` (**BOOT.BIN vaddr 0x3a43c**), que lee el byte 2 (nivel) del registro de 4 B por índice en `ctx+0x155C` (ctx = 0x261418, BSS del módulo `modehsys`); `ctx+idx*4+0x155C` se alcanza con `idx = CARD_IntID[CardID-4000]` (función 0x4743c, puntero en 0xE9718+0x38). Cadena del editor: `libdeck.prx` 0x6a48 → stub 0x1ca0c → **BOOT 0x478fc** (wrapper) [mapeo de stubs por NID: del relevamiento, no verificado palabra por palabra] → si el flag 0x26130C ≠ 0 usa el scan de tabla 0x3a4e4, si no `get_limit` 0x3a43c (wrapper y `get_limit` verificados por mí en desensamblado). Los mensajes 133/136 viven en 0x6a98..0x6b40. **Hecho clave:** `libehsys` lo exporta **sólo** `BOOT.BIN` (ningún `gmodule/*.prx` lo provee), así que parchear BOOT/EBOOT alcanza a todos los PRX.
- **L7 (dos defectos en el patch del relevamiento).** (a) `addiu t1,v0,0x155c` estaba en el *delay slot* del `jal get_ctx`, o sea leía `v0` antes de que la llamada lo devolviera: el fill quedaba apuntando a basura. (b) La palabra VMA 0x3a47c tiene una entrada `R_MIPS_26` en `.rel.text` (14 752 entradas, offsets absolutos: el loader les suma la base en runtime), y el patch escribía ahí un `addiu`: la reloc lo habría corrompido. Regla operativa nueva: **toda palabra dentro de un offset con reloc debe ser un `j`/`jal` con target módulo-relativo correcto**.
- **L8 (sonda que se implementó en su lugar).** En vez de reescribir el bucle de inicialización, se parchean dos palabras **sin reloc** dentro del cuerpo de `get_limit`: VMA 0x3a454 `lbu v0,2(v0)` (02 00 42 90) → `li v0,3` (03 00 02 24) y VMA 0x3a458 `andi v0,v0,3` (03 00 42 30) → `nop` (00 00 00 00). Resultado: `get_limit` devuelve **3 siempre** (desactiva transitoriamente toda la lista de prohibidas). Es deliberadamente una **sonda diagnóstica**, no el parche final: separa «el veredicto es el nivel» de «el veredicto es otra cosa (posesión/otra tabla)». Canaria visible: cartas que hoy están prohibidas (p. ej. Raigeki 4343, Dark Hole 4342, Time Seal 4984) pasan a poder entrar al deck.
- **L9 (por qué sonda y no el fix «correcto» todavía).** Hay una contradicción abierta: los dos inicializadores de nivel son **por CardID** (`set_limit(c,3)` para c=4007..6957, en BOOT 0x3a468 y en `liblimitlist.prx` 0x5428) y `CARD_IntID[4453] = CARD_IntID[4661] = 2480` en el artefacto, así que el índice 2480 *debería* quedar en 3 y la carta ser legal — pero en planB/planD/planF el resultado observado fue «Forbidden» (L12/L13/L15/L17). O sea: el modelo estático no explica el veredicto observado, y el dato que falta sólo lo da el runtime. Además el contenedor **sí** está crecido de forma consistente (Prop/Pass/Genre/Indx/Sort = 2481 registros, IntID = 2960), así que no hay un conteo rancio que explique el 0. Resultado del ISO: cualquiera de los dos desenlaces es informativo (si la carta pasa → el veredicto es el nivel y C es viable con un fix de nivel; si sigue prohibida → el veredicto no es el nivel y corresponde A, ya probado por planF).
- **L10 (ISO de prueba C1, verificado offline).** `tools/e5_patch_iso.py` → **`trabajo/e5/TF1-E5-C1.iso`** (798 787 584 B, igual al base): `PSP_GAME/USRDIR/duelsys/cardinfo_spa.ehp` ← `trabajo/e1spa/cardinfo_spa_E1.ehp` (carta nueva en índice 2480, CardID 4661, ATK 4900/DEF 1200, `E1 TEST CARD`; `CARD_IntID[4453]=2480` hace visible la carta usando la posesión real del jugador), más `BOOT.BIN` y `EBOOT.BIN` = motor parcheado (EBOOT zero-padded a 1104032 B, con `7f 45 4c 46`, para que cualquier camino del loader use el motor parcheado). Canaria de datos presente: GAGAGIGO (5759, índice 1574) ATK **4850**. Verificación independiente con `tools/iso9660.py`: exactamente 6 bytes distintos del artefacto original (0x3a4b4/0x3a4b6/0x3a4b7 y 0x3a4b8/0x3a4ba/0x3a4bb), las palabras parcheadas leídas = `0x24020003`, `0x00000000`, EBOOT = motor + ceros, tamaño igual al del directorio ISO.

- **L11 (usuario, verbatim).** «1 y 3 ok pero yo no tengo mas cartas ademas del deck principal que te dan, tendrias que agregar a la fuerza cartas prohibidas desde tu lado o que use un coigo para tener todas las cartas para ver si 2 funciona»
- **L12 (resultado de la prueba C1 — la sonda diagnóstica FUNCIONÓ).** La canaria de datos (GAGAGIGO ATK 4850) y la pregunta central (la carta nueva entra al deck **sin** ícono rojo) dieron **ok**. Consecuencias: (a) el motor parcheado **sí** está cargado (es la única diferencia con planB), (b) el veredicto «Forbidden» **es** el nivel leído por `get_limit` (la sonda solo cambió ese lector), (c) por lo tanto **C es viable**: se puede agregar cartas en índices nuevos sin sacrificar ninguna carta real. La canaria 2 (carta prohibida usable) no se pudo medir porque el save del usuario solo tiene el deck inicial; **no es bloqueante**: el desenlace de la canaria 1 ya demuestra que el parche cargó y que el nivel es la palanca.
- **L13 (fix de producto, F1).** La sonda C1 desactiva toda la lista de prohibidas (no sirve como producto). El parche de producto se implementó en el **wrapper exportado de 0x478fc** (no en `get_limit`, que no tiene espacio): el wrapper ahora calcula el nivel él mismo y devuelve **3** cuando el registro está sin inicializar (puntero nulo o **palabra de 4 bytes == 0**, que es el caso de los índices apendeados), y el byte 2 (el nivel real) en cualquier otro caso; la lista de prohibidas queda intacta porque una carta prohibida *poseída* tiene bytes de posesión distintos de cero. Además: entrada de dirección del NID `0xcda3b5c5` (índice 803, tabla en 0x6aa20) repuntada de 0x3a43c a 0x478fc, y los dos llamadores internos (`jal 0x3a43c` en 0x469cc y 0x46ab0) repuntados. Detalle del loader: la entrada de reloc del wrapper en 0x47918 se repuntó a la palabra muerta 0x3a43c (el cuerpo viejo de `get_limit` queda sin referencias), porque toda palabra con reloc `R_MIPS_26` debe seguir siendo un `j`/`jal` válido. El camino del wrapper que consultaba la tabla cruda (flag 0x26130C) se descarta: la evidencia (Dark Hole se ve Prohibida aunque la tabla de BOOT dice Limitada) muestra que el nivel efectivo es el del ctx.
- **L14 (ISO de producto C2, verificado offline).** `tools/e5_c2_patch.py` → **`trabajo/e5/TF1-E5-C2.iso`** (798 787 584 B, igual al base): mismo cardinfo E1 (índice 2480, CardID 4661, ATK 4900, `E1 TEST CARD`; canaria GAGAGIGO ATK 4850) + motor parcheado en `BOOT.BIN` y `EBOOT.BIN` (zero-padded a 1104032 B). Relectura independiente con `tools/iso9660.py`: el wrapper son exactamente las 17 palabras previstas, la tabla de exportación quedó en 0x478fc, la reloc en 0x3a43c, los dos llamadores en `jal 0x478fc`, y **48 bytes** difieren del artefacto original, todos dentro del conjunto previsto; el cuerpo viejo de `get_limit` quedó intacto (C2 ≠ C1, la lista de prohibidas no se toca). `objdump` confirma los saltos (`beqzl` a 0x47930 y `j` a 0x47934).

- **L15 (usuario, verbatim):** «1,2,3 ok. Todo funciono» — con C2 (parche de producto) la carta nueva entra al deck sin ícono rojo, sus cartas propias siguen usables y un duelo con la carta nueva arranca y permite invocarla. **T8 cerrado.**
- **L16 (cierre).** Con C verificada en emulador, T9 queda cerrado y se habilita el port de las 18 (nueva fase, handoff `ESTADO-E6.md`): decisiones del usuario (textos a `datos/`, donante de arte elegido por el agente, obtención por edición del save, las 18 de una), tabla de contenido escrita (`datos/cartas_18.tsv`) y un bloqueo nuevo de layout del ISO (el contenedor no entra: ver `ESTADO-E6.md` §4) que necesita una decisión del usuario. Los cuatro artefactos de E5 (tres herramientas + este documento) quedan commiteados al cerrar la sesión.

# Frente B · El efecto real de las 4 Mágicas como código nuevo

Fase **propia**, separada de E7 frente A (recetas de fusión: cerrado y validado in-game).
Objetivo: que las 4 Mágicas del port ejecuten su **efecto real** en el motor de TF1, escribiendo
**código MIPS nuevo** (no por Fusión), usando la referencia de ARC-V Tag Force Special
(`ESTADO-E9.md`) y el 2º `PT_LOAD` del módulo como espacio. ISO de partida: `trabajo/e8/TF1-E8-G6.iso`
(nunca se modifica; un artefacto ISO por ronda).

## Specs

- **S1 — Alcance (fase propia, decidida por el usuario).** «A ahora y B después, en rondas
  separadas» (L2, ronda anterior): esta fase es el **frente B**, que `ESTADO-E7.md` §3 define como
  «**Efectos de las 4 Mágicas** — sobre todo las de «Cambio de Máscara», que son la receta
  concesionada del usuario». E7 frente A quedó **cerrado y validado in-game** (T18 de
  `odd/tasks/e7-recetas-fusion.md`, `ESTADO-E7.md` §8.7).
  **Decisión abierta del usuario, después de T1**: cuántas de las 4 Mágicas entran en esta fase y en
  qué orden (ver T7).

- **S2 — Semántica de «Cambio de Máscara» (4704), texto exacto**
  (`datos/efectos_heroes_enmascarados.txt` §3.1 — Mágica de Juego Rápido):
  > - Selecciona un monstruo HÉROE que controles y mándalo al Cementerio.
  > - Después, si dejó el Campo por este efecto, Invoca de Modo Especial desde tu Deck Extra un HÉROE
  >   Enmascarado del mismo atributo que tenía ese monstruo en el Campo.
  Predicado: **mismo atributo**. Ejemplo del documento: «un HÉROE de OSCURIDAD puede transformarse en
  Dark Law o Anki».

- **S3 — Semántica de las otras tres (texto exacto, `datos/efectos_heroes_enmascarados.txt` §3):**
  - **Cambio de Máscara II (4721)**, Mágica de Juego Rápido: «Descarta una carta y selecciona un
    monstruo boca arriba que controles que tenga Nivel.» / «Manda ese monstruo al Cementerio e Invoca
    de Modo Especial desde tu Deck Extra un HÉROE Enmascarado del mismo atributo, pero de Nivel mayor
    que el que tenía ese monstruo.» / «El monstruo seleccionado no tiene que ser un HÉROE, pero el
    descarte es obligatorio.» / «Sólo puedes activar 1 «Cambio de Máscara II» por turno.»
  - **Cambio de Forma (4726)**, Mágica de Juego Rápido: «Selecciona un monstruo de Fusión HÉROE que
    controles y devuélvelo al Deck Extra.» / «Después, Invoca de Modo Especial desde tu Deck Extra un
    HÉROE Enmascarado del mismo Nivel que el monstruo devuelto, pero con nombre distinto.» / «No exige
    que ambos monstruos tengan el mismo atributo.»
  - **Carga de Máscara (4730)**, Mágica Normal: «Selecciona un monstruo HÉROE y una Mágica de Juego
    Rápido «Cambio/a» en tu Cementerio.» / «Añade ambas cartas a tu mano.»
  - Nota del mismo documento: «Cambio de Forma busca por Nivel, no por atributo. Cambio de Máscara
    busca por atributo. Cambio de Máscara II busca por atributo y Nivel mayor. Son tres predicados
    distintos.»

- **S4 — Restricciones de la familia (texto exacto del mismo documento, notas para el port).**
  «Cambio de Máscara no es una Invocación por Fusión y no puede activarse durante el Damage Step.»

- **S5 — Nada de lo que ya funciona se rompe** (heredada de E7 S4). Las 105 recetas de fusión de la
  ronda F4 y todo el comportamiento nativo del motor siguen resolviendo igual: ninguna región del
  módulo fuera del plan de parches de la ronda puede cambiar.

- **S6 — Espacio para el código nuevo.** El código vive donde T1 lo mida. Candidato ya validado
  in-game: el 2º `PT_LOAD` del módulo (`VMA 0x112910`, `p_flags 7` = RWX), hoy con 848 B de tabla de
  recetas y **800 B** de holgura dentro del *extent* ISO del módulo.

- **S7 — Un artefacto ISO por ronda** (heredada de E7 S6). Nunca se toca la ISO original ni la de
  partida (`trabajo/e8/TF1-E8-G6.iso`).

- **S8 — Verificación offline + una sola varilla en PPSSPP por ronda** (heredada de E7 S4/S5): la
  verificación del artefacto es independiente y el test in-game lo hace el usuario, con una sola
  varilla de decisión por ronda.

- **S10 — Relocalizaciones (invariante medida, T3b).** El módulo es un PRX **relocalizable** (en
  `.text`, 241/241 `j` y 14479/14479 `jal` llevan `R_MIPS_26`; `.rel.data` tiene 6844 `R_MIPS_32`) ⇒
  **la base de carga no es 0**. El linker **omite** la reloc en celdas nulas. Por lo tanto: (a) un
  puntero nuevo sólo puede escribirse en una celda que **ya** tenga `R_MIPS_32` (o agregando la reloc);
  (b) **todo código nuevo debe ser libre de relocalizaciones** —derivar la base de `ra` y saltar con
  `lui/addiu` + `addu` + `jr`—; (c) nunca escribir un valor no nulo en una celda sin reloc.
- **S9 — Sonda de viabilidad antes del efecto real** (patrón EXP1/EXP2 de E7, decisión L5 de esa
  fase: «Probar antes el mecanismo de efectos (1 palabra)»). El primer corte construible es una
  **sonda** con código propio de tamaño mínimo que pruebe que la ruta de despacho es viva y editable;
  el efecto real se escribe recién cuando la sonda dé positivo.

## Tasks

| ID | Specs | Qué | Route | Commit |
| --- | --- | --- | --- | --- |
| T1 | S1, S6, S9 | Recon read-only: el despacho de **activación**, la ABI del handler y el **espacio ejecutable real**. | worker | hecho (E4-E7) |
| T1b | S1 | Recon de las **primitivas faltantes** de E8: lectura de atributo, «mandar al Cementerio» y la UI de selección de objetivo. Bloquea T4, no T2. | worker | — |
| T2 | S1, S9 | Elegir la **carta de prueba** (intersección del deck del usuario con las tablas de 24 B), decidir con el usuario la **sonda mínima** (EXP3) y construirla + su ISO. | worker + user | hecho (L4, E10, E11) |
| T3 | S8, S9 | Test in-game del usuario de EXP3. | user | **descartada**: la ISO quedó invalidada (L5, E12, E13) |
| T3b | S1, S9, S10 | **Diagnóstico del crash de EXP3** (causa raíz: relocalizaciones faltantes) y diseño corregido de la sonda. | worker | hecho (E13) |
| T3c | S1, S9, S10 | Construir **EXP4**: sonda **pareada** —carta A = copia literal de la entrada del donante; carta B = la misma entrada con `slot4` apuntando a un **stub propio libre de relocalizaciones**— y su ISO. | worker | hecho (E16, E18) |
| T3d | S8, S9, S10 | Test in-game del usuario de EXP4. | user | **descartada**: crasheó al usar 6431; ISO superseded por EXP4b (L7, E17) |
| T3e | S8, S9, S10 | Test in-game del usuario de **EXP4b** (una sola varilla): Olla de la Codicia → robar 2; El Guerrero Volviendo Con Vida → robar 2 (camino de datos puro); Recuperación de Fusión → robar 2 vía nuestro stub. | user | hecho — **negativo parcial** (L8, E19) |
| T3f | S1, S9, S10 | **Desambiguar E19**: verificar para 5330/6431 la **tabla que selecciona el despachador** según su clase y contrastarla con las celdas parcheadas; averiguar de qué depende el resolver `0x79ea0`; rediseñar y construir **EXP5** anclada en una carta con línea base validada in-game (**4844**). | worker | hecho (E21, E22) |
| T3g | S8, S9, S10 | Test in-game de EXP5: el donante 4529 hace que el rival robe 2 (4844 vía nuestro stub, 5328 directo). | user | **hecho y validado** (L9, E23) |
| T4 | S2, S4, S6, S10 | Implementar el efecto real de «Cambio de Máscara» (4704) como código nuevo + ISO. **Tres restricciones ya medidas**: (i) 4704 **no tiene entrada** en ninguna tabla de 24 B ⇒ hay que **reutilizar un slot libre o insertar** respetando el **orden** de la búsqueda binaria y el largo declarado de la tabla, y resolver el **gate `entry+16`** (E5); (ii) el código debe ser **libre de relocalizaciones** (S10) y **keyed explícitamente por 4704**, nunca por el CardID del objetivo (E21); (iii) presupuesto de código: ~**780 B** de holgura en el layout actual (o crecer el módulo hasta file `0x167800`). | worker | — |
| T5 | S5, S6, S8 | Verificación **independiente** del artefacto de T4 (geometría, plan de parches, nada fuera del plan; las 105 recetas intactas). | verify | — |
| T6 | S2, S8 | Test in-game del efecto real: un HÉROE en el campo se transforma en el Enmascarado del **mismo atributo** sin Polimerización, y una fusión nativa sigue resolviendo. | user | — |
| T7 | S1, S3 | Decidir alcance y orden de las 3 Mágicas restantes (II, Forma, Carga) con el costo ya medido. | user | — |
| T8 | S5, S7 | Cierre de la fase: `ESTADO-E7.md`/README, artefactos fijados y commits por unidad de trabajo. | inline | — |

## Log

- **L1** (usuario, verbatim): «Sigamos, frente B no?»
- **L2** (usuario, verbatim, ronda anterior): «A ahora y B después, en rondas separadas» ⇒ el frente B
  quedó como **fase propia**, no como parte de E7.
- **L3** (estado heredado, medido y validado): E7 frente A cerrado — 105 recetas (una alcanzable por
  resultado), ISO `trabajo/e7/TF1-E7-F4.iso`, ronda in-game del usuario OK sobre las tres señales
  (Dian con Clayman; Rey del Pantano + «Cambio de Máscara»; Contraste Chaos con Cuervo + Fuente).
  Detalle: `ESTADO-E7.md` §8.7 y T18 de `odd/tasks/e7-recetas-fusion.md`.
- **E1** (medido, heredado de `ESTADO-E7.md` §7.2–§7.5): el despacho de efectos parece ser por **tablas
  de datos** —4 tablas de entradas de 24 B `{u32 CardID; 5×u32 slots}` en `.data` (`0x100644` 764,
  `0x104dfc` 454, `0x1078a4` 175, `0x108924` 213) y un despachador en `.text 0x48d74` que elige tabla
  por los bits 2–3 del byte 3 de la carta y hace búsqueda binaria por la clave u16 en `carta+0`—; las 4
  Mágicas del port (4704, 4721, 4726, 4730) **no tienen entrada** en ninguna tabla ni inmediatos reales
  en el código.
- **E2** (medido, sonda EXP1): repuntar la entrada de «Rescate» (5908) en la tabla de 8 B
  `{u16 CardID; u16 0; u32 handler}` de `0x10b018` al handler de Monster Reborn **no cambió el efecto**
  in-game ⇒ esa tabla **no es** la palanca del efecto de activación. Artefacto de la sonda:
  `trabajo/e7/TF1-E7-EXP1.iso`; protocolo en `trabajo/e7/T7-EXP1.md`.
- **E3** (medido, heredado): `.text` termina en `0xfa218` y `.sceStub.text` arranca ahí mismo ⇒ el
  frente de efectos necesita **espacio nuevo para código**, el mismo problema de layout que resolvió
  E7 con el 2º `PT_LOAD` (validado in-game por EXP2 y usado por las rondas F1–F4).
- **E4** (T1, medido por analista read-only, 2026-11): **el despacho de activación es la tabla de 24 B**.
  `find_handler(carta*)` en `.text 0x48d74`: `lbu a2,3(a0)` → **bits 4–5** del byte 3 = **clase** (0–3,
  selector de tabla; **corregido en E21** — acá decía bits 2–3, que es un error de aritmética del
  desplazamiento `sll 26 / srl 30`; la conclusión no cambia): 3→T4 `0x108924` (213); 2→T1 `0x100644` (764) si `((lhu@carta+2<<20)>>26)==35`,
  si no T3 `0x1078a4` (175); 1→T2 `0x104dfc` (454); 0→T1. Búsqueda binaria stride 24
  (`0x48e24 sll a0,a1,1; 0x48e28 addu; 0x48e2c sll a0,a0,3`), comparación `lw 0(a0)` contra
  `0x48e78` (struct sintético de 24 B en pila, `0x48e9c sh a0,24(sp)`) ⇒ **la clave es el u16 en
  `carta+0` = CardID**, no `prop1 & 0x3fff` de TFSP. 18 sitios `jal 0x48d74`. Confirmado: 4704/4721/
  4726/4730 siguen con **0 inmediatos** que gobiernen la activación.
- **E5** (T1, medido): **el hook de resolución es `entry+4`**, leído y llamado por el wrapper `0x49744`
  (`0x497c4 jal 0x48d74; 0x497d4 lw v0,4(v0); 0x497e4 jalr ra,v0`), con **`a0 = carta`, `a1 = ctx`** y
  el retorno en `v0`. Los otros slots: `+8` = filtro `(carta, jugador, zona)` (`0x49070` recorre 2×11
  zonas); `+12` = `(carta, objetivo)`; `+16`/`+20` = `(carta, arg)`. El estado del efecto vive en
  `[0x11cf88]` (código de paso que devuelve el handler; lo escribe el llamador `0x4d200`), `[0x11cfa0]`
  = modo ejecutar(0)/consultar(1), `[0x11cf84]` = contador de paso, `[0x11ce6c]` = carta activa.
  El **gate de activación** es `0x4983c`: compara `entry+16` **por identidad** contra un set fijo de
  punteros (`0x6c4d8`, `0x6c820`, `0x6db3c`, `0x6f2b4`, `0x702a4`, `0x714f0`, `0x72c30`, `0x710bc`).
  **Riesgo abierto para T4**: una entrada nueva necesita un `entry+16` de ese set o el gate la bloquea;
  el protocolo del bucle de pasos sólo está trazado parcialmente.
- **E6** (T1, medido; **corrige** la lectura de E2 y de `ESTADO-E7.md` §7.2): la tabla de 8 B de
  `0x10b018` tiene **364 entradas `{u32 CardID; u32 handler}`** (no 23) y es un despacho por carta que
  consulta `0x470f0(jugador, opcode, CardID, param)` vía `0x7c114`→`0xb8bc8`→`0xb8b58` (búsqueda
  binaria stride 8, `addiu a3,zero,364`). Eso **explica el negativo de EXP1**: esa tabla no es el
  resolver de activación.
- **E7** (T1, medido): **espacio**. El módulo de `TF1-E8-G6.iso` es **prístino** (sin 2º `PT_LOAD`,
  sha256 `6867fb17…`): su extent va de LBA 12048 (719 sectores) a `libduel_mgr.prx` en LBA 12767 =
  file `0x167800` ⇒ el módulo **puede crecer en el lugar** hasta `0x167800` sin mover el archivo
  siguiente (techo duro). Cola libre del prístino: 1718 B; en el layout de F4 (2º `PT_LOAD` con 848 B
  de recetas) quedan **800 B**. `p_flags = 7` (RWX) en ambos segmentos ⇒ **se puede ejecutar**. No hay
  bytes muertos internos (la única grieta aparente es la tabla de secciones ELF `0x10c230..0x10c618`).
- **E8** (T1, **parcial**): primitivas componibles. (b) **Invocación Especial del Deck Extra sin
  Fusión**: `0xb88b4(jugador, loc=12, idx)` — Cyber-Stein `0xad380` itera el Deck Extra
  (`lw 24(s0)` count, `lhu 1568(v0)` ids) y la usa; la distinción «no es Fusión» se ve en que **no
  llama al finder de recetas**. (a) **mandar al Cementerio: NO aislada** (Foolish Burial `0xaf564` usa
  `0xb88b4(jugador, loc=13, idx)` + import `0xdaf0c`; Agujero Oscuro resuelve por `0xca0c0`→
  `0xc9d80(carta, mask, 14, 2)`). (c) **lectura de atributo: NO identificada** (el atributo es
  `CARD_Prop.bin` prop2 bits 4–7, vía import de libehsys sin resolver). (d) UI de selección de
  objetivo: **no fijada** (`0xbd1cc` encola un evento en `[0x11d0c8]`). ⇒ **T1b**.
- **E9** (T1, propuesta para T2): la sonda mínima es de **una sola ISO y una sola varilla**: repuntar
  el `entry+4` de una carta que el usuario pueda activar a un **stub propio** escrito en la cola del 2º
  `PT_LOAD` (p. ej. `j 0x7837c`, el resolver de Agujero Oscuro 4342) y ajustar su `entry+8` al filtro
  del donante. Si en PPSSPP esa carta ahora destruye todos los monstruos, quedan probadas **las dos
  mitades**: que el slot `+4` es una palanca viva y que **nuestro código en el segmento nuevo se
  ejecuta**. Candidatos de donante por efecto inconfundible: Agujero Oscuro 4342 (`{0x7837c, 0x503e8,
  0, 0, 0}`), Monster Reborn 4842 (`{0x804f8, 0, 0x68f08, 0, 0xa45f8}`). Queda por elegir **la carta
  de prueba**, que debe ser jugable desde la mano en un duelo normal del save del usuario.
- **L4** (usuario, decisiones, verbatim): «Par: Olla de la Codicia + Refuerzo del Ejército» (carta par de
  la sonda) y «Sí, ese es mi deck actual» (el deck que se usa es el de `trabajo/save/live/DATA0.mc3`).
- **E10** (T1b/T2, medido): intersección del deck del usuario con las tablas de 24 B. El save vivo
  `trabajo/save/live/DATA0.mc3` tiene **49 cartas de baraja (37 distintas)** y **24** con entrada de
  24 B; el más viejo `trabajo/e6/DATA0.hero` tiene 42/35 con 17. Las 4 Mágicas del port están
  poseídas y en la baraja del `.mc3` pero **sin** entrada de 24 B (coherente con E1). Informe:
  `trabajo/b1/T2-CANDIDATOS.md`; script `trabajo/b1/recon/t2_candidates.py`.
- **E11** (T2, construido y **verificado**): **EXP3**. Stub de 8 B (`j 0x7837c` + `nop` =
  `0x0801E0DF`, `0x00000000`) anexado en la cola del 2º `PT_LOAD`, file `0x1674e0` = **VMA
  `0x112c60`**; PH[1] `p_filesz/p_memsz` `0x350 → 0x358`; módulo `trabajo/b1/libduel_eng_exp3.prx`
  **1.471.720 B** (`0x1674e8`, sha256 `f17a5164…588`); ISO `trabajo/b1/TF1-B1-EXP3.iso`
  (798.787.584 B, sha256 `632fc75b…933`), **4 sectores** distintos `[38, 12562, 12564, 12766]`,
  `libduel_mgr.prx` intacto, tamaño de ISO sin cambios. Parches: **4844** (Olla de la Codicia)
  `slot4 → 0x112c60`, `slot8 → 0x503e8`; **5328** (Refuerzo del Ejército) `slot4 → 0x7837c`,
  `slot8 → 0x503e8`; `slot12/16/20` intactos; **13 de 24 bytes** declarados cambiados; recetas de F4,
  `.rel.data` y tabla de secciones byte-idénticas. Herramienta `tools/b1_probe.py`
  (`dump`/`build`/`verify`/`iso`, se niega a escribir si falla una precondición o un pin). Reporte y
  protocolo de prueba: `trabajo/b1/T2-EXP3.md`.
  **Error del padre, cazado por el worker**: el diseño decía «file `0x1674e0` = VMA `0x112c58`»; el
  mapeo de PH[1] es `VMA = file − 0x54880`, así que el punto de anexado es **`0x112c60`** (el
  `0x112c58` es el terminador `(10,0,0,0)` de la tabla de recetas, que debe quedar intacto). Se
  corrigió (Opción A) **antes** de construir. Lección: calcular el mapeo file↔VMA de cada segmento
  antes de declarar un punto de anexado; con `0x112c58` el resolver habría ejecutado el terminador
  (`0x0000000A` = `movz`) y la sonda habría dado un **falso negativo** silencioso.
- **L5** (usuario, verbatim): «fuí a seleccionarla y crash».
- **E12** (T3, **fallo reportado por el usuario**): la ronda in-game de EXP3 **crasheó** al ir a
  seleccionar una carta de la mano. Captura del estado: duelo en curso, **turno 2**, MP1, LP 8000 vs
  9000, con una carta resaltada en la mano y su previsualización abierta. Queda por precisar: **qué**
  carta era, en **qué** momento exacto (consulta al seleccionar / activación / elección de objetivo) y
  si la **otra** carta sonda llegó a producir su efecto. Hipótesis principal a verificar en **T3b**: el
  `slot8` que repuntamos a `0x503e8` (filtro de Agujero Oscuro) también se consulta en el camino de
  **consulta** (`0x48f78`, modo 1), y ahí la carta de prueba puede quedar en un estado que el motor no
  espera. Nota de método: no se declara probada ni refutada la hipótesis de `slot4`; EXP3 quedó
  **inconclusa**.
- **E13** (T3b, medido — **causa raíz del crash de EXP3**): no fue la semántica de `slot8` sino **dos
  relocalizaciones faltantes** (S10). (1) `slot8 = 0x503e8` se escribió en las celdas `0x101174`
  (4844) y `0x1023bc` (5328), que **no** tienen `R_MIPS_32` porque su valor original era 0 ⇒ en
  runtime quedan en `0x000503e8` y el `jalr` salta a una dirección no mapeada. (2) El `j 0x7837c` del
  stub **no** tiene `R_MIPS_26` ⇒ salta a `0x0007837c`. Cualquiera de los dos, ejecutado, crashea.
  **Descartado**: `0x503e8` es un filtro de zona `(carta, jugador, zona)→0/1`, determinista y
  memory-safe, y **no** lee el flag de modo (`0x10cfa0`). Medido además: **sólo 3** entradas de las 4
  tablas usan ese filtro (4342 Agujero Oscuro, **5114 Tributo Torrencial**, 5841) y las tres comparten
  `slot4 = 0x7837c`; y ese resolver **depende** de `slot8` (`0x4901c` devuelve −1 si `slot8 == 0`).
  **No aislado**: qué corre la UI al pasar el cursor (ningún export alcanza por `jal` a
  `0x48f78`/`0x4901c`/`0x49744`) ⇒ el fallo encaja mejor con selección/activación. Informe
  `trabajo/b1/diag/T3b-CRASH.md`.
- **E14** (T1b, medido — **corrige E5 y E8**): (a) **las direcciones `0x11xxxx` estaban mal**:
  `PH[0].p_memsz = 0x112910`, así que ningún global puede estar ahí (se leyó el offset de `lw/sw` sin
  extender el signo). Correctas, **−0x10000**: paso del efecto `0x10cf88`, modo `0x10cfa0`, contador
  `0x10cf84`, cola de UI `0x10d0c8`. (b) **`0xb88b4` NO invoca**: es el *append* a la lista de
  referencias (índice `[0x10d8e8]`, `0x10d8ec`, loc `0x10e0ec`, satura a 511); quien elige la operación
  es el `opcode` del motor (`0x470f0`→`0xb8bc8`). La Invocación Especial real es
  **`0x21be4(jugador, &ranura, posición, CardID<<16)`** (+ ejecutor `0x213dc`); «no es Fusión» =
  ausencia de `0xa0530`/recetas, **sin bandera**. (c) **Mandado al Cementerio**: el movimiento atómico
  es **`0xc9564(jugador, zona, destino, flags, CardID)`**; `0xc9d80` = destruir; envoltorios `0xca0c0`
  (destruir, destino 14, flags 2) y **`0xcaa34`** (destino 14, flags 0, sin destruir). Códigos de
  ubicación medidos: **0..10 = Campo** (12 ranuras de 20 B en `+0x30`), 11 = Mano `+0x120`, 12 = Deck
  Extra `+0x620`, 13 = Deck `+0x3A0`, **14 = Cementerio `+0x710`**, 15 = Desterrado `+0xA80`; base por
  jugador `0x10e4ec + jugador*4012`. (d) **Atributo**: getter `BOOT.BIN 0x47754` =
  `(prop2>>4)&0xF` sobre el registro de 8 B de `0x474f8(CardID)`, importado como stub **`0xfc0f8`**
  (NID `0xe62cce79`); el predicado «mismo atributo» **ya existe**: **`0xde618(CardID, attr)`**, con
  molde de uso en `0xaf634(jugador, attr)`. (e) **Selección de objetivo: negativo medido** — el motor
  no llama a un handler para pedir la elección: el filtro se declara en `entry+8` (barrido 2×11 por
  `0x49070` en modo consulta), entrega hasta 5 handles y el handler los lee con `0xa3118(carta,k)` +
  `0xdea14(handle)`. Informe `trabajo/b1/primitivas/T1b-PRIMITIVAS.md`. **Defecto de herramienta
  pendiente**: `trabajo/b1/recon/prxelf.py:disasm_word` imprime `.word` para los opcodes 0x16, `lwc1`,
  `swc1` y `sllv` (idioma de copia/máscaras del motor) — afecta la legibilidad de futuros recon.
- **E15** (T3c, medido): el par fijo 4844+5328 con un solo donante es **insatisfacible** bajo S10: el
  patrón de relocs es **por celda y por carta** — 4844 = `R.R.R` (+4/+12/+20 con `R_MIPS_32`), 5328 =
  `R.R..` (+4/+12) —, y **no existe** una celda `R_MIPS_32` con valor 0 en el módulo. El donante clásico
  (Monster Reborn `{0x804f8, 0, 0x68f08, 0, 0xa45f8}`, también `R.R.R`) tiene `slot20 != 0` ⇒ copiarlo
  en 5328 deja ese puntero sin relocalizar y vuelve el crash de EXP3. Segundo error del padre: el stub
  son **20 B** (5 instrucciones: `lui`+`addiu`+`addu`+`jr`+`nop`), no 16. Informe
  `trabajo/b1/diag/T3c-PREMISA.md`.
- **L6** (padre, decisión de diseño de T3c, a partir de E15): **donante = 4844 «Olla de la Codicia»**
  (`{0x79ea0, 0, 0x68f54, 0, 0xa4934}`, patrón `R.R.R`): su efecto —**robar 2**— es incondicional, no
  pide objetivo ni Cementerio y se ve al instante en un duelo de turno 2, y la carta queda **intacta**
  como referencia en la mano del usuario. **A = 5330** (`R.R.R`) recibe la entrada del donante literal ⇒
  el camino de datos queda probado. **B = 6431** (`R.R.R`) recibe la misma entrada con `slot4 →
  0x112c60` (nuestro stub) ⇒ prueba que **nuestro código se ejecuta**. Stub de 20 B libre de relocs:
  `lui t9,3; addiu t9,t9,0xFFB8; addu t9,t9,ra; jr t9; nop`, con `ra = base + 0x497e8` (medido:
  `0x497e4 jalr ra,v0`) ⇒ `t9 = base + 0x79ea0`, el resolver del donante. PH[1] `0x350 → 0x364`,
  módulo `0x1674f4`. Predicción: Olla de la Codicia roba 2 (base); A debe robar 2; B debe robar 2 **a
  través de nuestro código**. Ambos roban 2 ⇒ ruta probada y T4 desbloqueada; A sí y B no ⇒ el problema
  está en el segmento/código nuevo; ninguno ⇒ cae el modelo de despacho por `slot4`.
- **E16** (T3c, construido y **verificado**; ejecuta L6): **EXP4**. Donante **4844 Olla de la Codicia**
  intacto (`{0x79ea0, 0, 0x68f54, 0, 0xa4934}`, patrón `R.R.R`); **A = 5330** con los 5 slots del
  donante literales; **B = 6431** con la misma entrada y `slot4 → 0x112c60`; ambos están en la baraja
  del save vivo. Stub de 20 B **libre de relocs** anexado en file `0x1674e0` = VMA `0x112c60`; PH[1]
  `0x350 → 0x364`; módulo `trabajo/b1/libduel_eng_exp4.prx` **1.471.732 B** (`0x1674f4`, sha256
  `87a08a69…305`); ISO `trabajo/b1/TF1-B1-EXP4.iso` (798.787.584 B, sha256 `6c95e125…f90`), **4
  sectores** `[38, 12564, 12568, 12766]`, `libduel_mgr.prx` intacto, tamaño sin cambios; **cero relocs
  nuevas** (`​.rel.data`, `.rel.text` y tabla de secciones byte-idénticas) y las recetas de F4 intactas.
  EXP3 sigue reproducible y sus pines intactos. Reporte: `trabajo/b1/T3c-EXP4.md`.
  **Segundo error del padre, cazado por el worker**: el `jalr` deja **`ra = PC + 8`**, así que con el
  `jalr` en `0x497e4` vale `ra = base + 0x497ec` (no `0x497e8`) ⇒ `delta = 0x79ea0 − 0x497ec =
  0x306b4` (`lui t9,3; addiu t9,t9,0x06B4`). Con mi valor el stub habría saltado a `base + 0x797a4`,
  **0x6FC antes** del resolver del donante. Lección: la dirección de retorno de un `jal`/`jalr` es la
  instrucción **posterior al delay slot**.
- **L7** (usuario, verbatim + `[Image#2]`): «crash al usar recuperación de fusion, las demas no han sido
  probadas. Anota resultados y guarda sesion para continuar despues».
- **E17** (T3d, **fallo del usuario** + **verificado byte a byte por el padre**): la ronda de EXP4
  crasheó al **activar «Recuperación de Fusión» (6431 = carta B)**; «Olla de la Codicia» (base) y «El
  Guerrero Volviendo Con Vida» (A) **no llegaron a probarse**. Causa raíz, medida en el artefacto: la
  **tercera instrucción del stub quedó mal codificada** — `addu t9,t9,t9` (**0x0339C821**) donde el
  diseño pedía `addu t9,t9,ra` (**0x033FC821**) ⇒ `t9 = 3·0x306b4` y el `jr t9` saltaba a
  `0x0009141C` (sin base, no mapeado). El `ra` (PC+8) y el `delta` (0x306b4) estaban **bien**.
  **Insuficiencia de verificación**: `_assert_stub_arithmetic` comparaba los words contra una **tupla
  literal** ⇒ verificación **tautológica** (misma clase de defecto que el aviso
  `R3-vacuous-new-results-check` de la ronda F4) y un error de codificación pasó el `verify4` en verde.
  **El crash NO refuta la hipótesis de `slot4`** ni el modelo de despacho: el camino de **datos puros**
  (carta A) sigue **sin probar** y es la medición decisiva de la próxima ronda.
- **E18** (T3c/E17, construido y **verificado por el padre**): **EXP4b**, mismo diseño con el word
  corregido. En `tools/b1_probe.py`: constante `0x033FC821`, `_decode_stub_word` nuevo y
  `_assert_stub_arithmetic` que ahora **desensambla** y compara **semántica** (`lui t9,3` /
  `addiu t9,t9,0x06B4` / `addu t9,t9,ra` / `jr t9` / `nop`). **RED**: el artefacto viejo **falla**
  `verify4` («patched image differs from the re-derived image at offset 0x1674ea»). **GREEN**:
  `trabajo/b1/libduel_eng_exp4b.prx` 1.471.732 B sha256 `33ee94df…244` + `trabajo/b1/TF1-B1-EXP4b.iso`
  798.787.584 B sha256 `266387b8…1fb`, **4 sectores** `[38, 12564, 12568, 12766]`, ISO del mismo
  tamaño y `libduel_mgr.prx` intacto. Decodificado por el padre: `ra + 0x306b4 = 0x79ea0` = resolver del
  donante ✓. **EXP4 (el crasheado) queda superseded**.
- **L8** (usuario, verbatim): «Anota y guarda: Solo olla de la codicia activo y resolvio el efecto, las
  otras dos activaron efecto pero solo se fueron para el cementerio sin hacer nada mas».
- **E19** (T3e, **resultado del usuario**, con el control validado en la **misma ISO**): **Olla de la
  Codicia (4844, intacta) activó y resolvió su efecto** (roba 2) ⇒ **el control queda establecido
  in-game**. **El Guerrero Volviendo Con Vida (5330, carta A) y Recuperación de Fusión (6431, carta B)
  activaron, se fueron al Cementerio y no hicieron nada más**: en ninguna de las dos apareció el efecto
  del donante (robar 2).
  Lectura: el **camino de datos puros** (carta A) dio **negativo** ⇒ **no** queda probado que
  `entry+4` redirija el efecto de una carta existente; y como A y B se comportaron **igual**, el
  resultado **no** discrimina nada sobre nuestro stub (B no aporta información propia).
  **Ambigüedad de diseño (falla del padre)**: A y B eran cartas con efecto **condicional** (buscar un
  Guerrero del Cementerio / reciclar 2 Fusión), así que «no hizo nada» **no** distingue «el parche no
  cambió nada» de «corrió su efecto original y no había objetivo legal».
  **Caveat fuerte que hay que cerrar ANTES de concluir** (E20): si el **selector de tabla** del
  despachador (`lbu a2,3(a0)` → bits 2–3 del byte 3 = clase) **no** elige para 5330/6431 la tabla donde
  escribimos, el parche fue **vacuo** y el negativo no dice nada del modelo. Un dato a favor del modelo:
  4844, en la misma tabla y con su entrada propia, **sí** funciona; y sigue en pie que el efecto de
  una carta nueva necesita dónde escribirse (S6/S10).
- **E20** (plan de T3f): (a) para **5330** y **6431**, derivar de su registro de carta la **clase**
  (byte 3, bits 2–3) y con ella la **tabla que selecciona el despachador**, y contrastarla con las
  celdas parcheadas (`0x1023E4`, `0x1041E4`); buscar además **claves duplicadas** de esos CardID en las
  4 tablas. (b) Averiguar de qué depende el resolver `0x79ea0` (Olla de la Codicia) además de `slot4`:
  ¿lee la clase/props del registro de carta, o `slot12`/`slot20`? (c) Rediseñar la sonda **EXP5** anclada
  en una carta con **línea base validada in-game**: **4844** (roba 2, medido en la misma ISO de E19) ⇒
  su `slot4` → **nuestro stub** reenviando al resolver de un donante **incondicional y visible**
  (`slot8 == 0`), y el `slot4` de **5328** (patrón `R.R..`) → el resolver del donante **directo**. Con
  línea base conocida, cualquier cambio de comportamiento de 4844 respecto de «roba 2» es **inequívoco**.
- **E21** (T3f, medido): **el parche de E19 NO era vacuo**, y la causa del negativo es de fondo.
  **Corrección de bits del selector** (afecta a E4/E5/E13): la clase sale de `lbu a2,3(a0)` + `sll 26` +
  `srl 30` ⇒ son los **bits 4–5** del byte 3 (no 2–3), y el subcampo de la clase 2 es
  `(lhu@+2<<20)>>26` = **bits 6–11** (comparado con 35 = `0b100011`), no 6–9. Medido además: **5330 y
  6431 son Mágicas de clase 0, aparecen en UNA sola tabla cada una** (T1@`0x1023e4` y T1@`0x1041e4`) y
  **no** tienen clave duplicada en las 4 tablas (136 CardIDs sí están duplicados; estos no) ⇒ el
  despachador **sí** lee T1 para ellas y **el parche estaba donde el motor lee**.
  **La causa real**: `0x79ea0` (resolver de Olla de la Codicia) es un **resolver compartido de «robar
  N»** (31 entradas) que **relee el CardID de la carta que lo llama** (`lhu 0(a0)`) y elige N con un
  switch: **4844 → 2** y **un CardID desconocido → N = 0**, y `blezl s0` **saltea el robo**. También lee
  el bit de dueño (`byte2 bit0 XOR byte3 bit7`) y los globales de estado del jugador; **no** lee
  clase/props/kind, ni `slot8/12/16/20`, ni los globales de carta activa, y **nunca** llama a
  `find_handler`. ⇒ **copiar una entrada literal NO puede transplantar el efecto del donante a otra
  carta: el resolver vuelve a leer el CardID del objetivo.** Eso explica exactamente E19 (5330 y 6431
  cayeron en N = 0 → nada) y por qué A y B se comportaron igual. **El modelo de `entry+4` no queda
  refutado: lo que falló fue la elección del donante.**
- **E22** (T3f, construido y **verificado por el padre**: `verify5: OK`, stub decodificado y
  `ra + 0x32f6c = 0x7c758`): **EXP5**. Donante **4529** (T2@`0x105024`, entrada `{0x7c758, 0, 0, 0,
  0}`, `slot8 = 0`): su resolver `0x7c758` = «**el no-dueño roba 2**» (`v0=1; a1=2;
  a0=1-(byte2&1); jal 0xbebfc`), **independiente de la carta objetivo** ⇒ sirve para cualquier carta.
  Par: **4844** `slot4 → 0x112c60` (nuestro stub reloc-free, `delta 0x32f6c`, `ra = base+0x497ec`) ⇒
  prueba que **nuestro código del 2º `PT_LOAD` se ejecuta**; **5328** `slot4 → 0x7c758` directo ⇒ prueba
  que `entry+4` es **palanca viva**. Sólo cambia `slot4` de cada celda (ambas ya con `R_MIPS_32`);
  `slot8/12/16/20` intactos. `trabajo/b1/libduel_eng_exp5.prx` 1.471.732 B sha256 `ef905398…427`;
  `trabajo/b1/TF1-B1-EXP5.iso` 798.787.584 B sha256 `0651b845…48f`, **4 sectores**
  `[38, 12562, 12564, 12766]`, `.rel.data`/`.rel.text`/tabla de secciones byte-idénticas, recetas F4
  intactas, EXP3/EXP4b reproducibles. Reportes: `trabajo/b1/T3f-DIAGNOSTICO.md`, `trabajo/b1/T3f-EXP5.md`.
  **Predicción con línea base conocida**: 4844 normalmente **le roba 2 a él** ⇒ ahora debe **robar 2 el
  RIVAL** (su mano sin cambios, la del rival +2); 5328 (buscaba un Guerrero) ⇒ ahora **roba 2 el rival**.
  Ambos ⇒ ruta probada de punta a punta y **T4 desbloqueada**; sólo 5328 ⇒ el motor redirige el efecto
  pero nuestro código no corre; **ninguno** ⇒ el modelo cae de verdad.
- **L9** (usuario, verbatim): «Prueba hecha, funciono y tanto olla como refuerzo hicieron que el rival
  robara dos cartas, ahora si guarda sesion».
- **E23** (T3g, **resultado del usuario — ÉXITO**): en `trabajo/b1/TF1-B1-EXP5.iso`, **Olla de la
  Codicia (4844) y Refuerzo del Ejército (5328) hicieron robar 2 al RIVAL** ⇒ las **dos mitades**
  quedan probadas **in-game**: (1) **`entry+4` de la tabla de 24 B es palanca viva** (5328, directo, sin
  código nuevo nuestro); (2) **nuestro código en el 2º `PT_LOAD` se ejecuta** (4844, a través del stub
  **libre de relocalizaciones**). Queda **validada de punta a punta la ruta del frente B** con sus tres
  piezas: **tabla de 24 B + código nuevo libre de relocs + segmento extra RWX**. Y E21 queda confirmado:
  con un donante **card-independiente**, el transplante de efecto **sí** gana.
  Consecuencia inmediata: **T4 queda desbloqueado** — ya no se trata de si la ruta existe, sino de
  escribir el handler del efecto real con las tres restricciones anotadas en la fila de T4.
  Artefactos de la ronda: `trabajo/b1/libduel_eng_exp5.prx` (sha256 `ef905398…427`),
  `trabajo/b1/TF1-B1-EXP5.iso` (798.787.584 B, sha256 `0651b845…48f`).

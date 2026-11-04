# E9 · Referencia: cómo funciona «Cambio de Máscara» en ARC-V Tag Force Special

Exploración **read-only** (2026-11-03). Nada de lo que sigue modifica ISOs ni el motor:
todo se midió sobre copias extraídas a `trabajo/e9/recon/`.

- ISO fuente: `YGO_TFSP_REBOOT - BETA 1.0 (Español) - OFFLINE.iso` (768.542.720 B, raíz del proyecto).
- Listado completo del ISO: `trabajo/e9/recon/iso_tree.txt` (1511 archivos, ISO9660 plano).
- Herramientas usadas: `tools/iso9660.py`, `tools/ehp.py`, y los scripts nuevos de
  `trabajo/e9/recon/` (`tfsp_cardinfo.py`, `tfsp_scan_imm.py`, `tfsp_tables.py`, `dis.py`).

---

## 1. La carta existe y está localizada (medido)

Base de datos del juego: `/PSP_GAME/USRDIR/duelsys/cardinfo_jpn.ehp`
(1.238.704 B, contenedor **EHP v3**: magic `EHP\x03`, marker `"NOT "`, 23 miembros
`CARD_*.bin`). Contiene **7256 cartas** (posiciones 0..7255; la 0 está vacía).

Los nombres están en `CARD_Name_R.bin` en **UTF-16LE plano**; las descripciones
(`CARD_Desc_R.bin`, 546.272 B) están comprimidas (el índice de descripción de las
últimas cartas llega a ~4.370.098 → tamaño descomprimido).

| Carta | posición en el cardinfo | passcode | CardID (campo de 13 bits `p1&0x1fff`) |
|---|---|---|---|
| **Cambio de Máscara** | **4853** | 21143940 (`0x142A184`) | **874** (`0x36a`) |
| Cambio de Máscara II | 5018 | 93600443 (`0x5943ABB`) | 1079 (`0x437`) |
| Cambio de Forma | 4855 | 84536654 | 876 (`0x36c`) |
| Carga de Máscara | 6982 | 87819421 | 3117 (`0xc2d`) |

- El nombre `"Cambio de Máscara"` vive en `CARD_Name_R.bin` en el offset relativo
  `0x30b74` → offset absoluto `0x181128A4` de la ISO. El de `"Cambio de Máscara II"`
  está en `0x327D6` (0x1C62 = 7266 B después).
- `CARD_Indx_R.bin` son **14512 u32 = 7256 pares (offset de nombre, offset de descripción)**.
- `CARD_Pass.bin` = 7256 u32 (passcodes). Ojo: los passcodes repetidos existen
  (p. ej. Burstinatrix aparece 2 veces, posiciones 292 y 2470, con CardID 3844 y 6311).

## 2. El despacho de efectos de TFSP usa el MISMO esquema que TF1

Motor: `/PSP_GAME/USRDIR/gmodule/rel_DuelEng.prx` (6.851.733 B, ELF32 MIPS **little endian**,
3 program headers, `.text` de 4,65 MB).

Se encontraron **4 tablas de entradas de 24 B** `{u32 ID; 5 × u32 slots}` en `.data`,
ordenadas por ID (aptas para búsqueda binaria) — **exactamente el patrón que E7 midió en
TF1** (`libduel_eng.prx`, tablas de 24 B `{u32 CardID; 5×u32}` con despachador en
`.text 0x48d74`):

| tabla | offset en el prx | entradas | rango de IDs |
|---|---|---|---|
| t1 | `0x499974` | 1264 | 3461 .. 8998 |
| t2 | `0x48ec48` | 1206 | 3000 .. 9000 |
| t3 | `0x4addf8` | 745 | 3460 .. 8994 |
| t4 | `0x4a5dc8` | 609 | 3459 .. 8990 |

Total 3824 entradas, 3240 IDs distintos (una carta puede tener más de una entrada; hay
IDs repetidos, p. ej. `3000, 3000, 3000` al inicio de t2).

Los slots 1..4 contienen punteros a `.text` (a veces 0) → cada entrada *apunta a código*,
igual que en TF1.

### 2.1 La entrada de «Cambio de Máscara»  ⚠️ **INVALIDADO — ver §9 (la clave era 13 bits, no 14; ese registro es de otra carta)**

**t2, entrada #167, en `0x48fbf0`:**

```
0x48fbf0   id = 0x12f5 (4853)   w1 = 0x000fc794   w2 = 0x0009ad28   w3 = 0x000c94f4   w4 = 0   w5 = 0
```

Evidencia de que es la carta correcta: las tres entradas consecutivas #167/#168/#169 tienen
IDs **4853, 4854, 4855**, que son las posiciones del cardinfo de
**Cambio de Máscara**, **HÉROE Enmascarado Goka** y **Cambio de Forma** — tres cartas
consecutivas de la misma tanda. (Además `Carga de Máscara`, posición 6982, tiene entrada
en t4 #251 en `0x4a7550`: `{0x1b46, 0xf1198, 0x98ebc, 0x1a85e4, 0, 0}`.)

Forma de los punteros de esa entrada (desensamblado con `trabajo/e9/recon/dis.py`):

- `w1 = 0xfc794` → función **grande** con un switch sobre `lhu a1,0(a0)` comparando contra
  constantes `9757, 8662, 10530, 10186, 11070, ...` (ramas). Tiene pinta de *handler de
  resolución de efecto*, compartido por muchas cartas.
- `w2 = 0x9ad28` → predicado chico (`jal 0x86940`, compara `lhu 2(s0)` con un argumento y
  devuelve 0/1).
- `w3 = 0xc94f4` → predicado chico: `lhu 4(a1) < 13`, `lhu 8(a1) == 0`, compara `2(a0)` con
  `2(a1)` y termina en `xori v0, v0, 0x10F6`.

### 2.2 Hallazgo lateral: «Cambio de Máscara II» no tiene entrada

La posición 5018 (**Cambio de Máscara II**) **no aparece en ninguna de las 4 tablas**
(búsqueda exhaustiva de `0x139A` como u32 alineado en toda el área cargada: 0 coincidencias).
Hipótesis a verificar in-game: **TFSP no la tiene implementada** (existe en la base pero sin
efecto). Es la misma familia que las otras tres, que sí tienen entrada.

## 3. Preguntas abiertas (honestas)

1. **Correspondencia ID ↔ carta**: los IDs de las tablas llegan a **9000** y las funciones
   referenciadas comparan IDs de hasta **11070**, mientras el cardinfo del mod tiene 7256
   posiciones. O sea, el *espacio de IDs del motor* es más amplio que el cardinfo que trae
   esta ISO. La coincidencia consecutiva 4853/4854/4855 identifica sin duda la entrada, pero
   **no** está cerrado cómo se indexa el motor. Candidato a resolver con las listas de
   recetas (`deck/all_j.ehp`, `deck/recipe_view.ehp`, y la lista de recetas dentro de
   `EBOOT.BIN`, ELF MIPS de 2.059.817 B donde `"Cambio de Máscara"` está en `0x149C56`).
2. **No hay referencias directas a las bases de tabla** (`lui`+`addiu`) en el `.text` de
   `rel_DuelEng.prx` → el consumidor (despachador) no se localizó por ese método; hay que
   buscarlo por otras vías (patrón de búsqueda binaria stride 24, u otro `.prx`).
3. **Rol de cada slot**: en TF1 el despachador leía `entry+8`; en TFSP `entry+8` de esta
   carta es un predicado chico, así que el rol de los 5 slots debe confirmarse leyendo el
   consumidor antes de sacar conclusiones.

## 4. Lectura para el port a TF1

- TFSP implementa el efecto en **código MIPS del mismo ISA** que TF1 (ambos PSP) ⇒ si se
  aísla el handler, es material de referencia **directamente comparable**, no una mera
  descripción funcional.
- TFSP resuelve el despacho con **el mismo esquema de datos que TF1** (tablas de 24 B con
  slots de punteros). Eso refuerza que la vía de E7 (extender tablas del motor) es la vía
  del propio linaje, no una invención.
- TF1 hoy: 4704/4721/4726/4730 tienen **0 entradas y 0 inmediatos de código** (medido en E7)
  ⇒ sigue haciendo falta código nuevo + espacio para él. TFSP es el modelo a copiar.
- Contexto de esfuerzo: `.text` de TFSP es 4,65 MB contra ~1 MB de TF1, coherente con un
  handler por carta/efecto.

## 5. Próximos pasos concretos (cuando se retome)

1. Encontrar el **despachador** de las tablas de 24 B en TFSP (punto 3.2) y documentar el rol
   de cada slot.
2. Aislar el **handler de Cambio de Máscara** y mapear sus llamadas al motor: mover al
   Cementerio, Invocación Especial del Deck Extra filtrada por atributo, y la restricción
   «no es Invocación por Fusión / no en Damage Step».
3. Cerrar la numeración ID ↔ carta (punto 3.1) con las listas de recetas.
4. Confirmar in-game si **Cambio de Máscara II** no tiene efecto en TFSP (punto 2.2).

## 6. Segunda ronda: cacería del despachador (resultado: **negativo medido**)

Se intentó localizar el código que consume las tablas de 24 B. Todo lo que sigue es medido
sobre `trabajo/e9/recon/rel_DuelEng.prx` (scripts `dispatch_find.py` y sondas inline).

### 6.1 Hechos de layout que sí quedaron claros

- `rel_DuelEng.prx` tiene **un solo `PT_LOAD`** que cubre `0x0..0x4DD038` (RWX); luego
  `.bss` en `0x4DD040` (memsz `0x7ECF0`). Los dos bloques grandes `0x4DD8E4` (1,4 MB) y
  `0x632A84` (352 KB) tienen **`memsz = 0` ⇒ no se cargan**.
- Las 4 tablas caen en la sección 24 (`vaddr 0x471748`, flags `0x2` = **ALLOC sin WRITE**)
  ⇒ son **`.rodata`**: tablas `const` de registros con punteros a código, tal como las emite
  el compilador para un despacho. (Las análogas de TF1 también eran datos estáticos.)
- `sceModuleInfo` (vaddr `0x46FB38`) dice `modname = 'modduel_eng'` y **`gp = 0`** ⇒ no hay
  small-data: la hipótesis de referencias `gp`-relativas queda descartada.
- El bloque no cargado de `0x632A84` contiene entradas `{u32 type; u32 addr}` con
  `type = 2` (R_MIPS_32) y `addr` recorriendo **los campos de la tabla t2**
  (`0x48EC30, 0x48EC34, 0x48EC38, 0x48EC44, 0x48EC48, 0x48EC4C, 0x48EC54, 0x48EC5C …`)
  ⇒ al menos confirma que el cargador trata esos campos como **punteros**.

### 6.2 Negativos medidos (por qué no se llegó al consumidor)

1. **Ninguna instrucción de `.text` forma las bases de tabla.** Barrido completo de pares
   `lui`+`addiu/ori` en los 4,65 MB: 0 referencias a `0x48EC48 / 0x499974 / 0x4ADDF8 /
   0x4A5DC8`. Y los immediatos bajos `0x9974 / 0xEC48 / 0xDDF8 / 0x5DC8` aparecen 2 veces
   en todo `.text`, ambas en `beq` (op `0x14`/`0x04`), no en cargas.
2. **Ninguna celda de datos apunta a las tablas.** En el área cargada: `0x499974`,
   `0x4ADDF8`, `0x4A5DC8` → **0 apariciones**; `0x48EC48` → **1 aparición**, en `0x64B3A4`,
   que está dentro del bloque **no cargado**.
3. **La clave de «Cambio de Máscara» (4853) casi no aparece.** En el área cargada sólo hay
   3 immediatos de código (`addiu a2,zero,4853` en vaddr `0x082084`, `0x0993F8`, `0x203DC8`,
   rodeados de 5658/5400/6880/7432/7651 ⇒ rutinas de **listas de cartas**, no de efectos) y
   el registro de la tabla en `0x48FBF0`.
4. **`EBOOT.BIN` no tiene copia de la tabla.** ELF32 MIPS, `PT_LOAD` único de 1,77 MB:
   0 apariciones alineadas de `4853`, `4855`, `6982` (3 espurias de `5018`).
5. **Sólo 4 sitios en todo `.text` calculan `x*24`** (vaddr `0x1FCEC`, `0x1FDA0`, `0x1FE7C`,
   `0x1FF30`) y pertenecen a **una** función que opera sobre un array de registros de 24 B
   en **`.bss`** (`lw/sw …,6976(v1)` con `v1 = idx*24 + base`): no son nuestras tablas
   ⇒ la aritmética del consumidor no está expresada como `x*24` en `.text`.
6. Los 70 sitios `jalr` cuyo destino viene de un `lw` con offset ≤ 40 no discriminan nada.

### 6.3 Lectura honesta del negativo

Dentro de `rel_DuelEng.prx` **no hay ninguna referencia estática** a esas tablas: ni
immediatos, ni celdas de datos. Con tablas `const` en `.rodata` las salidas posibles son:

- **(i)** el consumidor vive en **otro módulo** y recibe la base por una *variable importada*
  (en PSP eso se resuelve con un stub parcheado al cargar ⇒ la dirección de la tabla **no
  aparece** en el archivo del importador); o
- **(ii)** el consumidor obtiene la base desde el bloque no cargado (`0x632A84`), que ya
  demostró enumerar los campos de la tabla.

### 6.4 Próximas sondas concretas (en orden de costo)

1. **Empírica (la más informativa, mismo método que funcionó en E7 con EXP1):** parchear el
   registro de «Cambio de Máscara» en una copia de la ISO — p. ej. apuntar los 3 slots a la
   función común `0x1A85E4`, o intercambiar `w2`/`w3` — y ver en PPSSPP si el efecto cambia.
   Eso confirma de una vez que el registro **es** el despacho de ese efecto y revela qué slot
   es el efecto y cuál la condición de activación.
2. **Estática:** parsear bien las tablas *export/stub* del módulo (`ent_top = 0x46FA5C`,
   `stub_top = 0x46FA84`) para ver si las tablas están exportadas, y buscar en los otros
   24 `.prx` (y en `EBOOT.BIN`) un import de `modduel_eng` que reciba esa variable.
3. **Cerrar la numeración** de la clave (4853 ↔ carta): comparar el espacio de ids del motor
   (las funciones referenciadas comparan contra `8662 / 9757 / 10530 / 11070`, muy por encima
   de las 7256 posiciones del cardinfo del mod) con las listas de recetas.

## 7. Protocolo del test A (acordado con el usuario)

Secuencia: (1) ISO **normal** + cheat de todas las cartas ⇒ armar un deck HÉROE
Enmascarado, **guardar con el cheat activo**; (2) duelo **de referencia** en la ISO normal:
activar «Cambio de Máscara» y anotar qué pasa; (3) abrir `TFSP-E9-A1.iso` con el mismo save
(compatible: el parche sólo toca el `.prx`, no el save) y repetir el duelo; (4) comparar.

Clave de lectura (de la más fácil de ver a la más fina):

- **Señal 1 — filtro de activación.** Con el parche, «Cambio de Máscara» hereda el predicado
de «Cambio de Forma»: si deja de dejarse activar con un HÉROE cualquiera en el campo y sólo
acepta un **Fusión HÉROE**, los slots de predicado del registro gobiernan la carta.
- **Señal 2 — destino del monstruo.** Referencia (ISO normal): manda el HÉROE al
**Cementerio** y baja un HÉROE Enmascarado del **mismo atributo**. Con el parche: el Fusión
vuelve al **Deck Extra** y baja un HÉROE Enmascarado del **mismo Nivel** con otro nombre.
- **Señal 3 — recíproca.** «Cambio de Forma» debe pasar a comportarse como «Cambio de
Máscara» (Fusión al Cementerio + mismo atributo).

Interpretación: cualquiera de las tres señales ⇒ **el registro ES el despacho** y la clave es
la posición de la carta ⇒ quedan habilitados los 3 punteros de código del efecto
(`0xFC794` switch sobre `lhu 0(a0)`, `0x9AD28`, `0xC94F4`) como referencia del port.
Ninguna señal ⇒ el registro no gobierna el efecto (o la clave vive en otro espacio de ids);
siguiente sonda: mismo swap usando 2-3 cartas que estén seguro en el deck.

## 9. CORRECCIÓN (tras el test A) — el id del motor son 14 bits, no 13

El test A dio **negativo** (con el payload swapeado, «Cambio de Máscara» resolvió normal). La
causa se midió después y **invalida la identificación del §2.1**: parcheamos el registro de
otra carta.

**Hallazgo**: la clave del despacho es **`CARD_Prop.prop1 & 0x3FFF` (14 bits, 0..11657)**, no
la posición en el cardinfo ni el campo de 13 bits. Evidencia: la máscara de 14 bits cubre
**99.9% (3236/3240)** de las claves de las tablas y **contiene las 5 constantes del switch**
(9757, 8662, 10530, 10186, 11070); la de 13 bits cubre 80.8% y no contiene ninguna.

**Id reales**: «Cambio de Máscara» **9066**, «Cambio de Forma» **9068**, «Cambio de Máscara II»
**9271**, «Carga de Máscara» **11309** (y sí tienen registro: la afirmación previa de que
«Cambio de Máscara II no tiene entrada» era un artefacto del espacio de claves equivocado).

**Las tablas estaban truncadas en §2**: el detector filtraba claves ≤ 9000 y cortaba los runs.
Las tablas reales suman ~**7663 registros** en `0x4785EC..0x4B6FA8` de `.rodata`; las 4 que
reporté (1264/1206/745/609) eran fragmentos. Script corregido: `recon/tfsp_tables2.py`.
Lección metodológica: un filtro de rango sobre una tabla **ordenada** trunca la tabla y hace
creer que el rango de ids termina donde termina el filtro.

### 9.1 Registros reales (prx file offsets)

| carta | id | offset | w1 | w2 | w3 | w4 | w5 |
|---|---|---|---|---|---|---|---|
| Cambio de Máscara | 9066 | `0x495E60` | `134dac` | `9a4f0` | `c2918` | 0 | `16ffe0` |
| Cambio de Forma | 9068 | `0x495E78` | `134dac` | `9a4f0` | `c2918` | 0 | `170000` |
| Cambio de Máscara II | 9271 | `0x496280` | `134dac` | `9a4f0` | `c4224` | `b04b8` | `16ffe0` |
| Carga de Máscara | 11309 | `0x499268` | `fae10` | 0 | `cccc4` | 0 | `17469c` |

### 9.2 El sistema de efectos de TFSP es un intérprete de códigos

Los slots son funciones, y el que **distingue** a las cartas es un **thunk**:
`j 0x16FCA8` con el código descriptor en el delay slot (`addiu a2,zero,CODE`).

- **«Cambio de Máscara» y «Cambio de Forma» son idénticos salvo ese código: 58 vs 79.**
- «Cambio de Máscara II» comparte el código 58 y cambia w3/w4.

También quedó localizado el **predicado de activación de la familia** en vaddr `0x09A520`:
cadena que compara `lhu 0(s0)` contra 9068/9066/9271/7162/10326/11510 y chequea flags
en `+14` y `+2` del struct de carta; para 9066 devuelve «activable» directo.

### 9.3 Qué significa para el port a TF1

La referencia útil ya no es «el código del efecto» (en TFSP es un intérprete de códigos), sino:
(a) la **spec funcional** (que ya está verbatim en `datos/efectos_heroes_enmascarados.txt`), y
(b) que **la diferencia entre Cambio de Máscara y Cambio de Forma es una sola decisión**:
qué monstruo del Deck Extra invoca (mismo **atributo** vs mismo **Nivel**).

### 9.4 Próximos pasos (corregidos)

1. Leer `0x16FCA8` y su tabla de códigos ⇒ semántica del código 58 y 79 (filtro + orden de
   pasos: mandar al Cementerio, invocar del Deck Extra, restricciones).
2. Sonda corregida y mínima (**1 palabra**): cambiar el código del registro real de MC
   (58 → 79) y ver en PPSSPP si pasa a comportarse como Form Change. Ahora sí es concluyente
   (el ISO `TFSP-E9-A1.iso` queda invalidado como sonda de MC).

### 9.5 El intérprete (vaddr `0x16FCA8`) — caracterizado

Es una rutina **compartida de «ejecutar paso de efecto»**, no una función por carta:

- Entrada: `a0` = struct de carta, `a1` = contexto, **`a2` = el código del thunk** (queda en `s2`).
- Ramifica por **id de carta** (`lhu 0(s0)` contra 7595, 10668, 7495, 3511, 8569, 8688, …) y usa el
  **código como parámetro de variante** (p. ej. `if code == 101 -> s5 = 49`).
- Llama helpers del motor (`0x1A9C54`, `0x1B50F0`, `0x1BDF6C`, `0x1BE24C`, `0x1B5270`…) y pasa una
  **tabla de parámetros en `0x1A9420`** (`lui a3,0x1b; addiu a3,a3,-0x6be0`).
- Cuenta/marca estado en `0x79F0C` (`lw/sw 3012(s1)` con `s1 = 0x79348`).

⇒ En TFSP el efecto es **registro de datos + intérprete compartido**: los slots del registro son
los pasos y el código del thunk es el parámetro que elige la variante concreta. No hay «código de
Cambio de Máscara» que se pueda copiar textualmente; lo copiable es la **estructura** y la
**diferencia** (código 58 vs 79 + los otros tres slots compartidos).

### 9.6 Sonda corregida «B» (lista para probar)

Perfil activo de `tools/e9_expA.py`: swapea **sólo el thunk** entre los dos registros reales
(MC `0x16FFE0` código 58 ↔ Form Change `0x170000` código 79; los otros cuatro slots ya son
idénticos, así que el diff son 6 bytes). ISO: `trabajo/e9/TFSP-E9-A2.iso`.
`trabajo/e9/TFSP-E9-A1-INVALID.iso` queda renombrado como inválido (parcheaba el registro de
otra carta).

Clave de lectura, igual que antes pero ahora sobre el registro correcto: activando «Cambio de
Máscara» debe pasar a resolver como «Cambio de Forma» (el Fusión vuelve al **Deck Extra** y baja
un HÉROE Enmascarado del **mismo Nivel**) en vez de mandarlo al **Cementerio** y bajar uno del
**mismo atributo**. Si el código es la palanca, además el filtro de resolución debería exigir un
Fusión HÉROE. Si **no** cambia nada, la conclusión es que el intérprete decide por **id de carta**
y el registro sólo aporta el flujo de pasos.

**Barrido hecho (negativo útil)**: el intérprete de `0x16FCA8` **no compara el código contra 58
ni 79** (0 cargas en `0x16FCA8..0x16FFD0`), y un barrido global de comparaciones contra `s2`
sólo devuelve ids de carta ⇒ la semántica del código **no** está en un `if (code == 58)`:
o se resuelve por **tabla**, o vive en los otros slots. Los candidatos reales para el trabajo
son los slots que MC **comparte** con Form Change (`w1 = 0x134DAC`, `w2 = 0x9A4F0`,
`w3 = 0xC2918`); el código 58/79 sólo distingue la variante. Próximo paso si se retoma:
seguir el flujo de `0x134DAC` / `0xC2918` y/o la tabla de parámetros `0x1A9420`.

### 9.7 Resultado del test A2 — **concluyente (negativo)**

Prueba in-game (PPSSPP, `TFSP-E9-A2.iso`, save con 3 copias de MC): «Cambio de Máscara» sobre
**HÉROE Elemental Nova Master** (Fusión, FUEGO, **Nivel 8**) ⇒ invocó **HÉROE Enmascarado Goka**
(Fusión, FUEGO, **Nivel 6**).

- Coincide el **atributo** (FUEGO) y **no** el **Nivel** (8 → 6) ⇒ la resolución aplicó la regla de
  «Cambio de Máscara» (mismo **atributo**), no la de «Cambio de Forma» (mismo **Nivel**), con el
  thunk del código ya swapeado (58 → 79).
- ⇒ **El código de script del registro (`w5`) no es la palanca de la resolución**: la semántica la
  decide el **id de carta** dentro del intérprete compartido (`lhu 0(s0)`), coherente con las ramas
  leídas en `0x16FCA8`.
- Confirmaciones laterales del test: un **Fusión HÉROE** es objetivo válido de MC (Nova Master lo fue)
  y el registro/punteros no alteran la elegibilidad del objetivo.
- Nota de método: el filtro de **activación** no discrimina (MC y Form Change **comparten** la función
  de condición `w2 = 0x9A4F0`, que ramifica por id). La señal válida es la **resolución**.

**Consecuencia para el port a TF1**: TFSP **no** entrega un handler de efecto reutilizable como dato;
un efecto del linaje es `registro por carta + intérprete compartido keyed por id`, así que en TF1 hay
que escribirlo como **código** (mismo camino que concluyó E7). Lo que sí aporta como referencia: la
estructura, la lista de decisiones de diseño del efecto (filtro por atributo + Invocación Especial
desde el Deck Extra + las dos restricciones) y la diferencia mínima con Cambio de Forma.

## 10. Artefactos de esta exploración

`trabajo/e9/recon/`: `iso_tree.txt`, `cardinfo_jpn.ehp`, `rel_DuelEng.prx`, `EBOOT.BIN`,
`recipe_view.ehp`, `all_j.ehp`, `tfsp_cardinfo.py`, `tfsp_scan_imm.py`, `tfsp_tables.py`, `dis.py`.

Todo esto es gitignored (carpeta de trabajo); nada commiteado: la entrega de la rama
`spike/e1-test` sigue pendiente de decisión del usuario (PRs encadenados).

# E8 — Arte de carta: usar imágenes de EDOPro

Estado: **ronda 3 cerrada**, con la vía técnica resuelta. Pendiente: el pipeline definitivo
(producir e inyectar el arte de las 18) y la elección final tamaño/colores.

Rondas: E8-1 (contenedor + dialecto GIM) · E8-2 (primer centinela: el motor acepta nuestro
formato) · E8-3 (matriz de formatos).

---

## 1. Resultado de un vistazo

| Pregunta | Respuesta | Evidencia |
| --- | --- | --- |
| ¿El motor dibuja un GIM hecho por nosotros? | **SÍ** | Centinela magenta/lima con banda blanca apareció en el recuadro de Avian (ISO `TF1-E8-F5`) |
| ¿Acepta el formato 4 (INDEX4, 4 bpp)? | **SÍ** | Bladedge: cuadrantes + X blanca (ISO `TF1-E8-M2`) |
| ¿Acepta una paleta de 16 entradas? | **SÍ** | Clayman: colores exactos, X negra (ISO `TF1-E8-M2`) |
| ¿Cuál es el lienzo que llena el recuadro? | **~64×56** (proporción 1.14) | 64×56 llena; 128×56 deja banda (letterbox) |
| ¿Se puede leer el formato 8 nativo? | **NO** | Negativo limpio tras búsqueda exhaustiva; ya no hace falta |
| ¿El arte lleva el nombre pintado? | **NO** (en el álbum) | Ver §3.4 y §3.5 |

**Consecuencia**: el arte de las 18 es un problema nuestro, no del juego. Escribimos el
formato que queremos y el motor lo dibuja.

---

## 2. Specs

- **S1** — «para el arte es posible usar las imagenes de edo pro tanto para las cartas
  grandes [...] y las pequeñas».
- **S2** — Antes de prometer arte, construir el visor: extraer y **ver** una carta real a
  tamaño nativo. Decidido por el usuario como paso 1 (E8-1).
- **S3** — Si el visor no alcanza, no seguir descifrando el formato nativo: **escribir
  nuestro propio formato** y comprobar si el motor lo dibuja (decisión del usuario, E8-2).
- **S4** — El arte del álbum **no** se edita por idioma (medido: ver §3.5).
- **S5** — Nada de esto modifica el ISO original ni los artefactos de E6: todo son archivos
  nuevos y los `.cip` prístinos se conservan.
- **S6** — Toda afirmación sobre el arte se valida **mirando la imagen**, nunca con un
  checksum. Un decodificador puede satisfacer un round-trip byte a byte y aun así ser falso.
- **S7** — «Vamos ahora si a inyectar el arte de edopro al TF1» (E8-4): el arte de las 18 se
  inyecta en **slots propios**, no aliasados. Cada CardID 4661..4730 recibe su propio slot en
  `cardh_s.cip` y `cardm_s.cip`; las cartas donantes **conservan su arte intacto**.
- **S8** — **Ninguna carta existente cambia**: los slots nuevos se agregan al final del
  contenedor y las 2527 entradas de tabla existentes quedan byte a byte idénticas. Los
  contenedores crecen y se reubican en el espacio libre del ISO (región de `UPDATE/DATA.BIN`).
- **S9** — El arte se produce a la **geometría nativa del recuadro**, no a la proporción de la
  ilustración: `cardh` **128×56 en formato 4 (INDEX4, 16 colores)** y `cardm` **64×48 en formato
  4**. Una textura de 64 de ancho **no** llena el recuadro: el motor dibuja 1:1 contra un destino
  de 128×64 y deja la mitad derecha con VRAM sucia (medido en E8-4, §9.6).

---

## 3. Hechos medidos

### 3.1 Contenedor CIP/CPM

- Archivos: `PSP_GAME/USRDIR/card/cardh_{e,f,g,i,s}.cip` (CIP) y `cardm_{e,f,g,i,s}.cip` (CPM).
- Header de 48 B: `@0x10` HeaderSize (dónde empiezan los blobs), `@0x14` MinCardNumber = 4007,
  `@0x18` MaxCardNumber = 6957, `@0x1C` OffsetTableTop = 48, `@0x20` BitshiftSize (2 cardh / 1 cardm).
- Tabla: 8 B por CardID en `OffsetTableTop + (cardid − MinCardNumber) × 8`.
  **`offset = campo_A << 11`**; el segundo u32 es padding 0.
- `cardh_s.cip`: 10.375.168 B, stride de slot **exactamente 4096**; base de blobs 24576.
  `cardm_s.cip`: 5.199.872 B, stride 2048.
- 2527 artes sobre 2479 CardIDs, 37 cartas con variantes de arte, 472 entradas en cero.
- **Prueba**: `encode(decode(payload)) == payload` en los 2527 y rebuild del contenedor entero
  con sha256 idéntico (`cardh` 1fb9b5dd…, `cardm` 131ac03c…).

### 3.2 Dialecto GIM de TF1 (resuelto)

- Archivo = magic 16 B + cadena de bloques desde 0x10. Cabecera de bloque 16 B:
  `u16 type, u16 pad, u32 size, u32 next (relativo al bloque), u32 0x10`. Tipos 2/3 = wrappers,
  5 = paleta, 4 = imagen.
- Cabecera de imagen/paleta, 0x40 B en `bloque+0x10`: `u16 headerSize=0x30, u16 pad, u16 format,
  u16 flags, u16 width, u16 height, u16 bpp`, y `u32 @+0x20 = 0x40 + payload`.
- Textura en `cabecera_imagen + 0x40`.
- **format 3 = RGBA8888 (32 bpp)** · **format 4 = INDEX4 (4 bpp, el píxel izquierdo va en el
  nibble BAJO)** · **format 5 = INDEX8 (8 bpp)**.
- Paleta = bloque tipo 5; **la cantidad de entradas es variable** y se lee de su cabecera
  (256 × RGBA8888 = 1024 B en el caso clásico; se probaron 16 y funcionan).
- **Swizzle del GE de PSP**: unidades de 128 B = 16 B de ancho × 8 filas; unidades en orden de
  fila sobre `(rowBytes/16) × (height/8)`. Exige altura múltiplo de 8.
- **format 8 (el nativo de las cartas): NO descifrado.** Ver §3.3.

### 3.3 El header de 128 B de los slots de carta es plantilla

Los **2547 slots** de `cardh_s.cip` tienen los **primeros 128 bytes idénticos** (un solo hash).
Esos 128 B son magic(16) + 2 wrappers(32) + cabecera de bloque de imagen(16) + cabecera de
imagen(64). Solo los 3968 B siguientes son por carta.

El header declara `128×64` a 4 bpp = 4096 B, que **no entra** en los 3968 disponibles (y el
bloque declarado, 4176 B, se pasa del slot). O sea: **la geometría declarada es vestigial**,
copiada de un GIM más grande. Los campos "de tamaño" (0x1070/0x1060/0x1050/0x1040) tampoco son
tamaños: cada uno vale `0x1080 − inicio_de_bloque`.

### 3.4 El arte es SOLO el recuadro de la ilustración

> **CORREGIDO en §9.9 (E8-8).** La textura nativa de `cardh` **sí** incluye la banda del nombre
y relleno con clave de color verde; no es solo la ilustración. Lo que el motor dibuja aparte es el
marco, el texto de efecto y el ATK/DEF. El nombre pintado en el arte —lo que el usuario había dicho
desde el principio— aplica también a `cardh`.

Confirmado en pantalla: el marco de la carta, la barra del nombre, el texto del efecto y el
ATK/DEF los dibuja el motor como capas aparte. La imagen del arte cubre únicamente el recuadro
de la ilustración. El motor **escala** la textura al recuadro y **letterboxea** si la proporción
no coincide.

Esto simplifica todo: **no hay que dibujar la carta, solo la ilustración**, y el nombre nunca se
toca. El arte recortado de EDOPro (sin marco) es el insumo correcto — no el render completo.

### 3.5 El arte es independiente del idioma

`cardh_s.cip` y `cardh_e.cip` coinciden entre **99,8% y 100%** byte a byte en la misma carta
(dos de cuatro muestras idénticas del todo). El archivo está duplicado por idioma pero el
contenido **no** se diferencia. Corrección anotada también en `ESTADO-E6.md` §12.A.

---

## 4. La matriz de formatos (E8-3) y su resultado

ISO `trabajo/e8/TF1-E8-M2.iso` (copia de `TF1-E6-18.iso`; difiere en **4 sectores**, todos dentro
del extent de `cardh_s.cip`). Dos centinelas, ambos en slots de arte **exclusivos y únicos**:

| Carta | Slot | Formato | Lienzo | Patrón | Resultado en pantalla |
| --- | --- | --- | --- | --- | --- |
| Bladedge (6477) | 4512 | 4 (INDEX4) | 128×56 | marco cyan, X blanca, 4 cuadrantes | **Dibujado**, pero **letterboxed**: deja banda abajo |
| Clayman (6312) | 4236 | 5 (INDEX8) | 64×56 | marco amarillo, X negra, 4 cuadrantes | **Dibujado y llena el recuadro entero** |

Lectura:

1. **Formato 4 aceptado** → el motor despacha por código de formato del GIM.
2. **Paleta de 16 entradas aceptada** → la cantidad de entradas de la paleta es variable de verdad.
3. **La proporción del recuadro es ~1,14** (64×56), no 2,29. El motor escala por ancho y
   letterboxea el resto: la banda que sobraba en Bladedge era relleno, no rechazo.

Cada canary costó 3856 B de los 4096 del slot, con **240 B de holgura**.

---

## 5. Presupuesto del slot y la decisión que queda

Overhead fijo de un GIM propio: 16 (magic) + 32 (wrappers) + 16 + 64 (cabecera de paleta) +
16 + 64 (cabecera de imagen) = **208 B**, más **4 B por entrada de paleta**.

Con `p` colores y `w×h` píxeles a 8 bpp:

| Lienzo | Colores posibles | Comentario |
| --- | --- | --- |
| 64×56 | hasta **76** | proporción nativa, llena el recuadro |
| 64×48 | hasta **204** | 8 filas menos, 2,7× colores |
| 64×40 | **256** (tope) | el de E8-2; no llena, el motor escala |

A 4 bpp (formato 4) el mismo slot da el doble de píxeles (128×56 = 3584 B), pero cualquier lienzo
de proporción 2,29 se letterboxea, así que el ancho extra se desperdicia salvo que se use para
más alto (64×112) — y eso excede el recuadro.

**Recomendación**: 64×56 con la mayor cantidad de colores que entre (~76). Es la proporción
nativa y la mejor relación nitidez/color. La alternativa defendible es 64×48 con ~204 colores si
la cuantización a 76 colores se ve sucia en una ilustración concreta.

---

## 6. Lo que falta

- **T1** — Pipeline definitivo: arte recortado de EDOPro → recorte al recuadro (proporción 1,14) →
  cuantización a `p` colores → `build_gim_format5(64, 56, …)` → `inject` en el slot de cada carta.
- **T2** — Decidir `p` mirando 2-3 cartas reales cuantizadas a 76 y a 204 colores.
- **T3** — Aplicar a las 18 cartas de E6 (recordar §3.5: **un solo idioma**, no cinco).
- **T4** — Elegir la fuente del arte: EDOPro / ygoprodeck publican el arte **recortado**, que es
  justo lo que este pipeline necesita.

---

## 9. Ronda E8-4 — pipeline definitivo (en curso)

Objetivo: producir e inyectar el arte recortado de las 18 en un ISO nuevo, partiendo de
`trabajo/e6/TF1-E6-18.iso`. Tareas **T5..T10** (continúan T1..T4).

### 9.1 El problema de espacio (medido, no supuesto)

`cardh_s.cip` y `cardm_s.cip` del ISO de E6 tienen **2527 slots físicos y los 2527 están
referenciados**: no hay slot libre. Las 18 cartas nuevas **no tienen slot propio**: E6 les copió
la entrada de 8 bytes del donante, así que hoy **comparten slot** con él.

Entradas actuales (CardID → slot cardh / slot cardm): 4661→4624/2318 · 4665→4974/2493 ·
4671→4532/2272 · 4672→4792/2402 · 4673→4534/2273 · 4681→4790/2401 · 4684→4806/2409 ·
4686→4492/2252 · 4689→4810/2411 · 4690→4978/2495 · 4696→4782/2397 · 4697→4958/2485 ·
4699→*alt*[4232,4234]/[2122,2123] · 4701→4376/2194 · 4704→4996/2504 · 4721→4668/2340 ·
4726→*alt*[1660,1662]/[836,837] · 4730→4328/2170.

Aritmética del contenedor:

| | `cardh_s.cip` | `cardm_s.cip` |
| --- | --- | --- |
| `bitshift` / stride | 2 / **4096** | 1 / **2048** |
| `blob_base` | 24576 | 24576 |
| tamaño / slots | 10.375.168 B / 2527 (slots 12..5064, paso 2) | 5.199.872 B / 2527 (slots 12..2538, paso 1) |
| `total_size` @0x04 | = tamaño de archivo | = tamaño de archivo |
| último slot | 5064 @ 10.371.072 | 2538 @ 5.197.824 |

**Slots nuevos**: cardh 5066, 5068, …, 5100 (18) → archivo 10.448.896 B (5102 sectores);
cardm 2539, 2540, …, 2556 (18) → archivo 5.236.736 B (2557 sectores). Entrada = 8 B
`<u32 slot, u32 0>` en `table_top + (cardid − 4007) × 8`; hay que actualizar `total_size` @0x04
(espejo de 4 B en BE, igual que el resto del header: **verificar cómo está escrito**).

### 9.2 Reubicación en el ISO (plan)

Región libre medida en `TF1-E6-18.iso` (`tools/e6_iso_space.py`): **LBA 3646..10639**
(6993 sectores, 14,3 MB), justo después de `cardinfo_spa.ehp` (LBA 3091, 555 sectores).
Además quedó libre el extent viejo de `cardinfo` (LBA 331709, 550 sectores).

Plan (cabe porque los contenedores crecidos no entran juntos en la región libre):

1. `cardh_s.cip` crecido (5102 sectores) → **LBA 3646**.
2. `cardm_s.cip` crecido (2557 sectores) → **extent viejo de `cardh_s.cip`, LBA 251955**
   (5066 sectores: entra holgado).
3. Actualizar **los dos** directory records (extent + tamaño, LE y BE) con
   `e6_iso_space.relocate_record` / `iso_replace.find_record`.

### 9.3 Fuente del arte y parámetros

- Arte **recortado** de ygoprodeck (= el CDN que usa EDOPro). Baja a
  `trabajo/e8/art_src/<cardid>.jpg`; el manifiesto con passcodes y URLs es
  `trabajo/e8/art_src/manifest.tsv`. Las 18 son **624×624** y ya están convertidas a PNG.
- El tooling es stdlib y **no lee JPEG**: la conversión usa PowerShell `System.Drawing`
  (`trabajo/e8/_conv_all.ps1`).
- **Falta** en `tools/tf1_art.py`: remuestreo por **área/box** (el `resize_nearest` actual aleja
  demasiado a 624→64) y recorte a proporción; opcional **dithering** Floyd–Steinberg.
- Parámetros por defecto: **cardh 64×56 con 76 colores** (= 4096 B exactos), **cardm 32×24 con
  256 colores** (2000 B en 2048). El motor escala por ancho y letterboxea (E8-3).

### 9.4 Tareas

| ID | Tarea | Spec |
| --- | --- | --- |
| T5 | `tools/tf1_art.py`: `resize_area`, `cover_crop`, dithering opcional; `inject` con `--resample area` y `--dither` | S6 |
| T6 | `tools/tf1_art18.py` `preview`: hoja comparativa (p. ej. 3 cartas × 76/204 colores) para fijar `p` | S6, T2 |
| T7 | `tools/tf1_art18.py` `build`: 18 arts propios en cardh/cardm (slots nuevos, tabla, `total_size`) | S7 |
| T8 | Reubicación de los dos contenedores + ISO nuevo con records actualizados | S8 |
| T9 | Aceptación: diff por sectores confinado a los dos extents nuevos, decode-back píxel a píxel, `verify` de contenedores, `diff` contra el ISO de E6 | S6, S8 |
| T10 | Prueba del usuario en PPSSPP y cierre del handoff | S6 |
| T11 | Códec nativo de `cardm` (DXT1 64×64 con palabras intercambiadas) | §9.8 |
| T12 | ISO definitivo: `cardh` 128×56 f4/16 + `cardm` DXT1 64×64 | S7, S8, S9 |

### 9.6 Resultado del test in-game y corrección de geometría (T10, parcial)

El usuario subió 18 capturas del detalle de carta a `trabajo/Resultados art e8/`. Lectura:

1. **Lo bueno**: las 18 muestran su ilustración correcta, distinta y reconocible (se acabó el
   arte del donante). El formato 5, la paleta de 76 entradas y el dithering se dibujan bien.
2. **El defecto**: la ilustración ocupa **solo la mitad izquierda (~57%) del recuadro**; la mitad
   derecha queda negra con rayas (VRAM sucia). Medido recortando la ventana y comparando lado a
   lado contra el canvas inyectado: el arte **no está distorsionado, está cortado**, o sea el motor
   lo dibuja **1:1 contra un destino de 128 de ancho** y nuestros 64 px cubren la mitad.

Esto **corrige** la lectura de E8-3 (`INTERPRETACION-E8-M2.md`): el caso real era
«A llena el ancho; B no», es decir **W128**, no W64. Encaja con: el encabezado nativo de `cardm`
(`CPM_GIMHEADER`) declara 64×64 y el de `cardh` 128×64; y con la lectura A de E8-3 (Bladedge
128×56 = «dibujado, con banda abajo») que solo tiene sentido si A **llenó el ancho**.

**Presupuesto a 128 de ancho** (slot de 4096 B): el formato 5 no alcanza (128×56 = 7168 B de
píxeles). El formato 4 sí: **128×56 a 4 bpp = 3584 B + 208 + 64 = 3856 B** (240 B de holgura),
con 16 colores — el tope del formato. Es la misma geometría del canary A de E8-3, ya probado
como «dibujado». 128×56 llena el ancho bajo **cualquiera** de las lecturas (1:1, escala por ancho
o escala por alto), así que es la opción robusta.

`cardm` a 64×48 formato 4 = 1536 + 208 + 64 = 1808 B en 2048 (una 64×56 a 16 colores se pasa por
16 B).

Nota: los contenedores crecidos conservan **el mismo tamaño en sectores** (5102/2557), así que el
plan de reubicación de §9.2 no cambia.

**Rehecho (ronda E8-4b)**: `build`/`iso`/`accept` corridos con `--cardh-format 4 --cardh-w 128
--cardh-h 56 --cardh-colors 16 --cardm-format 4 --cardm-w 64 --cardm-h 48 --cardm-colors 16`
(dither + area). Contenedores y LBAs sin cambios (`cardh_art.cip` 10.448.896 B sha256
`7b2c9513…`, `cardm_art.cip` 5.236.736 B sha256 `cdeff223…`); payloads 3856 B y 1808 B;
`accept` T9.1..T9.6 OK; el ISO de E6 sigue intacto.

**Compromiso de calidad**: a 128 de ancho el formato 5 no entra en 4096 B (128×56 = 7168 B de
píxeles contra 4096 del slot), así que la geometría nativa en un slot estándar obliga a formato 4
con **16 colores** (`art_preview_128.png` vs el fuente: sirve, pero pierde detalle y aparece
dither).

### 9.7 Ronda E8-4c — región privada por carta (experimento)

Segundo test del usuario sobre E8-4b: **el ancho se arregló** (el arte llena todo el recuadro),
pero queda **banda abajo** (56 renglones contra los 64 del destino) y la paleta de 16 colores.

Hipótesis: `offset = slot << 11` da granularidad de 2048 B, así que **un arte puede ocupar varios
slots consecutivos** mientras ninguna otra carta apunte adentro. Bajo esa hipótesis, `cardh`
**128×64 formato 5 con 256 colores** (8192 + 208 + 1024 = 9424 B) vive en una región privada de
12288 B (6 slots), y `cardm` **64×64 formato 5 / 256** (5328 B) en una de 6144 B (3 slots).

Se implementó `--cardh-region`/`--cardm-region` en `tools/tf1_art18.py` (default 4096/2048 =
comportamiento anterior, reproducible byte a byte) y se construyó `trabajo/e8/TF1-E8-ART2.iso`:

| | E8-4b (`TF1-E8-ART.iso`) | E8-4c (`TF1-E8-ART2.iso`) |
| --- | --- | --- |
| `cardh` | 128×56 f4, 16 col | **128×64 f5, 256 col** |
| `cardm` | 64×48 f4, 16 col | **64×64 f5, 256 col** |
| contenedores | 10.448.896 / 5.236.736 B | 10.596.352 / 5.310.464 B (5174 / 2593 sectores) |
| reubicación | cardh → 3646 · cardm → 251955 | igual (entra en la región libre) |
| ISO | — | 7768 sectores cambiados, **0 fuera** |

`accept` T9.1..T9.6 OK; `cardh_art2.cip` sha256 `ad8a4fe5…`, `cardm_art2.cip` sha256 `d881a170…`,
`TF1-E8-ART2.iso` sha256 `54951cf3…`. El ISO de E8-4b y el de E6 quedaron intactos. Preview:
`art_preview_256.png` (128×64/256 col a 4× vs el fuente) — prácticamente idéntico.

**Resultado (T10): el experimento FALLÓ, y con el síntoma exacto del riesgo.**

El usuario probó `TF1-E8-ART2.iso` y reportó arte «con mucho zoom» que «sigue sin entrar en el
cuadrado», más ruido arcoíris. Lectura: en el **detalle** el tercio superior del recuadro muestra
el arte correcto y el resto es ruido; en las **miniaturas de campo y álbum** (deck de duelo, lista
de cartas) las 18 salen directamente como ruido, mientras las cartas que no son las 18 se ven
normales.

Conclusión: **el motor copia como máximo el tamaño del slot** (4096 B en `cardh`, 2048 B en
`cardm`) y no sigue la cadena GIM más allá. Un arte más grande se trunca y la parte que sobra es
basura. Por lo tanto:

- **No existe** una geometría nativa 128×64 para `cardh`: la textura sola a 128×64 en formato 4 ya
  son 4096 B y cualquier cabecera la pasa del slot. Máximo alcanzable: **128×56**.
- **`cardm`**: máximo 2048 B ⇒ 64×48 en formato 4 con 16 colores (1808 B), o 64×56 con solo 12
  colores (2048 B exactos).

**E8-4b (`trabajo/e8/TF1-E8-ART.iso`) queda como el techo definitivo**: 128×56 f4/16 para `cardh`
(llena el ancho; quedan 8 de 64 filas sin cubrir) y 64×48 f4/16 para `cardm`. `TF1-E8-ART2.iso`
queda descartado y no se usa.

### 9.8 Códec nativo de `cardm` descifrado (E8-5)

La verificación in-game del **arte de campo** con E8-4b mostró el defecto: en la lista de cartas del
duelo y en el campo, las fichas de las 18 son **ruido arcoíris**, mientras las cartas que no son
las 18 se ven perfectas. La ventana de detalle que usa `cardh` sí sale bien.

**Causa**: los slots de `cardm` **no son contenedores GIM**. El motor los lee como **píxeles
crudos**, así que nuestra cabecera GIM le entra como basura. E8 los había anotado como «cuerpos
desnudos formato 8» y nunca se verificó en pantalla (el canario de `cardm` de E8-2 jamás se miró
en el campo).

**Códec real (descifrado y probado visualmente)**: cada slot de 2048 B es una imagen **DXT1 (BC1)
de 64×64 con las dos palabras de 32 bits de cada bloque intercambiadas**: primero los 4 bytes de
índices (en orden 0,1,2,3) y después los dos colores en RGB565 (`c0lo, c0hi, c1lo, c1hi`). **Sin
swizzle del GE y sin paleta.**

Evidencia de referencia: `referencia/CIPTool/README.md:7` («The game uses DXT1 texture
compression») y `CIPTool.cpp:715-716, 511-512, 556-557`: CIPTool **no convierte** — en `CPM_MODE`
solo antepone la constante `CPM_GIMHEADER` (un GIM de 128 B que declara formato 8, 64×64, 4 bpp =
2048 B) y copia los bytes crudos del slot.

Prueba visual: `trabajo/e8/cardm_probe/cardm_native_6477_Bladedge_4x.png` (y `_6312_Clayman`,
`_6310_Avian`) son miniaturas de carta completas y reconocibles (marco, barra de nombre, recuadro
de efecto y ATK/DEF incluidos). Reproducir con `python3 trabajo/e8/cardm_decode.py`. El intercambio
se detectó por estadística de bytes: en DXT1 estándar los bytes de índice deben ser uniformes, pero
el byte 5 tenía media 202 y el 7 nunca pasaba de 0xD5 — esas posiciones restringidas son las altas
de los colores RGB565. Un barrido de 20.160 disposiciones de bloque dio ganador a
«extremos en 4..7» por amplio margen.

**Consecuencia**: `cardm` puede llevar arte real a 64×64 con **color completo** (DXT1), sin el tope
de 16 colores ni el problema de tamaño — el slot nativo de `cardm` es exactamente 2048 B =
64×64 DXT1.

### 9.9 `cardh` también es DXT1 — y la textura trae la banda del nombre (E8-8)

El usuario cuestionó que el arte grande estuviera resuelto (la franja inferior seguía ahí). Se
probó el mismo truco que descifró `cardm` sobre los 3968 B que siguen a la cabecera de 128 B de un
slot de `cardh`: **DXT1 estándar = ruido; DXT1 con las dos palabras de 32 bits invertidas =
ilustración reconocible** (Bladedge, Clayman y Avian). O sea, `cardh` usa **el mismo códec** que
`cardm`.

**Layout exacto** (barrido de anchos de fila y swizzles, ganador por amplio margen):

- Textura en el **byte 128** del slot (los primeros 128 B son la plantilla GIM constante, vestigial).
- Bloque BC1 de 8 B con índices primero (0..3) y los dos colores RGB565 después (4..7).
- **32 bloques por fila (128 px)**, orden fila a fila, **sin swizzle**. 496 bloques = **128×62 px**
  (el 128×64 declarado necesitaría 4096 B y solo entran 3968).

**Hallazgo importante**: la textura nativa **no es solo la ilustración**. Contiene además la
**banda del nombre** (el texto de la carta) y grandes zonas de **verde `(0,97,0)` usado como clave
de color** (transparente). Esto **corrige §3.4**: el nombre sí está pintado en el arte, tal como el
usuario dijo en E6 L14.

Pruebas: `trabajo/e8/cardh_layout/WINNER_128x62_{6477,6312,6310}_*.png`; barrido en
`cardh_layout/sweep_raw.txt` y `RESULT.md`.

**Consecuencia**: el arte grande puede rehacerse en **DXT1 128×62 a color completo** con la
cabecera nativa de 128 B, en vez del GIM de 128×56 a 16 colores. Eso elimina casi toda la franja
(quedan 2 filas de 64, igual que el nativo) y devuelve el color. Queda por decidir **qué va en la
zona del nombre**: el nombre en español compuesto, o relleno con la clave verde.

### 9.12 El editor de deck usaba otro idioma (E8-12)

Síntoma del usuario: con el arte ya correcto en álbum y duelo, en el **editor de deck** las 18
salían como el **reverso**.

Causa medida (`trabajo/e8/E8-DECKART-01.md`): todo el arte se carga desde
`PSP_GAME/USRDIR/card/card{h,m}_{e,f,g,i,s}.cip`, y las **únicas** referencias a esas rutas están en
`EBOOT.BIN`: una tabla de seis punteros por tamaño, indexada `j,e,g,f,i,s` por un valor de idioma en
tiempo de ejecución (cargadores en `.text` `0x4d9f8` para `cardh` y `0x4dab0` para `cardm`). El
builder parcheaba **solo `_s`**, así que los 18 CardIDs tienen entrada 0 en los otros idiomas → el
editor de deck, que resuelve por otro índice, dibuja el reverso. `CARD_Top_S`/`CARD_SamePict_S` no
son fuentes de arte. La imagen española no tiene `_j` (el camino existe en EBOOT pero el archivo
nunca se usa).

**Arreglo (ISO `TF1-E8-FINAL-C.iso`)**: como el arte es independiente del idioma (§3.5), en vez de
duplicar 8 contenedores (imposible: un `cardh` crecido son 5102 sectores y ningún extent libre o
liberado llega a ese tamaño) se **aliasan los 8 directory records** de `cardh_{e,f,g,i}` y
`cardm_{e,f,g,i}` al extent y tamaño de `_s`. Cambio total contra FINAL-B: **un solo sector, el 27**
(64 bytes, todos dentro de los 8 records). Las diez rutas de arte leen un mismo contenedor por
tamaño (sha256 idéntico). Los extents viejos de esos 8 archivos quedan sin referenciar (74,7 MB de
espacio desperdiciado, inofensivo).

Consecuencia asumida y declarada: los idiomas distintos del español pasan a mostrar el arte
`_s` (medido 99,8–100 % idéntico al suyo), que es arte nuestro de todos modos.

### 9.13 La grilla del editor de deck usa un atlas prebakeado (E8-13)

El reverso de las 18 en el editor de deck **no** venía del arte ni de un tope de código.
`trabajo/e8/E8-DECKGATE-01.md` y la ronda siguiente lo midieron: la grilla no renderiza desde
`cardm`, **blitea miniaturas prebakeadas** de `PSP_GAME/USRDIR/deck/all_<lang>.ehp`, que contiene
`fileTbl.dat` y el atlas `cis_all.gim`. Los 18 CardIDs no estaban en `fileTbl.dat` ⇒ reverso.

De `libdeck.prx` (desensamblado): tile **22×30**, **23 columnas**, 17 filas por página = **391
fichas/página**, 7 páginas = **2737** de capacidad, 2452 usadas, **285 libres**. La regla es
`idx = posición del CardID en el fileTbl ordenado`, `X=(idx%23)*22`, `Y=(idx/23)*30`.

**Falso positivo que costó una ronda**: el primer intento no reconocía las fichas porque
`GimTexture` lee mal *este* GIM (el atlas trae una tabla de offsets de 16 B dentro del bloque de
paleta y del de imagen: **una paleta por página**, con los datos reales en `0x90 + p*1024` y
`0x1cf0 + p*262144`). Con los offsets correctos las 6310/6312/6477 aparecen en su posición y la
regla queda **confirmada**. Ojo: `GimTexture` sigue bien para **nuestros** GIM; el layout del atlas
es distinto.

**Arreglo (`TF1-E8-FINAL-D.iso`)**: `fileTbl` es una lista **ordenada** con búsqueda binaria
(`libdeck.prx:0x113f0`), así que insertar 4661..4730 en el medio **desplaza los índices**: se
reindexó el atlas entero moviendo cada ficha sobreviviente a su nuevo índice y renderizando las 18
nuevas a 22×30 desde `trabajo/e8/art_full/`. `fileTbl` 2452 → 2470. Los **seis** `deck/all_<lang>.ehp`
(seis idiomas) crecieron 32 B cada uno y entraron en sus sectores ya asignados (holgura mínima
496 B): **extents sin cambios**, solo los campos de tamaño de los directory records.

Diff contra FINAL-C: 5129 sectores, todos dentro de los seis extents del deck salvo el **29**
(directorio `deck`), que cambia exactamente en los 12 bytes de tamaño de los seis records. Nada más.

### 9.14 Estado al cerrar la sesión — qué sigue

**Cerrado y validado por el usuario en PPSSPP:**

- Arte de las 18 en **`cardh`** (detalle/álbum) con colocación **B**: DXT1 nativo 128×62, color
  completo, ilustración en x 0..77, resto tomado de la referencia nativa.
- Arte de las 18 en **`cardm`** (campo y listas de duelo): **mini-carta completa** 64×64 DXT1.
- **Editor de deck**: las 18 ya muestran su miniatura (atlas `deck/all_<lang>.ehp` + `fileTbl`
  ordenado, 6 idiomas).
- ISO vigente: **`trabajo/e8/TF1-E8-FINAL-D.iso`** (sha256 `6eff712b…`). Base: `trabajo/e6/TF1-E6-18.iso`.
  Save: `trabajo/e6/DATA0.hero`.

**Pendiente único de arte: la banda del nombre en la textura grande.**

La textura nativa de `cardh` trae el nombre pintado; la nuestra muestra hoy el de la carta de
referencia (Bladedge). Datos ya medidos en §9.9/§9.11: banda en **x 80..127, y 40..59** (48×20 px),
fondo naranja `#CE7129`, renglones de glifos en y 43..49 y y 55..59. Nombres en español en
`datos/cartas_18.tsv`. Decisión del usuario pendiente entre (a) extraer la fuente de las bandas
nativas y componer, (b) fuente propia simple, (c) dejarlo.

**Otras cosas para la próxima sesión:**

1. Analizar `YGO_TFSP_REBOOT - BETA 1.0 (Español) - OFFLINE.iso` (Tag Force Special) como
   referencia de arte/banda. Estructura medida: `card/cardh_j.cip`, `cardj256_j.cip` (208 MB) y
   `cardm_j.cip`, solo `_j`; motor distinto, no es reemplazo directo.
2. Quedan **sin commitear** de sesiones anteriores: `ESTADO-E6.md` (M), `tools/e6_patch_save.py`
   (M) y `datos/receta_hero.tsv` (nuevo) — la receta HÉROE de Jaden concedida en el save. No los
   toqué; decisión del usuario.
3. Cierre de entrega: actualizar el README con el procedimiento de reconstrucción y decidir
   push/PR (decisión del usuario).
4. `tools/tf1_art.py` tiene un lector de GIM (`GimTexture`) que **no** contempla el layout del
   atlas del editor de deck (paleta por página con tabla de offsets de 16 B). Anotado por si algún
   día se reusa; para nuestros GIM está bien.

### 9.15 Entrega: la rama no entra en un PR solo

Al cerrar E8, `spike/e1-test` acumula **27 commits / ~8100 líneas** sobre `main` (sin lockfiles).
Eso pasa el límite de ~400 líneas por commit de revisión por mucho, así que la entrega necesita
**PRs encadenados** (o partir por fase: E0..E6 ya validado por el usuario, E8 aparte). El corte
natural propuesto: (1) datos y port E0..E6, (2) arte E8. Decisión del usuario.

### 9.10 Estado real del arte grande (respuesta al usuario)

El arte grande **no estaba resuelto**: el GIM de 128×56 llena el ancho pero deja 8 filas sin
pintar (VRAM sucia) y usa 16 colores. Con §9.9 pasa a ser resoluble de verdad: DXT1 128×62 a color
completo, con la franja reducida a 2 filas.

### 9.11 Pendiente de decidir (producto)

1. **Arte grande**: DXT1 128×62 solo con la ilustración y la zona del nombre en clave verde, o
   además componer la banda del nombre en español.
2. **Arte chico (`cardm`)**: el nativo es una **mini-carta completa** (marco, nombre, texto,
   ATK/DEF). Hoy inyectamos solo la ilustración. Hay que decidir si se compone la mini-carta
   completa o se acepta la ilustración dentro del marco que dibuja la interfaz.

### 9.5 Resultado del build (T5..T9)

- `tools/tf1_art.py`: `resize_area`, `cover_crop`, dithering Floyd–Steinberg, `prepare_gim`,
  `Container.from_bytes`, `inject --resample area|dither`. Se corrigió un bug latente de
  `_median_cut` (el primer corte ordenaba la lista del llamador in place y mezclaba los índices;
  error medio por canal 76 → 6,15). Los centinelas de E8 no lo tocaban porque usan la vía de
  colores distintos ≤16.
- Contenedores: `cardh_art.cip` 10.448.896 B (5102 sectores) · `cardm_art.cip` 5.236.736 B
  (2557 sectores). 18 slots propios cada uno; las 2527 entradas previas y todo el header salvo las
  18 entradas + `total_size` quedan byte a byte idénticos.
- `trabajo/e8/TF1-E8-ART.iso`: **7660 sectores cambiados**, todos dentro de los dos extents nuevos
  (cardh 3646..8748, cardm 251955..254512) más el sector 27 del directory record. **0 fuera.**
  El ISO de E6 no se tocó (mismo tamaño y sha256). Decode-back píxel a píxel en las 18 (cardh y
  cardm); `verify` sale 0 en ambos contenedores.
- **Riesgo abierto (T10)**: los slots de `cardm` nativos son cuerpos formato 8 desnudos; nuestro
  GIM de cardm es formato 5, así que **el render del arte de campo no está verificado in-game**.
  El test de PPSSPP debe mirar el arte pequeño en el duelo además del álbum.

---

## 7. Log

- **L1** — Pedido original del usuario, verbatim: «Estaba pensando si para el arte es posible usar
  las imagenes de edo pro tanto para las cartas grandes: [Image#1] y las pequeñas: [Image#2]».
- **L2** — Elegido el camino «E8 paso 1: decodificar y MIRAR primero»: «Vamos con esa».
- **L3** — Agotado el camino del visor sobre el formato nativo, el usuario eligió
  «Probar si el motor acepta NUESTRO formato».
- **L4** — Resultado del centinela de E8-2 (rayas magenta/lima visibles en el recuadro de Avian):
  el motor acepta un GIM propio.
- **L5** — Matriz de E8-3 con dos centinelas; el usuario preguntó «¿suficiente prueba?».
  Sí: formato 4 aceptado, paleta de 16 aceptada, recuadro de proporción ~1,14.
- **L6** — Instrucción de cierre del usuario: «Cuando esto termine se hace prueba y luego se
  anotan los resultados para cerrar y guardar sesion».
- **L7** — Pedido de apertura de E8-4, verbatim: «Vamos ahora si a inyectar el arte de edopro al
  TF1».
- **L8** — Resultado del test in-game, verbatim: «Subi los resultados aca: C:\Users\Danieldlrt09\
  Proyectos\MASK HERO in TF1\trabajo\Resultados art e8». Lectura en §9.6: las 18 ilustraciones son
  correctas pero ocupan media ventana ⇒ hay que rehacerlas a 128 de ancho, formato 4.
- **L9** — Rehecho a 128×56 formato 4 / 16 colores y 64×48 para cardm (ronda E8-4b, §9.6).
- **L10** — Segundo test in-game (2 capturas, Anki y Caos), verbatim: «y practicamente así con
  todas». Lectura: el ancho se arregló; quedan la banda inferior y el dither de 16 colores. Se
  pasó a la ronda E8-4c (§9.7): región privada por carta, 128×64 formato 5 con 256 colores.
- **L12** — Cuarto test in-game, verbatim: «Nada, sigue en reverso y la versión grande se tiene
  que perfeccionar». El reverso se debía al atlas del editor de deck (§9.13); la «versión grande»
  sigue pendiente por la banda del nombre.
- **L11** — Tercer test in-game (detalle + duelo), verbatim: «Da la sensación como si tuvieran
  mucho zoom pero siguen sin entrar en el cuadrado de la carta». **E8-4c descartado**: el motor no
  lee más allá del slot (4096 B en `cardh`, 2048 B en `cardm`), así que el arte grande se trunca y
  el resto sale como ruido. **E8-4b queda como techo** (§9.7).

## 8. Artefactos

- `tools/tf1_art.py` — `list`, `gim`, `extract`, `verify`, `inject`; contenedor CIP/CPM, dialecto
  GIM (formatos 3, 4, 5), swizzle, encoder de formatos 4 y 5 con paleta de tamaño variable, PNG
  propio (sin dependencias). `extract` **se niega** a escribir un PNG de formato 8.
- `trabajo/e8/build_e8.py` — build y aceptación deterministas de la matriz; corta si un objetivo
  no es exclusivo.
- `trabajo/e8/TF1-E8-M2.iso` — ISO de la matriz. `TF1-E8-F5.iso` — ISO del primer centinela.
  **Purgados** (junto con los de E1-test planB/planF, E5-C1/C2 y los E8-ART/ART2/FINAL
  intermedios): eran artefactos de fases cerradas o iteraciones superadas, pesaban 8,18 GB en
  `trabajo/` (gitignored) y son regenerables con los scripts. Quedan solo el ISO prístino del
  juego, `trabajo/e6/TF1-E6-18.iso` (base/deliverable de E6) y `trabajo/e8/TF1-E8-ABC.iso`
  (test vigente). Por eso las menciones a esos nombres en este handoff son históricas.
- `trabajo/e8/matrix_6477.png`, `matrix_6312.png`, `canary_cardh.png`, `canary_cardm.png` — previews,
  idénticas píxel a píxel a lo inyectado.
- `trabajo/e8/INTERPRETACION-E8-M2.md` — tabla de lectura del test.
- `trabajo/e8/window_s0002.png`, `_proof_help_*.png`, `_proof_parts.png` — pruebas del dialecto
  contra assets reales del juego.

---

## 9.16 El arte grande no encaja: el motor PLIEGA la textura (ronda E8-14)

Estado al cerrar la sesión (2026-11-02). **Lo entregado y validado antes sigue vigente**: arte de las
18 en `cardm` (campo/duelo), editor de deck y barra del nombre. Lo que falta es **la geometría exacta
del recuadro grande** (`cardh`) y el **nombre en español** en la barra.

### 9.16.1 Causa medida: el motor no dibuja la textura plana

El recuadro **no** es un blit 1:1 de la textura 128x62. Con una **sonda de coordenadas** (patrón de
degradado) probada in-game se leyó el mapeo real:

| Zona de la textura | Va a |
| --- | --- |
| **`x0..77`** (78x62) | **mitad ARRIBA** del recuadro, ancho completo · ~76% del alto |
| **`x78..127`** (50x62) | **franja ABAJO** (~24%) · y de esa zona solo se usan las filas de arriba |
| banda del nombre `x80..127, y40..59` | **barra superior** (de ahí sale el texto del nombre) |

Evidencia: `trabajo/e8/_probe/p1.png`, `trabajo/e8/_probe2/q2.png`, informe
`trabajo/e8/E8-CARDH-MAP.md`. Medición fina de la sonda de marcadores (Acido, `q2.png`): fin de la
mitad de arriba en **75,7%**; línea verde (textura `x=39`) en **44,6%** del ancho; línea azul
(`y=31`) en **41%**; la franja inferior usa **otra escala horizontal** (marcadores en 27% y 79,5%,
no en el 50% esperado).

**Consecuencia**: la mitad de arriba y la franja de abajo tienen **escalas horizontales distintas**.
Por eso el arte de abajo queda corrido. No es un simple recorte.

### 9.16.2 Lo que NO es el problema (descartado con evidencia)

- **La imagen de EDOPro**: el arte nativo de TF1 también se ve "recortado" así (mapeo interno).
- El códec DXT1, el espacio del slot (4096 B) y la pérdida de color: no intervienen.
- `FIX3` (cover a 2:1) y `FIX9` (transposición) fallaron; `FIX4` (plegado 77,5%) fue "el más fiel",
  `FIX8` quedó "casi".

### 9.16.3 Próximo paso (a ejecutar en sesión nueva)

1. Con los números de `PROBE2`, **pre-compensar cada mitad a su escala**: partir el arte en 75,7% /
   24,3%, estirar la mitad de arriba ~12% en horizontal y ajustar la franja inferior para que encaje
   con la de arriba.
2. Reconstruir desde `TF1-E8-FINAL-D.iso` con el parche quirúrgico (36 sectores, extent `cardh`
   3646..8748) y validar in-game.
3. **Nombre en español** en la banda `x80..127, y40..59` (glifos nativos o fuente propia; decisión
   §9.14).

### 9.16.4 ISOs y artefactos vigentes

- **Mejor hasta ahora**: `trabajo/e8/TF1-E8-FIX8.iso` (sha256 `64ca280ca361a9defa8d1a65…`) — "casi".
- Sondas: `trabajo/e8/TF1-E8-PROBE.iso` (`984a81b58cb7822396264a89…`),
  `trabajo/e8/TF1-E8-PROBE2.iso` (`325bb72de352471e1a4f76bc…`).
- Descartados: `FIX`, `FIX2`, `FIX3`, `FIX4`, `FIX5`, `FIX6`, `FIX7`, `FIX9`.
- Base intacta: `trabajo/e8/TF1-E8-FINAL-D.iso` (vigente, validado) y `trabajo/e6/TF1-E6-18.iso`.
- Capturas del usuario: `trabajo/e8/_nat/`, `_prev/`, `_probe/`, `_probe2/`.
- Save: `trabajo/e6/DATA0.hero`.

### 9.16.5 Sin commitear (de sesiones previas)

`ESTADO-E6.md` (M), `tools/e6_patch_save.py` (M), `datos/receta_hero.tsv` (nuevo) — la receta HÉROE
de Jaden concedida en el save. **No tocados**, decisión del usuario. Este E8-CARDH-MAP.md y los ISOs
viven en `trabajo/` (gitignored).

### 9.16.6 Ronda E8-14 — mapeo medido con números e ISO candidato (G1)

**Limpieza**: borrados los 8 ISOs descartados (`FIX`, `FIX2`..`FIX7`, `FIX9`) — **6094 MiB** liberados.
Quedan el ISO prístino del juego, el de Tag Force Special (referencia), `TF1-E6-18.iso` (base),
`TF1-E8-FINAL-D.iso` (validado), `TF1-E8-FIX8.iso` y las dos sondas.

**Método**: la textura-sonda se **recuperó del propio ISO** (`iso_replace.read_iso_file` +
`tf1_art.decode_cardh_slot`) y se midió contra la captura `q2.png` con código, no a ojo. La cifra
**44,6% de §9.16.1 era un borde de recuadro mal medido**: la línea lima (textura `x=39`) cae en
**50,4% ≈ 39/77**. La **ventana superior es un 3x uniforme** de textura `x0..77` (78x62 → 234x186 px).

**Corrección grande**: la franja inferior **no** usa la escala de 78. **Tilita la región derecha
`x78..127` cada 144 px** (`u = 78 + (X − 144·t)/2.88`); tile0 usa filas `0..17,5` y tile1 filas
`19,8..37,3` (disjuntas). Eso explica el «la franja de abajo se corre a la derecha» de `FIX8`.

**ISO candidato**: `trabajo/e8/TF1-E8-G1.iso` (sha256 `533c0a9f325be2f711b7975448bbd795…`),
**36 sectores** cambiados, todos dentro del extent `cardh` (LBA `8712..8747`), **0 fuera**; FINAL-D
intacto (mismo tamaño). Informe: `trabajo/e8/E8-14-SOLVE.md`.

**Verificación (no por checksum)**: modelo forward vs `art_src/<cid>.png` con MAE **18,7..31,8**
(piso del códec DXT1), validado además en la captura independiente `_cmp_sq_u07.png` (MAE 34,8).

### 9.16.7 Ronda E8-14 G2 — pulido tras el test in-game (costura + suavizado)

**Test del usuario de G1**: «Si señor ahora si» — el recuadro grande por fin entra completo y
continuo. Dos defectos finos reportados:

1. «se ve un tanto mas pixeleado a comparación con otra [carta nativa] … esta se ve mas "suave"».
2. Un «trozito» a quitar: una banda oscura con una franja verde en el borde.

**Causa del trozito**: la inversión de G1 sólo escribía los texeles que su modelo muestrea; las
filas 17,5..19,6 y 38..39 del carril (y `x110..127` de las filas 20..36) conservaban la referencia
nativa de FINAL-D (Bladedge), y asomaban en la costura entre los dos tiles.

**ISO `trabajo/e8/TF1-E8-G2.iso`** (sha256 `9c49a787926c2472f289683920a2f46d51dcbf9766a66ed7d311b2ec70c9f030`):
- **Fix A**: el carril `x78..127, y0..39` se escribe como una sola pieza contigua (tile0 filas
  0..18, tile1 filas 19..39) → 0 píxeles de clave verde muestreados en los 18 (medido).
- **Fix B**: cada texel es el **promedio por área** del arte 624x624 sobre su huella exacta
  (`resize_area`), en vez del muestreo por vecino sobre un intermedio de 234 de G1. MAE vs
  `art_src`: **12,4..20,9** (G2 ≤ G1 en 18/18).
- Banda del nombre `x80..127, y40..59` byte-idéntica a FINAL-D.
- **36 sectores**, LBA `8712..8747`, todos dentro del extent `cardh`, 0 fuera. Evidencia visual:
  `trabajo/e8/_probe2/g2_seam_g1_vs_g2_4661_3x.png` (izq G1 con la línea verde / der G2 sin ella).

**Pendiente**: confirmación in-game de G2. El pixelado se reduce pero no desaparece: la textura es
128x62 mostrada a ~3x, el mismo presupuesto nativo. Queda luego el **nombre en español** en la banda
(x80..127, y40..59; decisión §9.14).

### 9.16.8 El «trozito»: causa medida y G5

Tras el test de G2 («el arte quedó bien»), el usuario reportó que **seguía un «trozito»**: una franja
de color raro entre la barra del nombre y el resto, en las **18** (mágicas y monstruos).

**Diagnóstico en 3 pasos (sin adivinar):**
1. **G3** — se pintó la región derecha `x78..127` en bandas por fila (solo 2 cartas). El trozito
   **no cambió de color**; la barra del nombre sí (rojo/blanco) y la franja inferior también
   (magenta/cyan/amarillo/azul → confirma el modelo de tiles de §9.16.6). ⇒ el trozito **no** sale
   de `x78..127`.
2. **G4** — se pintó la región izquierda `x0..77` en bandas. El trozito se volvió **naranja** ⇒
   sale de `x0..77`, filas **56..61**.
3. **Causa raíz**: en una carta **nativa**, las filas `60..61` de `x0..77` contienen el **color de la
   banda del nombre** (naranja `206,113,33`) o negro; en la nuestra contenían **arte**. El motor
   dibuja esas filas como una franja pegada a la barra y en nativo se confunden con la barra.

Dato clave de seguridad: las filas `58..61` del lienzo base caen por **debajo de la costura**
(`v=58 → Y≈180.8`, costura en `Y≈180`), o sea **no son visibles en el recuadro** — reescribirlas no
lo afecta.

**Fix G5** (`trabajo/e8/TF1-E8-G5.iso`, sha256 `ce946fc9…`): en los 18 slots, filas `58..61` ←
verbatim de las filas `58..61` de Bladedge (6477, slot 4512, nativo intacto). **28 sectores**, todos
dentro del extent `cardh`, 0 fuera.

**Test de G5 (usuario)**: el trozito **desapareció**, pero apareció una **línea rosa en la costura**
del recuadro (en las 18). Causa: la fila `58` vive en el bloque DXT1 `56..59`, que **sí** se ve en la
costura; al reescribir `58..59` cambió ese bloque visible. Las filas `60..61` están en el bloque
`60..63` (por debajo de la costura, `Y≥186`), así que sólo ellas son seguras.

**Fix G6** (`trabajo/e8/TF1-E8-G6.iso`, sha256
`571d3f784e9e0497ef5f9ca2d1b7b89f9abdc4b485b4b10655389d3c2fc98dee`): ídem G5 pero **sólo filas
`60..61`** ← Bladedge (deja `58..59` = arte para no tocar el bloque visible). **28 sectores**, todos
dentro del extent, 0 fuera.

**Test de G6 (usuario)**: «Correcto, arte completado al 50%» → el trozito y la línea rosa
resueltos. Geometría del arte **cerrada**.

### 9.16.9 Texto de arriba (banda del nombre) — G7

Segunda mitad: el nombre en la barra. La banda nativa (`cardh` x80..127, y40..59) trae el nombre en
1–2 líneas de glifos diminutos (crema/amarillos sobre naranja; p.ej. Bladedge = «Elemental HERO» /
«Bladedge»). El motor dibuja esa banda en la barra superior (probado in-game en G3) y **no** afecta
al recuadro.

**ISO `trabajo/e8/TF1-E8-G7.iso`** (sha256
`52bd9c1a21b0ee3ef5c9ae3aa7f24ef6297cce84d6259da2e04952ca6fbb0673`): partiendo de G6, los 18
slots reciben el **nombre en español** (`datos/cartas_18.tsv`), partido en 2 líneas y ajustado al
ancho de 44 px de la banda. **18 sectores**, LBA `8713..8747`, todos dentro del extent, 0 fuera.
Informe: `trabajo/e8/E8-15-NAMES.md`.

**Honestidad (importante)**:
1. **Fuente FALLBACK**, no nativa. La extracción de glifos nativos se intentó y se descartó: los
glifos nativos son de trazo de 1 px, altos ~5-6 px, promediados por DXT1 y autoescalados a lo ancho
de la banda (la misma letra a distinta escala) → no se recuperan bitmaps ni avances. Se usó una
fuente condensada propia con las métricas medidas. Se ve más gruesa que la nativa fina.
2. El fondo de la barra pasó de naranja (donante) al color de marco nativo por clase (lila=fusión,
naranja=efecto, verde=mágica) → cambio visible, no pedido explícitamente (pero más correcto).
3. El mapeo banda→barra no está del todo fijado (la banda nativa de 2 líneas se ve como barra de 1
línea), así que **requiere confirmación in-game**.

Evidencia visual: `trabajo/e8/_probe2/g7_sheet_all18.png`, `g7_native_vs_g7_4661_*_8x.png`,
`g7_band_4697_8x.png` (nombre largo, escala 0,77), `g7_band_4704_8x.png` (mágica/verde).

**Test de G7 (usuario)**: «está terrible» — la barra mostró el renglón 1 grande a la izquierda y el
renglón 2 chico a la derecha, desalineados.

**Causa y decisión (verificada con la nativa Flame Wingman)**: el motor lee los **dos renglones de la
banda como las dos mitades horizontales de la barra** (renglón 1 → mitad izquierda, renglón 2 → mitad
derecha) con **una sola escala**. G7 falló porque ajustó cada renglón al ancho completo por separado.
Además: la barra usa el nombre **en inglés** incluso en el cliente español (confirmado con la nativa
Clayman, `Elemental HERO Clayman`) — la banda de `cardh` es independiente del idioma. Los nombres en
inglés están en `trabajo/e8/art_src/manifest.tsv` (`nombre_en`).

**ISO `trabajo/e8/TF1-E8-G8.iso`** (sha256
`da9185931649b8c4b868d4c2b476c0cad20c23e6061b519f354b8fb50c6c5180`): desde G6, los 18 slots con el
**nombre en inglés**, partido en dos renglones a la mitad (por longitud en píxeles) y **ambos a la
misma escala** `S = 48 / max(w1,w2)`. Fondo nativo por clase (lila=fusión, naranja=efecto,
verde=mágica). **18 sectores**, LBA `8713..8747`, todos dentro del extent, 0 fuera. Tabla de
escalas en `E8-15-NAMES.md` §8. Los más ajustados: 4672/4681/4697 (`S=1.263`). Sigue siendo la
**fuente fallback (b)**; la fuente nativa fina requeriría buscarla como atlas en otro asset.
Pendiente test in-game.

Evidencia visual G8: `trabajo/e8/_probe2/g8_bar_<cid>.png` (simulación de barra: renglón1+renglón2),
`g8_sheet_all18.png`, `g8_native_vs_g8_4661.png`.

**Test de G8 (usuario)**: «sigue viendo muy mal» — glifos demasiado **grandes y gruesos** (~2-3 px
de trazo), y el renglón largo se metía bajo el ícono. La nativa usa glifos **diminutos de trazo 1 px**
(~6 px de alto, ~4 px de avance).

**Decisión del usuario (formato)**: usar el estilo corto de Arc-V Tag Force Special → **«M·HERO
Anki»** y las mágicas en inglés.

**ISO `trabajo/e8/TF1-E8-G9.iso`** (sha256
`0776e9284491ae8e43dfa66ac34e4d7113a14436eef8c622003d7d798f6e3e5c`): desde G6, los 18 slots con
nombres cortos (M·HERO Acid…M·HERO Fountain, C·HERO Chaos, Mask Change, Mask Change II, Form Change,
Mask Charge), renderizados a la **escala natural de la fuente** (sin estirar): **cuerpo 6 px, trazo
1 px, avance 4 px**, punto medio 1 px. Fondo nativo por clase. **18 sectores**, LBA `8713..8747`,
todos dentro del extent, 0 fuera. Comparativa nativa 8x: `trabajo/e8/_probe2/g9_native_vs_g9_4661.png`
(izq nativa fina / centro G9) — métricas ya comparables. Tabla en `E8-15-NAMES.md` §9.

Sigue siendo **fuente fallback** (sans plano vs serif fina nativa; color plano vs antialiaseado por
DXT1).

**Test de G9 (usuario)**: «no se ve bien y hasta la tipografía es horrible»; además el trozito
reapareció en otro color (el compositor de G9 reescribió las filas 60–61, que en G6 llevaban el
patrón que lo camufla).

### 9.16.10 Cierre de la fase de arte (decisión del usuario)

Tras probar G7/G8/G9, el usuario decidió **dejar el texto del nombre para más adelante**. Por lo
tanto:

- **La geometría del arte queda CERRADA** en `trabajo/e8/TF1-E8-G6.iso` (arte validado in-game;
  recuadro grande correcto, sin trozito ni línea de costura). La barra superior muestra todavía el
  nombre del donante («Elemental HERO Bladedge»).
- **Limpieza**: borrados los ISOs superados/de diagnóstico (G1, G2, G3, G4, G5, G7, G8) — **5332 MiB**.
  Se conservan G6 (vigente) y G9 (último intento de nombre, por si se retoma).
- **Pendiente de nombres** (retomable): el bloqueo es la **fuente**. La barra de TF1 **pre-renderiza**
  el nombre dentro de la banda con una **serif fina**, sin fuente en runtime. Caminos evaluados:
  (1) traer las bandas «M·HERO» del ISO de **Tag Force Special** (tiene esas cartas); (2) cosechar
  glifos nativos de las bandas; (3) diseñar una serif propia. Lecciones dejadas: **no estirar el
  texto** (engrosa los trazos 1 px); la banda se lee como **dos mitades** (renglón 1 → izq, renglón 2
  → der) con una escala; métricas nativas ≈ cuerpo 6 px / trazo 1 px / avance 4 px; **no tocar las
  filas 58–61** salvo con el patrón de la banda (rompe el camuflaje del trozito / toca el bloque
  visible).

**Entrega**: el arte está en `TF1-E8-G6.iso`. Sin commitear siguen `ESTADO-E6.md`,
`tools/e6_patch_save.py` y `datos/receta_hero.tsv` (de sesiones previas). La entrega (PRs encadenados,
README) sigue siendo decisión del usuario.

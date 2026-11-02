# ESTADO — Spike E6: portar las 18 cartas HÉROE Enmascarado

Fecha: sesión del cierre de E5 + arranque de E6 (decisión de layout y build offline hechos).
Estado: **E6 cerrado y validado por el usuario en PPSSPP (T13).** Las 18 cartas están portadas, el jugador las posee (`DATA0.18`), el juego las muestra con nombre/arte/ATK/DEF/texto, se agregan al deck y se juegan en duelo. Queda el cierre de entrega (push/PR, decisión del usuario) y, si se quiere que las cartas *actúen*, la fase de efectos (§11).
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

**RESUELTO (esta sesión) — opción A.** Se neutralizó `PSP_GAME/SYSDIR/UPDATE/DATA.BIN` reescribiendo su registro de directorio con longitud 0 (los 7548 sectores quedan libres; el juego nunca lee esa carga de firmware) y el contenedor se escribió en LBA 3091, el inicio de la región liberada. La cola no usada LBA 3646..10639 queda sin referenciar y la asignación vieja del contenedor (LBA 331709..332259) también queda libre. No hubo que tocar películas ni recortar textos.

## 5. Tareas

| ID | Tarea | Estado |
|---|---|---|
| T11 | Tabla de contenido de las 18 (`datos/cartas_18.tsv`) con códigos derivados y donantes de arte | **hecha** — la verifica el build |
| T12 | Construir el contenedor de 2481+18 registros (Prop/Genre/Pass/Indx/Name/Desc/IntID) y verificar que los 2480 previos no cambian | **hecha** |
| T12b | Liberar espacio en el ISO y reubicar el contenedor (ver §4) | **hecha (opción A)** — ya no bloqueada |
| T12c | ISO final: contenedor reubicado + alias de arte en `cardh_s.cip`/`cardm_s.cip` + motor C2 + verificación offline | **hecha** |
| T13 | Prueba del usuario: las 18 visibles en el álbum (nombre, arte, ATK/DEF, nivel) y jugables | **hecha — validada**: «Kind of possession card 53» (= 35 + 18), Trunk 18, texto y arte correctos, y duelo en curso con HÉROE ENMASCARADO HORNO en el campo y las fusiones en el deck de fusión (§7 L13) |
| T14 | Editar el save para que el jugador posea las 18 | **hecha** — `tools/e6_patch_save.py` (§10) |
| T15 | Levantar el límite de 2480 índices del juego (frame del álbum + los dos clamps) | **hecha** — 4 palabras de módulo (§10.4) |

## 6. Plan de build (para no re-derivar; es el spec que se le pasó al worker cancelado)

Herramientas: `tools/e6_build_18.py` (constructor, ya escrito: implementa los pasos 1..6 de este plan) y `tools/e6_iso_space.py` (analizador/movedor, ya existe). Reutilizar, sin modificar, `tools/cardinfo_add.py` (agregado de un registro) y `tools/e5_c2_patch.py` (parche del motor: 17 palabras del wrapper en 0x478fc, entrada de reloc repuntada, entrada de dirección del NID `0xcda3b5c5` → 0x478fc, y los dos `jal 0x478fc`; EBOOT.BIN = el ELF parcheado con ceros hasta 1104032 B).

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
- **L6 (usuario, textual).** «Termina lo que dejamos a medio camino, me asuste por el gran consumo de creditos que ha causado este proyecto así que terminemos, pruebas y cerramos sesion»
- **L7 (usuario, textual).** «Expliame bien estas opciones» (pedido sobre las opciones de espacio en el ISO) y «Editar mi save (te paso copia)» (vía de obtención elegida, T14).
- **L8 (hallazgo).** El contenedor creció a 555 sectores contra 550 asignados y el ISO base no tiene región contigua libre (sólo LBA 0..21, que es metadata de ISO9660 y no se puede usar); por eso el build necesita reubicar el contenedor. Decisión: opción A (ver §4/§5). E1/E5 no tuvieron este problema porque su carta única entraba en la holgura de 1184 B.
- **L9 (build).** `tools/e6_build_18.py` construye el contenedor y el ISO, y verifica ambos (ver §9 y el commit `8a89d18`). Se corrigieron dos errores propios de contabilidad de la verificación antes de la pasada final; el artefacto no cambió. Con esto T12, T12b y T12c quedan hechos y el corte queda en T13 (prueba del usuario) y T14 (propiedad en el save).
- **L10 (usuario, textual).** «[Image#1] es esto lo que tengo que copiar?» (la carpeta de savedata, `ULES006000001`) y luego «Prueba otra vez» tras los tres pasos pedidos. Resultado: el `DATA0` llegó **en texto plano** (65536 B, entropía 1,37 en vez de 7,95) — la vía `EncryptSave = False` funcionó sin implementar cripto (ver §10.1).
- **L11 (hallazgo).** Con el save legible se identificó la tabla de propiedad del save por sus 35 entradas no nulas (exactamente las 35 cartas distintas del deck) y, con ella, el **bloqueo real** del port: el array `CardID[índice]` que arma el álbum vive en un frame de 6000 B que termina justo donde termina el array de 2480 entradas, así que los índices 2480..2497 desbordaban la pila del llamador (ver §10.3). El test de E5 con **una** carta había pasado justo porque caía adentro del frame.
- **L12 (decisión + build).** Se eligió la vía que **no pierde ninguna carta**: extender la tabla del save en la cola libre que sigue a los 2480 registros, y subir el límite del juego con 4 palabras de módulo (frame del álbum y su epilogue, más los dos `slti …,2480`). `tools/e6_patch_save.py` concede las 18 (54 bytes cambiados, todos dentro de la extensión) y el ISO se reconstruyó y verificó por sectores (1105/1105 nombrados por el plan). Commit `9781db0`; artefactos y protocolo en §9 y §10.5.
- **L13 (usuario, textual).** «Todo validado. Dime que es lo que seguiria y guarda sesion» + tres capturas. **T13 cerrada.** Evidencia de las capturas: el editor de deck muestra **«Kind of possession card 53»** (= las 35 propias + las 18 nuevas, que es exactamente el número que concede el parche) y **Trunk 18**; la carta «CAMBIO DE MÁSCARA II» se ve como MÁGICA/JUEGO RÁPIDO con su arte y su texto en español; un duelo arranca y se juega (LP 5700 vs 6000, turno 24) con **HÉROE ENMASCARADO HORNO** (2200/1000) en el campo y su texto; el deck de fusión del duelo lista las fusiones nuevas (HÉROE DEL CONTRASTE CHAOS 3000/2600 entre ellas). Con esto E6 queda cerrado: T11..T15 hechas y la prueba del usuario pasada.

## 8. Entrega (corte de slice)

Rama `spike/e1-test`. E5 se cerró con cuatro commits (el slice de la estrategia C queda cerrado y verificado):

- `ac4187b` feat(e5): las tres herramientas (`e5_patch_iso.py`, `e5_patch_iso_c2.py`, `e5_c2_patch.py`)
- `81d8ae6` docs(e5): `ESTADO-E5-limite.md`
- `aebb888` feat(e6): `datos/cartas_18.tsv` + `datos/efectos_heroes_enmascarados.txt`
- `b69bc37` docs(e6): este documento + `tools/e6_iso_space.py`

Slice de E6 (las 18), con sus propios commits de unidad de trabajo:

- `aebb888` / `b69bc37` (sesión previa): tabla de contenido y analizador de espacio
- `8a89d18` feat(e6): construye la base de datos de 18 cartas y el ISO de prueba verificado (`tools/e6_build_18.py`)
- `6964825` docs(e6): registra el build del slice (§4/§5/§7/§9)
- `9781db0` feat(e6): concede la posesión de las 18 y levanta el límite de 2480 índices (`tools/e6_patch_save.py` + los 4 parches de módulo)
- este commit (`docs(e6)`): agrega §10 y actualiza el corte del slice

**El corte de entrega queda acá**: T11..T15 hechas, verificadas offline y **validadas por el usuario en PPSSPP** (L13); el slice de E6 está cerrado. Los ISO de prueba y el save parcheado viven en `trabajo/` y están en `.gitignore`. Push, PR y merge son decisión del usuario: nada se subió.

---

## 11. Qué seguiría (después de E6)

1. **Cierre de entrega.** La rama `spike/e1-test` acumula 23 commits desde `main`, por encima del slice revisable de ~400 líneas: conviene partirla en PRs encadenados (spikes E0-E3 / E1-test / E5 / E6) o al menos publicar E6 solo. Decisión del usuario: push/PR/merge. Falta además una sección de README con *cómo se reconstruye* el ISO de las 18 (`tools/e6_build_18.py container` → `iso`) y el save (`tools/e6_patch_save.py patch`).
2. **E7 (opcional, el reto real que queda): que las cartas *actúen*.** El port es de datos; los efectos de TF1 viven en código de motor por carta. Para que las 18 tengan su efecto y para que las 11 fusiones se puedan invocar habría que averiguar si TF1 guarda recetas de fusión en datos (`duelsys/*.ehp`) y cómo se cablea un efecto en `libduel_eng.prx`/`libduel_mgr.prx` (los módulos son ELF sin cifrar, o sea que es abordable, pero es una fase grande y de riesgo alto). Alcance a decidir con una pregunta al usuario antes de empezar.
3. **Pendientes menores.** (a) Obtener las 18 *sin* parchear el save: existe `libpassword.prx` (máquina de contraseñas) y `libshop.prx`, así que la vía "comprarlas" o "contraseña" es investigable; hoy las cartas nuevas tienen `password = 0`. (b) El juego puede reescribir el save con 2480 registros al guardar → si las 18 desaparecen, re-aplicar `tools/e6_patch_save.py patch`. (c) Índices alfabéticos del álbum: `CARD_Top_S`/`CARD_SamePict_S` no se tocaron. (d) Borrar los ISOs de prueba viejos de `trabajo/` (~2,4 GB).

---

## 9. Prueba en PPSSPP (T13)

Protocolo:

1. **Backup** del `DATA0` que hoy tenés en el memstick (`ppsspp_win/memstick/PSP/SAVEDATA/ULES006000001/DATA0`): copialo a `DATA0.orig`. Después copiá `trabajo/e6/DATA0.18` sobre `DATA0` (mismo nombre, mismo tamaño).
2. Abrir `trabajo/e6/TF1-E6-18.iso` en PPSSPP con el idioma de la interfaz del juego en español y con `EncryptSave` **apagado**.
3. Arrancar desde una pantalla nueva y **no cargar un save state viejo** (un save state sobreescribe RAM y daría un falso negativo).
4. Comprobar: (a) el juego arranca; (b) el álbum muestra las 18 cartas nuevas con nombre, arte, ATK/DEF y texto; (c) tus 35 cartas siguen intactas; (d) las 18 se pueden agregar a un deck sin ícono de prohibida; (e) un duelo arranca y una de ellas se invoca.

Qué reportar si algo falla (para acotar el diagnóstico): ¿las 18 aparecen en el álbum? ¿aparecen con el nombre/arte correctos? ¿se pueden agregar al deck? ¿el duelo arranca?

Expectativas conocidas que **no** son fallos:

- Los efectos de las cartas no se ejecutan: el port es de datos (nombre, arte, ATK/DEF, tipo/atributo/nivel, texto). TF1 mantiene los efectos de carta como código de motor, no como datos.
- Las invocaciones por Fusión no existen: no hay recetas de fusión para las 11 fusiones (Cambio de Máscara y sus variantes tampoco ejecutan su efecto).

---

## 10. T14/T15 — posesión en el save y el límite de 2480 índices (referencia medida)

### 10.1 El save de TF1 está cifrado; PPSSPP lo escribe en texto plano

El `DATA0` del jugador venía cifrado con el esquema de savedata de PSP (KIRK/AES con una *game key*
por juego): 65552 B = 16 B de prefijo + 65536 B de payload, entropía ~7,95. **No hace falta
implementar la cripto**: con `EncryptSave` apagado en PPSSPP (Ajustes → Sistema, o `[System]
EncryptSave = False` en `ppsspp.ini`), el emulador descifra al cargar —tiene la key que el propio
juego le pasa— y reescribe el save **en texto plano**. El camino de carga lo decide el campo
`SAVEDATA_PARAMS` del `PARAM.SFO`. Save en texto plano = **65536 B exactos**.

### 10.2 Formato de la tabla de propiedad (medido)

Tabla de **2480 registros de 4 bytes** en el offset `0x155C`, stride 4, **indexada por índice
interno** (0..2479):

| byte | campo |
|---|---|
| 0 | `0x04` = poseída; `0x00` = no |
| 1 | copias poseídas |
| 2 | nivel de límite: 3 ilimitada, 2 semi, 1 limitada, 0 prohibida |
| 3 | 0 |

Es la misma tabla que lee el lector de límites del motor (en E5: para un índice ≥2480 lee palabra
cero → prohibida; de ahí el parche C2). **Identificación**: las 35 entradas no nulas coinciden
exactamente con las 35 cartas distintas del deck inicial (28 con 1 copia, 7 con 2). Los **3079 bytes
siguientes** (`0x3C1C..0x4823`) están en cero y sin referencias → la tabla se puede extender.

### 10.3 El bloqueo: el array del álbum tiene lugar para 2480 índices

`libcardalbum.prx` vma `0x3D38` (`addiu sp,sp,-6000`) construye en la pila el mapa
`CardID[índice]` (u16, stride 2, base `sp+0x40E`) recorriendo los CardIDs 4007..6957 vía
`CARD_IntID`, y después lo recorre con `slti s1,2480` (vma `0x3E6C`). El array termina en
`sp+0x1770` = exactamente el final del frame: **sólo entra el índice 2480**; 2481..2497 escriben
hasta 12 B más allá del frame (pila del llamador). El test de E5 con una sola carta cayó justo
adentro, por eso pasó sin problemas.

### 10.4 Parches aplicados (commit `9781db0`)

| archivo | offset | antes | después | por qué |
|---|---|---|---|---|
| `gmodule/libcardalbum.prx` | `0x3D98` | `0x27bde890` | `0x27bde860` | frame 6000 → 6048 B (las 2498 entradas terminan en `sp+0x1792`) |
| `gmodule/libcardalbum.prx` | `0x3F84` | `0x27bd1770` | `0x27bd17a0` | epilogue que cierra el frame: +6000 → +6048 |
| `gmodule/libcardalbum.prx` | `0x3ECC` | `0x2a2309b0` | `0x2a2309c2` | bucle de la lista poseída: 2480 → 2498 |
| `gmodule/libduel_draw.prx` | `0x54314` | `0x2a2309b0` | `0x2a2309c2` | clamp del cursor de la lista: 2480 → 2498 (es un clamp de UI, no un tamaño de array) |

Cada palabra se localiza por búsqueda exacta del word dentro del módulo, con **afirmación de
unicidad** (si aparece más de una vez, el build se detiene). Además se verificó que la función del
frame **no lee argumentos del stack** del llamador (sus 16 accesos `sp`-relativos caen dentro del
frame), así que agrandarlo no mueve nada que la función lea.

### 10.5 Artefactos

- `tools/e6_patch_save.py` — `show` documenta el estado del save; `patch` escribe los 18 registros
  (`04 01 03 00`) en `0x3C1C + 4i` y verifica que las 35 entradas previas queden byte a byte
  idénticas y que **sólo** cambien bytes dentro de la extensión de 72 B.
- `trabajo/e6/DATA0.18` (65536 B, sha256 `1b6292e0dd8ac37a1892efc4489436c05afc90382a08a0cbd33c913cf6d670a6`)
  — el save con las 18 concedidas.
- `trabajo/e6/TF1-E6-18.iso` — contenedor reubicado, motor C2, arte aliasado y los 4 parches de
  módulo; verificado por sectores (1105 cambiados, los 1105 nombrados por el plan).
- `trabajo/e6/save_probe.py` y `trabajo/e6/save_probe2.py` — las sondas que encontraron la tabla
  (mapa de densidad + búsqueda por stride con las cartas del deck como anclas).

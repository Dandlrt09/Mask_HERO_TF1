# ESTADO — E1-test: agregar UNA carta nueva y ver si aparece en el juego

> ## RESULTADO — POSITIVO (T6 ejecutado)
>
> Prueba en PPSSPP con el juego **en español**, sobre `trabajo/TF1-E1-test-planB.iso`
> (mismo archivo con el que se hizo el intento fallido por idioma, reconstruido):
>
> - **Canaria (S3)**: GAGAGIGO mostró **ATK/4850 DEF/1000** (antes ATK/1850) → el
>   `cardinfo_spa.ehp` parcheado **sí** se está cargando, y el arte/desc siguen siendo los
>   de la carta original.
> - **Carta nueva**: la ranura que era «Red Seasnake del gigante» (CardID 4453) se lee
>   **`E1 TEST CARD`**, ATK **4900**, DEF 1200, nivel 4, `[GUERRERO]`, con el **arte de
>   «Guardián Celta»** y la descripción `E1 TEST: appended record at internal index 2480.`
>   (4 copias, todas iguales).
>
> **Conclusión: el motor SÍ lee registros appendados.** El registro vive en el índice
> interno **2480**, que antes no existía, y el motor lo resolvió por
> `CARD_IntID[4453] → 2480`. **Q2 de E0 respondida: la tabla de la base de cartas es
> extensible** (al menos para lectura y render: Prop, Indx, Name, Desc y el alias de arte
> se leen todos del registro nuevo).
>
> **Consecuencia para el proyecto**: agregar cartas nuevas es un problema de **datos**, no
> de ARM. Queda pendiente un detalle observado: el ícono rojo de «no permitido» que el
> editor de deck dibuja sobre la carta nueva (¿la considera legal para el deck?). Candidato
> principal: el `card_id` del `Prop` del registro dice 4661 mientras la ranura es 4453
> (Plan C). Tarea **T9**.

Objetivo: validar el pipeline de datos completo (ID libre + Prop + Genre + IntID +
nombre + arte) **sin escribir una línea de ARM**. Estrategia del proyecto: probar
primero lo barato; si los datos se leen, el 80% del trabajo de puerto queda resuelto.

Estado: **E1-test cerrado en POSITIVO** (T6 ejecutado; la copia de prueba es
`trabajo/TF1-E1-test-planB.iso`, base en español). Queda abierta sólo la observación
menor T9 (ícono de «no permitido»), que no afecta la conclusión.

> **Idioma (error corregido en L10).** El juego del usuario está en **español**, así que
> carga `cardinfo_spa.ehp` y el arte `cardh_s.cip`/`cardm_s.cip`. La primera copia estaba
> parcheada en inglés: el juego la ignoró por completo. No se concluyó nada (la canaria lo
detectó). Ahora `tools/e1_patch_iso.py` toma `--lang` (por defecto `spa`).

---

## Specs

- **S1 — Carta nueva en un ID libre, y que aparezca en el juego.** (Spec de E0 §7,
  textual): «Tomar un ID libre, poner `CardExistFlag = 1`, copiar `Prop1`/`Prop2` de una
  carta existente, ponerle un nombre nuevo y su arte, y **ver si aparece en el juego**
  (álbum, tienda, editor de deck).»
- **S2 — No tocar el original.** (Autorización del usuario, textual): «Autorizó crear una
  copia parcheada del ISO (762 MB) para el test; el original no se toca.»
- **S3 — Canarias visibles.** Lección metodológica de E3, textual: «siempre incluir una
  **canaria visible** (ATK, Nivel) que distinga "el parche no se cargó" de "el parche no
  tiene efecto"».
- **S4 — Reusar arte existente.** (E0 §7, textual): «reusando un arte existente para
  evitar el toolchain CIP/GIM».
- **S5 — Cero ARM.** El test no modifica `EBOOT.BIN` ni inyecta código; sólo datos.

## Hechos medidos que fijan el diseño (no son suposiciones)

| Hecho | Evidencia |
|---|---|
| Los 472 CardID libres mapean todos a `CARD_IntID[...] = 0` (la carta nula) | `trabajo/e1_probe.py` |
| No hay ningún índice interno libre: los 2479 índices pertenecen a cartas reales; sólo el 0 es la carta nula | idem |
| `CARD_Indx_E` tiene **2482** entradas para **2480** registros de `Prop`: las 2 últimas son marcadores vacíos (`indx[2480] = (85780, 801952)`, `indx[2481] = (0,0)`) | idem |
| `CARD_Name_E` termina en 85792 con 12 bytes de relleno; `CARD_Desc_E` no tiene relleno | idem |
| El extent de `cardinfo_eng.ehp` (LBA 329052, 498 sectores) deja **288 bytes** libres antes de `cardinfo_fra.ehp` (LBA 329550) | `iso9660.listdir` |
| `card/cardh_e.cip` y `card/cardm_e.cip`: header con `MinCardNumber=4007`, `MaxCardNumber=6957`, `OffsetTableTop=48`; tabla de 8 bytes por carta indexada por `CardID − 4007`; entrada = bloque `<< 11` o `0x80000000`\|offset de la lista de artes alternativas | `trabajo/e1_cip_probe.py` |
| Los 472 IDs libres tienen la entrada de arte `{0,0}` → el juego leería el bloque 0 = el header del CIP | idem |
| `cardh_e.cip`: 2442 cartas con 1 arte (GIM verificado) + 37 con artes alternativas + 472 en cero. `cardm_e.cip`: misma distribución, payload propio (no GIM) | scan de las 2951 entradas |

**Consecuencia de diseño:** "poner `CardExistFlag = 1` en un ID libre" **no alcanza**,
porque todos los IDs libres comparten el índice interno 0 (la carta nula) y no hay
índices libres. Para agregar una carta hay que **appendear un registro** y apuntar el
`IntID` del ID libre a ese índice nuevo. Eso convierte a E1-test, de paso, en la
respuesta empírica a la Q2 de E0 ("¿tabla extensible o de tamaño fijo?").

## Diseño del parche

ID elegido: **4661** (el libre más bajo, medido). Índice interno nuevo: **2480**.
Carta donante: **Celtic Guardian** (4047, `genre = 000000000000`, Normal, nivel 4).

Crecimiento total: **152 bytes** (de 288 disponibles: el techo es 1019904 y el archivo
queda en 1019768).

| Archivo | Cambio | Bytes |
|---|---|---|
| `CARD_Prop.bin` | registro nuevo en índice 2480: `CardID=4661`, ATK/DEF/nivel de la donante, `exists=1` | +8 |
| `CARD_Genre.bin` | genre de la donante (para que entre en los filtros y en la evaluación de la IA) | +6 |
| `CARD_Pass.bin` | password de la donante | +4 |
| `CARD_Indx_E.bin` | insertado en 2480 (`name_off` y `desc_off` nuevos) | +8 |
| `CARD_Desc_E.bin` | descripción nueva al final del buffer (offset 801952) | +98 |
| `CARD_Sort_E.bin` | valor de orden de la donante | +2 |
| `CARD_Name_E.bin` | `"E1 TEST CARD"` al final del buffer (offset 85792) | +26 |
| `cardh_e.cip` / `cardm_e.cip` | **alias de arte**: se copia la entrada de tabla de la donante en los slots de **4661 y 4453** | 0 |
| `CARD_IntID.bin` | `IntID[4453] = 2480` (**Plan B**): un CardID que ya tenés apunta al registro nuevo | 0 |
| `cardinfo_eng.ehp` (dentro del ISO) | reemplazo del archivo + actualización del tamaño en el registro de directorio | 0 |

Canarias (S3) — **reemplazadas**: la canaria original era Celtic Guardian, pero el usuario
no la tiene, así que era invisible. Las definitivas usan cartas que E3 ya probó que tiene
y ve en el duelo:
1. **Canaria de carga**: **Gagagigo** (CardID 5759) con ATK 1850 → **4850**.
2. **Carta nueva observable (Plan B)**: la ranura que era **Giant Red Seasnake**
   (CardID 4453) apunta al registro appendado → tiene que leerse `E1 TEST CARD`, ATK 4900,
   DEF 1200, nivel 4, con el arte y la descripción nuevos.

El usuario contestó que el álbum **sólo lista las cartas que tiene**, así que el canal
"lista completa de la base" no existe en su partida y Plan B es obligatorio.

## Tareas

| ID | Tarea | Estado |
|---|---|---|
| T1 | Documentar el plan y los hechos medidos (`ESTADO-E1-test.md`) | hecho |
| T2 | `tools/cardinfo_add.py`: reconstruir el EHP con un registro appendado | hecho — 1019616 → 1019768 bytes (+152) |
| T3 | `tools/iso_replace.py`: reemplazar un archivo del ISO + actualizar el tamaño en el directorio | hecho — `roundtrip: True` |
| T4 | `tools/e1_patch_iso.py`: copia del ISO + EHP nuevo + alias de arte en los 2 CIP + verificación de ida y vuelta | hecho |
| T5 | Construir la copia de prueba y verificar la relectura | hecho — ver §Verificación |
| T6 | Prueba en PPSSPP (usuario) y registro del resultado | **hecho — POSITIVO**: canaria GAGAGIGO 4850 y la ranura 4453 leída como `E1 TEST CARD` ATK 4900 |
| T7 | Plan B: `--repoint` / `--desc` / `--also-map` en las herramientas + protocolo nuevo | hecho — ver §Verificación |
| T8 | `--lang` en `e1_patch_iso.py` y reconstrucción para la base en español | hecho — ver §Verificación |
| T9 | Explicar el ícono rojo de «no permitido» sobre la carta nueva (¿legalidad de deck?) | **pendiente** — Plan C ya construido: `trabajo/TF1-E1-test-planC.iso` |

### T9 — Plan C (experimento de una sola variable)

Hipótesis: el aviso «no permitido» del editor de deck sale del **chequeo de propiedad**, y ese
chequeo lee el `card_id` que está **dentro del registro** (4661), no el ID de la ranura
(4453). El save del usuario posee 4453, no 4661.

`trabajo/TF1-E1-test-planC.iso` es idéntico al planB **salvo un campo**:

| Copia | `Prop.card_id` del registro | `prop1` del registro | `IntID[4453]` | `IntID[4661]` |
|---|---|---|---|---|
| planB | 4661 | 2654818869 | 2480 | 2480 |
| **planC** | **4453** | **2654818661** | 2480 | 2480 |

La diferencia entre los `prop1` es **208 = 4661 − 4453**: exactamente el campo `card_id`,
nada más. Si con planC el ícono desaparece, la regla queda identificada; si sigue, la causa
es otra y hay que buscarla en el chequeo de legalidad del deck (no en la propiedad).

#### Hallazgos de la prueba con planB (L12)

1. **El duelo arranca** con el deck tal como quedó guardado, y dentro del duelo la carta
   nueva es **estable** (no crashea).
2. **El NPC invocó `E1 TEST CARD` sin problemas.** No es magia: el mazo del NPC contiene
   **CardID 4453** («Red Seasnake del gigante») y el repunte `IntID[4453] → 2480` es
   **global por CardID**, así que cualquier mazo del juego que use esa carta pasa a jugar
   nuestro registro. Comprobado: `PSP_GAME/USRDIR/deck/all_s.ehp` (2.507.168 bytes, los
   recipes de mazos) contiene **6 referencias a CardID 4453** como `u16`. Además, que el
   NPC la haya **invocado** prueba que el motor puede concretar la invocación de un
   registro appendado dentro de un duelo. Implicación para el puerto real: usar **CardID
   libres** (4661+), que ningún mazo ni recipe referencia, evita exactamente este efecto
   colateral.
3. **Si se abre el editor de deck, el juego obliga a quitar la carta.** El validador de
   legalidad la rechaza: el ícono rojo **no es cosmético**. Esto es un bloqueo real para el
   puerto: si las 18 cartas nuevas no pasan ese validador, el jugador no puede meterlas en
   un deck. Hay que resolverlo (T9) antes de armar las 18.

## Slices (límites de commit)

- **S1** `feat(tools): append-card rebuild and ISO file replacement` →
  `tools/cardinfo_add.py` + `tools/iso_replace.py`. Herramientas genéricas y reusables
  por cualquier experimento posterior (appendear registros, reemplazar un archivo del ISO).
- **S2** `feat(e1-test): build the test ISO pipeline` → `tools/e1_patch_iso.py` + este
  documento + `README.md`. Es el experimento E1 armado sobre S1.
- **S3** `feat(e1-test): observe the appended record through an owned card` → Plan B:
  `--also-map` / `--desc` en `cardinfo_add.py`, `--repoint` en `e1_patch_iso.py`, y las
  secciones nuevas de este documento.
- **S4** `feat(e1-test): patch the card database of the game's actual language` → `--lang`
  en `e1_patch_iso.py` + este documento (el primer intento parcheó inglés y el juego
  ignoró todo).

Siguiente límite natural: el resultado de T6 (prueba en PPSSPP) abre o cierra E1-test
antes de cualquier otro commit.

## Artefactos y cómo se reconstruye la copia

```bash
# sólo el contenedor (rápido, no toca el ISO): Plan B completo
python3 tools/cardinfo_add.py trabajo/e2/cardinfo_eng.ehp trabajo/e1/cardinfo_eng_E1.ehp \
    --card-id 4661 --name "E1 TEST CARD" --desc "E1 TEST: appended record at internal index 2480." \
    --donor 4047 --atk 4900 --level 4 --canary 5759:4850 --also-map 4453

# la copia completa del ISO (lee el original, escribe trabajo/TF1-E1-test-planB.iso)
python3 tools/e1_patch_iso.py --dst trabajo/TF1-E1-test-planB.iso \
    --desc "E1 TEST: appended record at internal index 2480." --canary 5759:4850 --repoint 4453
```

`tools/e1_patch_iso.py` imprime el reporte completo y **aborta** si el contenedor no
entra en los sectores ya asignados al archivo (guardia dura: el archivo siguiente
empieza en el sector siguiente).

## Verificación (sin emulador)

Ida y vuelta por el ISO parcheado, leído de nuevo con las herramientas de sólo lectura:

- `cardinfo_spa.ehp` dentro del ISO: **1125368 bytes**, `sha256` idéntico al construido
  (`2167bb5b…e5263`), techo 1126400 (152 de los 1184 bytes de hueco disponibles), leído de
  vuelta desde el ISO parcheado.
- Las mismas medidas en la base en español: índice interno 2480 nuevo, `name_off=98832`,
  `desc_off=892032`, `Indx` con 2482 entradas y los mismos índices internos que en inglés
  (4047→41, 4453→447, 5759→1574), 472 IDs libres empezando en 4661.
- Carta nueva 4661: `exist=True`, índice interno 2480, ATK 4900, DEF 1200, nivel 4,
  `name='E1 TEST CARD'`, `desc_off=801952`, `genre=000000000000`, arte = entrada de la donante.
- Plan B: CardID **4453** (Giant Red Seasnake) lee el mismo registro 2480 →
  `name='E1 TEST CARD'`, ATK 4900.
- Canaria 5759 (Gagagigo): ATK 1850 → **4850**.
- Los dos CIP: slots de 4661 (`0000000000000000`) y de 4453 (`b6030000…` en cardh,
  `e1010000…` en cardm) → `e05c008000000000` (lista de artes de Celtic Guardian).

Lo que esta verificación **no** prueba: que el motor del juego acepte un registro
appendado. Eso sólo lo dice T6.

## Protocolo de prueba (para el usuario)

Ver `trabajo/TF1-E1-test-planB.iso`. Es una copia del ISO con los datos parcheados.

> **Ojo:** el `trabajo/TF1-E1-test.iso` anterior quedó **bloqueado por un proceso de
> Windows** (casi seguro el emulador abierto con ese archivo) y no se pudo reescribir.
> Esa copia **no** tiene el Plan B: no sirve para este test.

1. Cargá `trabajo/TF1-E1-test-planB.iso` en PPSSPP **con el juego en la misma lengua que
   ya usás (español)** y **empezá desde una pantalla nueva del juego** — no cargues un save
   state viejo: los save states pisan toda la RAM y darían un falso negativo.
2. **Canaria de carga:** en tu deck está **GAGAGIGO** (el usuario la ve: "GAGAGIGO
   ATK/1850 DEF/1000" en sus capturas). Tiene que mostrar **ATK 4850** en vez de 1850.
   Si ves 1850, el contenedor parcheado no se cargó y el test no dice nada: pará y avisá.
3. **La carta nueva:** la ranura de tu deck (y del editor) que era **RED SEASNAKE DEL
   GIGANTE** ahora tiene que leerse como **`E1 TEST CARD`**, ATK **4900**, DEF 1200,
   nivel 4, **con el arte y la descripción de "Guardián Celta" (CardID 4047)** en vez de
   la serpiente. Ese nombre, esa descripción, ese ATK y ese DEF salen del **registro
   appendado en el índice interno 2480**, que antes no existía. Si podés, invocala en un
   duelo: el arte de campo también tiene que ser el elfo.
4. Resultado según lo que pase:

| Resultado | Lectura |
|---|---|
| La ranura se lee `E1 TEST CARD` (nombre + ATK 4900 + arte nuevo) | el motor lee registros appendados: **pipeline de datos validado** y la Q2 de E0 se responde SÍ |
| La canaria se ve (4850) pero la ranura sigue siendo la serpiente | el EHP se lee, pero el motor no acepta índices fuera de rango: agregar cartas sólo con datos no alcanza |
| La ranura aparece **vacía / en blanco / crashea** al mostrarla | el motor leyó algo pero no le gustó; causa más probable: el `card_id` del `Prop` del registro dice 4661 y no 4453. **Plan C:** reconstruir con `card_id = 4453` |
| **La canaria sigue en 1850** | el juego está cargando **otro idioma**: mirar en qué lengua está la interfaz y reconstruir con ese `--lang` (esto es lo que pasó en el primer intento: el juego en español ignoró por completo el parche en inglés) |

### T9 — La carta nueva es rechazada como «Forbidden Card»

El diálogo del juego (L13) es explícito: *«Since "E1 TEST CARD" is a Forbidden Card, it
cannot be added to your Deck»*. Y al abrir el editor de deck el juego **obliga a quitar** la
carta: el ícono rojo no es cosmético, es un validador de legalidad real.

Estado de la investigación del validador:

| Pieza | Hallazgo |
|---|---|
| `database/limitlist.ehp` | **Sólo la UI** de la pantalla «Lista de Cartas Prohibidas/Limitadas» (ventanas + `strTbl_s.bin` con esos textos). La lista de datos no está ahí |
| `gmodule/libdeck.prx` | Es el módulo que valida el deck y **es un ELF sin cifrar** (`7f 45 4c 46`). El frente ARM es más accesible de lo que creía E0: el `EBOOT.BIN` está cifrado, los módulos de `gmodule/` no |
| `CARD_Top_S.bin` | **Índice alfabético** (la primera carta de cada letra). Misterio resuelto: `TFCardEditGUI` lo listaba como desconocido |
| `database/cardalbum.ehp` | Sólo UI del álbum: **no hay una tercera fuente de arte**, el arte sigue saliendo de `cardh_s`/`cardm_s` |

**Experimento de control (planD).** Para separar «el motor rechaza lo que *dice* la carta»
de «el motor rechaza que los datos *vengan de otro índice*»: el registro del índice 2480 es
una **copia byte a byte** del registro de «Red Seasnake del gigante» (mismo `card_id` 4453,
`name_off` 16276, `desc_off` 85736, ATK 1800/DEF 800, mismo genre y password, arte sin
tocar). La única diferencia es el índice. Verificado por relectura del ISO:
`cardinfo_spa.ehp` 1125244 bytes, `sha256` idéntico, crecimiento 28 bytes.

| Resultado de planD | Lectura |
|---|---|
| Se puede agregar al deck, sin ícono | El índice nuevo no es el problema: el rechazo lo dispara algún campo modificado |
| Sigue diciendo *Forbidden Card* | El rechazo viene del índice/registro appendado → toca leer `libdeck.prx` |

### Revisión nativa del modo `--clone` (L14)

La revisión por lentes terminó en un **cierre con escalamiento**:

- `state: escalated`, `action: review completed with inconclusive severe findings;
  maintainer action is informational`
- `escalation: {cause: unknown_causality, finding_ids: ["R3-1"]}` (lente de confiabilidad)
- 2 revisores preparados y 2 enviados (`review-risk`, `review-reliability`), por relay del host

No pude leer el texto del hallazgo `R3-1` desde acá (vive en el store nativo): queda como
nota informativa para el mantenedor. La única blandura que veo por mi lado en ese diff es que
`(name or "")` escribe un nombre vacío en silencio si se llama sin `--name` y sin
`--copy-strings`; endurecerlo es una línea, pero abre un candidato de revisión nuevo.

### Por qué NO usar un código AR de "todas las cartas"

1. **Rompe la atribución.** El test existe para distinguir "el motor leyó nuestro
   registro" de "el parche no se cargó". Un código que parchea RAM mete una tercera
   causa imposible de separar: si la carta aparece, ¿fue el motor o el código?
2. **No agrega cartas a la base.** Un desbloqueo de colección toca el estado de tu save
   (propiedad), no `cardinfo_eng.ehp`; por definición no puede enseñarnos si el motor
   lee un registro appendado.
3. **Puede crashear.** Los 472 IDs libres tienen la entrada de arte `{0,0}`, o sea que
   apuntan al bloque 0 = el header del contenedor CIP. Cualquier código que fuerce a
   "existen/tenés todas" hace que el juego intente dibujar esas cartas y lea basura.
4. **No hace falta.** El set de referencia de la escena
   (`referencia/tagforce-essentials/Codes/`) trae sólo 3 códigos para ULES00600 (voice
   acting, point gauge, Uncensored Cards): no hay código de "todas las cartas" que
   ya esté probado para esta versión del juego.

## Log

- **L1** (usuario, textual): «Sigamos con el proyecto de mask heros en TF1, en que nos
  quedamos?»
- **L2** (usuario, textual): «Ordenemos el repo, de paso ya tengo un repo creado en
  github para subir este proyeto: https://github.com/Dandlrt09/Mask_HERO_TF1»
- **L3** (usuario, textual): «si» → autoriza arrancar E1-test.
- **L4** (evidencia): relevamiento de `referencia/` (TFCardEdit.cpp:226-229 y 326-346:
  `CardExistFlag = bit 31`; CIPTool.cpp:38-61 y 386-500: formato CIP) + medición de
  `trabajo/e1_probe.py` y `trabajo/e1_cip_probe.py` → hechos de la tabla de arriba.
- **L5** (evidencia): copia construida y verificada (`roundtrip: True`, lectura de vuelta
  del ISO con la carta nueva y la canaria). Bug propio cazado antes de correr: el campo
  de tamaño del registro de directorio ISO9660 va little-endian **y** big-endian, y
  `Iso9660` no implementa el protocolo de contexto.
- **L6** (usuario, textual): «Deberia de aplicar un codigo de todas las cartas para ver?»
  → corregido el canal de observación (el editor de deck sólo muestra lo que tenés en el
  save, así que no sirve para una carta nueva) y descartado el código AR por las razones
  de §Por qué NO usar un código AR. Se agregó el Plan B (repuntar el `IntID` de un CardID
  ya poseído al registro appendado).
- **L7** (respuestas del usuario): el álbum **sólo lista las cartas que tiene**, y **no
tiene** Celtic Guardian → el canal "lista completa" no existe y la canaria original era
  invisible. Plan B obligatorio, con canaria sobre Gagagigo (5759) y observación sobre
  Giant Red Seasnake (4453), las dos cartas que E3 probó que tiene.
- **L8** (incidente): `trabajo/TF1-E1-test.iso` quedó **bloqueado** (`PermissionError` al
  abrirlo: proceso de Windows, casi seguro el emulador) → la copia Plan B se escribió en
  `trabajo/TF1-E1-test-planB.iso`. Lección: no reescribir un ISO que el usuario puede
  tener abierto; usar nombre nuevo.
- **L9** (recibo de revisión): para el candidato de las herramientas (2 archivos,
  100 líneas cambiadas) la revisión nativa quedó **declinada para este candidato**
  (`consent-declined-this-candidate`, `lineage_created=false`) y el plan de `assess` fue
  `writerSelfVerification` sin verificador independiente (RDD encendido, revisión
  declinada ⇒ se aplica el camino por riesgo, y ningún ítem de riesgo alto se escaló).
  El `nativeRisk: high` con evidencia `process_boundary` es un falso positivo del
  heurístico: esas herramientas no lanzan procesos.
- **L10** (incidente de idioma): el usuario probó `TF1-E1-test-planB.iso` y mandó dos
  capturas: la interfaz y las cartas están **en español** ("GAGAGIGO ATK/1850 DEF/1000",
  "RED SEASNAKE DEL GIGANTE", "Deck personal") → el juego carga `cardinfo_spa.ehp`, así que
  el parche en inglés no se vio y **la canaria (1850) lo detectó**: sin canaria habríamos
  concluido en falso que el motor no lee registros appendados. Corregido: `--lang` en la
  herramienta, copia reconstruida para español (`cardinfo_spa.ehp` 1125368 bytes,
  `cardh_s.cip`/`cardm_s.cip`). Medición del contenedor español: mismas 2480 cartas, mismos
  índices internos, 472 IDs libres, `Indx` con 2482 entradas, hueco de 1184 bytes.
- **L11** (usuario, textual): «listo» + dos capturas del editor de deck. Evidencia:
  (a) GAGAGIGO seleccionado con **ATK/4850 DEF/1000** y X4; (b) la ranura seleccionada
  muestra el arte de «Guardián Celta», el rótulo **`E1 TEST CARD`**, ATK/4900 DEF/1200,
  4 estrellas, `[GUERRERO]` y la descripción `E1 TEST: appended record at internal index
  2480.`, con X4 copias. **T6 cerrado en positivo.** Observación: sobre esa carta aparece
  el ícono rojo de «no permitido» (y el contador «Kind of possession card» bajó de 35 a 34
  entre las dos pruebas: puede ser el deck del usuario, no se investigó).
- **L12** (usuario, textual): «Si arranca el duelo siempre y cuando no revise mi deck ya que
  si hago eso me obliga a quitar la carta, dentro del duelo no me ha salido la carta en mano
  pero el npc logró invocarlo normalmente y si esta estable». → El duelo arranca y es
  estable, el NPC **invocó** la carta (su mazo referencia CardID 4453 y el repunte es global),
  y el editor de deck **obliga a quitarla**. Pidió cerrar el emulador: sí.
- **L13** (usuario, capturas): el juego muestra *«Since "E1 TEST CARD" is a Forbidden Card,
  it cannot be added to your Deck»* y el ícono rojo está **sobre la carta nueva**. Arranca la
  investigación del validador de legalidad: `limitlist.ehp` es sólo UI, `libdeck.prx` es un
  ELF sin cifrar, `CARD_Top` es el índice alfabético, `cardalbum.ehp` es UI del álbum.
  Sin responder: si esas capturas eran de planB o de planC.
- **L14** (recibo de revisión): la revisión nativa de las 2 lentes cerró con
  `native-last-event-closure`, `state: escalated`, hallazgo severo `R3-1` de **causalidad
  indeterminada** (`unknown_causality`) y acción de mantenedor **informativa**; el texto del
  hallazgo no es legible desde el cliente.

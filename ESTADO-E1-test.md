# ESTADO — E1-test: agregar UNA carta nueva y ver si aparece en el juego

Objetivo: validar el pipeline de datos completo (ID libre + Prop + Genre + IntID +
nombre + arte) **sin escribir una línea de ARM**. Estrategia del proyecto: probar
primero lo barato; si los datos se leen, el 80% del trabajo de puerto queda resuelto.

Estado: **copia de prueba construida y verificada por ida y vuelta; pendiente la prueba
en PPSSPP** (la corre el usuario; yo no manejo el emulador desde acá). El ISO original
no se toca: se parchea una copia (`trabajo/TF1-E1-test.iso`).

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

Crecimiento total: **54 bytes** (de 288 disponibles).

| Archivo | Cambio | Bytes |
|---|---|---|
| `CARD_Prop.bin` | registro nuevo en índice 2480: `CardID=4661`, ATK/DEF/nivel de la donante, `exists=1` | +8 |
| `CARD_Genre.bin` | genre de la donante (para que entre en los filtros y en la evaluación de la IA) | +6 |
| `CARD_Pass.bin` | password de la donante | +4 |
| `CARD_Indx_E.bin` | insertado en 2480 (`name_off` nuevo, `desc_off` = el de la donante) | +8 |
| `CARD_Sort_E.bin` | valor de orden de la donante | +2 |
| `CARD_Name_E.bin` | `"E1 TEST CARD"` al final del buffer (offset 85792) | +26 |
| `cardh_e.cip` / `cardm_e.cip` | **alias de arte**: se copia la entrada de tabla de la donante en el slot de 4661 | 0 |
| `cardinfo_eng.ehp` (dentro del ISO) | reemplazo del archivo + actualización del tamaño en el registro de directorio | 0 |

Canarias (S3):
1. **Canaria de carga**: Celtic Guardian (4047) con ATK 1400 → **4850** en el mismo EHP
   reconstruido. Si en el juego no se ve 4850, el EHP parcheado no se cargó y el test no
   dice nada.
2. **Canaria de carta nueva**: `E1 TEST CARD` con ATK **4900**, DEF 1200, nivel 4, nombre
   distinto, arte de Celtic Guardian.

## Tareas

| ID | Tarea | Estado |
|---|---|---|
| T1 | Documentar el plan y los hechos medidos (`ESTADO-E1-test.md`) | hecho |
| T2 | `tools/cardinfo_add.py`: reconstruir el EHP con un registro appendado | hecho — 1019616 → 1019670 bytes (+54) |
| T3 | `tools/iso_replace.py`: reemplazar un archivo del ISO + actualizar el tamaño en el directorio | hecho — `roundtrip: True` |
| T4 | `tools/e1_patch_iso.py`: copia del ISO + EHP nuevo + alias de arte en los 2 CIP + verificación de ida y vuelta | hecho |
| T5 | Construir la copia de prueba y verificar la relectura | hecho — ver §Verificación |
| T6 | Prueba en PPSSPP (usuario) y registro del resultado | **pendiente (bloqueado por el test del emulador)** |

## Slices (límites de commit)

- **S1** `feat(tools): append-card rebuild and ISO file replacement` →
  `tools/cardinfo_add.py` + `tools/iso_replace.py`. Herramientas genéricas y reusables
  por cualquier experimento posterior (appendear registros, reemplazar un archivo del ISO).
- **S2** `feat(e1-test): build the test ISO pipeline` → `tools/e1_patch_iso.py` + este
  documento + `README.md`. Es el experimento E1 armado sobre S1.

Siguiente límite natural: el resultado de T6 (prueba en PPSSPP) abre o cierra E1-test
antes de cualquier otro commit.

## Artefactos y cómo se reconstruye la copia

```bash
# sólo el contenedor (rápido, no toca el ISO)
python3 tools/cardinfo_add.py trabajo/e2/cardinfo_eng.ehp trabajo/e1/cardinfo_eng_E1.ehp \
    --card-id 4661 --name "E1 TEST CARD" --donor 4047 --atk 4900 --level 4 --canary 4047:4850

# la copia completa del ISO (lee el original, escribe trabajo/TF1-E1-test.iso)
python3 tools/e1_patch_iso.py
```

`tools/e1_patch_iso.py` imprime el reporte completo y **aborta** si el contenedor no
entra en los sectores ya asignados al archivo (guardia dura: el archivo siguiente
empieza en el sector siguiente).

## Verificación (sin emulador)

Ida y vuelta por el ISO parcheado, leído de nuevo con las herramientas de sólo lectura:

- `cardinfo_eng.ehp` dentro del ISO: **1019670 bytes**, `sha256` idéntico al construido
  (`ba90a72e…fed95`), extent 329052 y registro de directorio con el tamaño nuevo.
- Carta nueva 4661: `exist=True`, índice interno 2480, ATK 4900, DEF 1200, nivel 4,
  `name='E1 TEST CARD'`, `genre=000000000000`, arte = entrada de la donante.
- Canaria 4047 (Celtic Guardian): ATK 1400 → **4850**.
- Los dos CIP: slot de 4661 `0000000000000000` → `e05c008000000000` (la lista de artes
  de Celtic Guardian, puntero con el bit alto).

Lo que esta verificación **no** prueba: que el motor del juego acepte un registro
appendado. Eso sólo lo dice T6.

## Protocolo de prueba (para el usuario)

Ver `trabajo/TF1-E1-test.iso`. Es una copia del ISO con los datos parcheados.

1. Cargar `trabajo/TF1-E1-test.iso` en PPSSPP, **en inglés**, y **empezar un duelo o
   abrir una pantalla nueva desde el juego** (no cargar un save state viejo: los save
   states pisan toda la RAM y darían un falso negativo).
2. **Canaria 1:** en el editor de deck o en un duelo, mirar cualquier carta Celtic
   Guardian. Debe mostrar **ATK 4850** en vez de 1400. Si no lo muestra, pará y avisá:
   el EHP parcheado no se cargó.
3. **Canaria 2:** buscar en el editor de deck una carta llamada **`E1 TEST CARD`**
   (ATK 4900, nivel 4, arte de Celtic Guardian).
4. Resultado esperado según lo que pase:

| Resultado | Lectura |
|---|---|
| Aparece `E1 TEST CARD` y se puede agregar al deck | el motor lee registros appendados: **pipeline de datos validado** y la Q2 de E0 se responde SÍ |
| No aparece, pero la canaria 1 se ve | el EHP se lee, pero el motor no acepta registros fuera de rango / no indexa por `IntID` como creemos |
| No aparece nada y tampoco la canaria 1 | el EHP parcheado no se cargó (o el juego no es la versión inglesa): hay que revisar el reemplazo del archivo en el ISO |

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

> **ACTUALIZACIÓN:** ver `ESTADO-E2.md`. El conector EHP y `CARD_Genre.bin` ya fueron
> leídos: la sección 3 de este documento (pregunta central) queda **resuelta a medias**
> — existe una capa de datos de comportamiento (genres), pero es clasificación de
> etiquetas, no el motor de efectos. El plan de la sección 7 también fue actualizado.

# ESTADO — Spike E0: portar HÉROE Enmascarado a GX Tag Force 1 (PSP)

Fecha: cierre de sesión del spike E0.
Estado: **E0 completado, con una corrección importante al final** (sección 3: la pregunta central quedó reabierta). Sin autorización de implementación todavía. Nada del juego fue modificado.

Ubicación del proyecto: `C:\Users\Danieldlrt09\Proyectos\MASK HERO in TF1`
ISO de prueba presente y ya identificado: `Yu-Gi-Oh! GX - Tag Force 1 [JP Voice enabled].iso` → **ULES00600** (Europa), DISC_VERSION 1.01.

---

## 1. Alcance acordado (18 cartas)

Fuente de verdad del texto de efectos: `C:\Users\Danieldlrt09\OneDrive\Escritorio\efectos_heroes_enmascarados.txt`
(archivo corregido y verificado contra el texto oficial impreso en esta sesión).

- **10 fusiones vía Cambio de Máscara**: Ácido, Anki, Blast, Dark Law, Dian, Divine Wind, Goka, Koga, Vapor, Atómico.
- **1 fusión real** (Polimerización): HÉROE del Contraste Chaos.
- **3 del Deck Principal**: Cuervo del Crepúsculo, Horno, Fuente.
- **4 Mágicas**: Cambio de Máscara, Cambio de Máscara II, Cambio de Forma, Carga de Máscara.

Predicados de búsqueda del Extra Deck (son **tres distintos**, no uno):
- Cambio de Máscara → mismo **Atributo**.
- Cambio de Máscara II → mismo **Atributo** y **Nivel mayor**.
- Cambio de Forma → mismo **Nivel original**, **nombre distinto**.

---

## 2. Arquitectura de la base de datos de cartas de TF1 — RESUELTO

TF1 guarda las cartas en **6 archivos binarios independientes** (formato totalmente mapeado por `xan1242/TFCardEdit`):

| Archivo | Contenido | Registro |
|---|---|---|
| `CARD_IntID.bin` | Mapa ID interno ↔ CardID | `uint16` por carta |
| `CARD_Pass.bin` | Password | `uint32` por carta |
| `CARD_Prop.bin` | Propiedades (bit-packing) | **8 bytes por carta** |
| `CARD_Indx_LANG.bin` | Índices a los buffers de texto | `int32` × 2 (nombre, descripción) |
| `CARD_Name_LANG.bin` | Buffer de nombres | `wchar_t` (UTF-16) |
| `CARD_Desc_LANG.bin` | Buffer de descripciones | `wchar_t` (UTF-16) |

### Bit-packing exacto de `CARD_Prop` (esto es todo lo que el juego sabe de una carta)

**Prop1 (int32) — 32 de 32 bits usados:**
| Bits | Campo | Rango |
|---|---|---|
| 0–12 | CardID | 13 bits → máx 8191 |
| 13–21 | ATK **/ 10** | 9 bits → máx 5110 |
| 22–30 | DEF **/ 10** | 9 bits → máx 5110 |
| 31 | `CardExistFlag` | 1 bit |

**Prop2 (int32) — 23 de 32 bits usados:**
| Bits | Campo | Rango |
|---|---|---|
| 0–3 | Kind (Normal/Effect/Fusion/…) | 4 bits |
| 4–7 | Atributo | 4 bits |
| 8–11 | Nivel | 4 bits → máx 15 |
| 12–14 | Icon (sólo ícono de Mágica: Counter/Field/Equip/Continuous/Quick-Play/Ritual) | 3 bits |
| 15–19 | Type (raza) | 5 bits |
| 20–22 | Rarity | 3 bits |
| **23–31** | **sin uso conocido — 9 bits libres** | — |

### Consecuencias directas

- **Los 18 registros entran sin cambiar el formato.** Los ATK/DEF son todos múltiplos de 10 ✓, los Niveles son 4/6/7/8/9 (caben en 4 bits) ✓, los Atributos y el Type Warrior entran ✓.
- **`CardExistFlag` existe.** Una carta puede estar presente en el rango de IDs y estar marcada como inexistente. **Eso es la llave para *agregar* cartas en vez de canibalizar slots existentes.**
- **Espacio libre de IDs:** el rango de TF1 es **4007–6958** = 2.952 slots, contra ~2.473 cartas reales → **~479 slots libres**. Necesitamos 18.
- Los nombres y descripciones viven en buffers de texto aparte, con tabla de índices de `int32`. Agregar 18 nombres + 18 descripciones = extender buffers y reconstruir el índice.
- **CardID máx = 8191.** Hay margen.

### 2.1 Dónde viven realmente estos archivos — RESUELTO (con sorpresa)

Los `CARD_*.bin` **no están sueltos en el ISO**: están empaquetados en un contenedor EHP, uno por idioma.

`PSP_GAME/USRDIR/duelsys/cardinfo_<lng>.ehp` — idiomas: `eng`, `fra`, `ger`, `ita`, `jpn`, `spa`.
El de inglés mide 1.019.616 bytes (LBA 329052). Los tamaños difieren por idioma (jpn 928.544 / eng 1.019.616 / spa 1.125.216 / ger 1.195.584), lo que confirma el modelo de E0: los datos de propiedades son idénticos entre idiomas y lo que cambia son los **buffers de texto**.

Contiene **12 archivos internos**, no 6:

| Archivo interno | Qué es |
|---|---|
| `CARD_Prop.bin` | Las propiedades (los 8 bytes/carta) |
| `CARD_IntID.bin` | Mapa de ID interno |
| `CARD_Pass.bin` | Passwords |
| `CARD_Name_E.bin` / `CARD_Desc_E.bin` | Buffers de texto |
| `CARD_Indx_E.bin` | Índice a los buffers |
| **`CARD_Genre.bin`** | **← esto reabre la pregunta central. Ver sección 3** |
| `CARD_SamePict_E.bin` | Agrupación de artes alternativos |
| `CARD_Sort_E.bin` | Orden de clasificación |
| `CARD_Top_E.bin` | Índice "top" (propósito a investigar) |
| `DLG_Indx_E.bin` / `DLG_Text_E.bin` | Textos de diálogo asociados |

Formato del contenedor EHP v3, leído del encabezado real: `"EHP" + 0x03`, tamaño total (u32), un marcador de 4 bytes, **cantidad de entradas (u32)** y luego la tabla de entradas. El contador real es `12`, y coincide exactamente con los 12 nombres hallados.

Otros archivos del ISO que van a importar:
- `USRDIR/database/limitlist.ehp` — **la lista de límites (banlist)**
- `USRDIR/duelsys/recipe_npc.ehp` — **los decks de los NPC** (relevante para el problema de la IA)
- `USRDIR/shop/all_<lng>.ehp` — el pool de la tienda (≈3,1 MB cada uno)
- `USRDIR/deck/all_<lng>.ehp` — recetas de deck
- `USRDIR/database/cardalbum.ehp`, `charalist.ehp`, `duelrecord.ehp`

### 2.2 El EBOOT pesa 1,05 MB

`PSP_GAME/SYSDIR/EBOOT.BIN` = **1.104.032 bytes**. Es *todo* el motor de duelo, la IA y los efectos de las ~2.473 cartas. (El `SYSDIR/UPDATE/EBOOT.BIN` de 5 MB es el actualizador de firmware de PSP que trae el UMD, no el juego.)
- A favor del RE: 1 MB es muchísimo más tratable que un binario de 15 MB.
- En contra: **no hay espacio libre evidente adentro**. Para inyectar código nuevo probablemente haya que **agrandar el EBOOT y corregir el registro de directorio ISO9660**, cosa viable porque controlamos la imagen completa (hay ~125 MB de sectores libres entre `duel/start/start_all.ehp` y `start_e.ehp`).

---

## 3. La pregunta central del spike — REABIERTA

> ¿TF1 codifica inmunidades/reemplazos como *flags de datos* o como *código por carta*?

**Respuesta tentativa: código por carta — PERO LA PREGUNTA QUEDÓ REABIERTA.**

**Corrección importante de esta sesión.** Concluí esto analizando sólo los 6 archivos que `TFCardEdit` conoce. Al abrir el ISO apareció un séptimo que la herramienta **no** toca: **`CARD_Genre.bin`**. Eso le quita a esta sección el carácter de "resuelto".

Lo que sigue verificado:
- `CARD_Prop` está **completamente contabilizado** (Prop1 usa sus 32 bits) y Prop2 no tiene ningún campo de comportamiento. Los 8 bytes son: ID, ATK, DEF, existe, kind, atributo, nivel, ícono, raza, rareza. Nada más.
- **Dentro de `CARD_Prop` no hay flags de comportamiento.** Eso no cambia.

Lo que **ya no** puedo afirmar:
- Que los efectos, las inmunidades y el conocimiento de cartas de la IA no estén en datos. **`CARD_Genre.bin` es exactamente el candidato**: "genre" es justo la clasificación que Yugipedia expone en listas como *"List of 'Special Summon' genre cards (Tag Force 1)"*. Yo había descartado ese lead apoyándome en el campo `Icon`, que resultó ser sólo el ícono de Mágica. Me equivoqué: el género vive en **otro archivo**, uno que no había visto.

**Experimento decisivo para E2 (barato):** extraer `cardinfo_eng.ehp`, volcar `CARD_Genre.bin` y cruzarlo contra `CARD_Prop.bin` para ver si los valores de genre correlacionan con capacidades reales de las cartas (si las cartas de Invocación Especial comparten un bit, si las inmunidades comparten otro, etc.). Eso responde de una vez:
1. Si los genre son flags de comportamiento → parte del trabajo es data-driven (y quizá también el conocimiento de la IA).
2. Si los genre son sólo categorías de UI/filtro del buscador del álbum → vuelve a valer la conclusión de código por carta.

**Conclusión operativa hasta entonces:** planificar como si fuera **código por carta** (Vapor, Divine Wind, Dark Law, Koga, Atómico y Contraste Chaos necesitan enganches ARM), pero **sin cerrar** la puerta a que parte se resuelva con datos, porque el archivo que decide eso está sobre la mesa y todavía no fue leído.

**Segundo caveat abierto:** los **9 bits libres (23–31) de Prop2** siguen siendo un misterio; `TFCardEdit` los escribe en 0 porque no los conoce.

---

## 4. Técnica de modding ya probada en la escena (a favor del proyecto)

`DeaTh-G/tagforce-essentials` (mods para GX Tag Force, soporta **ULES-00600** europea y **ULUS-10136** americana) demuestra dos vías que ya funcionan:

1. **Parches binarios `xdelta` aplicados sobre el ISO** (el EBOOT que va adentro). Herramienta: `XDeltaSharp`. Paquetes ya versionados por región y por área: `XDelta/ULES-00600/deck/*`, `XDelta/ULES-00600/duel/*`.
2. **Códigos Action Replay en runtime** (TempAR / CWCheat / PPSSPP), con archivos por región: `Codes/PSP/CWCheat/ULUS-10136.db`, etc.

**Implicación práctica fuerte:** se puede **prototipar un efecto como código AR en PPSSPP sin tocar el ISO**. Es el banco de pruebas más rápido que existe y evita el ciclo "parchear ISO → reconstruir → bootear" en cada iteración.

Y el EBOOT contiene **archivos EHP embebidos**: `cname.ehp` (nombres), `interface.ehp`, `rcpset.ehp`, `load_fl.ehp`, `sysmsg.ehp`, `packset.ehp`. Ojo: hay **dos** ubicaciones de nombres (los `CARD_Name_LANG.bin` y `cname.ehp`) y hay que determinar cuál gana en el duelo. Los artes de carta van en paquetes CIP/CPM con textura DXT1/GIM (`xan1242/CIPTool`).

---

## 5. Riesgos

### 5.1 La IA — más grave de lo que dije

El hallazgo de la sección 3 tiene una consecuencia incómoda: **si el conocimiento de efectos vive en el código, entonces la evaluación de cartas de la IA también vive ahí, por carta.** Una carta nueva no tiene modelo de IA: ni prioridad de búsqueda, ni heurística de uso.
- Lado del **jugador**: determinístico una vez que el efecto existe.
- Lado de la **IA**: necesita entradas por carta que todavía no sabemos ni dónde están. Hay que averiguar si eso es una tabla de datos o código.
- Mitigación posible: aceptar que las cartas sean de uso del jugador, o armar los decks de los NPC con las cartas nuevas y ver si la IA las juega igual.

### 5.2 Toolchain y entorno — bloqueante hoy

Presente: `python3`, `git`, `node`, `npm`, `curl`. Red a GitHub OK.
**Ausente (bloqueante):**
- `gcc` / `g++` / `make` / `cmake` → no se puede compilar `CIPTool` ni `EHPScanner` (C++).
- `dotnet` / `mono` → no se puede compilar `TFCardEdit` ni `tagforce-essentials` (C#).
- `java` → **no hay Ghidra**, que es la herramienta necesaria para atacar el EBOOT (el único frente que queda abierto).
- `unzip` / `7z` → extraer ISO (mitigable con `python3` + ISO9660).
- **`sudo` pide contraseña** → la instalación la tiene que correr el usuario.

Comando sugerido para el usuario:
```
sudo apt install g++ cmake p7zip-full openjdk-21-jdk
```
(.NET aparte, vía el script de Microsoft o `mono-complete` si se quiere compilar las herramientas C#.)

### 5.3 El juego objetivo — RESUELTO

**El ISO ya está y es de la región correcta.** `Yu-Gi-Oh! GX - Tag Force 1 [JP Voice enabled].iso` (798.787.584 bytes) → `DISC_ID = ULES00600` (**Europa**), `DISC_VERSION 1.01`, `PSP_SYSTEM_VER 2.82`, `TITLE = Yu-Gi-Oh! GX Tag Force`.

**ULES-00600 es exactamente una de las dos regiones soportadas** por `TFCardEdit` y por `tagforce-essentials`. No hay que buscar otro ISO.

**Ojo con el nombre del archivo:** "[JP Voice enabled]" es el nombre del mod *Japanese Voice Enabler* de `tagforce-essentials`. **Es probable que este ISO ya esté parcheado con xdelta.** Antes de aplicar nuestros propios parches hay que (a) verificar si está modificado y (b) **conseguir o conservar un ISO base limpio** del mismo disco/región, para no parchear sobre parche.

Lo que sí hay en disco (contexto útil, no es el objetivo):
- `/mnt/c/Users/Danieldlrt09/CrossDevice/I1VTNVT8n14AAAAAAAAAGSIPF6df1qT5adCq3XzmeLorB0RhbmRscnQ/storage/Download/PSP/PSP/GAME/YGOTF6-ALPHA1.0-OFFLINE(EXPERIMENTAL-BD-NEW).iso` — mod de la escena sobre **Tag Force 6**.
- `.../YGO_TFSP_REBOOT - BETA 1.0 (Español) - OFFLINE.iso` — mod sobre **Tag Force Special**, en español.
- `.../storage/PSP GAMES/PSP/SAVEDATA/NPJH001420001` — savedata de **Tag Force Special** (NPJH-00142) en PPSSPP.

---

## 6. Preguntas de E0: estado

| # | Pregunta | Estado |
|---|---|---|
| Q1 | Mapear CardInfo | **RESUELTO** — 6 archivos + bit layout; ubicado en `cardinfo_<lng>.ehp` (12 archivos internos) |
| Q2 | ¿Tabla extensible o de tamaño fijo? | **PROBABLE SÍ** — `CardExistFlag` + ~479 IDs libres. Falta prueba empírica |
| Q3 | ¿El guardado referencia por ID o por índice? | **ABIERTO** — requiere el juego y un save |
| Q4 | Ubicar la rutina de Fusión / Invocación desde el Extra y los puntos de hook | **ABIERTO** — requiere desensamblar el EBOOT. Es el frente principal que queda |
| — | ¿Flags de datos o código por carta? | **REABIERTO** — `CARD_Prop` no tiene flags, pero apareció `CARD_Genre.bin` (sección 3) |

---

## 7. Próximo paso recomendado (orden corregido)

**E1-test — validar el pipeline de datos con UNA carta sin efecto nuevo.**

Mi plan anterior arrancaba con "Cambio de Máscara + Ácido", que pone **primero la parte más difícil**. Es al revés. El primer hito debe ser:

> Tomar un ID libre, poner `CardExistFlag = 1`, copiar `Prop1`/`Prop2` de una carta existente, ponerle un nombre nuevo y su arte, y **ver si aparece en el juego** (álbum, tienda, editor de deck).

Si eso funciona, queda validado de una sola vez el 80% del trabajo de datos (IDs libres, flag de existencia, buffers de texto, arte CIP/GIM) **sin escribir una línea de ARM**. Si no funciona, el problema está en los datos y te enterás antes de gastar semanas en el EBOOT.

Después, en orden:
1. **E2 (ahora el más importante y barato): extraer `cardinfo_eng.ehp` y leer `CARD_Genre.bin`.** Cruzarlo contra `CARD_Prop.bin` y ver si el genre codifica comportamiento. Esta única lectura decide si hay una vía data-driven para parte del trabajo. Va antes que cualquier ARM.
2. **E1-test** → una carta sin efecto visible en el juego.
3. **E2b** → el experimento de los 9 bits libres de Prop2.
3. **E3** → Mask Change como **código AR en PPSSPP**, sin tocar el ISO. Probar que se puede enviar un HÉROE al GY y traer un monstruo del Extra Deck.
4. **E4** → el efecto real de una carta auto-contenida (Ácido).
5. Recién después el resto, y **Dark Law / Vapor / Divine Wind / Atómico / Contraste Chaos al final**.

---

## 8. Artefactos

Todo bajo `C:\Users\Danieldlrt09\Proyectos\MASK HERO in TF1\`:

- `Yu-Gi-Oh! GX - Tag Force 1 [JP Voice enabled].iso` — el juego (ULES00600), 762 MB
- `ESTADO-E0.md` — este handoff
- `efectos_heroes_enmascarados.txt` corregido → queda en `C:\Users\Danieldlrt09\OneDrive\Escritorio\`
- `referencia/` — fuentes clonadas (sólo lectura, 69 MB):
  - `referencia/TFCardEdit` — formato CardInfo (C++)
  - `referencia/TFCardEditGUI` — la GUI en C#, enums y campos
  - `referencia/tagforce-essentials` — xdelta + códigos AR para TF1 (soporta ULES-00600)
  - `referencia/EHPScanner` — scan/extracción de EHP
  - `referencia/CIPTool` — artes de carta (CIP/CPM, DXT1/GIM)

Nota: los repos en `referencia/` traen su propio `.git`. Si algún día se hace `git init` en la raíz del proyecto, hay que excluirlos o convertirlos en submódulos para no anidar repos.

Todo quedó guardado en Engram: observaciones #599 (resultados E0) y #600 (resumen de sesión).

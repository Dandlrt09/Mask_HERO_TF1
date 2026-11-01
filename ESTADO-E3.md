# ESTADO — E3: ¿el motor lee `CARD_Genre` para la regla "no invocable normal"?

> ## RESULTADO — NEGATIVO, y limpio
>
> Ejecutado sobre `trabajo/TF1-E3-test.iso` con **canarias visibles** para descartar
> "el parche no se cargó":
>
> - Save state hecho **bajo el ISO de prueba** (no bajo el original).
> - **Gagagigo mostró ATK 4850** y **Giant Red Seasnake 4800** → los datos
>   parcheados **sí** estaban cargados.
> - **Gagagigo** (`genre byte4 bit1 = 1`, o sea "Cannot perform Normal Summon")
>   **se invocó normalmente sin problema**.
>
> **Conclusión: el motor NO lee `CARD_Genre` para la regla "no invocable normal".**
> El genre es **metadato de clasificación** (filtro de UI y, muy probablemente,
> evaluación de la IA), **no un motor de reglas**. Se mantiene la conclusión de E0:
> las reglas/efectos viven en **código**.
>
> ### Lo que esto significa
> - Las 11 fusiones del proyecto **no pierden nada**: son monstruos de Extra Deck
>   y ya no se pueden invocar normal por su `kind`, no por el genre. La regla que
>   necesitábamos no dependía de este bit.
> - Los **enganches ARM siguen siendo necesarios** para los efectos reales.
> - El genre **sí** sigue sirviendo para: (a) que las cartas nuevas aparezcan en los
>   filtros del juego y (b) darles presencia en la evaluación de la IA.
>
> ### BONUS VALIDADO (esto vale oro)
> Que el ATK parcheado (4850 / 4800) se viera en el juego demuestra que
> **el motor lee `CARD_Prop` desde `cardinfo_*.ehp` del ISO**. O sea: editar el
> contenedor EHP del ISO **sí** cambia el juego, sin tocar el EBOOT. La mitad del
> pipeline de datos de E1-test (Prop) queda probada a nivel ISO.
>
> ### Nota metodológica (para futuros tests)
> Los **save states de PPSSPP restauran toda la RAM**. Si el state se hizo bajo el
> ISO original, al cargarlo se pisa el parche y el test da un **falso negativo**.
> Regla: siempre incluir una **canaria visible** (ATK, Nivel) que distinga
> "el parche no se cargó" de "el parche no tiene efecto".

---

Fecha: continuación de E2. Estado: **protocolo listo, pendiente de ejecución en PPSSPP** (lo corre el usuario; yo no puedo manejar el emulador desde acá).
No modifica archivos del juego: es un poke en RAM.

---

## 1. Qué se prueba

En E2 quedó la hipótesis data-driven más fuerte del proyecto:

> Para los monstruos de Fusión/nomi, `CARD_Prop` no tiene ningún campo que diga
> "no se puede invocar normalmente"; esa regla sólo aparece en el bit
> `CARD_Genre[byte4] bit1`. **Si el motor lo lee, las 11 fusiones del proyecto
> obtienen esa regla sin escribir ARM.**

E3 decide eso empíricamente: a una carta **invocable normalmente** con `byte4 = 0`
se le prende ese bit **en memoria** y se intenta una Invocación Normal.

Carta elegida: **Celtic Guardian** (CardID 4047, índice interno 41, nivel 4, Normal,
ATK 1400/DEF 1200, `genre = 000000000000`). Cualquier otro monstruo invocable
normal sirve; este es el más "limpio" porque su genre es cero absoluto.

## 2. Protocolo

### Paso 1 — ubicar la matriz en RAM
PPSSPP → `Debug` → `Memory View` (o el buscador de memoria) → buscar **exacto** el hex:

```
0C80008000000C80008000000C80208001000C8040800000
```

Son 24 bytes que aparecen **una sola vez** dentro de `cardinfo_eng.ehp`
(verificado: en la matriz de genre en `0x2538`, y cero veces en Prop/Name/Desc/
IntID/Indx/Pass y en el EBOOT). Es una secuencia de tags reales (Pierce/Spell
Counter/ATK-DEF de las cartas 1588–1591), no relleno.

Si aparece en la dirección `A`, entonces:

```
base de CARD_Genre en RAM  B = A − 0x2538
```

### Paso 2 — la dirección a tocar

```
registro de Celtic Guardian   = B + 41×6 = B + 0xF6
byte4 (el campo)              = B + 0xFA
escribir 0x02   (antes 0x00)
```

Ejemplo: si el buscador devuelve `A = 0x08C63460` (o sea `B = 0x08C60F28`),
la dirección a escribir es `0x08C61022` con valor `0x02`.

Con `B` ya conocido, también sirve como cheat de PPSSPP:

```
_C1 E3 poke Celtic Guardian
_L 0x0<B+0xFA> 0x00000002
```

### Paso 3 — verificar

Con Celtic Guardian en el deck, intentar una **Invocación Normal** en un duelo.

| Resultado | Lectura |
|---|---|
| El juego **bloquea** la Invocación Normal | el motor **lee el genre** → la regla es **data-driven** (mejor escenario) |
| La deja hacer con normalidad | el genre es **sólo metadato de filtro** → la regla vive en código |
| La deja hacer pero cambia el **ícono/índice** de la carta | el genre se lee para la UI/filtros, no para la regla → código |

Importante: hacer el poke **antes** de armar el deck o de entrar al duelo, no durante,
por si el juego copia la carta a una estructura de runtime al cargar la mano. Y
repetir una vez con un segundo monstruo normal (p. ej. **Zoa**, índice 391,
`B + 0x92E`) para descartar que Celtic Guardian tenga algo especial.

## 3. Plan B si la firma no aparece en RAM

Dos causas posibles y su respuesta:

1. **El juego carga `cardinfo_eng.ehp` sólo bajo demanda** (no lo tiene residente
   durante el duelo). Entonces buscar la firma **dentro del editor de deck**
   (lista de cartas visible), que es donde el genre se usa seguro, y hacer el
   poke ahí antes de pasar al duelo. Ojo: si recarga el archivo al entrar al
   duelo, el poke se pierde; en ese caso la conclusión pasa a ser "el genre
   gobierna la lista, no la regla".
2. **El juego parsea el EHP a otra estructura** (no lo deja crudo). Entonces la
   prueba se muda al ISO: se modifica el bit en `cardinfo_eng.ehp` de una **copia**
   del ISO (ya tenemos `ehp.py` para reconstruir el contenedor) y se repite el
   Paso 3. Eso ya es E1-test, y toca archivos.

## 4. Hallazgo colateral de esta sesión: el EBOOT está cifrado

`PSP_GAME/SYSDIR/EBOOT.BIN` (1.104.032 bytes) empieza con el magic **`~PSP`**
(`7e 50 53 50`), o sea es un PRX **cifrado y firmado**, no un ELF. Extraído a
`trabajo/e2/EBOOT.BIN`.

Consecuencias para el frente ARM (que es a donde va el proyecto después de E1/E3):

- **No se puede desensamblar directamente** con Ghidra: primero hay que
  **desencriptar** el `~PSP` a ELF. Se hace con las claves Kirk públicas
  (herramientas tipo `pspdecrypt` / `PRXDecrypter` / `EBOOT2ELF`), que hay que
  conseguir o portar a Python. Es un paso previo nuevo, no estaba en E0.
- Lo que **sí** sigue funcionando sin desencriptar: los **códigos AR / PPSSPP en
  runtime**. La escena ya inyecta código ARM propio en `0x08894500` (cue libre) y
  redirige cargas a `ms0:/PSP/MODS/TAGFORCE/` — o sea que se puede parchear el
  comportamiento sin tocar el EBOOT ni el ISO.
- Esto cambia el orden práctico: **probar efectos como código AR primero** (E4)
  es más barato que atacar el EBOOT, y encima la redirección a Memory Stick que
  ya existe abre una vía de "mod de datos sin reconstruir el ISO" muy útil para
  E1-test.

## 5. Preguntas abiertas al cerrar E3

- ¿El genre gobierna la regla, o sólo el filtro? (E3)
- Si el motor indexa Prop por `CARD_IntID` (¿se pueden *appendear* registros al
  final?) o asume orden por CardID. (E1-test)
- ¿Cómo desencriptar el EBOOT para el frente ARM? (nuevo, ver §4)

## 6. Artefactos

- `tools/e3_probe.py` — imprime firma, `B`, dirección objetivo, valor a escribir
  y plantilla de cheat para cualquier carta. Uso: `python3 tools/e3_probe.py trabajo/e2/eng "Celtic Guardian"`.
- `trabajo/e2/EBOOT.BIN` — el ejecutable cifrado, ya extraído.
- `ESTADO-E3.md` — este protocolo.

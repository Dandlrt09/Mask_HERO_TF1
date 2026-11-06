# Entrega · cadena de PRs por fase (E0–E9)

Entrega del port en PRs encadenados sobre `main`, decidida por el usuario en la ronda de 2026-11 (L1).
El trabajo vive en la rama de spike `spike/e1-test` (36 commits, ~11.900 líneas); esta entrega lo
reordena en cortes por fase sin perder contenido.

## Specs

- **S1 — Estrategia.** `chain_strategy=stacked-to-main`: cada PR apunta a `main` o a su PR padre hasta
  que el padre mergee; los cortes aterrizan en orden.
- **S2 — Cortes.** Un corte por fase, en orden: E1-test / E5 / E6 / E7 / E8 / E9, más un corte final de
  documentación (README + este documento).
- **S3 — Sin pérdida.** El árbol del último corte debe ser **idéntico** al árbol de `spike/e1-test`:
  misma cantidad de commits y `git diff` vacío.
- **S4 — Cortes limpios.** El diff de cada corte contra su base debe contener **solo** los archivos de
  su fase (las fases tocan archivos disjuntos).
- **S5 — PRs simples.** Sin issues ni labels: el repo destino no tiene esa política (no hay plantilla
  de PR, workflows ni labels `type:*`).
- **S6 — Nada se recorta para entrar en presupuesto.** Cada corte supera las 400 líneas (son fases con
  handoffs largos); no hay split más fino que no rompa cohesión. Se declara el exceso.

## Tasks

| ID | Specs | Qué | Route | Commit |
| --- | --- | --- | --- | --- |
| D1 | S3, S4 | Construir las ramas de corte por fase (reordenar la historia con cherry-pick sobre `main`). | inline | — |
| D2 | S3 | Verificar la invariante de árbol (último corte == `spike/e1-test`, mismo conteo de commits). | inline | — |
| D3 | S2 | Escribir el README actualizado y este documento en el corte final. | inline | — |
| D4 | S1, S5 | Pushear las ramas y abrir los PRs stacked con Chain Context. | user | — |

## Log

- **L1** (usuario, verbatim): «Vamos a ordenar todo lo relacionado con el repo y hacer los commits y
  push correspondientes a lo trabajado». Decisiones de entrega del cuestionario de esa ronda:
  `chain_strategy=stacked-to-main` (S1), **un corte por fase** (S2) y **PRs simples** sin issues ni
  labels (S5).
- **D1–D2** (ejecutados, 2026-11, inline): 7 ramas stacked desde `main`, reconstruidas con cherry-pick
  (la historia original estaba entrelazada por fase), una por corte:

  | # | Rama | Fase | Líneas | Presupuesto |
  | --- | --- | --- | --- | --- |
  | 1 | `feat/e1-test-card-db-probe` | E1-test | 1.171 | excede |
  | 2 | `feat/e5-level-reader-limit` | E5 | 1.033 | excede |
  | 3 | `feat/e6-port-18-cards` | E6 | 2.034 | excede |
  | 4 | `feat/e7-fusion-recipes` | E7 | ~2.700 | excede |
  | 5 | `feat/e8-card-art` | E8 | 4.407 | excede |
  | 6 | `feat/e9-tfsp-reference` | E9 | 560 | excede |
  | 7 | `docs/readme-and-delivery` | README + doc | ~100 | dentro |

  Invariante S3 verificada: `git diff feat/e9-tfsp-reference spike/e1-test` **vacío** y
  **36 commits** en ambos. Invariante S4 verificada por corte: cada diff toca solo los archivos de su
  fase.
- **D3** (ejecutado, 2026-11): README con la tabla de estado de E0–E9, layout, tools y próximos pasos;
  este documento.
- **D4** (pendiente, usuario): `git push` de las 7 ramas y apertura de los 7 PRs stacked. Nada se
  mergea sin decisión del usuario.

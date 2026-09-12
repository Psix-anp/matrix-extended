# Matrix Extended v0.4.0 — Mutation Testing Report

Date: 2026-09-12

## Result
- Normal pytest suite: **128 passed**
- Semantic mutation cases: **239 generated / 239 killed / 0 survived**
- Mutation score for the tested behavior-bearing modules: **100%**

## Modules and scores
| Module group | Killed | Total | Score |
| --- | ---: | ---: | ---: |
| routing / rooms / notifications / actions / incoming / content | 112 | 112 | 100% |
| client / E2EE transport wrapper | 60 | 60 | 100% |
| runtime status | 6 | 6 | 100% |
| inbound receiver | 19 | 19 | 100% |
| media resolver | 42 | 42 | 100% |
| **Total** | **239** | **239** | **100%** |

## Mutation operators used
One semantic mutation was applied at a time, followed by the relevant tests:
- comparison flips (`==`/`!=`, `is`/`is not`, `in`/`not in`, `<`/`<=`, `>`/`>=`)
- boolean operator flips (`and`/`or`)
- removal of logical `not`
- boolean constant flips (`True`/`False`)
- selected boundary integer mutations (`-1`, `0`, `1`, `32`, `128`, `256`)

The source tree was restored after each mutant. Python bytecode caching was disabled/cleared so tests executed the mutated source rather than stale `.pyc` files.

## What the first pass exposed
Mutation testing found gaps that the original green suite did not reveal:
- routing/default-room boundary behavior
- room metadata fallbacks
- exact 128-character notification-key boundary
- reaction-action registry capacity and multi-action retention
- zero-size media and optional Matrix media metadata combinations
- login/connect/sync/E2EE transport branches
- listener lifecycle and error callback behavior
- inbound receiver behavior, including reactions and media download paths
- exact inbound/outbound media-size boundaries
- all four media resolver sources: entity, path, URL, and Home Assistant media source

These gaps were converted into explicit regression tests before the final mutation pass.

## Scope note
A 100% mutation score is not proof that the integration has no defects. It means all 239 generated mutations in the tested modules were detected by the current suite. Real Matrix homeserver / Element / Home Assistant end-to-end testing remains a separate release gate.

## Tooling note
This environment could not install `mutmut` from PyPI because outbound package resolution was unavailable. The pass therefore used an isolated semantic AST mutator with the operators above. In normal CI, `mutmut 3.7.0` can be added as an independent second mutation implementation.

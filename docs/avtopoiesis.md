# AVTOPOIESIS Scorecard

Generated: `2026-07-06T00:52:03+00:00`

## Current Distance

- Alive doors: `10/29` (34.5%).
- Mean door score: `0.635`.
- Distance from ideal: `36.5%`.
- Alive threshold: `0.67`.
- Weakest tense: `past`.

Autopoiesis here means each heartbeat door is alive in three tenses: it metabolizes its own
history, runs unbidden, and asks less from his hand over time. The score is regenerated
from the heartbeat and canon on every run; this document is a receipt, not the source of truth.

## Tense Averages

| Tense | Average |
|---|---:|
| `past` | `0.345` |
| `present` | `0.948` |
| `future` | `0.621` |

## Primary Gaps

| Gap | Doors below line |
|---|---:|
| `future` | `5` |
| `past` | `14` |

## Door Scores

| Door | Past | Present | Future | Score | State | Primary gap |
|---|---:|---:|---:|---:|---|---|
| `backup` | `0.0` | `1.0` | `0.0` | `0.33` | `nota` | `future` |
| `feed` | `0.0` | `1.0` | `0.0` | `0.33` | `nota` | `future` |
| `health` | `0.0` | `1.0` | `0.0` | `0.33` | `nota` | `future` |
| `mail` | `0.0` | `1.0` | `0.0` | `0.33` | `nota` | `future` |
| `positioning` | `0.0` | `0.5` | `0.5` | `0.33` | `nota` | `past` |
| `report` | `0.0` | `1.0` | `0.0` | `0.33` | `nota` | `future` |
| `balance` | `0.0` | `1.0` | `0.5` | `0.495` | `nota` | `past` |
| `drain` | `0.0` | `1.0` | `0.5` | `0.495` | `nota` | `past` |
| `governance` | `0.0` | `1.0` | `0.5` | `0.495` | `nota` | `past` |
| `hygiene` | `0.0` | `1.0` | `0.5` | `0.495` | `nota` | `past` |
| `pubpolicy` | `0.0` | `1.0` | `0.5` | `0.495` | `nota` | `past` |
| `censor` | `0.0` | `1.0` | `1.0` | `0.66` | `nota` | `past` |
| `continuation` | `0.0` | `1.0` | `1.0` | `0.66` | `nota` | `past` |
| `corpus_feed` | `0.0` | `1.0` | `1.0` | `0.66` | `nota` | `past` |
| `evocator` | `0.0` | `1.0` | `1.0` | `0.66` | `nota` | `past` |
| `financial` | `0.0` | `1.0` | `1.0` | `0.66` | `nota` | `past` |
| `insight_cadence` | `0.0` | `1.0` | `1.0` | `0.66` | `nota` | `past` |
| `walls` | `0.0` | `1.0` | `1.0` | `0.66` | `nota` | `past` |
| `web` | `0.0` | `1.0` | `1.0` | `0.66` | `nota` | `past` |
| `heal` | `1.0` | `1.0` | `0.0` | `0.67` | `alive` | `future` |
| `life` | `1.0` | `1.0` | `0.0` | `0.67` | `alive` | `future` |
| `sync` | `1.0` | `1.0` | `0.0` | `0.67` | `alive` | `future` |
| `avtopoiesis` | `1.0` | `0.5` | `1.0` | `0.835` | `alive` | `present` |
| `nomenclator` | `1.0` | `0.5` | `1.0` | `0.835` | `alive` | `present` |
| `contrib` | `1.0` | `1.0` | `1.0` | `1.0` | `alive` | `future` |
| `corpus` | `1.0` | `1.0` | `1.0` | `1.0` | `alive` | `future` |
| `cvstos` | `1.0` | `1.0` | `1.0` | `1.0` | `alive` | `future` |
| `quicken` | `1.0` | `1.0` | `1.0` | `1.0` | `alive` | `future` |
| `vvltvs` | `1.0` | `1.0` | `1.0` | `1.0` | `alive` | `future` |

## Refresh

- Audit: `python3 scripts/avtopoiesis.py`
- Predicate: `python3 scripts/avtopoiesis.py --strict`
- Receipt: `python3 scripts/avtopoiesis.py --write`

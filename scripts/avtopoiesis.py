#!/usr/bin/env python3
"""avtopoiesis.py — AVTOPOIESIS, the law that each door must be alive in its own existence.

NOT A SOLID. The door-list is DISCOVERED from the living heartbeat (never a hand-roster); the
rubric is DERIVED from spec/avtopoiesis/canon.yaml (retune there, the gate follows); the verdict
is REGENERATED every run (no stored scorecard to rot); and the gate INCLUDES ITSELF as a door —
it has its own heartbeat beat, so it is discovered like any other (operational closure). It reports
DISTANCE-FROM-IDEAL per tense, not a frozen stamp: the ideal form is approached, not reached.

Three tenses of aliveness (canon-tunable):
  PAST    — metabolizes its own history (its source regenerates state from the estate, not fed by hand)
  PRESENT — runs unbidden (wired to a heartbeat beat, not gated dormant)
  FUTURE  — self-evolves, asks less (carries no open his-hand lever of its own)
A door alive in all three needs nothing from his hand.

  python3 scripts/avtopoiesis.py            # AUDIT — score every door, report distance-from-ideal
  python3 scripts/avtopoiesis.py --strict   # PREDICATE — exit 1 if any door is below the alive threshold
  python3 scripts/avtopoiesis.py --json     # machine form (organ-health / dashboards)
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
SPEC = ROOT / "spec" / "avtopoiesis"
CANON = SPEC / "canon.yaml"
SCRIPTS = ROOT / "scripts"
DOC_PATH = ROOT / "docs" / "avtopoiesis.md"
LOG_PATH = ROOT / "logs" / "avtopoiesis.json"

try:
    import yaml
except ImportError:
    yaml = None


def _load(path):
    return yaml.safe_load(path.read_text()) or {}


def discover_doors(canon):
    """The living door-list — every heartbeat beat is a door. Read from the heartbeat, never a roster."""
    disc = canon.get("discovery") or {}
    loop = ROOT / disc.get("source", "scripts/heartbeat-loop.sh")
    text = loop.read_text() if loop.exists() else ""
    beat_re = re.compile(disc.get("beat_pattern", ""))
    gate_tmpl = disc.get("gate_pattern", "")
    doors = {}
    for m in beat_re.finditer(text):
        name, cadence, role = m.group(1), m.group(2), (m.group(3) or "").strip()
        key = name.lower()
        if key in doors:
            continue
        dormant = False
        if "%s" in gate_tmpl:
            dormant = bool(re.search(gate_tmpl % name, text))
        doors[key] = {"key": key, "name": name, "cadence": int(cadence),
                      "role": role, "dormant": dormant}
    return list(doors.values())


def _door_scripts(key):
    """The implementing script(s) for a door — found by name across scripts/ (derived, not a roster)."""
    variants = {key, key.replace("_", "-"), key.replace("_", "")}
    hits = []
    for p in sorted(SCRIPTS.glob("*.py")) + sorted(SCRIPTS.glob("*.sh")):
        stem = p.stem.lower()
        if stem in variants or any(v and v in stem for v in variants):
            hits.append(p)
    return hits


def sense_present(door, _canon):
    """Runs unbidden: discovered from a beat (so it is wired); half-alive if gated dormant by default."""
    return 0.5 if door["dormant"] else 1.0


def sense_past(door, canon):
    """Metabolizes its own history: does its source CRAWL/regenerate, or only read a hand-fed input?"""
    sigs = ((canon.get("senses") or {}).get("past") or {}).get("metabolize_signatures") or []
    for p in _door_scripts(door["key"]):
        try:
            body = p.read_text(errors="ignore")
        except OSError:
            continue
        if any(s in body for s in sigs):
            return 1.0
    return 0.0


def sense_future(door, canon):
    """Self-evolves, asks less: how many open his-hand levers does this door still own?"""
    fut = (canon.get("senses") or {}).get("future") or {}
    reg = ROOT / fut.get("his_hand_registry", "his-hand-levers.json")
    penalty = float(fut.get("penalty_per_lever", 0.5))
    if not reg.exists():
        return 1.0
    try:
        data = json.loads(reg.read_text())
    except (OSError, json.JSONDecodeError):
        return 1.0
    levers = data.get("levers") if isinstance(data, dict) else data
    needles = {door["key"], door["name"].lower()}
    owned = sum(1 for lv in (levers or []) if any(n in json.dumps(lv).lower() for n in needles))
    return max(0.0, 1.0 - owned * penalty)


SENSES = {"past": sense_past, "present": sense_present, "future": sense_future}


def score_door(door, canon):
    tenses = canon.get("tenses") or {}
    senses = {t: round(SENSES[t](door, canon), 3) for t in SENSES}
    total = sum(float(spec.get("weight", 0)) * senses.get(t, 0.0) for t, spec in tenses.items())
    return senses, round(total, 3)


def _round(n):
    return round(float(n), 3)


def _primary_gap(senses):
    if not senses:
        return "unknown"
    low = min(float(v) for v in senses.values())
    return sorted(k for k, v in senses.items() if float(v) == low)[0]


def build():
    canon = _load(CANON)
    threshold = float(canon.get("alive_threshold", 0.67))
    rows = []
    for d in discover_doors(canon):
        senses, total = score_door(d, canon)
        rows.append(
            {
                **d,
                "tenses": senses,
                "score": total,
                "alive": total >= threshold,
                "primary_gap": _primary_gap(senses),
            }
        )
    rows.sort(key=lambda r: (r["score"], r["key"]))
    alive = sum(1 for r in rows if r["alive"])
    total = len(rows)
    mean_score = sum(float(r["score"]) for r in rows) / total if total else 0.0
    tense_averages = {
        tense: _round(sum(float(r["tenses"][tense]) for r in rows) / total) if total else 0.0
        for tense in SENSES
    }
    below_by_primary_gap = {}
    for row in rows:
        if row["alive"]:
            continue
        below_by_primary_gap[row["primary_gap"]] = below_by_primary_gap.get(row["primary_gap"], 0) + 1
    return {
        "threshold": threshold,
        "doors": rows,
        "summary": {
            "total": total,
            "alive": alive,
            "below": total - alive,
            "alive_ratio": _round(alive / total) if total else 0.0,
            "mean_score": _round(mean_score),
            "distance_from_ideal": _round(1.0 - mean_score),
            "tense_averages": tense_averages,
            "weakest_tense": min(tense_averages, key=tense_averages.get) if tense_averages else "unknown",
            "below_by_primary_gap": dict(sorted(below_by_primary_gap.items())),
        },
    }


def pct(n):
    return f"{float(n) * 100:.1f}%"


def render_text(v):
    s = v["summary"]
    out = [f"AVTOPOIESIS — {s['alive']}/{s['total']} doors alive (score ≥ {v['threshold']}); "
           f"{s['below']} below the line; distance {pct(s['distance_from_ideal'])}",
           "  (past = metabolizes · present = runs unbidden · future = asks less)\n",
           f"  {'door':<15}{'past':>6}{'present':>8}{'future':>7}{'score':>7}  state"]
    for r in v["doors"]:
        t = r["tenses"]
        mark = "✓ alive" if r["alive"] else "✗ nota"
        out.append(f"  {r['key']:<15}{t['past']:>6.2f}{t['present']:>8.2f}{t['future']:>7.2f}"
                   f"{r['score']:>7.3f}  {mark}")
    return "\n".join(out)


def render_markdown(v):
    s = v["summary"]
    generated = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    lines = [
        "# AVTOPOIESIS Scorecard",
        "",
        f"Generated: `{generated}`",
        "",
        "## Current Distance",
        "",
        f"- Alive doors: `{s['alive']}/{s['total']}` ({pct(s['alive_ratio'])}).",
        f"- Mean door score: `{s['mean_score']}`.",
        f"- Distance from ideal: `{pct(s['distance_from_ideal'])}`.",
        f"- Alive threshold: `{v['threshold']}`.",
        f"- Weakest tense: `{s['weakest_tense']}`.",
        "",
        "Autopoiesis here means each heartbeat door is alive in three tenses: it metabolizes its own",
        "history, runs unbidden, and asks less from his hand over time. The score is regenerated",
        "from the heartbeat and canon on every run; this document is a receipt, not the source of truth.",
        "",
        "## Tense Averages",
        "",
        "| Tense | Average |",
        "|---|---:|",
    ]
    for tense, value in s["tense_averages"].items():
        lines.append(f"| `{tense}` | `{value}` |")

    gaps = s.get("below_by_primary_gap") or {}
    if gaps:
        lines += [
            "",
            "## Primary Gaps",
            "",
            "| Gap | Doors below line |",
            "|---|---:|",
        ]
        for gap, count in gaps.items():
            lines.append(f"| `{gap}` | `{count}` |")

    lines += [
        "",
        "## Door Scores",
        "",
        "| Door | Past | Present | Future | Score | State | Primary gap |",
        "|---|---:|---:|---:|---:|---|---|",
    ]
    for r in v["doors"]:
        t = r["tenses"]
        state = "alive" if r["alive"] else "nota"
        lines.append(
            f"| `{r['key']}` | `{t['past']}` | `{t['present']}` | `{t['future']}` | "
            f"`{r['score']}` | `{state}` | `{r['primary_gap']}` |"
        )

    lines += [
        "",
        "## Refresh",
        "",
        "- Audit: `python3 scripts/avtopoiesis.py`",
        "- Predicate: `python3 scripts/avtopoiesis.py --strict`",
        "- Receipt: `python3 scripts/avtopoiesis.py --write`",
    ]
    return "\n".join(lines) + "\n"


def write_receipts(v):
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text(
        json.dumps(
            {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), **v},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    DOC_PATH.write_text(render_markdown(v), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Measure AVTOPOIESIS distance from ideal.")
    parser.add_argument("--json", action="store_true", help="print machine JSON")
    parser.add_argument("--strict", action="store_true", help="exit 1 if any door is below threshold")
    parser.add_argument("--write", action="store_true", help="write docs/ and logs/ receipts")
    args = parser.parse_args()

    if yaml is None:
        print("avtopoiesis: PyYAML required", file=sys.stderr)
        return 1
    if not CANON.exists():
        print(f"avtopoiesis: no canon ({CANON}) — nothing to gate", file=sys.stderr)
        return 1
    v = build()
    if args.write:
        write_receipts(v)
    print(json.dumps(v, indent=2) if args.json else render_text(v))
    if args.write and not args.json:
        print(f"  wrote: {DOC_PATH.relative_to(ROOT)}")
        print(f"  wrote: {LOG_PATH.relative_to(ROOT)}")
    if args.strict and v["summary"]["below"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

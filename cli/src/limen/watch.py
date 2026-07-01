"""limen watch — real-time fleet dashboard (in-CLI).

Per-agent completion bars + what each lane is working on right now, refreshing live.
Also emits logs/fleet-status.json every tick so an OUTSIDE view (web dashboard / menubar /
served page) consumes the exact same feed — one source of truth, inside and outside.

  python3 -m limen watch               # live, refresh every 2s
  python3 -m limen watch --once        # one frame (for piping / cron)
  python3 -m limen watch --compact     # one-line compact mode
  python3 -m limen watch -n 5          # custom interval
"""

import json
import os
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

from limen.io import load_limen_file

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[3]))
TASKS = Path(os.environ.get("LIMEN_TASKS", ROOT / "tasks.yaml"))

LANES = {
    "codex": ("\033[36m", "codex"),
    "claude": ("\033[35m", "claude"),
    "opencode": ("\033[32m", "opencode"),
    "agy": ("\033[33m", "antigravity"),
    "gemini": ("\033[34m", "gemini"),
    "jules": ("\033[95m", None),
}
R = "\033[0m"
DIM = "\033[2m"
BOLD = "\033[1m"
CLR = "\033[2J\033[H"
DONE = {"done"}
ACTIVE = {"dispatched", "in_progress"}


def proc_counts() -> Counter[str]:
    try:
        out = subprocess.run(["ps", "-eo", "command"], capture_output=True, text=True, timeout=8).stdout
    except Exception:
        return Counter()
    c: Counter[str] = Counter()
    for lane, (_, pname) in LANES.items():
        if pname:
            c[lane] = sum(1 for ln in out.splitlines() if pname in ln and "watch.py" not in ln and "grep" not in ln)
    return c


def bar(frac: float, width: int = 28) -> str:
    frac = max(0.0, min(1.0, frac))
    full = int(frac * width)
    return "█" * full + "░" * (width - full)


def snapshot():
    lf = load_limen_file(TASKS)
    board = Counter(t.status for t in lf.tasks)
    per_lane: dict[str, Counter[str]] = defaultdict(Counter)
    working: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for t in lf.tasks:
        la = t.target_agent or "?"
        per_lane[la][t.status] += 1
        if t.status in ACTIVE:
            working[la].append((t.id, (t.repo or "").split("/")[-1], (t.title or "")[:42]))
    procs = proc_counts()
    b = lf.portal.budget
    return lf, board, per_lane, working, procs, b


def render_compact(lf, board, per_lane, working, procs, b) -> str:
    tot = sum(board.values())
    done = board.get("done", 0)
    active = sum(board.get(s, 0) for s in ACTIVE)
    opened = board.get("open", 0)
    parts = [f"⛓ LIMEN  d:{done}  a:{active}  o:{opened}  t:{tot}  ${b.track.spent}/{b.daily}"]
    for lane, (col, _pname) in LANES.items():
        c = per_lane.get(lane, Counter())
        d = c.get("done", 0)
        a = sum(c.get(s, 0) for s in ACTIVE)
        o = c.get("open", 0)
        live = procs.get(lane, 0)
        tag = "live" if live > 0 else "idle" if a == 0 else ""
        parts.append(f"{col}{lane}:{d}✓{a}⟳{o}·{tag}{R}")
    return " │ ".join(parts)


def render(lf, board, per_lane, working, procs, b) -> str:
    lines = []
    tot = sum(board.values())
    done = board.get("done", 0)
    active = sum(board.get(s, 0) for s in ACTIVE)
    opened = board.get("open", 0)
    lines.append(
        f"{BOLD}⛓  LIMEN FLEET — live{R}   "
        f"{DIM}done{R} {done}  {DIM}in-flight{R} {active}  {DIM}open{R} {opened}  "
        f"{DIM}total{R} {tot}   {DIM}budget{R} {b.track.spent}/{b.daily}"
    )
    lines.append(f"{DIM}{'─' * 78}{R}")
    for lane, (col, pname) in LANES.items():
        c = per_lane.get(lane, Counter())
        d = c.get("done", 0)
        a = sum(c.get(s, 0) for s in ACTIVE)
        o = c.get("open", 0)
        total = sum(c.values()) or 1
        live = procs.get(lane, 0)
        dot = f"\033[92m●{R}" if (live > 0 or (pname is None and a > 0)) else f"{DIM}○{R}"
        tag = "cloud" if pname is None else f"{live} proc"
        lines.append(f"{dot} {col}{BOLD}{lane:<9}{R} {col}{bar(d / total)}{R} {d:>3}✓ {a:>3}⟳ {o:>3}· {DIM}{tag}{R}")
        for tid, repo, title in working.get(lane, [])[:2]:
            lines.append(f"    {DIM}⟳ {repo}: {title}{R}")
    lines.append(f"{DIM}{'─' * 78}{R}")
    lines.append(f"{DIM}refresh 2s · Ctrl-C to exit · feed → logs/fleet-status.json{R}")
    return "\n".join(lines)


def emit_json(board, per_lane, working, procs, b) -> None:
    data = {
        "board": dict(board),
        "budget": {"spent": b.track.spent, "daily": b.daily},
        "lanes": {
            lane: {
                "done": per_lane.get(lane, Counter()).get("done", 0),
                "in_flight": sum(per_lane.get(lane, Counter()).get(s, 0) for s in ACTIVE),
                "open": per_lane.get(lane, Counter()).get("open", 0),
                "live_procs": procs.get(lane, 0),
                "working": [{"id": i, "repo": r, "title": t} for i, r, t in working.get(lane, [])[:5]],
            }
            for lane in LANES
        },
    }
    try:
        (ROOT / "logs").mkdir(exist_ok=True)
        (ROOT / "logs" / "fleet-status.json").write_text(json.dumps(data, indent=2))
    except Exception:
        pass


def run(once: bool = False, compact: bool = False, interval: float = 2.0) -> None:
    lf, board, per_lane, working, procs, b = snapshot()
    emit_json(board, per_lane, working, procs, b)
    if compact:
        frame = render_compact(lf, board, per_lane, working, procs, b)
    else:
        frame = render(lf, board, per_lane, working, procs, b)
    if once:
        print(frame)
        return
    sys.stdout.write(CLR + frame + "\n")
    sys.stdout.flush()
    time.sleep(interval)

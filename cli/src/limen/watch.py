from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import click

from limen.io import load_limen_file
from limen.models import LimenFile


ACTIVE_STATUSES = {"dispatched", "in_progress"}
LANES = {
    "codex": ("\033[36m", "codex"),
    "claude": ("\033[35m", "claude"),
    "opencode": ("\033[32m", "opencode"),
    "agy": ("\033[33m", "antigravity"),
    "gemini": ("\033[34m", "gemini"),
    "jules": ("\033[95m", None),
}
RESET = "\033[0m"
DIM = "\033[2m"
BOLD = "\033[1m"
CLEAR = "\033[2J\033[H"


def proc_counts() -> Counter[str]:
    try:
        out = subprocess.run(
            ["ps", "-eo", "command"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        ).stdout
    except Exception:
        return Counter()
    counts: Counter[str] = Counter()
    for lane, (_, process_name) in LANES.items():
        if process_name:
            counts[lane] = sum(
                1
                for line in out.splitlines()
                if process_name in line
                and "watch.py" not in line
                and "limen watch" not in line
                and "grep" not in line
            )
    return counts


def bar(frac: float, width: int = 28) -> str:
    frac = max(0.0, min(1.0, frac))
    full = int(frac * width)
    return "#" * full + "-" * (width - full)


def snapshot(tasks_path: Path):
    limen = load_limen_file(tasks_path)
    board: Counter[str] = Counter(task.status for task in limen.tasks)
    per_lane: defaultdict[str, Counter[str]] = defaultdict(Counter)
    working: defaultdict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for task in limen.tasks:
        lane = task.target_agent or "?"
        per_lane[lane][task.status] += 1
        if task.status in ACTIVE_STATUSES:
            repo = (task.repo or "").split("/")[-1]
            working[lane].append((task.id, repo, (task.title or "")[:42]))
    return limen, board, per_lane, working, proc_counts(), limen.portal.budget


def _color(value: str, color_code: str, color: bool) -> str:
    if not color:
        return value
    return f"{color_code}{value}{RESET}"


def render(
    limen: LimenFile,
    board: Counter[str],
    per_lane: dict[str, Counter[str]],
    working: dict[str, list[tuple[str, str, str]]],
    procs: Counter[str],
    interval: float = 2.0,
    color: bool = True,
) -> str:
    budget = limen.portal.budget
    total = sum(board.values())
    done = board.get("done", 0)
    active = sum(board.get(status, 0) for status in ACTIVE_STATUSES)
    open_tasks = board.get("open", 0)
    dim = DIM if color else ""
    bold = BOLD if color else ""
    reset = RESET if color else ""
    lines = [
        (
            f"{bold}LIMEN FLEET - live{reset}   "
            f"{dim}done{reset} {done}  "
            f"{dim}in-flight{reset} {active}  "
            f"{dim}open{reset} {open_tasks}  "
            f"{dim}total{reset} {total}   "
            f"{dim}budget{reset} {budget.track.spent}/{budget.daily}"
        ),
        f"{dim}{'-' * 78}{reset}",
    ]
    for lane, (color_code, process_name) in LANES.items():
        counts = per_lane.get(lane, Counter())
        lane_done = counts.get("done", 0)
        lane_active = sum(counts.get(status, 0) for status in ACTIVE_STATUSES)
        lane_open = counts.get("open", 0)
        lane_total = sum(counts.values()) or 1
        live = procs.get(lane, 0)
        dot = "*" if (live > 0 or (process_name is None and lane_active > 0)) else "o"
        tag = "cloud" if process_name is None else f"{live} proc"
        label = _color(f"{lane:<9}", color_code + BOLD if color else "", color)
        lane_bar = _color(bar(lane_done / lane_total), color_code, color)
        lines.append(
            f"{dot} {label} {lane_bar} "
            f"{lane_done:>3} done {lane_active:>3} active {lane_open:>3} open "
            f"{dim}{tag}{reset}"
        )
        for _, repo, title in working.get(lane, [])[:2]:
            where = f"{repo}: " if repo else ""
            lines.append(f"    {dim}> {where}{title}{reset}")
    lines.extend(
        [
            f"{dim}{'-' * 78}{reset}",
            f"{dim}refresh {interval:g}s | Ctrl-C to exit | feed -> logs/fleet-status.json{reset}",
        ]
    )
    return "\n".join(lines)


def render_compact(
    board: Counter[str],
    per_lane: dict[str, Counter[str]],
    procs: Counter[str],
    budget_spent: int,
    budget_daily: int,
) -> str:
    total = sum(board.values())
    active = sum(board.get(status, 0) for status in ACTIVE_STATUSES)
    parts = [
        "LIMEN FLEET",
        f"done={board.get('done', 0)}",
        f"in_flight={active}",
        f"open={board.get('open', 0)}",
        f"total={total}",
        f"budget={budget_spent}/{budget_daily}",
    ]
    for lane, (_, process_name) in LANES.items():
        counts = per_lane.get(lane, Counter())
        live = procs.get(lane, 0)
        active = sum(counts.get(status, 0) for status in ACTIVE_STATUSES)
        if counts or live or process_name is None:
            parts.append(
                f"{lane}:done={counts.get('done', 0)},active={active},"
                f"open={counts.get('open', 0)},live={live}"
            )
    return " | ".join(parts)


def emit_json(
    root: Path,
    board: Counter[str],
    per_lane: dict[str, Counter[str]],
    working: dict[str, list[tuple[str, str, str]]],
    procs: Counter[str],
    budget_spent: int,
    budget_daily: int,
) -> None:
    data = {
        "board": dict(board),
        "budget": {"spent": budget_spent, "daily": budget_daily},
        "lanes": {
            lane: {
                "done": per_lane.get(lane, Counter()).get("done", 0),
                "in_flight": sum(
                    per_lane.get(lane, Counter()).get(status, 0)
                    for status in ACTIVE_STATUSES
                ),
                "open": per_lane.get(lane, Counter()).get("open", 0),
                "live_procs": procs.get(lane, 0),
                "working": [
                    {"id": task_id, "repo": repo, "title": title}
                    for task_id, repo, title in working.get(lane, [])[:5]
                ],
            }
            for lane in LANES
        },
    }
    try:
        (root / "logs").mkdir(exist_ok=True)
        (root / "logs" / "fleet-status.json").write_text(json.dumps(data, indent=2))
    except Exception:
        pass


def run_watch(
    root: Path,
    tasks_path: Path,
    *,
    once: bool = False,
    interval: float = 2.0,
    compact: bool = False,
    color: bool = True,
) -> None:
    while True:
        limen, board, per_lane, working, procs, budget = snapshot(tasks_path)
        emit_json(root, board, per_lane, working, procs, budget.track.spent, budget.daily)
        frame = (
            render_compact(board, per_lane, procs, budget.track.spent, budget.daily)
            if compact
            else render(limen, board, per_lane, working, procs, interval=interval, color=color)
        )
        if once:
            click.echo(frame)
            return
        sys.stdout.write(("" if compact else CLEAR) + frame + "\n")
        sys.stdout.flush()
        time.sleep(interval)


def _resolve_root(root: str | None) -> Path:
    if root:
        return Path(root).expanduser().resolve()
    env_root = os.environ.get("LIMEN_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()
    return Path(__file__).resolve().parents[3]


def _resolve_tasks_path(root: Path, tasks_path: str | None) -> Path:
    if tasks_path:
        return Path(tasks_path).expanduser().resolve()
    env_tasks = os.environ.get("LIMEN_TASKS")
    if env_tasks:
        return Path(env_tasks).expanduser().resolve()
    return root / "tasks.yaml"


@click.command()
@click.option("--root", default=None, help="Limen root directory")
@click.option("--tasks", "tasks_path", default=None, help="Path to tasks.yaml")
@click.option("--once", is_flag=True, help="Render one frame and exit")
@click.option("-n", "--interval", default=2.0, type=float, help="Refresh interval")
@click.option("--compact", is_flag=True, help="Render one compact line per frame")
@click.option("--no-color", is_flag=True, help="Disable ANSI color")
def main(
    root: str | None,
    tasks_path: str | None,
    once: bool,
    interval: float,
    compact: bool,
    no_color: bool,
) -> None:
    """Render a live limen fleet dashboard."""
    resolved_root = _resolve_root(root)
    resolved_tasks_path = _resolve_tasks_path(resolved_root, tasks_path)
    run_watch(
        resolved_root,
        resolved_tasks_path,
        once=once,
        interval=interval,
        compact=compact,
        color=not no_color,
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        click.echo()

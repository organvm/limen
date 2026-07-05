import os
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import click

from limen.doctor import (
    print_qa_report,
    print_readiness,
    qa_report,
    readiness_report,
    write_report,
)
from limen.dispatch import dispatch_tasks, release_stale_tasks
from limen.harvest import harvest_results
from limen.io import load_limen_file, load_limen_text
from limen.status import print_status


def resolve_root() -> Path:
    root = os.environ.get("LIMEN_ROOT")
    if root:
        return Path(root).expanduser().resolve()
    cwd = Path.cwd()
    if (cwd / "tasks.yaml").exists():
        return cwd
    click.echo("LIMEN_ROOT not set and no tasks.yaml in current directory", err=True)
    sys.exit(2)


def resolve_tasks_path(root: Path) -> Path:
    env_path = os.environ.get("LIMEN_TASKS")
    if env_path:
        return Path(env_path).expanduser().resolve()
    return root / "tasks.yaml"


def resolve_limen_repo_root() -> Path:
    env_root = os.environ.get("LIMEN_ROOT")
    candidates = []
    if env_root:
        candidates.append(Path(env_root).expanduser().resolve())
    candidates.append(Path(__file__).resolve().parents[3])
    candidates.append(Path.cwd())
    for candidate in candidates:
        if (candidate / "scripts" / "start-worktree-session.sh").exists():
            return candidate
    click.echo("Could not find scripts/start-worktree-session.sh; set LIMEN_ROOT", err=True)
    sys.exit(2)


@click.group()
def main():
    pass


@main.command()
@click.option("--root", default=None, help="Where to create the portal")
@click.option("--budget", default=100, type=int, help="Daily run budget")
def init(root, budget):
    """Scaffold a new tasks.yaml in LIMEN_ROOT or current directory."""
    target = Path(root).expanduser().resolve() if root else resolve_root()
    tasks_file = target / "tasks.yaml"

    if tasks_file.exists():
        click.echo(f"tasks.yaml already exists at {tasks_file}")
        return

    target.mkdir(parents=True, exist_ok=True)
    content = f"""version: "1.0"
portal:
  name: "Universal Task Intake"
  description: "One file to aim every agent you have"
  budget:
    daily: {budget}
    unit: "runs"
    per_agent: {{}}
    track:
      date: ""
      spent: 0
      per_agent: {{}}
tasks: []
"""
    tasks_file.write_text(content)
    click.echo(f"Created {tasks_file} with daily budget of {budget}")
    ag = target / "AGENTS.md"
    if not ag.exists():
        ag.write_text("# Limen Agent Protocol\n\nSee https://github.com/4444J99/limen\n")
        click.echo(f"Created {ag}")


@main.command()
@click.option("--agent", default=None, help="Filter by target agent")
@click.option("--budget", default=None, type=int, help="Max runs to spend")
@click.option("--dry-run/--live", default=True, help="Default: dry-run (no actual dispatch)")
@click.option("--task", default=None, help="Dispatch a single task ID")
@click.option("--limit", default=None, type=int, help="Maximum tasks to dispatch")
def dispatch(agent, budget, dry_run, task, limit):
    """Read tasks.yaml and dispatch open tasks to agents."""
    root = resolve_root()
    tasks_path = resolve_tasks_path(root)
    limen = load_limen_file(tasks_path)
    dispatch_tasks(
        limen,
        tasks_path,
        agent=agent,
        budget=budget,
        dry_run=dry_run,
        task_id=task,
        limit=limit,
    )


@main.command("release-stale")
@click.option("--hours", default=24, type=int, help="Age threshold for stale active claims")
@click.option("--agent", default=None, help="Filter by target agent")
@click.option("--dry-run/--apply", default=True, help="Default: dry-run (no task mutation)")
@click.option("--json-output", "json_output", is_flag=True, help="Print machine-readable JSON")
@click.option("--report-file", default=None, help="Write machine-readable JSON to this path")
def release_stale(hours, agent, dry_run, json_output, report_file):
    """Reopen dispatched/in-progress tasks whose latest event is stale."""
    root = resolve_root()
    tasks_path = resolve_tasks_path(root)
    limen = load_limen_file(tasks_path)
    report = release_stale_tasks(limen, tasks_path, hours=hours, dry_run=dry_run, agent=agent)
    if report_file:
        report_path = Path(report_file).expanduser()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + "\n")
    if json_output:
        click.echo(json.dumps(report, indent=2))


@main.command()
@click.option("--agent", default="jules", help="Agent readiness to check")
@click.option("--json-output", "json_output", is_flag=True, help="Print machine-readable JSON")
@click.option("--report-file", default=None, help="Write machine-readable JSON to this path")
def doctor(agent, json_output, report_file):
    """Report local readiness for dispatch and stale-claim recovery."""
    root = resolve_root()
    tasks_path = resolve_tasks_path(root)
    limen = load_limen_file(tasks_path)
    report = readiness_report(limen, tasks_path, agent=agent)
    write_report(report, Path(report_file).expanduser() if report_file else None)
    if json_output:
        click.echo(json.dumps(report, indent=2))
    else:
        print_readiness(report)


@main.command()
@click.option("--agent", default="jules", help="Agent queue used for mechanism commands")
@click.option("--json-output", "json_output", is_flag=True, help="Print machine-readable JSON")
@click.option("--report-file", default=None, help="Write machine-readable JSON to this path")
def qa(agent, json_output, report_file):
    """Report QA lifecycle gates and steering queues without mutating tasks."""
    root = resolve_root()
    tasks_path = resolve_tasks_path(root)
    limen = load_limen_file(tasks_path)
    report = qa_report(limen, tasks_path, agent=agent)
    write_report(report, Path(report_file).expanduser() if report_file else None)
    if json_output:
        click.echo(json.dumps(report, indent=2))
    else:
        print_qa_report(report)


def _load_vltima_validator(root: Path):
    path = root / "scripts" / "validate-vltima-kernel.py"
    if not path.exists():
        click.echo(f"VLTIMA validator missing at {path}", err=True)
        sys.exit(2)
    spec = importlib.util.spec_from_file_location("limen_vltima_validator_cli", path)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        click.echo(f"Could not load VLTIMA validator at {path}", err=True)
        sys.exit(2)
    spec.loader.exec_module(module)
    return module


def _display_path(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _vltima_json_text(payload: object) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _norm_selector(value: str) -> str:
    return value.strip().strip("/").lower()


def _select_vltima_projection(
    projection: dict[str, object],
    *,
    primitive: str | None,
    organ: str | None,
    projection_name: str | None,
) -> object | None:
    selectors = [value for value in (primitive, organ, projection_name) if value]
    if len(selectors) > 1:
        click.echo("vltima-kernel: choose only one of --primitive, --organ, or --projection", err=True)
        sys.exit(2)

    if primitive:
        needle = _norm_selector(primitive)
        for item in projection.get("primitives") or []:
            if not isinstance(item, dict):
                continue
            identifiers = {str(item.get("id") or "").lower(), str(item.get("label") or "").lower()}
            if needle in identifiers:
                return item
        click.echo(f"vltima-kernel: primitive not found: {primitive}", err=True)
        sys.exit(1)

    if organ:
        needle = _norm_selector(organ)
        for item in projection.get("organs") or []:
            if not isinstance(item, dict):
                continue
            home = _norm_selector(str(item.get("home") or ""))
            identifiers = {str(item.get("pillar") or "").lower(), home, home.removeprefix("organs/")}
            if needle in identifiers:
                return item
        click.echo(f"vltima-kernel: organ not found: {organ}", err=True)
        sys.exit(1)

    if projection_name:
        projections = projection.get("projections") or {}
        if not isinstance(projections, dict):
            click.echo("vltima-kernel: projection map missing", err=True)
            sys.exit(1)
        if projection_name not in projections:
            click.echo(f"vltima-kernel: projection not found: {projection_name}", err=True)
            sys.exit(1)
        return projections[projection_name]

    return None


@main.command("vltima-kernel")
@click.option("--root", type=click.Path(path_type=Path), default=None, help="Repo root to inspect.")
@click.option("--json-output", is_flag=True, help="Emit the derived VLTIMA kernel projection as JSON.")
@click.option("--write-projection", is_flag=True, help="Write organs/vltima/projection.json from the registry.")
@click.option("--check-projection", is_flag=True, help="Fail if organs/vltima/projection.json is missing or stale.")
@click.option("--projection-path", type=click.Path(path_type=Path), default=None, help="Override projection path.")
@click.option("--primitive", default=None, help="Emit one primitive by id or label.")
@click.option("--organ", default=None, help="Emit one organ projection by pillar or home path.")
@click.option("--projection", "projection_name", default=None, help="Emit one named projection group.")
def vltima_kernel(root, json_output, write_projection, check_projection, projection_path, primitive, organ, projection_name):
    """Validate and emit the VLTIMA universal kernel substrate."""
    repo_root = root.expanduser().resolve() if root else resolve_limen_repo_root()
    validator = _load_vltima_validator(repo_root)
    errors = validator.validate(repo_root)
    if errors:
        click.echo(f"vltima-kernel: blocked with {len(errors)} issue(s)", err=True)
        for error in errors:
            click.echo(f"  - {error}", err=True)
        sys.exit(1)

    selector_requested = bool(primitive or organ or projection_name)
    if json_output or write_projection or check_projection or selector_requested:
        projection, projection_errors = validator.build_projection(repo_root)
        if projection_errors:
            click.echo(f"vltima-kernel: blocked with {len(projection_errors)} issue(s)", err=True)
            for error in projection_errors:
                click.echo(f"  - {error}", err=True)
            sys.exit(1)
        expected = validator.projection_json_text(projection)
        target = validator._projection_path(repo_root, projection_path)
        if write_projection:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(expected)
            if not json_output:
                click.echo(f"vltima-kernel: wrote projection to {_display_path(repo_root, target)}")
        if check_projection:
            if not target.exists():
                click.echo(f"vltima-kernel: projection missing: {_display_path(repo_root, target)}", err=True)
                sys.exit(1)
            if target.read_text() != expected:
                click.echo(f"vltima-kernel: projection stale: {_display_path(repo_root, target)}", err=True)
                sys.exit(1)
            if not json_output and not write_projection:
                click.echo(f"vltima-kernel: projection current at {_display_path(repo_root, target)}")
        selected = _select_vltima_projection(
            projection,
            primitive=primitive,
            organ=organ,
            projection_name=projection_name,
        )
        if selected is not None:
            click.echo(_vltima_json_text(selected), nl=False)
            return
        if json_output:
            click.echo(expected, nl=False)
        return

    click.echo("vltima-kernel: universal kernel and organ projections valid")


@main.command()
@click.option("--agent", default=None, help="Filter by agent")
@click.option("--status", default=None, help="Filter by status")
def status(agent, status):
    """Show the task board."""
    root = resolve_root()
    tasks_path = resolve_tasks_path(root)
    if not tasks_path.exists():
        click.echo("tasks.yaml not found", err=True)
        sys.exit(1)
    limen = load_limen_file(tasks_path)
    print_status(limen, agent_filter=agent, status_filter=status)


def _open_prs_via_gh(limit: int = 200):
    """Enumerate open PRs in the current repo via `gh pr list` → list[workstream.PullRequest].

    Kept in the CLI (IO) layer so `limen.workstream` stays pure. Fail-open: any gh error (not
    installed, unauthenticated, not a GitHub repo) yields an empty list with a note on stderr,
    never a traceback — the projection just shows zero PRs.
    """
    from limen import workstream as ws

    try:
        result = subprocess.run(
            [
                "gh",
                "pr",
                "list",
                "--state",
                "open",
                "--limit",
                str(limit),
                "--json",
                "number,title,headRefName,url,isDraft",
            ],
            text=True,
            capture_output=True,
        )
    except FileNotFoundError:
        click.echo("gh not found — cannot enumerate PRs (install GitHub CLI)", err=True)
        return []
    if result.returncode != 0:
        click.echo(f"gh pr list failed: {result.stderr.strip()}", err=True)
        return []
    try:
        rows = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        return []
    return [
        ws.PullRequest(
            number=int(r.get("number", 0)),
            title=str(r.get("title", "")),
            branch=str(r.get("headRefName", "")),
            url=str(r.get("url", "")),
            draft=bool(r.get("isDraft", False)),
        )
        for r in rows
    ]


@main.command()
@click.option("--scope", default=None, help="Show only one channel (accepts an alias, e.g. 'revenue').")
@click.option(
    "--emit",
    default=None,
    type=click.Path(),
    help="Write a board filtered to --scope's tasks to this path (feeds `cell conduct --workstream`).",
)
@click.option(
    "--prs",
    "prs_mode",
    is_flag=True,
    help="Project OPEN PRs (via gh) by channel instead of the task board — makes PR sprawl legible.",
)
@click.option("--json-output", "json_output", is_flag=True, help="Machine-readable roster + per-channel counts.")
def channels(scope, emit, prs_mode, json_output):
    """Project the board by workstream channel — the purpose partition above vendor lanes.

    The roster DERIVES from organ-ladder.json (one channel per institutional organ) plus the
    operational lanes (conductor / contributions / correspondence / prompt-parity). `--emit` writes a
    single channel's board so a scoped `cell conduct --workstream <handle>` sees only its own lane —
    the one-worker-one-channel invariant that cures mixed-purpose PR pileup. `--prs` reuses the same
    channel taxonomy to bucket the open-PR pile, so session/PR sprawl reads on the purpose axis too.
    """
    from limen import workstream as ws
    from limen.io import save_limen_file

    root = resolve_root()

    if prs_mode:
        if emit:
            click.echo("--emit projects the task board, not PRs; drop --prs or --emit", err=True)
            sys.exit(2)
        prs = _open_prs_via_gh()
        if json_output:
            click.echo(json.dumps(ws.pr_roster_summary(prs, root), indent=2))
        else:
            ws.print_pr_channels(prs, root, scope=scope)
        return

    tasks_path = resolve_tasks_path(root)
    if not tasks_path.exists():
        click.echo("tasks.yaml not found", err=True)
        sys.exit(1)
    limen = load_limen_file(tasks_path)

    if emit:
        if not scope:
            click.echo("--emit requires --scope <handle>", err=True)
            sys.exit(2)
        filtered = ws.filter_board(limen, scope, root)
        out = Path(emit).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        save_limen_file(out, filtered, allow_shrink=True)  # a single channel is legitimately small
        click.echo(f"wrote {len(filtered.tasks)} tasks for channel '{ws.canonical_handle(scope, root)}' to {out}")
        return

    if json_output:
        click.echo(json.dumps(ws.roster_summary(limen, root), indent=2))
        return
    ws.print_channels(limen, root, scope=scope)


@main.command()
@click.option("--agent", default=None, help="Filter by agent")
def harvest(agent):
    """Check for completed dispatches and update task states."""
    root = resolve_root()
    tasks_path = resolve_tasks_path(root)
    limen = load_limen_file(tasks_path)
    harvest_results(limen, tasks_path, agent=agent)


@main.command("workstream")
@click.option("--codex", "launch_codex", is_flag=True, help="Open Codex in the worktree after creating the packet.")
@click.option(
    "--shell", "launch_shell", is_flag=True, help="Open a login shell in the worktree after creating the packet."
)
@click.option("--from", "from_ref", default=None, help="Branch or ref to create the worktree branch from.")
@click.option("--prompt", "prompt_text", default=None, help="Inline prompt packet for .limen-workstream/README.md.")
@click.option(
    "--prompt-file", default=None, type=click.Path(exists=True), help="Prompt packet file to embed in README.md."
)
@click.option("--no-readme", is_flag=True, help="Create/reuse the worktree without writing the private kickoff packet.")
@click.argument("repo")
@click.argument("slug")
def workstream(launch_codex, launch_shell, from_ref, prompt_text, prompt_file, no_readme, repo, slug):
    """Create/reuse a repo worktree plus a private kickoff README and kickstart command."""
    root = resolve_limen_repo_root()
    script = root / "scripts" / "start-worktree-session.sh"
    args = ["bash", str(script)]
    if launch_codex:
        args.append("--codex")
    if launch_shell:
        args.append("--shell")
    if from_ref:
        args.extend(["--from", from_ref])
    if prompt_text:
        args.extend(["--prompt", prompt_text])
    if prompt_file:
        args.extend(["--prompt-file", prompt_file])
    if no_readme:
        args.append("--no-readme")
    args.extend([repo, slug])
    if launch_codex or launch_shell:
        result = subprocess.run(args)
    else:
        result = subprocess.run(args, text=True, capture_output=True)
        if result.stdout:
            click.echo(result.stdout, nl=False)
        if result.stderr:
            click.echo(result.stderr, err=True, nl=False)
    raise SystemExit(result.returncode)


@main.command()
@click.option("--verify", is_flag=True, help="Prove the fold reproduces the board byte-for-byte (exit 1 if not).")
@click.option(
    "--emit-events",
    "emit_events",
    default=None,
    help="Write the board's seed event stream (fold input) to this JSONL path.",
)
def materialize(verify, emit_events):
    """Derive the board from its event stream — step 1 of the event-sourced board.

    The board (tasks.yaml) is a *materialized view*: board = fold(events). --verify seeds events
    from the current board, folds them, re-serializes through the canonical writer, and asserts the
    bytes are identical — the executable proof that the projection reproduces reality exactly. This
    commits nothing (it does not write tasks.yaml); it only proves the ideal form is faithful.
    """
    from limen.materialize import canonical_board_text, events_to_jsonl, fold, seed_events_from_board

    root = resolve_root()
    tasks_path = resolve_tasks_path(root)
    if not tasks_path.exists():
        click.echo("tasks.yaml not found", err=True)
        sys.exit(1)

    # Read the board bytes exactly ONCE: seed events from, and compare against, the same buffer.
    # The live board is rewritten every beat, so a second read_text() could observe a different file
    # than the one we folded — a TOCTOU false-negative. load_limen_text parses that single snapshot.
    on_disk = tasks_path.read_text()
    board = load_limen_text(on_disk, name=tasks_path.name)
    events = seed_events_from_board(board)

    if emit_events:
        out = Path(emit_events).expanduser()
        out.write_text(events_to_jsonl(events))
        click.echo(f"wrote {len(events)} events to {out}")

    if verify or not emit_events:
        rebuilt = fold(events)
        # canonical serialization = exactly what save_limen_file writes (mode=json, exclude_none,
        # sort_keys=False). Compare against the snapshot we loaded from — not a fresh read.
        rebuilt_bytes = canonical_board_text(rebuilt)
        identical = rebuilt_bytes == on_disk
        click.echo(
            f"materialize: {len(board.tasks)} tasks, {len(events)} events; "
            f"fold(events) == tasks.yaml bytes: {identical}"
        )
        if not identical:
            click.echo(
                "  NON-IDENTICAL — the board on disk is not canonical, or the fold lost a field. "
                "Re-run `limen doctor`; do not migrate writers until this exits 0.",
                err=True,
            )
            sys.exit(1)


@main.command("tabularius-events")
@click.option("--write", is_flag=True, help="Write logs/tickets/events.jsonl from the current board projection.")
@click.option(
    "--sync-archive",
    is_flag=True,
    help="Append archived tickets after the event-log manifest watermark before verifying.",
)
@click.option("--verify", is_flag=True, help="Verify the compacted event log folds to tasks.yaml.")
@click.option(
    "--event-log",
    type=click.Path(path_type=Path),
    default=None,
    help="Override the default logs/tickets/events.jsonl path.",
)
@click.option(
    "--emit-board",
    type=click.Path(path_type=Path),
    default=None,
    help="Write a regenerated board cache from the event log to this side path; refuses tasks.yaml.",
)
def tabularius_events(
    write: bool,
    sync_archive: bool,
    verify: bool,
    event_log: Path | None,
    emit_board: Path | None,
) -> None:
    """Compact and verify TABVLARIVS' canonical replay log."""
    from limen.tabularius import (
        compact_event_log,
        event_log_path,
        sync_event_log_from_archive,
        verify_event_log,
        write_event_log_board,
    )

    root = resolve_root()
    tasks_path = resolve_tasks_path(root)
    if not tasks_path.exists():
        click.echo("tasks.yaml not found", err=True)
        sys.exit(1)

    target = event_log or event_log_path(tasks_path)
    if not write and not sync_archive and not verify and emit_board is None:
        verify = True

    result = None
    if write:
        result = compact_event_log(tasks_path, target)
    if sync_archive:
        result = sync_event_log_from_archive(tasks_path, target)
    if emit_board is not None:
        result = write_event_log_board(tasks_path, emit_board, target)
    if result is None:
        result = verify_event_log(tasks_path, target)
    click.echo(
        f"tabularius-events: {result.events} events, {result.archive_tickets} archived tickets; "
        f"{result.note}: {result.verified}; path={result.event_log}"
    )
    if (verify or write or emit_board is not None) and not result.verified:
        sys.exit(1)


@main.command()
@click.option("--once", is_flag=True, help="One frame then exit")
@click.option("--compact", is_flag=True, help="One-line compact mode")
@click.option("-n", "--interval", default=2.0, type=float, help="Refresh interval in seconds")
def watch(once, compact, interval):
    """Show the real-time fleet dashboard."""
    from limen.watch import run

    run(once=once, compact=compact, interval=interval)


if __name__ == "__main__":
    main()

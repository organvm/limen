from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "quicken.py"
sys.path.insert(0, str(ROOT / "cli" / "src"))


def _load():
    spec = importlib.util.spec_from_file_location("quicken", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _configure(mod, tmp_path: Path) -> None:
    mod.ROOT = tmp_path
    mod.PROJECTS = tmp_path / ".claude" / "projects"
    mod.TASKS = tmp_path / ".claude" / "tasks"
    mod.JOURNAL = tmp_path / "logs" / "session-lifecycle.jsonl"
    mod.RESIDUE_OUT = tmp_path / "docs" / "QUICKEN-RESIDUE.md"
    mod.CLOSEOUT_LOG = tmp_path / "logs" / "session-closeout.jsonl"
    mod.LEDGER = tmp_path / "tasks.yaml"
    mod.STALE_MIN = 20
    mod.HORIZON_DAYS = 3
    mod.CLOSED_HRS = 18
    mod.REAP_ON = True


def _write_jsonl(path: Path, records: list[dict], *, moved: float | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")
    if moved is not None:
        os.utime(path, (moved, moved))


def _write_session(mod, sid: str, title: str, cwd: str, prompt: str, *, moved: float) -> Path:
    stream = mod.PROJECTS / mod._enc(cwd) / f"{sid}.jsonl"
    _write_jsonl(
        stream,
        [
            {"type": "ai-title", "aiTitle": title},
            {"type": "permission-mode", "permissionMode": "acceptEdits"},
            {"type": "last-prompt", "lastPrompt": prompt},
            {"cwd": cwd},
        ],
        moved=moved,
    )
    return stream


def _write_todo(mod, sid: str, status: str, subject: str = "finish", desc: str = "") -> None:
    task_dir = mod.TASKS / sid
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "1.json").write_text(
        json.dumps({"subject": subject, "status": status, "description": desc, "blockedBy": []}),
        encoding="utf-8",
    )


def _row(title: str, residue: str | None, *, state: str = "STALLED", cwd: str = "/tmp/work") -> dict:
    return {
        "sessionId": title.lower().replace(" ", "-"),
        "title": title,
        "last_prompt": "",
        "perm": "acceptEdits",
        "cwd": cwd,
        "moved": time.time() - 3600,
        "stream": "",
        "fleetview": True,
        "state": state,
        "todos": [],
        "decision": {
            "layer": "protocol" if residue else "ideal-form",
            "action": "stage the human atom" if residue else "resume",
            "residue": residue,
            "recorded": False,
            "n_pending": 1 if residue else 0,
            "n_done": 0,
        },
        "is_self": False,
    }


def _stalled_row(sid: str, cwd: str, title: str = "repeat offender session") -> dict:
    return {
        "sessionId": sid,
        "title": title,
        "last_prompt": "Resume and FINISH your original purpose",
        "cwd": cwd,
        "moved": 0.0,
        "state": "STALLED",
        "is_self": False,
        "decision": {"residue": None, "layer": "ideal-form", "n_done": 0, "n_pending": 0},
    }


def _journal_with_breathes(tmp_path, sid: str, n: int):
    journal = tmp_path / "session-lifecycle.jsonl"
    lines = [f'{{"ts": 1, "breathed": "{sid}", "ok": true}}' for _ in range(n)]
    lines.append("not json at all {{{")
    journal.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return journal


def test_malformed_numeric_env_falls_back(monkeypatch):
    monkeypatch.setenv("LIMEN_QUICKEN_STALE_MIN", "not-an-int")
    monkeypatch.setenv("LIMEN_QUICKEN_HORIZON_DAYS", "0")
    monkeypatch.setenv("LIMEN_QUICKEN_CLOSED_HRS", "-1")

    quicken = _load()

    assert quicken.STALE_MIN == 20
    assert quicken.HORIZON_DAYS == 3
    assert quicken.CLOSED_HRS == 18


def test_breathe_numeric_env_falls_back(monkeypatch, capsys):
    monkeypatch.setenv("LIMEN_QUICKEN_BREATHE_CAP", "bad")
    monkeypatch.setenv("LIMEN_QUICKEN_BREATHE_TIMEOUT", "0")
    quicken = _load()

    quicken.breathe([], "all", dry=True)

    assert "within cap=1" in capsys.readouterr().out


def test_hang_residue_does_not_refresh_unchanged_human_ask(tmp_path, monkeypatch):
    quicken = _load()
    tasks = tmp_path / "tasks.yaml"
    atom = "land the credential/secret (your account/identity)"
    title = "Audit Codex handoff and validate token-accountin"
    context = (
        f"Cheapest path \u2192 {atom}. Unblocks: {title}. "
        "Auto-hung by QUICKEN (finish-not-park); refreshes each beat until you act."
    )
    before = f"""version: '1.0'
tasks:
- id: ASK-quicken-credential
  title: {atom}
  type: ops
  target_agent: human
  priority: high
  budget_cost: 1
  status: needs_human
  labels:
  - user-ask
  - quicken-residue
  - needs-human
  urls: []
  context: "{context}"
  depends_on: []
  created: '2026-06-26'
  updated: '2026-07-04T19:36:24.651929Z'
  dispatch_log: []
"""
    tasks.write_text(before, encoding="utf-8")
    monkeypatch.setattr(quicken, "LEDGER", tasks)

    result = quicken.hang_residue(
        [
            {
                "state": "STALLED",
                "title": title,
                "decision": {"residue": atom},
            }
        ]
    )

    assert result["created"] == []
    assert result["refreshed"] == []
    assert result["homed"] == [f"{atom} \u2192 ASK-quicken-credential"]
    assert tasks.read_text(encoding="utf-8") == before


def test_write_residue_splits_queued_unblocks_before_deduping(monkeypatch):
    quicken = _load()
    atom = "send the drafted message (never auto-send)"
    monkeypatch.setattr(
        quicken,
        "_queue_residue_atoms",
        lambda: {atom: ["effort-level-ultracode, nous research outreach p"]},
    )

    doc = quicken.write_residue(
        [
            {
                "state": "STALLED",
                "title": "effort-level-ultracode",
                "decision": {"residue": atom},
            }
        ]
    )

    assert "effort-level-ultracode, effort-level-ultracode" not in doc
    assert "unblocks: effort-level-ultracode, nous research outreach p" in doc


def test_reap_done_apply_delegates_without_removing_worktree(tmp_path, monkeypatch):
    quicken = _load()
    worktree = tmp_path / ".claude" / "worktrees" / "spent"
    worktree.mkdir(parents=True)
    calls: list[tuple[str, ...]] = []

    def fake_git(_cwd: str, *args: str) -> tuple[int, str, str]:
        calls.append(args)
        if args == ("status", "--porcelain"):
            return 0, "", ""
        if args == ("rev-parse", "--abbrev-ref", "HEAD"):
            return 0, "spent-branch", ""
        if args[:2] in {("worktree", "remove"), ("branch", "-D")}:
            raise AssertionError(f"quicken must not physically remove roots: {args}")
        return 1, "", "unexpected"

    monkeypatch.setattr(quicken, "_git", fake_git)
    monkeypatch.setattr(quicken, "_branch_merged", lambda _cwd, _branch: (True, "0 commits ahead of origin/main"))

    result = quicken.reap_done(
        [
            {
                "state": "DONE",
                "cwd": str(worktree),
                "title": "Spent finished session",
                "is_self": False,
            }
        ],
        self_cwd=str(tmp_path / "other"),
        apply=True,
    )

    assert result["reaped"] == []
    assert result["delegated"] == [("Spent finished session", "spent-branch", "0 commits ahead of origin/main")]
    assert worktree.exists()
    assert ("worktree", "remove", str(worktree)) not in calls
    assert ("branch", "-D", "spent-branch") not in calls


def test_breathe_counts_ignores_malformed_lines(tmp_path, monkeypatch):
    quicken = _load()
    sid = "aaaabbbb-1111-2222-3333-444455556666"
    monkeypatch.setattr(quicken, "JOURNAL", _journal_with_breathes(tmp_path, sid, 2))

    assert quicken._breathe_counts() == {sid: 2}


def test_breathe_escalates_repeat_offender_idempotently(tmp_path, monkeypatch, capsys):
    quicken = _load()
    sid = "aaaabbbb-1111-2222-3333-444455556666"
    tasks = tmp_path / "tasks.yaml"
    tasks.write_text("version: '1.0'\ntasks: []\n", encoding="utf-8")
    monkeypatch.setattr(quicken, "JOURNAL", _journal_with_breathes(tmp_path, sid, 2))
    monkeypatch.setattr(quicken, "LEDGER", tasks)
    row = _stalled_row(sid, str(tmp_path))

    quicken.breathe([row], "all", dry=False)

    out = capsys.readouterr().out
    assert f"ESCALATE {sid[:8]}" in out
    assert "0 session(s) within cap" in out
    body = tasks.read_text(encoding="utf-8")
    assert f"ASK-quicken-escalate-{sid[:8]}" in body
    assert "quicken-escalate" in body
    assert f"claude --resume {sid}" in body
    assert any(e.get("escalated") == sid for e in quicken._read_jsonl(quicken.JOURNAL))

    before = tasks.read_text(encoding="utf-8")
    quicken.breathe([row], "all", dry=False)
    assert tasks.read_text(encoding="utf-8").count(f"ASK-quicken-escalate-{sid[:8]}") == before.count(
        f"ASK-quicken-escalate-{sid[:8]}"
    )


def test_breathe_under_threshold_still_breathes(tmp_path, monkeypatch, capsys):
    quicken = _load()
    sid = "ccccdddd-1111-2222-3333-444455556666"
    monkeypatch.setattr(quicken, "JOURNAL", _journal_with_breathes(tmp_path, sid, 1))
    row = _stalled_row(sid, str(tmp_path))

    quicken.breathe([row], "all", dry=True)

    out = capsys.readouterr().out
    assert f"DRY would breathe {sid}" in out
    assert "ESCALATE" not in out


def test_breathe_escalate_after_env_respected(tmp_path, monkeypatch, capsys):
    quicken = _load()
    sid = "eeeeffff-1111-2222-3333-444455556666"
    monkeypatch.setenv("LIMEN_QUICKEN_ESCALATE_AFTER", "5")
    monkeypatch.setattr(quicken, "JOURNAL", _journal_with_breathes(tmp_path, sid, 3))
    row = _stalled_row(sid, str(tmp_path))

    quicken.breathe([row], "all", dry=True)

    out = capsys.readouterr().out
    assert f"DRY would breathe {sid}" in out
    assert "ESCALATE" not in out


def test_breathe_named_sid_honored_over_escalation(tmp_path, monkeypatch, capsys):
    quicken = _load()
    sid = "abcdabcd-1111-2222-3333-444455556666"
    monkeypatch.setattr(quicken, "JOURNAL", _journal_with_breathes(tmp_path, sid, 4))
    row = _stalled_row(sid, str(tmp_path))

    quicken.breathe([row], sid, dry=True)

    out = capsys.readouterr().out
    assert f"DRY would breathe {sid}" in out
    assert "ESCALATE" not in out


def test_load_session_uses_canonical_cwd_and_filters_dispatch_runs(tmp_path: Path) -> None:
    quicken = _load()
    _configure(quicken, tmp_path)
    canonical = "/tmp/project.alpha"
    fallback = "/tmp/other"
    stream = quicken.PROJECTS / quicken._enc(canonical) / "sid.jsonl"
    _write_jsonl(
        stream,
        [
            {"type": "ai-title", "aiTitle": "Lifecycle work"},
            {"type": "last-prompt", "lastPrompt": "finish reversible work"},
            {"type": "permission-mode", "permissionMode": "plan"},
            {"cwd": fallback, "timestamp": "2026-06-30T00:00:00Z"},
            {"cwd": canonical, "timestamp": "2026-06-30T00:01:00Z"},
            "{not-json",
        ],
    )

    session = quicken.load_session(stream)

    assert quicken._enc(canonical) == "-tmp-project-alpha"
    assert quicken._decode_worktree("-tmp-project--alpha") == "/tmp/project/.alpha"
    assert session["sessionId"] == "sid"
    assert session["title"] == "Lifecycle work"
    assert session["perm"] == "plan"
    assert session["cwd"] == canonical
    assert session["fleetview"] is True

    dispatch = quicken.PROJECTS / quicken._enc(canonical) / "dispatch.jsonl"
    _write_jsonl(
        dispatch,
        [
            {"type": "ai-title", "aiTitle": "Generated task"},
            {"type": "last-prompt", "lastPrompt": "Complete task GEN-123"},
            {"cwd": canonical},
        ],
    )
    assert quicken.load_session(dispatch)["fleetview"] is False


def test_classify_state_and_cascade_decision_layers(tmp_path: Path) -> None:
    quicken = _load()
    _configure(quicken, tmp_path)
    now = 100_000.0

    assert quicken.classify_state({"moved": now - 60, "last_prompt": ""}, [], now) == "ALIVE"
    assert quicken.classify_state({"moved": now - 3600, "last_prompt": ""}, [{"status": "completed"}], now) == "DONE"
    assert quicken.classify_state({"moved": now - 3600, "last_prompt": "relay handoff"}, [], now) == "CLOSED"
    assert quicken.classify_state({"moved": now - 30 * 3600, "last_prompt": ""}, [], now) == "CLOSED"
    assert quicken.classify_state({"moved": now - 3600, "last_prompt": "continue"}, [], now) == "STALLED"

    base = {"title": "Release work", "last_prompt": ""}
    decision = quicken.cascade_decide(
        base,
        [{"status": "pending", "subject": "deploy", "desc": "HELD until gate opens"}],
    )
    assert decision["layer"] == "protocol+precedent"
    assert decision["residue"] == "open the gate to push/deploy (standing gate-hold)"
    assert decision["n_pending"] == 1

    assert quicken.cascade_decide(
        {"title": "Auth setup", "last_prompt": "sign in before continuing"},
        [],
    )["layer"] == "protocol"
    assert quicken.cascade_decide(
        {"title": "Quiet window", "last_prompt": ""},
        [{"status": "pending", "subject": "review", "desc": "resume only in a quiet window"}],
    )["layer"] == "precedent"
    assert quicken.cascade_decide(
        {"title": "Technical work", "last_prompt": "fix tests"},
        [],
    )["layer"] == "ideal-form"
    assert quicken.cascade_decide({"title": "", "last_prompt": ""}, [])["layer"] == "explore"


def test_gather_filters_dedupes_and_reports_residue(tmp_path: Path) -> None:
    quicken = _load()
    _configure(quicken, tmp_path)
    now = time.time()

    _write_session(quicken, "login", "Login Work", "/tmp/login", "sign in to continue", moved=now - 3600)
    _write_todo(quicken, "login", "pending", "auth", "needs login")
    _write_session(quicken, "dupe-old", "Same Title", "/tmp/dupe-old", "fix tests", moved=now - 3600)
    _write_session(quicken, "dupe-new", "Same Title", "/tmp/dupe-new", "fix tests", moved=now - 1800)
    _write_session(quicken, "done", "Done Work", "/tmp/done", "wrap up", moved=now - 3600)
    _write_todo(quicken, "done", "completed")
    _write_session(quicken, "ended", "Ended Work", "/tmp/ended", "continue", moved=now - 3600)
    _write_todo(quicken, "ended", "pending")
    quicken.CLOSEOUT_LOG.parent.mkdir(parents=True, exist_ok=True)
    quicken.CLOSEOUT_LOG.write_text(json.dumps({"sid": "ended"}) + "\n", encoding="utf-8")

    no_title = quicken.PROJECTS / "-tmp-no-title" / "no-title.jsonl"
    _write_jsonl(no_title, [{"type": "last-prompt", "lastPrompt": "not fleetview"}, {"cwd": "/tmp/no-title"}], moved=now)
    dispatch = quicken.PROJECTS / "-tmp-dispatch" / "dispatch.jsonl"
    _write_jsonl(
        dispatch,
        [
            {"type": "ai-title", "aiTitle": "Dispatch"},
            {"type": "last-prompt", "lastPrompt": "Complete task GEN-123"},
            {"cwd": "/tmp/dispatch"},
        ],
        moved=now,
    )

    rows = quicken.gather(now, self_sid="dupe-new")
    by_title = {row["title"]: row for row in rows}
    report = quicken.fmt_report(rows)
    residue = quicken.write_residue(rows)

    assert set(by_title) == {"Login Work", "Same Title", "Done Work", "Ended Work"}
    assert by_title["Login Work"]["state"] == "STALLED"
    assert by_title["Same Title"]["sessionId"] == "dupe-new"
    assert by_title["Same Title"]["superseded"] == 1
    assert by_title["Same Title"]["is_self"] is True
    assert by_title["Done Work"]["state"] == "DONE"
    assert by_title["Ended Work"]["state"] == "CLOSED"
    assert "irreducible atom: one login/identity step" in report
    assert "claude --resume login" in report
    assert "one login/identity step" in residue
    assert "Login Work" in residue


def test_hang_residue_creates_refreshes_and_homes_atoms(tmp_path: Path) -> None:
    quicken = _load()
    _configure(quicken, tmp_path)
    quicken.LEDGER.write_text(
        yaml.dump(
            {
                "version": "1.0",
                "tasks": [
                    {
                        "id": "EXISTING",
                        "title": "existing task",
                        "target_agent": "codex",
                        "status": "open",
                        "created": "2026-07-01",
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    login_atom = "one login/identity step (your hand: browser/OAuth/portal)"
    push_atom = "open the gate to push/deploy (standing gate-hold)"

    result = quicken.hang_residue([_row("Auth Flow", login_atom), _row("Release Gate", push_atom)])

    assert result["created"] == ["ASK-quicken-login"]
    assert result["homed"] == [f"{push_atom} \u2192 ASK-5-open-merge-gate (the standing gate-hold)"]
    board = yaml.safe_load(quicken.LEDGER.read_text(encoding="utf-8"))
    by_id = {task["id"]: task for task in board["tasks"]}
    assert by_id["ASK-quicken-login"]["status"] == "needs_human"
    assert by_id["ASK-quicken-login"]["target_agent"] == "human"
    assert "quicken-residue" in by_id["ASK-quicken-login"]["labels"]
    assert "Auth Flow" in by_id["ASK-quicken-login"]["context"]

    refreshed = quicken.hang_residue([_row("Auth Refresh", login_atom)])

    assert refreshed["refreshed"] == ["ASK-quicken-login"]
    board = yaml.safe_load(quicken.LEDGER.read_text(encoding="utf-8"))
    refreshed_task = {task["id"]: task for task in board["tasks"]}["ASK-quicken-login"]
    assert "Auth Refresh" in refreshed_task["context"]


def test_reap_done_previews_only_verified_clean_isolation_worktrees(tmp_path: Path, monkeypatch) -> None:
    quicken = _load()
    _configure(quicken, tmp_path / "main")
    clean = tmp_path / ".limen-worktrees" / "clean"
    dirty = tmp_path / ".limen-worktrees" / "dirty"
    clean.mkdir(parents=True)
    dirty.mkdir(parents=True)

    def fake_git(cwd: str, *args: str) -> tuple[int, str, str]:
        if args == ("status", "--porcelain"):
            return (0, " M file.py", "") if cwd == str(dirty) else (0, "", "")
        if args == ("rev-parse", "--abbrev-ref", "HEAD"):
            return 0, Path(cwd).name, ""
        raise AssertionError(args)

    monkeypatch.setattr(quicken, "_git", fake_git)
    monkeypatch.setattr(quicken, "_branch_merged", lambda cwd, branch: (True, "merged by test"))

    rows = [
        _row("Clean Done", None, state="DONE", cwd=str(clean)),
        _row("Dirty Done", None, state="DONE", cwd=str(dirty)),
        _row("Live", None, state="ALIVE", cwd=str(tmp_path / "live")),
    ]
    result = quicken.reap_done(rows, self_cwd=str(tmp_path / "self"), apply=False)

    assert result["would"] == [("Clean Done", "clean", "merged by test")]
    assert result["kept"] == [("Dirty Done", "uncommitted changes")]
    assert result["reaped"] == []


def test_breathe_dry_run_skips_contended_worktrees_and_honors_cap(tmp_path: Path, monkeypatch, capsys) -> None:
    quicken = _load()
    _configure(quicken, tmp_path / "main")
    oldest = tmp_path / "oldest"
    newest = tmp_path / "newest"
    contended = tmp_path / "contended"
    for path in (oldest, newest, contended):
        path.mkdir(parents=True)
    monkeypatch.setenv("LIMEN_QUICKEN_BREATHE_CAP", "1")

    old_row = _row("Old Stalled", None, cwd=str(oldest))
    old_row["sessionId"] = "old"
    old_row["moved"] = 100.0
    new_row = _row("New Stalled", None, cwd=str(newest))
    new_row["sessionId"] = "new"
    new_row["moved"] = 200.0
    blocked_row = _row("Blocked Stalled", None, cwd=str(contended))
    blocked_row["sessionId"] = "blocked"
    blocked_row["moved"] = 50.0
    alive_row = _row("Alive", None, state="ALIVE", cwd=str(contended))
    alive_row["sessionId"] = "alive"

    quicken.breathe([new_row, blocked_row, alive_row, old_row], "all", dry=True)

    out = capsys.readouterr().out
    assert "1 session(s) within cap=1" in out
    assert "DRY would breathe old" in out
    assert "blocked" not in out
    assert "new" not in out

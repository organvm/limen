from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "merge-ready.sh"


def _root(tmp_path: Path) -> Path:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    for name in ("merge-ready.py", "merge-drain.py"):
        (scripts / name).write_text(
            "import json, sys\nprint(json.dumps(sys.argv[1:]))\n",
            encoding="utf-8",
        )
    shutil.copy2(SCRIPT, scripts / "merge-ready.sh")
    return tmp_path


def _run(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(root / "scripts" / "merge-ready.sh"), *args],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


def test_default_wrapper_delegates_only_to_zero_write_preview(tmp_path: Path):
    result = _run(_root(tmp_path), "--scan", "17")

    assert result.returncode == 0
    assert result.stdout.strip() == '["--scan", "17"]'


def test_apply_without_receipt_fails_before_executor(tmp_path: Path):
    root = _root(tmp_path)
    result = _run(root, "--apply")

    assert result.returncode == 2
    assert "requires --authorization-receipt" in result.stderr


def test_receipt_without_apply_and_ambiguous_mode_fail_closed(tmp_path: Path):
    root = _root(tmp_path)

    receipt_only = _run(root, "--authorization-receipt", str(tmp_path / "receipt.json"))
    ambiguous = _run(root, "--apply", "--dry-run")
    caller_signers = _run(root, "--allowed-signers", str(tmp_path / "signers"))

    assert receipt_only.returncode == 2
    assert "requires --apply" in receipt_only.stderr
    assert ambiguous.returncode == 2
    assert "mutually exclusive" in ambiguous.stderr
    assert caller_signers.returncode == 2
    assert "unknown argument" in caller_signers.stderr


def test_apply_delegates_receipt_and_limit_to_guarded_executor(tmp_path: Path):
    root = _root(tmp_path)
    receipt = tmp_path / "receipt.json"
    result = _run(
        root,
        "--apply",
        "--limit",
        "1",
        "--authorization-receipt",
        str(receipt),
    )

    assert result.returncode == 0
    assert result.stdout.strip() == (f'["--apply", "--limit", "1", "--authorization-receipt", "{receipt}"]')


def test_wrapper_ignores_limen_root_and_uses_its_own_sibling_executor(tmp_path: Path):
    root = _root(tmp_path)
    attacker = tmp_path / "attacker"
    attacker.mkdir()
    env = os.environ.copy()
    env["LIMEN_ROOT"] = str(attacker)
    result = subprocess.run(
        ["bash", str(root / "scripts" / "merge-ready.sh"), "--scan", "3"],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == '["--scan", "3"]'


def test_legacy_wrapper_contains_no_direct_github_merge_or_review_command():
    source = SCRIPT.read_text(encoding="utf-8")

    assert "gh pr review " not in source
    assert "if gh pr merge " not in source
    assert "exec gh pr merge " not in source


def test_only_receipt_bound_executor_contains_an_executable_merge_command():
    allowed = ROOT / "scripts" / "merge-drain.py"
    python_merge = re.compile(r"\[\s*[\"']pr[\"']\s*,\s*[\"']merge[\"']")
    shell_merge = re.compile(r"^(?!\s*#).*\bgh\s+pr\s+merge\b", re.MULTILINE)

    offenders: list[str] = []
    for path in sorted((ROOT / "scripts").rglob("*")):
        if path.suffix not in {".py", ".sh"} or "/tests/" in path.as_posix():
            continue
        source = path.read_text(encoding="utf-8")
        if path != allowed and (python_merge.search(source) or shell_merge.search(source)):
            offenders.append(path.relative_to(ROOT).as_posix())

    assert offenders == []
    assert python_merge.search(allowed.read_text(encoding="utf-8"))

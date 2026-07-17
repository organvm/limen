from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "merge-drain.py"


def _load():
    spec = importlib.util.spec_from_file_location("merge_drain_uut", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _R:
    def __init__(self, out: str, returncode: int = 0):
        self.returncode = returncode
        self.stdout = out
        self.stderr = ""


class _Auth:
    def __init__(self, repo: str, number: int, head: str):
        self.repository = repo
        self.pull_request = number
        self.head_sha = head
        self.source = Path("/fixture/merge-authorization.json")
        self.authorization_id = "merge-fixture-001"
        self.receipt_sha256 = "f" * 64
        self.signer_principal = "keeper-citrine"
        self.allowed_signers = Path("/fixture/allowed-signers")
        self.allowed_signers_bytes = b"keeper-citrine ssh-ed25519 AAAAfixture\n"
        self.allowed_signers_sha256 = hashlib.sha256(self.allowed_signers_bytes).hexdigest()

    def permits(self, repo: str, number: int, head: str) -> bool:
        return (repo, number, head) == (self.repository, self.pull_request, self.head_sha)


def test_conflict_wins_over_stale_failing_checks(monkeypatch):
    mod = _load()

    def fake_gh(args, timeout=60):
        if args[:2] == ["pr", "view"]:
            return _R(
                json.dumps(
                    {
                        "state": "OPEN",
                        "isDraft": False,
                        "mergeable": "CONFLICTING",
                        "statusCheckRollup": [{"conclusion": "FAILURE"}],
                    }
                )
            )
        raise AssertionError(f"unexpected gh call: {args!r}")

    monkeypatch.setattr(mod, "gh", fake_gh)

    assert mod.assess(("organvm/domus-genoma", 185)) == (
        "organvm/domus-genoma",
        185,
        "CONFLICT",
    )


def test_ready_candidate_requires_exact_head_review_acceptance(monkeypatch):
    mod = _load()
    head = "a" * 40
    seen = []

    def fake_gh(args, timeout=60):
        if args[:2] == ["pr", "view"]:
            return _R(
                json.dumps(
                    {
                        "state": "OPEN",
                        "isDraft": False,
                        "mergeable": "MERGEABLE",
                        "statusCheckRollup": [{"conclusion": "SUCCESS"}],
                        "files": [{"path": "docs/x.md"}],
                        "baseRefName": "main",
                        "headRefOid": head,
                    }
                )
            )
        raise AssertionError(f"unexpected gh call: {args!r}")

    monkeypatch.setattr(mod, "gh", fake_gh)
    monkeypatch.setattr(mod, "stale_base_verdict", lambda *args, **kwargs: None)
    monkeypatch.setattr(mod, "_is_trivial", lambda *_args: False)
    monkeypatch.setattr(
        mod,
        "review_accepted",
        lambda repo, num, expected, _signers=None: seen.append((repo, num, expected)) or False,
    )

    assert mod.assess(("organvm/limen", 7)) == ("organvm/limen", 7, "REVIEW-HOLD")
    assert seen == [("organvm/limen", 7, head)]


def test_empty_review_gate_override_uses_repository_default(monkeypatch, tmp_path: Path):
    mod = _load()
    head = "d" * 40
    calls = []
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setenv("LIMEN_PR_REVIEW_GATE", "")

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return _R("")

    monkeypatch.setattr(mod.subprocess, "run", fake_run)

    allowed_signers = tmp_path / "allowed-signers"
    assert mod.review_accepted("organvm/limen", 7, head, allowed_signers) is True
    assert calls[0][0][1:] == [
        str(tmp_path / "scripts" / "pr-review-gate.py"),
        "7",
        "--repo",
        "organvm/limen",
        "--expected-head",
        head,
        "--require-published-result",
        "--quiet",
    ]


def test_merge_policy_uses_repository_script_and_exact_head(monkeypatch, tmp_path: Path):
    mod = _load()
    head = "f" * 40
    calls = []
    monkeypatch.setattr(mod, "ROOT", tmp_path)

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return _R("")

    monkeypatch.setattr(mod.subprocess, "run", fake_run)

    allowed_signers = tmp_path / "allowed-signers"
    assert mod.merge_policy_cleared("organvm/limen", 7, head, allowed_signers) is True
    assert calls[0][0] == [
        str(tmp_path / "scripts" / "merge-policy.sh"),
        "7",
        "--repo",
        "organvm/limen",
        "--expected-head",
        head,
    ]
    assert calls[0][1]["env"]["LIMEN_REVIEW_ALLOWED_SIGNERS"] == str(allowed_signers)


def test_merge_rechecks_review_and_pins_exact_head(monkeypatch):
    mod = _load()
    head = "b" * 40
    gh_calls = []
    review_calls = []
    policy_calls = []
    signer_snapshots = []
    authorization = _Auth("organvm/limen", 8, head)

    monkeypatch.setattr(mod, "pause_active", lambda: False)
    authorization_reads = []
    monkeypatch.setattr(
        mod,
        "load_authorization",
        lambda _path, **_kwargs: authorization_reads.append(_path) or authorization,
    )
    monkeypatch.setattr(
        mod,
        "review_accepted",
        lambda repo, num, expected, signers=None: (
            review_calls.append((repo, num, expected, signers)),
            signer_snapshots.append(signers.read_bytes()),
            True,
        )[-1],
    )
    monkeypatch.setattr(
        mod,
        "merge_policy_cleared",
        lambda repo, num, expected, signers=None: (
            policy_calls.append((repo, num, expected, signers)),
            signer_snapshots.append(signers.read_bytes()),
            True,
        )[-1],
    )

    def fake_gh(args, timeout=60):
        gh_calls.append(args)
        return _R("")

    monkeypatch.setattr(mod, "gh", fake_gh)

    assert mod.merge("organvm/limen", 8, head, authorization) is True
    assert len(review_calls) == len(policy_calls) == 1
    assert review_calls[0][:3] == ("organvm/limen", 8, head)
    assert policy_calls[0][:3] == ("organvm/limen", 8, head)
    assert review_calls[0][3] == policy_calls[0][3]
    assert review_calls[0][3] != authorization.allowed_signers
    assert not review_calls[0][3].exists()
    assert signer_snapshots == [authorization.allowed_signers_bytes] * 2
    assert authorization_reads == [authorization.source, authorization.source]
    assert gh_calls == [["pr", "merge", "8", "-R", "organvm/limen", "--squash", "--match-head-commit", head]]


def test_merge_rejects_authorization_that_expires_during_live_predicates(monkeypatch):
    mod = _load()
    head = "b" * 40
    authorization = _Auth("organvm/limen", 8, head)
    reads = iter([authorization, mod.AuthorizationError("authorization receipt is expired")])
    monkeypatch.setattr(mod, "pause_active", lambda: False)

    def reload_authorization(_path, **_kwargs):
        result = next(reads)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(mod, "load_authorization", reload_authorization)
    monkeypatch.setattr(mod, "review_accepted", lambda *_args: True)
    monkeypatch.setattr(mod, "merge_policy_cleared", lambda *_args: True)
    monkeypatch.setattr(
        mod,
        "gh",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("expired authorization reached effect")),
    )

    assert mod.merge("organvm/limen", 8, head, authorization) is False


def test_merge_does_not_misread_cannot_be_merged_as_success(monkeypatch):
    mod = _load()
    head = "b" * 40
    calls = []
    authorization = _Auth("organvm/limen", 8, head)
    monkeypatch.setattr(mod, "pause_active", lambda: False)
    monkeypatch.setattr(mod, "load_authorization", lambda _path, **_kwargs: authorization)
    monkeypatch.setattr(mod, "review_accepted", lambda *_args: True)
    monkeypatch.setattr(mod, "merge_policy_cleared", lambda *_args: True)

    def fake_gh(args, timeout=60):
        calls.append(args)
        if args[:2] == ["pr", "merge"]:
            return _R("cannot be merged while required checks are pending", returncode=1)
        if args[:2] == ["pr", "view"]:
            return _R(json.dumps({"state": "OPEN"}))
        raise AssertionError(f"unexpected gh call: {args!r}")

    monkeypatch.setattr(mod, "gh", fake_gh)

    assert mod.merge("organvm/limen", 8, head, authorization) is False
    assert calls[-1] == ["pr", "view", "8", "-R", "organvm/limen", "--json", "state,headRefOid"]


def test_merge_accepts_only_confirmed_concurrent_merge_after_command_failure(monkeypatch):
    mod = _load()
    head = "b" * 40
    authorization = _Auth("organvm/limen", 8, head)
    monkeypatch.setattr(mod, "pause_active", lambda: False)
    monkeypatch.setattr(mod, "load_authorization", lambda _path, **_kwargs: authorization)
    monkeypatch.setattr(mod, "review_accepted", lambda *_args: True)
    monkeypatch.setattr(mod, "merge_policy_cleared", lambda *_args: True)

    def fake_gh(args, timeout=60):
        if args[:2] == ["pr", "merge"]:
            return _R("pull request was already merged", returncode=1)
        if args[:2] == ["pr", "view"]:
            return _R(json.dumps({"state": "MERGED", "headRefOid": head}))
        raise AssertionError(f"unexpected gh call: {args!r}")

    monkeypatch.setattr(mod, "gh", fake_gh)

    assert mod.merge("organvm/limen", 8, head, authorization) is True


def test_merge_rejects_concurrent_merge_of_a_different_head(monkeypatch):
    mod = _load()
    head = "b" * 40
    authorization = _Auth("organvm/limen", 8, head)
    monkeypatch.setattr(mod, "pause_active", lambda: False)
    monkeypatch.setattr(mod, "load_authorization", lambda _path, **_kwargs: authorization)
    monkeypatch.setattr(mod, "review_accepted", lambda *_args: True)
    monkeypatch.setattr(mod, "merge_policy_cleared", lambda *_args: True)

    def fake_gh(args, timeout=60):
        if args[:2] == ["pr", "merge"]:
            return _R("pull request was already merged", returncode=1)
        if args[:2] == ["pr", "view"]:
            return _R(json.dumps({"state": "MERGED", "headRefOid": "c" * 40}))
        raise AssertionError(f"unexpected gh call: {args!r}")

    monkeypatch.setattr(mod, "gh", fake_gh)

    assert mod.merge("organvm/limen", 8, head, authorization) is False


def test_ready_head_for_merge_brackets_full_reassessment(monkeypatch):
    mod = _load()
    head = "e" * 40
    observations = iter([head, head])
    assessed = []
    monkeypatch.setattr(mod, "current_head", lambda *_args: next(observations))
    monkeypatch.setattr(
        mod,
        "assess",
        lambda item, **_kwargs: assessed.append(item) or (item[0], item[1], "READY"),
    )

    assert mod.ready_head_for_merge("organvm/limen", 8) == head
    assert assessed == [("organvm/limen", 8)]


def test_ready_head_for_merge_refuses_head_movement_or_changed_verdict(monkeypatch):
    mod = _load()
    heads = iter(["a" * 40, "b" * 40])
    monkeypatch.setattr(mod, "current_head", lambda *_args: next(heads))
    monkeypatch.setattr(mod, "assess", lambda item, **_kwargs: (item[0], item[1], "READY"))
    assert mod.ready_head_for_merge("organvm/limen", 8) == ""

    heads = iter(["c" * 40, "c" * 40])
    monkeypatch.setattr(mod, "current_head", lambda *_args: next(heads))
    monkeypatch.setattr(mod, "assess", lambda item, **_kwargs: (item[0], item[1], "CI-PENDING"))
    assert mod.ready_head_for_merge("organvm/limen", 8) == ""


def test_merge_review_rejection_causes_no_remote_mutation(monkeypatch):
    mod = _load()
    authorization = _Auth("organvm/limen", 8, "c" * 40)
    monkeypatch.setattr(mod, "pause_active", lambda: False)
    monkeypatch.setattr(mod, "load_authorization", lambda _path, **_kwargs: authorization)
    monkeypatch.setattr(mod, "review_accepted", lambda *_args: False)
    monkeypatch.setattr(mod, "gh", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("gh called")))

    assert mod.merge("organvm/limen", 8, "c" * 40, authorization) is False


def test_merge_policy_rejection_causes_no_remote_mutation(monkeypatch):
    mod = _load()
    head = "c" * 40
    authorization = _Auth("organvm/limen", 8, head)
    monkeypatch.setattr(mod, "pause_active", lambda: False)
    monkeypatch.setattr(mod, "load_authorization", lambda _path, **_kwargs: authorization)
    monkeypatch.setattr(mod, "review_accepted", lambda *_args: True)
    monkeypatch.setattr(mod, "merge_policy_cleared", lambda *_args: False)
    monkeypatch.setattr(
        mod,
        "gh",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("gh called")),
    )

    assert mod.merge("organvm/limen", 8, head, authorization) is False


def test_merge_receipt_mismatch_causes_no_predicate_or_remote_calls(monkeypatch):
    mod = _load()
    expected = "c" * 40
    authorization = _Auth("organvm/limen", 8, "d" * 40)
    monkeypatch.setattr(mod, "pause_active", lambda: False)
    monkeypatch.setattr(mod, "load_authorization", lambda _path, **_kwargs: authorization)
    monkeypatch.setattr(
        mod,
        "review_accepted",
        lambda *_args: (_ for _ in ()).throw(AssertionError("review gate called")),
    )
    monkeypatch.setattr(
        mod,
        "gh",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("gh called")),
    )

    assert mod.merge("organvm/limen", 8, expected, authorization) is False


def test_merge_refuses_receipt_replacement_during_assessment(monkeypatch):
    mod = _load()
    head = "c" * 40
    original = _Auth("organvm/limen", 8, head)
    replacement = _Auth("organvm/limen", 8, head)
    replacement.receipt_sha256 = "e" * 64
    monkeypatch.setattr(mod, "pause_active", lambda: False)
    monkeypatch.setattr(mod, "load_authorization", lambda _path, **_kwargs: replacement)
    monkeypatch.setattr(
        mod,
        "review_accepted",
        lambda *_args: (_ for _ in ()).throw(AssertionError("review gate called")),
    )

    assert mod.merge("organvm/limen", 8, head, original) is False


def test_merge_refuses_trust_replacement_between_predicates_and_effect(monkeypatch):
    mod = _load()
    head = "c" * 40
    original = _Auth("organvm/limen", 8, head)
    replacement = _Auth("organvm/limen", 8, head)
    replacement.allowed_signers_bytes = b"keeper-other ssh-ed25519 AAAAreplacement\n"
    replacement.allowed_signers_sha256 = hashlib.sha256(replacement.allowed_signers_bytes).hexdigest()
    reads = iter([original, replacement])
    review_calls = []
    policy_calls = []
    monkeypatch.setattr(mod, "pause_active", lambda: False)
    monkeypatch.setattr(mod, "load_authorization", lambda _path, **_kwargs: next(reads))
    monkeypatch.setattr(mod, "review_accepted", lambda *_args: review_calls.append(_args) or True)
    monkeypatch.setattr(mod, "merge_policy_cleared", lambda *_args: policy_calls.append(_args) or True)
    monkeypatch.setattr(
        mod,
        "gh",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("trust replacement reached effect")),
    )

    assert mod.merge("organvm/limen", 8, head, original) is False
    assert len(review_calls) == len(policy_calls) == 1


def test_default_preview_is_zero_write_and_never_merges(monkeypatch, tmp_path: Path):
    mod = _load()
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr(mod, "enumerate_open_prs", lambda *_args, **_kwargs: [("organvm/limen", 9)])
    monkeypatch.setattr(mod, "assess", lambda pr: (*pr, "READY"))
    monkeypatch.setattr(mod, "merge", lambda *_args: (_ for _ in ()).throw(AssertionError("merge called")))

    assert mod.main(["--scan", "1", "--scan-max", "1"]) == 0
    assert not (tmp_path / "logs").exists()


def test_authorization_set_rejects_multiple_heads_for_one_pull_request(monkeypatch):
    mod = _load()
    first = _Auth("organvm/limen", 8, "a" * 40)
    second = _Auth("organvm/limen", 8, "b" * 40)
    second.authorization_id = "merge-fixture-002"
    values = iter([first, second])
    monkeypatch.setattr(mod, "load_authorization", lambda *_args, **_kwargs: next(values))

    with pytest.raises(mod.AuthorizationError, match="multiple authorized heads"):
        mod._load_authorizations(
            [Path("/fixture/one.json"), Path("/fixture/two.json")],
            allowed_signers=Path("/fixture/allowed-signers"),
        )


def test_apply_without_authorization_refuses_before_scan_or_write(monkeypatch, tmp_path: Path):
    mod = _load()
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.delenv("LIMEN_REVIEW_ALLOWED_SIGNERS", raising=False)
    monkeypatch.setattr(
        mod,
        "enumerate_open_prs",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("scan called")),
    )

    assert mod.main(["--apply"]) == 2
    assert list(tmp_path.iterdir()) == []

    assert (
        mod.main(
            [
                "--apply",
                "--authorization-receipt",
                "/fixture/authorization.json",
            ]
        )
        == 2
    )
    assert list(tmp_path.iterdir()) == []


def test_apply_assesses_only_receipt_targets_and_passes_exact_authorization(monkeypatch, tmp_path: Path):
    mod = _load()
    head = "a" * 40
    authorization = _Auth("organvm/limen", 42, head)
    key = (authorization.repository, authorization.pull_request, authorization.head_sha)
    merge_calls = []
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr(mod, "pause_active", lambda: False)
    monkeypatch.setattr(
        mod,
        "_load_authorizations",
        lambda _paths, **_kwargs: {key: authorization},
    )
    monkeypatch.setattr(mod, "assess", lambda item, **_kwargs: (*item, "READY"))
    monkeypatch.setattr(mod, "ready_head_for_merge", lambda *_args: head)
    monkeypatch.setattr(
        mod,
        "merge",
        lambda repo, number, exact_head, receipt: merge_calls.append((repo, number, exact_head, receipt)) or True,
    )
    monkeypatch.setattr(
        mod,
        "enumerate_open_prs",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("fleet scan called")),
    )

    assert (
        mod.main(
            [
                "--apply",
                "--authorization-receipt",
                "/fixture/authorization.json",
                "--allowed-signers",
                "/fixture/allowed-signers",
                "--limit",
                "1",
            ]
        )
        == 0
    )
    assert merge_calls == [("organvm/limen", 42, head, authorization)]
    assert (tmp_path / "logs" / "merge-drain.log").exists()
    assert not (tmp_path / "logs" / ".pr-scan-cursor.merge").exists()


def test_apply_fails_when_authorized_target_does_not_merge(monkeypatch, tmp_path: Path):
    mod = _load()
    head = "a" * 40
    authorization = _Auth("organvm/limen", 42, head)
    key = (authorization.repository, authorization.pull_request, authorization.head_sha)
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr(mod, "pause_active", lambda: False)
    monkeypatch.setattr(mod, "_load_authorizations", lambda _paths, **_kwargs: {key: authorization})
    monkeypatch.setattr(mod, "assess", lambda item, **_kwargs: (*item, "CI-PENDING"))
    monkeypatch.setattr(mod, "exact_target_already_merged", lambda *_args: False)

    assert (
        mod.main(
            [
                "--apply",
                "--authorization-receipt",
                "/fixture/authorization.json",
                "--allowed-signers",
                "/fixture/allowed-signers",
                "--limit",
                "1",
            ]
        )
        == 1
    )


def test_apply_delegated_target_must_match_the_only_authorization(monkeypatch, tmp_path: Path):
    mod = _load()
    head = "a" * 40
    authorization = _Auth("organvm/limen", 42, head)
    key = (authorization.repository, authorization.pull_request, authorization.head_sha)
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr(mod, "pause_active", lambda: False)
    monkeypatch.setattr(mod, "_load_authorizations", lambda _paths, **_kwargs: {key: authorization})
    monkeypatch.setattr(
        mod,
        "assess",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("mismatched target assessed")),
    )

    assert (
        mod.main(
            [
                "--apply",
                "--authorization-receipt",
                "/fixture/authorization.json",
                "--allowed-signers",
                "/fixture/allowed-signers",
                "--target-repo",
                "organvm/limen",
                "--target-pr",
                "43",
                "--target-head",
                head,
            ]
        )
        == 2
    )


def test_pause_marker_keeps_preview_observable_and_zero_write(monkeypatch, tmp_path: Path):
    mod = _load()
    marker = tmp_path / "logs" / "AUTONOMY_PAUSED"
    marker.parent.mkdir(parents=True)
    marker.write_text("reason: containment\n", encoding="utf-8")
    before = marker.read_bytes()
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr(mod, "enumerate_open_prs", lambda *_args, **_kwargs: [("organvm/limen", 9)])
    monkeypatch.setattr(mod, "assess", lambda pr: (*pr, "READY"))
    monkeypatch.setattr(mod, "merge", lambda *_args: (_ for _ in ()).throw(AssertionError("merge called")))

    assert mod.main(["--scan", "1", "--scan-max", "1"]) == 0
    assert marker.read_bytes() == before
    assert sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*")) == [
        Path("logs"),
        Path("logs/AUTONOMY_PAUSED"),
    ]


def test_pause_marker_refuses_apply_before_loading_or_effect(monkeypatch, tmp_path: Path):
    mod = _load()
    marker = tmp_path / "logs" / "AUTONOMY_PAUSED"
    marker.parent.mkdir(parents=True)
    marker.write_text("reason: containment\n", encoding="utf-8")
    before = marker.read_bytes()
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr(
        mod,
        "_load_authorizations",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("authorization loaded")),
    )

    assert (
        mod.main(
            [
                "--apply",
                "--authorization-receipt",
                "/fixture/authorization.json",
                "--allowed-signers",
                "/fixture/allowed-signers",
            ]
        )
        == 3
    )
    assert marker.read_bytes() == before
    assert sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*")) == [
        Path("logs"),
        Path("logs/AUTONOMY_PAUSED"),
    ]

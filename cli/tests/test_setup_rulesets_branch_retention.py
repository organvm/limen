from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "setup-rulesets.py"
REPORT = ROOT / "docs" / "RULESETS-DRYRUN.md"


def load_setup_rulesets() -> ModuleType:
    spec = importlib.util.spec_from_file_location("setup_rulesets", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_setup_rulesets_preserves_source_branches() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    report = REPORT.read_text(encoding="utf-8")

    assert "allow_auto_merge=false" in text
    assert "allow_auto_merge=true" not in text
    assert "delete_branch_on_merge=false" in text
    assert "delete_branch_on_merge=true" not in text
    assert "source branches remain after merge" in report
    assert "receipt-backed reaping" in report
    assert "delete_branch_on_merge=true" not in report


def test_setup_rulesets_requires_review_gate_even_with_forced_ci_contexts() -> None:
    module = load_setup_rulesets()

    assert module.required_contexts(["python", "limen.pr_review_gate.v1", "web", "python"]) == [
        "python",
        "web",
        "limen.pr_review_gate.v1",
    ]
    assert module.required_contexts([]) == ["limen.pr_review_gate.v1"]


def test_setup_rulesets_protection_is_exact_head_and_review_fail_closed() -> None:
    module = load_setup_rulesets()
    body = module.protection_body(["pr-gate", "limen.pr_review_gate.v1", "python"], 424242)

    assert body["required_status_checks"] == {
        "strict": True,
        "checks": [
            {"context": "pr-gate"},
            {"context": "python"},
            {"context": "limen.pr_review_gate.v1", "app_id": 424242},
        ],
    }
    assert body["enforce_admins"] is True
    assert body["required_conversation_resolution"] is True
    assert body["required_pull_request_reviews"] == {
        "dismiss_stale_reviews": True,
        "require_code_owner_reviews": False,
        "required_approving_review_count": 0,
        "require_last_push_approval": False,
    }


def test_setup_rulesets_apply_refuses_when_project_ci_is_not_discoverable(monkeypatch) -> None:
    module = load_setup_rulesets()
    monkeypatch.setattr(module, "APPLY", True)
    monkeypatch.setattr(module, "target_repos", lambda: ["owner/repository"])
    monkeypatch.setattr(
        module,
        "gh_json",
        lambda *_args, **_kwargs: {"defaultBranchRef": {"name": "main"}},
    )
    monkeypatch.setattr(module, "detect_checks", lambda _repo: [])
    monkeypatch.setattr(
        module,
        "gh",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("remote mutation attempted")),
    )

    assert module.main() == 1


def test_setup_rulesets_apply_refuses_unpublishable_review_context(monkeypatch) -> None:
    module = load_setup_rulesets()
    monkeypatch.setattr(module, "APPLY", True)
    monkeypatch.setattr(module, "target_repos", lambda: ["owner/repository"])
    monkeypatch.setattr(
        module,
        "gh_json",
        lambda *_args, **_kwargs: {"defaultBranchRef": {"name": "main"}},
    )
    monkeypatch.setattr(module, "detect_checks", lambda _repo: ["pr-gate"])
    monkeypatch.setattr(module, "review_gate_publisher_available", lambda _repo, _branch: False)
    monkeypatch.setattr(
        module,
        "gh",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("remote mutation attempted")),
    )

    assert module.main() == 1


def test_review_gate_publisher_requires_a_live_default_branch_file(monkeypatch) -> None:
    module = load_setup_rulesets()
    monkeypatch.setattr(module, "gh_json", lambda *_args, **_kwargs: {"type": "file", "sha": "abc123"})
    assert module.review_gate_publisher_available("owner/repository", "main") is True

    monkeypatch.setattr(module, "gh_json", lambda *_args, **_kwargs: {})
    assert module.review_gate_publisher_available("owner/repository", "main") is False


def test_review_gate_app_identity_is_derived_live_and_must_be_unique(monkeypatch) -> None:
    module = load_setup_rulesets()
    head = "a" * 40
    dedicated_slug = "keeper-review-publisher"

    def one_app(args, **_kwargs):
        if "pulls?state=open" in args[-1]:
            return [{"head": {"sha": head}}]
        return {
            "check_runs": [
                {
                    "name": "limen.pr_review_gate.v1",
                    "app": {"id": 1, "slug": "github-actions"},
                },
                {
                    "name": "limen.pr_review_gate.v1",
                    "app": {"id": 424242, "slug": dedicated_slug},
                },
            ]
        }

    monkeypatch.setattr(module, "gh_json", one_app)
    assert module.review_gate_app_id("owner/repository", dedicated_slug) == 424242

    monkeypatch.setattr(
        module,
        "gh_json",
        lambda args, **_kwargs: (
            [{"head": {"sha": head}}]
            if "pulls?state=open" in args[-1]
            else {
                "check_runs": [
                    {
                        "name": "limen.pr_review_gate.v1",
                        "app": {"id": 424242, "slug": dedicated_slug},
                    },
                    {
                        "name": "limen.pr_review_gate.v1",
                        "app": {"id": 777777, "slug": dedicated_slug},
                    },
                ]
            }
        ),
    )
    assert module.review_gate_app_id("owner/repository", dedicated_slug) is None


def test_review_gate_app_rejects_generic_actions_and_requires_explicit_slug(monkeypatch) -> None:
    module = load_setup_rulesets()
    monkeypatch.delenv(module.REVIEW_GATE_APP_SLUG_ENV, raising=False)
    assert module.configured_review_gate_app_slug() is None

    monkeypatch.setenv(module.REVIEW_GATE_APP_SLUG_ENV, "github-actions")
    assert module.configured_review_gate_app_slug() is None
    assert module.review_gate_app_id("owner/repository", "github-actions") is None

    monkeypatch.setenv(module.REVIEW_GATE_APP_SLUG_ENV, "keeper-gate-v7")
    assert module.configured_review_gate_app_slug() == "keeper-gate-v7"


def _result(payload=None, *, returncode: int = 0, stderr: str = ""):
    stdout = "" if payload is None else json.dumps(payload)
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


class ApiSpy:
    def __init__(self, steps):
        self.steps = list(steps)
        self.calls = []

    def __call__(self, args, _timeout=45, *, input_text=None):
        assert self.steps, f"unexpected API call: {args}"
        expected_method, expected_path, response = self.steps.pop(0)
        assert args[0] == "api"
        method_index = args.index("--method")
        method = args[method_index + 1]
        path = args[method_index + 2]
        assert (method, path) == (expected_method, expected_path)
        self.calls.append({"method": method, "path": path, "input": input_text})
        return response

    def assert_finished(self):
        assert self.steps == []


def _live_settings(*, auto_merge=False, delete_branch=False):
    return {
        "allow_auto_merge": auto_merge,
        "delete_branch_on_merge": delete_branch,
    }


def _live_protection(body):
    value = copy.deepcopy(body)
    value["enforce_admins"] = {"enabled": body["enforce_admins"]}
    value["required_conversation_resolution"] = {"enabled": body["required_conversation_resolution"]}
    return value


def _ready_apply(module, monkeypatch) -> None:
    monkeypatch.setattr(module, "APPLY", True)
    monkeypatch.setattr(module, "target_repos", lambda: ["owner/repository"])
    monkeypatch.setattr(
        module,
        "gh_json",
        lambda *_args, **_kwargs: {"defaultBranchRef": {"name": "trunk"}},
    )
    monkeypatch.setattr(module, "detect_checks", lambda _repo: ["pr-gate", "python"])
    monkeypatch.setattr(module, "review_gate_publisher_available", lambda _repo, _branch: True)
    monkeypatch.setattr(module, "configured_review_gate_app_slug", lambda: "keeper-gate-v7")
    monkeypatch.setattr(
        module,
        "review_gate_app_id",
        lambda _repo, slug: 987654 if slug == "keeper-gate-v7" else None,
    )


def _success_steps(module, *, final_settings=None, final_protection=None):
    repo_path = "repos/owner/repository"
    protection_path = "repos/owner/repository/branches/trunk/protection"
    body = module.protection_body(["pr-gate", "python"], 987654)
    return [
        ("PATCH", repo_path, _result({})),
        ("GET", repo_path, _result(_live_settings())),
        ("PUT", protection_path, _result({})),
        ("GET", repo_path, _result(final_settings or _live_settings())),
        ("GET", protection_path, _result(final_protection or _live_protection(body))),
    ]


def test_apply_orders_fail_closed_settings_before_protection_and_verifies_live_state(
    monkeypatch,
) -> None:
    module = load_setup_rulesets()
    _ready_apply(module, monkeypatch)
    spy = ApiSpy(_success_steps(module))
    monkeypatch.setattr(module, "gh", spy)

    assert module.main() == 0
    spy.assert_finished()
    assert [(call["method"], call["path"]) for call in spy.calls] == [
        ("PATCH", "repos/owner/repository"),
        ("GET", "repos/owner/repository"),
        ("PUT", "repos/owner/repository/branches/trunk/protection"),
        ("GET", "repos/owner/repository"),
        ("GET", "repos/owner/repository/branches/trunk/protection"),
    ]
    settings_call = spy.calls[0]
    assert settings_call["input"] is None
    put_body = json.loads(spy.calls[2]["input"])
    assert put_body["required_status_checks"]["checks"][-1] == {
        "context": "limen.pr_review_gate.v1",
        "app_id": 987654,
    }


def test_apply_fails_before_protection_when_settings_patch_fails(monkeypatch) -> None:
    module = load_setup_rulesets()
    _ready_apply(module, monkeypatch)
    spy = ApiSpy(
        [
            (
                "PATCH",
                "repos/owner/repository",
                _result(returncode=1, stderr="settings denied"),
            )
        ]
    )
    monkeypatch.setattr(module, "gh", spy)

    assert module.main() == 1
    spy.assert_finished()
    assert all(call["method"] != "PUT" for call in spy.calls)


@pytest.mark.parametrize(
    "settings_result",
    [
        _result(returncode=1, stderr="read denied"),
        _result(_live_settings(auto_merge=True)),
        _result(_live_settings(delete_branch=True)),
        _result(payload=None),
    ],
)
def test_apply_fails_before_protection_when_initial_settings_are_not_confirmed(monkeypatch, settings_result) -> None:
    module = load_setup_rulesets()
    _ready_apply(module, monkeypatch)
    spy = ApiSpy(
        [
            ("PATCH", "repos/owner/repository", _result({})),
            ("GET", "repos/owner/repository", settings_result),
        ]
    )
    monkeypatch.setattr(module, "gh", spy)

    assert module.main() == 1
    spy.assert_finished()
    assert all(call["method"] != "PUT" for call in spy.calls)


def test_apply_propagates_protection_put_failure_with_auto_merge_off(monkeypatch) -> None:
    module = load_setup_rulesets()
    _ready_apply(module, monkeypatch)
    spy = ApiSpy(
        [
            ("PATCH", "repos/owner/repository", _result({})),
            ("GET", "repos/owner/repository", _result(_live_settings())),
            (
                "PUT",
                "repos/owner/repository/branches/trunk/protection",
                _result(returncode=1, stderr="protection denied"),
            ),
        ]
    )
    monkeypatch.setattr(module, "gh", spy)

    assert module.main() == 1
    spy.assert_finished()


@pytest.mark.parametrize(
    "final_settings",
    [
        _live_settings(auto_merge=True),
        _live_settings(delete_branch=True),
    ],
)
def test_apply_fails_if_final_repository_settings_drift_but_still_reads_protection(monkeypatch, final_settings) -> None:
    module = load_setup_rulesets()
    _ready_apply(module, monkeypatch)
    spy = ApiSpy(_success_steps(module, final_settings=final_settings))
    monkeypatch.setattr(module, "gh", spy)

    assert module.main() == 1
    spy.assert_finished()
    assert spy.calls[-1]["path"].endswith("/protection")


def test_apply_aggregates_final_settings_read_failure_with_protection_read(monkeypatch) -> None:
    module = load_setup_rulesets()
    _ready_apply(module, monkeypatch)
    steps = _success_steps(module)
    steps[-2] = (
        "GET",
        "repos/owner/repository",
        _result(returncode=1, stderr="final settings read denied"),
    )
    spy = ApiSpy(steps)
    monkeypatch.setattr(module, "gh", spy)

    assert module.main() == 1
    spy.assert_finished()
    assert spy.calls[-1]["path"].endswith("/protection")


def _mutated_protection(module, field: str):
    body = module.protection_body(["pr-gate", "python"], 987654)
    value = _live_protection(body)
    if field == "checks":
        value["required_status_checks"]["checks"][-1]["app_id"] = 111111
    elif field == "strict":
        value["required_status_checks"]["strict"] = False
    elif field == "admins":
        value["enforce_admins"] = {"enabled": False}
    elif field == "conversations":
        value["required_conversation_resolution"] = {"enabled": False}
    elif field == "dismiss_stale_reviews":
        value["required_pull_request_reviews"]["dismiss_stale_reviews"] = False
    elif field == "code_owners":
        value["required_pull_request_reviews"]["require_code_owner_reviews"] = True
    elif field == "approval_count":
        value["required_pull_request_reviews"]["required_approving_review_count"] = 1
    elif field == "last_push":
        value["required_pull_request_reviews"]["require_last_push_approval"] = True
    elif field == "restrictions":
        value["restrictions"] = {"users": []}
    else:  # pragma: no cover - test helper guard
        raise AssertionError(field)
    return value


@pytest.mark.parametrize(
    "field",
    [
        "checks",
        "strict",
        "admins",
        "conversations",
        "dismiss_stale_reviews",
        "code_owners",
        "approval_count",
        "last_push",
        "restrictions",
    ],
)
def test_apply_fails_on_each_live_protection_mismatch(monkeypatch, field) -> None:
    module = load_setup_rulesets()
    _ready_apply(module, monkeypatch)
    spy = ApiSpy(_success_steps(module, final_protection=_mutated_protection(module, field)))
    monkeypatch.setattr(module, "gh", spy)

    assert module.main() == 1
    spy.assert_finished()


@pytest.mark.parametrize(
    "protection_result",
    [
        _result(returncode=1, stderr="read denied"),
        _result(payload=None),
    ],
)
def test_apply_fails_when_final_protection_cannot_be_read(monkeypatch, protection_result) -> None:
    module = load_setup_rulesets()
    _ready_apply(module, monkeypatch)
    steps = _success_steps(module)
    steps[-1] = (
        "GET",
        "repos/owner/repository/branches/trunk/protection",
        protection_result,
    )
    spy = ApiSpy(steps)
    monkeypatch.setattr(module, "gh", spy)

    assert module.main() == 1
    spy.assert_finished()


def test_apply_blocks_without_dedicated_app_before_any_remote_mutation(monkeypatch) -> None:
    module = load_setup_rulesets()
    _ready_apply(module, monkeypatch)
    monkeypatch.setattr(module, "configured_review_gate_app_slug", lambda: None)
    monkeypatch.setattr(
        module,
        "gh",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("remote mutation attempted")),
    )

    assert module.main() == 1


def test_apply_aggregates_failures_and_continues_other_repository_transactions(monkeypatch) -> None:
    module = load_setup_rulesets()
    _ready_apply(module, monkeypatch)
    monkeypatch.setattr(module, "target_repos", lambda: ["owner/one", "owner/two"])
    body = module.protection_body(["pr-gate", "python"], 987654)
    spy = ApiSpy(
        [
            (
                "PATCH",
                "repos/owner/one",
                _result(returncode=1, stderr="first denied"),
            ),
            ("PATCH", "repos/owner/two", _result({})),
            ("GET", "repos/owner/two", _result(_live_settings())),
            (
                "PUT",
                "repos/owner/two/branches/trunk/protection",
                _result({}),
            ),
            ("GET", "repos/owner/two", _result(_live_settings())),
            (
                "GET",
                "repos/owner/two/branches/trunk/protection",
                _result(_live_protection(body)),
            ),
        ]
    )
    monkeypatch.setattr(module, "gh", spy)

    assert module.main() == 1
    spy.assert_finished()
    assert any(call["path"] == "repos/owner/two" for call in spy.calls)

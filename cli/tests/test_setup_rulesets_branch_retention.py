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
    assert "allow_auto_merge=true" not in report
    assert "delete_branch_on_merge=false" in text
    assert "delete_branch_on_merge=true" not in text
    assert "source branches remain after merge" in report.lower()
    assert "receipt-backed reaping" in report
    assert "delete_branch_on_merge=true" not in report
    assert "self-draining" not in report
    assert "--contain apply" in report


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
        "required_approving_review_count": 1,
        "require_last_push_approval": True,
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
    monkeypatch.setattr(module, "_protection_readback_state", lambda *_args: ("missing", "not protected"))
    monkeypatch.setattr(
        module,
        "gh",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("remote mutation attempted")),
    )

    assert module.main() == 1


def test_setup_rulesets_apply_refuses_without_executable_app_receipt(monkeypatch) -> None:
    module = load_setup_rulesets()
    monkeypatch.setattr(module, "APPLY", True)
    monkeypatch.setattr(module, "target_repos", lambda: ["owner/repository"])
    monkeypatch.setattr(
        module,
        "gh_json",
        lambda *_args, **_kwargs: {"defaultBranchRef": {"name": "main"}},
    )
    monkeypatch.setattr(module, "detect_checks", lambda _repo: ["pr-gate"])
    monkeypatch.setattr(module, "_protection_readback_state", lambda *_args: ("missing", "not protected"))
    monkeypatch.setattr(
        module,
        "review_gate_app_evidence",
        lambda _repo: (None, "no authenticated executable App receipt"),
    )
    monkeypatch.setattr(
        module,
        "gh",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("remote mutation attempted")),
    )

    assert module.main() == 1


def test_review_gate_app_identity_is_derived_from_authenticated_receipt_and_must_be_unique(monkeypatch) -> None:
    module = load_setup_rulesets()
    head = "a" * 40
    dedicated_slug = "keeper-review-publisher"

    monkeypatch.setattr(module, "validate_check_run_receipt", lambda *_args, **_kwargs: (True, ""))

    def one_app(args, **_kwargs):
        if "/pulls?" in args[-1]:
            return [{"number": 7, "head": {"sha": head}}]
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

    def two_apps(args, **_kwargs):
        if "/pulls?" in args[-1]:
            return [{"number": 7, "head": {"sha": head}}]
        return {
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

    monkeypatch.setattr(module, "gh_json", two_apps)
    assert module.review_gate_app_id("owner/repository", dedicated_slug) is None


def test_default_protection_scope_is_the_complete_seven_repo_cohort() -> None:
    module = load_setup_rulesets()
    assert module.target_repos() == list(module.RECOVERY_COHORT_REPOS)
    assert len(module.target_repos()) == 7


def test_apply_requires_and_reads_back_protection_for_all_seven_repositories(monkeypatch) -> None:
    module = load_setup_rulesets()
    monkeypatch.setattr(module, "APPLY", True)
    monkeypatch.setattr(module, "detect_checks", lambda _repo: ["pr-gate"])
    monkeypatch.setattr(module, "gh_json", lambda *_args, **_kwargs: {"defaultBranchRef": {"name": "main"}})
    monkeypatch.setattr(module, "_protection_readback_state", lambda *_args: ("missing", "not protected"))
    monkeypatch.setattr(
        module,
        "review_gate_app_evidence",
        lambda _repo: ({"slug": "keeper-gate-v7", "id": 987654}, ""),
    )
    readbacks = []

    def apply(repo, branch, body):
        readbacks.append((repo, branch, body))
        return True, []

    monkeypatch.setattr(module, "apply_protection_contract", apply)
    assert module.main() == 0
    assert [repo for repo, _branch, _body in readbacks] == list(module.RECOVERY_COHORT_REPOS)
    assert all(branch == "main" for _repo, branch, _body in readbacks)
    assert all(
        body["required_pull_request_reviews"]["required_approving_review_count"] == 1
        and body["required_pull_request_reviews"]["require_last_push_approval"] is True
        for _repo, _branch, body in readbacks
    )


def test_review_gate_app_rejects_generic_actions_without_caller_identity(monkeypatch) -> None:
    module = load_setup_rulesets()
    head = "a" * 40
    monkeypatch.setattr(
        module,
        "gh_json",
        lambda args, **_kwargs: (
            [{"number": 7, "head": {"sha": head}}]
            if "/pulls?" in args[-1]
            else {
                "check_runs": [
                    {
                        "name": module.REVIEW_GATE_CONTEXT,
                        "app": {"id": 1, "slug": "github-actions"},
                    }
                ]
            }
        ),
    )
    assert module.review_gate_app_evidence("owner/repository")[0] is None


def test_protection_preview_surfaces_account_plan_blocked_readback(
    monkeypatch,
    capsys,
) -> None:
    module = load_setup_rulesets()
    monkeypatch.setattr(module, "APPLY", False)
    monkeypatch.setattr(module, "target_repos", lambda: ["owner/private-repository"])
    monkeypatch.setattr(
        module,
        "gh_json",
        lambda *_args, **_kwargs: {"defaultBranchRef": {"name": "main"}},
    )
    monkeypatch.setattr(
        module,
        "_protection_readback_state",
        lambda *_args: ("blocked", "HTTP 403: Upgrade to GitHub Pro"),
    )

    assert module.main() == 1
    output = capsys.readouterr().out
    assert "BLOCKED" in output
    assert "account plan or permission gate" in output
    assert "HTTP 403" in output


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
    monkeypatch.setattr(module, "_protection_readback_state", lambda *_args: ("missing", "not protected"))
    monkeypatch.setattr(
        module,
        "review_gate_app_evidence",
        lambda _repo: ({"slug": "keeper-gate-v7", "id": 987654}, ""),
    )


def _success_steps(module, *, final_settings=None, final_protection=None):
    repo_path = "repos/owner/repository"
    protection_path = "repos/owner/repository/branches/trunk/protection"
    body = module.protection_body(["pr-gate", "python"], 987654)
    return [
        ("GET", repo_path, _result(_live_settings())),
        ("PUT", protection_path, _result({})),
        ("GET", repo_path, _result(final_settings or _live_settings())),
        ("GET", protection_path, _result(final_protection or _live_protection(body))),
    ]


def test_protection_apply_requires_containment_then_verifies_live_state_without_settings_mutation(
    monkeypatch,
) -> None:
    module = load_setup_rulesets()
    _ready_apply(module, monkeypatch)
    spy = ApiSpy(_success_steps(module))
    monkeypatch.setattr(module, "gh", spy)

    assert module.main() == 0
    spy.assert_finished()
    assert [(call["method"], call["path"]) for call in spy.calls] == [
        ("GET", "repos/owner/repository"),
        ("PUT", "repos/owner/repository/branches/trunk/protection"),
        ("GET", "repos/owner/repository"),
        ("GET", "repos/owner/repository/branches/trunk/protection"),
    ]
    assert all(call["method"] != "PATCH" for call in spy.calls)
    put_body = json.loads(spy.calls[1]["input"])
    assert put_body["required_status_checks"]["checks"][-1] == {
        "context": "limen.pr_review_gate.v1",
        "app_id": 987654,
    }


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
        value["required_pull_request_reviews"]["required_approving_review_count"] = 0
    elif field == "last_push":
        value["required_pull_request_reviews"]["require_last_push_approval"] = False
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
    monkeypatch.setattr(module, "review_gate_app_evidence", lambda _repo: (None, "missing App receipt"))
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
                "GET",
                "repos/owner/one",
                _result(returncode=1, stderr="containment unreadable"),
            ),
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


def _pull_node(number: int, *, active: bool):
    return {
        "id": f"PR_node_{number}",
        "number": number,
        "url": f"https://example.invalid/pulls/{number}",
        "autoMergeRequest": {"enabledAt": "2031-04-05T06:07:08Z"} if active else None,
    }


def _pull_page(nodes, *, next_cursor=None):
    return {
        "data": {
            "repository": {
                "pullRequests": {
                    "nodes": nodes,
                    "pageInfo": {
                        "hasNextPage": next_cursor is not None,
                        "endCursor": next_cursor,
                    },
                }
            }
        }
    }


def _cancelled_pull(number: int):
    return {
        "data": {
            "disablePullRequestAutoMerge": {
                "pullRequest": {
                    "id": f"PR_node_{number}",
                    "number": number,
                    "autoMergeRequest": None,
                }
            }
        }
    }


class ContainmentApiSpy:
    def __init__(self, steps):
        self.steps = list(steps)
        self.calls = []

    @staticmethod
    def _fields(args):
        fields = {}
        for index, value in enumerate(args):
            if value != "-f":
                continue
            key, item = args[index + 1].split("=", 1)
            fields[key] = item
        return fields

    def __call__(self, args, _timeout=45, *, input_text=None):
        assert self.steps, f"unexpected API call: {args}"
        expected, response = self.steps.pop(0)
        if args[:2] == ["api", "graphql"]:
            fields = self._fields(args)
            if "DisableRecoveryAutoMerge" in fields["query"]:
                actual = ("cancel", fields["pullRequestId"])
            else:
                actual = (
                    "inventory",
                    f"{fields['owner']}/{fields['name']}",
                    fields.get("cursor"),
                )
        else:
            method_index = args.index("--method")
            actual = (args[method_index + 1], args[method_index + 2])
        assert actual == expected
        self.calls.append({"operation": actual, "args": args, "input": input_text})
        return response

    def assert_finished(self):
        assert self.steps == []


def test_containment_mode_is_preview_by_default_and_rejects_mixed_apply() -> None:
    module = load_setup_rulesets()

    assert module._parse_contain_mode(["setup-rulesets.py", "--contain"]) == ("preview", "")
    assert module._parse_contain_mode(["setup-rulesets.py", "--contain", "preview"]) == ("preview", "")
    assert module._parse_contain_mode(["setup-rulesets.py", "--contain", "apply"]) == ("apply", "")
    assert module._parse_contain_mode(["setup-rulesets.py"]) == (None, "")
    assert module._parse_contain_mode(["setup-rulesets.py", "--contain", "destroy"])[1]
    assert module._parse_contain_mode(["setup-rulesets.py", "--contain", "apply", "--apply"])[1]


def test_explicit_repository_parser_accepts_only_bounded_owner_name_values() -> None:
    module = load_setup_rulesets()

    assert module._parse_repositories(
        [
            "setup-rulesets.py",
            "--repo",
            "example/nebula",
            "--repo=sample/aurora",
        ]
    ) == (["example/nebula", "sample/aurora"], "")

    for argv in (
        ["setup-rulesets.py", "--repo"],
        ["setup-rulesets.py", "--repo", "--contain"],
        ["setup-rulesets.py", "--repo", "missing-slash"],
        ["setup-rulesets.py", "--repo=too/many/slashes"],
        ["setup-rulesets.py", "--repo="],
    ):
        repositories, error = module._parse_repositories(argv)
        assert repositories == []
        assert error


def test_malformed_repository_argument_stops_before_default_cohort_expansion(monkeypatch) -> None:
    module = load_setup_rulesets()
    _repositories, error = module._parse_repositories(["setup-rulesets.py", "--contain", "apply", "--repo"])
    monkeypatch.setattr(module, "ARGUMENT_ERROR", error)
    monkeypatch.setattr(module, "CONTAIN_MODE", "apply")
    monkeypatch.setattr(
        module,
        "containment_main",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("default cohort expanded")),
    )

    assert module.main() == 2


def test_containment_explicit_cohort_is_bounded_and_deduplicated(monkeypatch) -> None:
    module = load_setup_rulesets()
    monkeypatch.setattr(
        module,
        "EXPLICIT",
        ["example/nebula", "example/nebula", "sample/aurora"],
    )

    assert module.containment_repos() == ["example/nebula", "sample/aurora"]


def test_auto_merge_inventory_paginates_every_open_pr_page(monkeypatch) -> None:
    module = load_setup_rulesets()
    spy = ContainmentApiSpy(
        [
            (
                ("inventory", "example/nebula", None),
                _result(
                    _pull_page(
                        [_pull_node(7, active=True), _pull_node(8, active=False)],
                        next_cursor="cursor-page-2",
                    )
                ),
            ),
            (
                ("inventory", "example/nebula", "cursor-page-2"),
                _result(_pull_page([_pull_node(109, active=True)])),
            ),
        ]
    )
    monkeypatch.setattr(module, "gh", spy)

    active, error = module.list_active_auto_merges("example/nebula")

    assert error == ""
    assert [pull["number"] for pull in active] == [7, 109]
    spy.assert_finished()


@pytest.mark.parametrize(
    ("active", "settings", "expected"),
    [
        ([_pull_node(12, active=True)], _live_settings(), 1),
        ([], _live_settings(auto_merge=True), 1),
        ([], _live_settings(delete_branch=True), 1),
        ([], _live_settings(), 0),
    ],
)
def test_containment_preview_is_read_only_and_reports_drift_as_nonzero(
    monkeypatch,
    active,
    settings,
    expected,
) -> None:
    module = load_setup_rulesets()
    monkeypatch.setattr(module, "CONTAIN_MODE", "preview")
    monkeypatch.setattr(module, "ARGUMENT_ERROR", "")
    monkeypatch.setattr(module, "containment_repos", lambda: ["example/nebula"])
    monkeypatch.setattr(
        module,
        "review_gate_app_evidence",
        lambda: (_ for _ in ()).throw(AssertionError("protection prerequisite consulted")),
    )
    spy = ContainmentApiSpy(
        [
            (
                ("inventory", "example/nebula", None),
                _result(_pull_page(active)),
            ),
            (
                ("GET", "repos/example/nebula"),
                _result(settings),
            ),
        ]
    )
    monkeypatch.setattr(module, "gh", spy)

    assert module.main() == expected
    spy.assert_finished()
    assert all(call["operation"][0] in {"inventory", "GET"} for call in spy.calls)


def test_containment_apply_paginates_cancels_locks_and_reads_back_without_protection(
    monkeypatch,
) -> None:
    module = load_setup_rulesets()
    monkeypatch.setattr(module, "CONTAIN_MODE", "apply")
    monkeypatch.setattr(module, "ARGUMENT_ERROR", "")
    monkeypatch.setattr(module, "containment_repos", lambda: ["example/nebula"])
    for prerequisite in (
        "detect_checks",
        "review_gate_app_evidence",
    ):
        monkeypatch.setattr(
            module,
            prerequisite,
            lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("protection prerequisite consulted")),
        )
    spy = ContainmentApiSpy(
        [
            (("PATCH", "repos/example/nebula"), _result(_live_settings())),
            (("GET", "repos/example/nebula"), _result(_live_settings())),
            (
                ("inventory", "example/nebula", None),
                _result(
                    _pull_page(
                        [_pull_node(7, active=True), _pull_node(8, active=False)],
                        next_cursor="cursor-page-2",
                    )
                ),
            ),
            (
                ("inventory", "example/nebula", "cursor-page-2"),
                _result(_pull_page([_pull_node(109, active=True)])),
            ),
            (("cancel", "PR_node_7"), _result(_cancelled_pull(7))),
            (("cancel", "PR_node_109"), _result(_cancelled_pull(109))),
            (("GET", "repos/example/nebula"), _result(_live_settings())),
            (
                ("inventory", "example/nebula", None),
                _result(_pull_page([_pull_node(8, active=False)])),
            ),
            (("GET", "repos/example/nebula"), _result(_live_settings())),
            (
                ("inventory", "example/nebula", None),
                _result(_pull_page([_pull_node(8, active=False)])),
            ),
            (("GET", "repos/example/nebula"), _result(_live_settings())),
        ]
    )
    monkeypatch.setattr(module, "gh", spy)

    assert module.main() == 0
    spy.assert_finished()
    patch = next(call for call in spy.calls if call["operation"][0] == "PATCH")
    assert json.loads(patch["input"]) == {
        "allow_auto_merge": False,
        "delete_branch_on_merge": False,
    }
    assert [call["operation"][0] for call in spy.calls[:3]] == [
        "PATCH",
        "GET",
        "inventory",
    ]
    first_cancel = next(index for index, call in enumerate(spy.calls) if call["operation"][0] == "cancel")
    assert first_cancel > 1
    assert all(
        not (call["operation"][0] == "PUT" and call["operation"][1].endswith("/protection")) for call in spy.calls
    )


@pytest.mark.parametrize(
    "settings_result",
    [
        _result(_live_settings(auto_merge=True)),
        _result(_live_settings(delete_branch=True)),
        _result(payload=None),
    ],
)
def test_containment_apply_fails_before_inventory_on_initial_settings_mismatch(
    monkeypatch,
    settings_result,
) -> None:
    module = load_setup_rulesets()
    monkeypatch.setattr(module, "CONTAIN_MODE", "apply")
    monkeypatch.setattr(module, "ARGUMENT_ERROR", "")
    monkeypatch.setattr(module, "containment_repos", lambda: ["sample/aurora"])
    spy = ContainmentApiSpy(
        [
            (("PATCH", "repos/sample/aurora"), _result(_live_settings())),
            (("GET", "repos/sample/aurora"), settings_result),
        ]
    )
    monkeypatch.setattr(module, "gh", spy)

    assert module.main() == 1
    spy.assert_finished()
    assert all(call["operation"][0] not in {"inventory", "cancel"} for call in spy.calls)


def test_containment_apply_fails_before_inventory_when_settings_patch_fails(
    monkeypatch,
) -> None:
    module = load_setup_rulesets()
    monkeypatch.setattr(module, "CONTAIN_MODE", "apply")
    monkeypatch.setattr(module, "ARGUMENT_ERROR", "")
    monkeypatch.setattr(module, "containment_repos", lambda: ["sample/aurora"])
    spy = ContainmentApiSpy(
        [
            (
                ("PATCH", "repos/sample/aurora"),
                _result(returncode=1, stderr="settings denied"),
            ),
        ]
    )
    monkeypatch.setattr(module, "gh", spy)

    assert module.main() == 1
    spy.assert_finished()
    assert all(call["operation"][0] not in {"inventory", "cancel"} for call in spy.calls)


def test_containment_apply_rejects_patch_response_that_does_not_confirm_request(
    monkeypatch,
) -> None:
    module = load_setup_rulesets()
    monkeypatch.setattr(module, "CONTAIN_MODE", "apply")
    monkeypatch.setattr(module, "ARGUMENT_ERROR", "")
    monkeypatch.setattr(module, "containment_repos", lambda: ["sample/aurora"])
    spy = ContainmentApiSpy(
        [
            (
                ("PATCH", "repos/sample/aurora"),
                _result(_live_settings(auto_merge=True)),
            ),
        ]
    )
    monkeypatch.setattr(module, "gh", spy)

    assert module.main() == 1
    spy.assert_finished()
    patch = spy.calls[0]
    assert json.loads(patch["input"]) == {
        "allow_auto_merge": False,
        "delete_branch_on_merge": False,
    }


def test_containment_apply_keeps_settings_locked_and_bounds_cancel_retries(monkeypatch) -> None:
    module = load_setup_rulesets()
    monkeypatch.setattr(module, "CONTAIN_MODE", "apply")
    monkeypatch.setattr(module, "ARGUMENT_ERROR", "")
    monkeypatch.setattr(module, "MAX_CONTAINMENT_PASSES", 2)
    monkeypatch.setattr(module, "containment_repos", lambda: ["sample/aurora"])
    spy = ContainmentApiSpy(
        [
            (("PATCH", "repos/sample/aurora"), _result(_live_settings())),
            (("GET", "repos/sample/aurora"), _result(_live_settings())),
            (
                ("inventory", "sample/aurora", None),
                _result(_pull_page([_pull_node(23, active=True)])),
            ),
            (
                ("cancel", "PR_node_23"),
                _result(returncode=1, stderr="mutation denied"),
            ),
            (("GET", "repos/sample/aurora"), _result(_live_settings())),
            (
                ("inventory", "sample/aurora", None),
                _result(_pull_page([_pull_node(23, active=True)])),
            ),
            (
                ("cancel", "PR_node_23"),
                _result(returncode=1, stderr="mutation still denied"),
            ),
        ]
    )
    monkeypatch.setattr(module, "gh", spy)

    assert module.main() == 1
    spy.assert_finished()
    assert [call["operation"][0] for call in spy.calls[:3]] == [
        "PATCH",
        "GET",
        "inventory",
    ]


def test_containment_apply_fails_if_settings_drift_during_drain(monkeypatch) -> None:
    module = load_setup_rulesets()
    monkeypatch.setattr(module, "CONTAIN_MODE", "apply")
    monkeypatch.setattr(module, "ARGUMENT_ERROR", "")
    monkeypatch.setattr(module, "containment_repos", lambda: ["sample/aurora"])
    spy = ContainmentApiSpy(
        [
            (("PATCH", "repos/sample/aurora"), _result(_live_settings())),
            (("GET", "repos/sample/aurora"), _result(_live_settings())),
            (
                ("inventory", "sample/aurora", None),
                _result(_pull_page([_pull_node(23, active=True)])),
            ),
            (("cancel", "PR_node_23"), _result(_cancelled_pull(23))),
            (
                ("GET", "repos/sample/aurora"),
                _result(_live_settings(auto_merge=True)),
            ),
        ]
    )
    monkeypatch.setattr(module, "gh", spy)

    assert module.main() == 1
    spy.assert_finished()
    assert spy.calls[-1]["operation"] == ("GET", "repos/sample/aurora")


def test_containment_apply_fails_if_settings_drift_after_stable_empty(
    monkeypatch,
) -> None:
    module = load_setup_rulesets()
    monkeypatch.setattr(module, "CONTAIN_MODE", "apply")
    monkeypatch.setattr(module, "ARGUMENT_ERROR", "")
    monkeypatch.setattr(module, "containment_repos", lambda: ["sample/aurora"])
    spy = ContainmentApiSpy(
        [
            (("PATCH", "repos/sample/aurora"), _result(_live_settings())),
            (("GET", "repos/sample/aurora"), _result(_live_settings())),
            (("inventory", "sample/aurora", None), _result(_pull_page([]))),
            (("GET", "repos/sample/aurora"), _result(_live_settings())),
            (("inventory", "sample/aurora", None), _result(_pull_page([]))),
            (
                ("GET", "repos/sample/aurora"),
                _result(_live_settings(auto_merge=True)),
            ),
        ]
    )
    monkeypatch.setattr(module, "gh", spy)

    assert module.main() == 1
    spy.assert_finished()


def test_containment_apply_fails_when_new_requests_prevent_bounded_fixed_point(
    monkeypatch,
) -> None:
    module = load_setup_rulesets()
    monkeypatch.setattr(module, "CONTAIN_MODE", "apply")
    monkeypatch.setattr(module, "ARGUMENT_ERROR", "")
    monkeypatch.setattr(module, "MAX_CONTAINMENT_PASSES", 2)
    monkeypatch.setattr(module, "containment_repos", lambda: ["sample/aurora"])
    spy = ContainmentApiSpy(
        [
            (("PATCH", "repos/sample/aurora"), _result(_live_settings())),
            (("GET", "repos/sample/aurora"), _result(_live_settings())),
            (
                ("inventory", "sample/aurora", None),
                _result(_pull_page([_pull_node(23, active=True)])),
            ),
            (("cancel", "PR_node_23"), _result(_cancelled_pull(23))),
            (("GET", "repos/sample/aurora"), _result(_live_settings())),
            (
                ("inventory", "sample/aurora", None),
                _result(_pull_page([_pull_node(24, active=True)])),
            ),
            (("cancel", "PR_node_24"), _result(_cancelled_pull(24))),
        ]
    )
    monkeypatch.setattr(module, "gh", spy)

    assert module.main() == 1
    spy.assert_finished()


def test_containment_apply_processes_every_repo_after_one_inventory_failure(monkeypatch) -> None:
    module = load_setup_rulesets()
    monkeypatch.setattr(module, "CONTAIN_MODE", "apply")
    monkeypatch.setattr(module, "ARGUMENT_ERROR", "")
    monkeypatch.setattr(
        module,
        "containment_repos",
        lambda: ["sample/aurora", "example/nebula"],
    )
    spy = ContainmentApiSpy(
        [
            (("PATCH", "repos/sample/aurora"), _result(_live_settings())),
            (("GET", "repos/sample/aurora"), _result(_live_settings())),
            (
                ("inventory", "sample/aurora", None),
                _result(returncode=1, stderr="inventory unavailable"),
            ),
            (("PATCH", "repos/example/nebula"), _result(_live_settings())),
            (("GET", "repos/example/nebula"), _result(_live_settings())),
            (
                ("inventory", "example/nebula", None),
                _result(_pull_page([])),
            ),
            (("GET", "repos/example/nebula"), _result(_live_settings())),
            (
                ("inventory", "example/nebula", None),
                _result(_pull_page([])),
            ),
            (("GET", "repos/example/nebula"), _result(_live_settings())),
        ]
    )
    monkeypatch.setattr(module, "gh", spy)

    assert module.main() == 1
    spy.assert_finished()
    assert any(call["operation"] == ("PATCH", "repos/example/nebula") for call in spy.calls)

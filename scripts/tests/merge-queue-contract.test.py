#!/usr/bin/env python3
"""Focused contracts for Limen's native merge-queue workflow and ruleset body."""

from __future__ import annotations

import contextlib
import importlib.util
import io
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import mock

import yaml


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "pr-gate.yml"
SETUP = ROOT / "scripts" / "setup-rulesets.py"


def load_setup_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("setup_rulesets_contract", SETUP)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def workflow_doc() -> dict:
    doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    # PyYAML 1.1 parses the bare workflow key `on` as boolean True.
    if True in doc and "on" not in doc:
        doc["on"] = doc.pop(True)
    return doc


def named_step(doc: dict, prefix: str) -> dict:
    return next(step for step in doc["jobs"]["pr-gate"]["steps"] if str(step.get("name", "")).startswith(prefix))


def test_workflow_event_contract() -> None:
    doc = workflow_doc()
    triggers = doc["on"]
    assert triggers["merge_group"] == {"types": ["checks_requested"]}

    pull_request = named_step(doc, "Verify implicated PR gates")
    assert "github.event_name == 'pull_request'" in pull_request["if"]
    assert pull_request["env"]["LIMEN_VERIFY_REQUIRE_BASE"] == "1"
    assert "--skip-ci-covered pr-gate.yml:pr-gate" in pull_request["run"]
    assert "--integration" not in pull_request["run"]

    merge_group = named_step(doc, "Verify merge-group integration gates")
    assert "github.event_name == 'merge_group'" in merge_group["if"]
    assert merge_group["env"]["MERGE_GROUP_BASE_SHA"] == "${{ github.event.merge_group.base_sha }}"
    assert "--changed --integration" in merge_group["run"]
    assert '--base "$MERGE_GROUP_BASE_SHA"' in merge_group["run"]
    assert "--skip-ci-covered" not in merge_group["run"]


def test_targeted_ruleset_and_classic_protection_contract() -> None:
    module = load_setup_module()
    assert module.checks_for_repo("organvm/limen") == ["pr-gate"]

    protection = module.classic_protection_body(["pr-gate"])
    assert protection["required_status_checks"] == {
        "strict": False,
        "contexts": ["pr-gate"],
    }
    assert protection["enforce_admins"] is False
    assert protection["required_pull_request_reviews"] is None

    ruleset = module.merge_queue_ruleset_body()
    assert ruleset["conditions"] == {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}}
    assert ruleset["enforcement"] == "active"
    assert [rule["type"] for rule in ruleset["rules"]] == ["merge_queue"]
    assert ruleset["rules"][0]["parameters"] == {
        "check_response_timeout_minutes": 60,
        "grouping_strategy": "HEADGREEN",
        "max_entries_to_build": 4,
        "max_entries_to_merge": 1,
        "merge_method": "SQUASH",
        "min_entries_to_merge": 1,
        "min_entries_to_merge_wait_minutes": 0,
    }


def test_ruleset_apply_is_idempotent_and_targeted() -> None:
    module = load_setup_module()
    success = SimpleNamespace(returncode=0, stderr="")

    for existing, method, path in (
        (
            [{"id": 731, "name": module.MERGE_QUEUE_RULESET_NAME}],
            "PUT",
            "/repos/organvm/limen/rulesets/731",
        ),
        ([], "POST", "/repos/organvm/limen/rulesets"),
    ):
        with (
            mock.patch.object(module, "gh_json", return_value=existing),
            mock.patch.object(module, "gh_input", return_value=success) as api,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            assert module.ensure_merge_queue("organvm/limen") is True
        api.assert_called_once_with(method, path, module.merge_queue_ruleset_body())

    with mock.patch.object(module, "gh_input") as api:
        assert module.ensure_merge_queue("organvm/another-repo") is None
        api.assert_not_called()


def test_dry_run_never_calls_mutating_seams() -> None:
    module = load_setup_module()
    module.APPLY = False
    with (
        mock.patch.object(module, "target_repos", return_value=["organvm/limen"]),
        mock.patch.object(
            module,
            "gh_json",
            return_value={"defaultBranchRef": {"name": "main"}},
        ),
        mock.patch.object(module, "gh") as gh_call,
        mock.patch.object(module, "gh_input") as gh_input_call,
        mock.patch.object(module, "ensure_merge_queue") as queue_call,
        mock.patch.object(module, "ensure_copilot_review") as copilot_call,
        contextlib.redirect_stdout(io.StringIO()),
    ):
        module.main()
    gh_call.assert_not_called()
    gh_input_call.assert_not_called()
    queue_call.assert_not_called()
    copilot_call.assert_not_called()


def test_apply_seam_has_no_duplicate_protection_call() -> None:
    source = SETUP.read_text(encoding="utf-8")
    assert 'APPLY = "--apply" in sys.argv' in source
    assert source.count('f"/repos/{repo}/branches/{branch}/protection"') == 1


def main() -> None:
    test_workflow_event_contract()
    test_targeted_ruleset_and_classic_protection_contract()
    test_ruleset_apply_is_idempotent_and_targeted()
    test_dry_run_never_calls_mutating_seams()
    test_apply_seam_has_no_duplicate_protection_call()
    print("merge-queue-contract: all focused contracts pass")


if __name__ == "__main__":
    main()

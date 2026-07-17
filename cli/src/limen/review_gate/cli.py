"""Command-line surface for the exact-head peer-review gate."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Sequence

from .github import fetch_pull_request, publish_status, resolve_repo, split_repo
from .model import (
    DIAGNOSTIC_SCHEMA,
    HEAD_SHA,
    SCHEMA,
    GateError,
    configured_review_gate_app_slug,
    error_report,
    evaluate,
    report_evidence_digest,
    snapshot_digest,
)


def load_fixture(path: Path) -> tuple[dict[str, Any], str | None]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise GateError(f"cannot read fixture: {exc}") from exc
    except ValueError as exc:
        raise GateError(f"fixture is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise GateError("fixture root must be a JSON object")
    fixture_repo = data.get("repository_name")
    if fixture_repo is not None and not isinstance(fixture_repo, str):
        raise GateError("fixture repository_name must be a string")
    pull = data.get("pullRequest")
    if not isinstance(pull, dict):
        raise GateError("fixture must contain a pullRequest object")
    return pull, fixture_repo


def emit(report: dict[str, Any], *, as_json: bool, quiet: bool) -> None:
    if as_json:
        print(json.dumps(report, sort_keys=True))
        return
    if quiet:
        return
    print(
        f"pr-review-gate: {str(report.get('status') or 'error').upper()} "
        f"{report.get('repository')}#{report.get('pull_request')} @ "
        f"{report.get('head_sha') or 'unavailable'}"
    )
    for reason in report.get("reasons") or []:
        print(f"  HOLD [{reason['code']}]: {reason['message']}")


def positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("PR must be a positive integer") from exc
    if number <= 0:
        raise argparse.ArgumentTypeError("PR must be a positive integer")
    return number


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("PR", type=positive_int)
    ap.add_argument("--repo")
    ap.add_argument("--expected-head")
    ap.add_argument("--fixture", type=Path)
    ap.add_argument(
        "--allowed-signers",
        type=Path,
        help="blocked compatibility input; local signer files are not a production custody source",
    )
    ap.add_argument(
        "--review-gate-app-slug",
        help="dedicated App slug (or LIMEN_REVIEW_GATE_APP_SLUG)",
    )
    ap.add_argument(
        "--review-gate-app-id",
        help="provisioned App id (or LIMEN_REVIEW_GATE_APP_ID); required for authoritative publication",
    )
    ap.add_argument(
        "--require-published-result",
        action="store_true",
        help="consumer mode: require the App's current exact-head successful receipt",
    )
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    publishing = ap.add_mutually_exclusive_group()
    publishing.add_argument("--publish-status", action="store_true")
    publishing.add_argument("--publish-diagnostic", action="store_true")
    return ap


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    repo = args.repo or ""
    requested = args.publish_status or args.publish_diagnostic
    check_name = DIAGNOSTIC_SCHEMA if args.publish_diagnostic else SCHEMA
    publication_head = args.expected_head if args.expected_head and HEAD_SHA.fullmatch(args.expected_head) else None
    raw_slug = args.review_gate_app_slug or os.environ.get("LIMEN_REVIEW_GATE_APP_SLUG")
    raw_app_id = args.review_gate_app_id or os.environ.get("LIMEN_REVIEW_GATE_APP_ID")
    app_slug: str | None = None
    report: dict[str, Any]

    try:
        app_slug = configured_review_gate_app_slug(raw_slug)
        if args.publish_status and app_slug is None:
            raise GateError("--publish-status requires a dedicated non-generic review-gate App slug")
        if args.publish_status and args.require_published_result:
            raise GateError("App evaluation cannot require its own current output")
        if args.fixture and requested:
            raise GateError("--fixture cannot be combined with check publication")
        if args.fixture:
            pull, fixture_repo = load_fixture(args.fixture)
            repo = repo or fixture_repo or "fixture/fixture"
            split_repo(repo)
            report = evaluate(
                pull,
                repo=repo,
                number=args.PR,
                expected_head=args.expected_head,
                fixture=True,
                allowed_signers=args.allowed_signers,
                review_gate_app_slug=app_slug,
                require_published_result=args.require_published_result,
            )
        else:
            repo = repo or resolve_repo()
            split_repo(repo)
            initial = fetch_pull_request(repo, args.PR)
            initial_head = str(initial.get("headRefOid") or "")
            if HEAD_SHA.fullmatch(initial_head):
                publication_head = initial_head
            final = fetch_pull_request(repo, args.PR)
            final_head = str(final.get("headRefOid") or "")
            if HEAD_SHA.fullmatch(final_head):
                publication_head = final_head
            report = evaluate(
                final,
                repo=repo,
                number=args.PR,
                expected_head=args.expected_head,
                rechecked_head=initial_head,
                rechecked_snapshot_digest=snapshot_digest(
                    initial,
                    repo=repo,
                    review_gate_app_slug=app_slug,
                ),
                allowed_signers=args.allowed_signers,
                review_gate_app_slug=app_slug,
                require_published_result=args.require_published_result,
            )
    except GateError as exc:
        report = error_report(
            repo=repo,
            number=args.PR,
            expected_head=args.expected_head,
            message=str(exc),
        )
        if publication_head is not None:
            report["head_sha"] = publication_head
            report["evidence_digest"] = report_evidence_digest(report)

    if requested:
        report["publication"]["requested"] = True
        if report.get("head_sha") is None:
            emit(report, as_json=args.json, quiet=args.quiet)
            return 2
        try:
            publish_status(
                report,
                check_name=check_name,
                publisher_app_slug=app_slug,
                publisher_app_id=raw_app_id,
            )
        except GateError as exc:
            report["status"] = report["final_status"] = "error"
            report["ok"] = False
            report["reason_codes"].append("status_publication_failed")
            report["reasons"].append({"code": "status_publication_failed", "message": str(exc)})
            emit(report, as_json=args.json, quiet=args.quiet)
            return 2
        report["publication"]["published"] = True

    emit(report, as_json=args.json, quiet=args.quiet)
    if report["status"] == "accepted":
        return 0
    if report["status"] == "rejected":
        return 1
    return 2

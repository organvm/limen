#!/usr/bin/env python3
"""Run the bounded, resumable governance-memory owner cadence.

The orchestrator owns ordering, limits, receipt binding, and resume semantics.
It does not own provider discovery, raw custody, normalization, constitutional
authority, graph reconciliation, or Atlas compilation. Those commands are
declared in a runtime JSON/YAML configuration and execute in their owner
worktrees.

An unchanged frozen snapshot reaches a fixed point:

* a completed stage is skipped only after its receipt, predecessor, inputs,
  owner revision, predicate, and output bytes are revalidated;
* every owner command is invoked again in proof mode and must report only
  byte-identical ``skipped_completed`` children with zero emitted events;
* run one is incomplete and run two readiness is derived from typed owner debt;
* full receipts and the post-proof final bundle pass runtime public schemas;
* the aggregate cadence receipt is derived only from the snapshot, config,
  owner readiness, and ordered stage receipts;
* no execution timestamp or local path is written to public receipts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

try:
    import yaml
    import rfc8785
    from jsonschema import Draft202012Validator, FormatChecker
    from jsonschema.exceptions import SchemaError
except ModuleNotFoundError:
    owned_python = (
        Path(__file__).resolve().parents[1] / "cli" / ".venv" / "bin" / "python"
    )
    if (
        __name__ == "__main__"
        and os.environ.get("LIMEN_GOV_RUNTIME_BOOTSTRAPPED") != "1"
        and owned_python.is_file()
        and Path(sys.executable).resolve() != owned_python.resolve()
    ):
        environment = dict(os.environ)
        environment["LIMEN_GOV_RUNTIME_BOOTSTRAPPED"] = "1"
        os.execve(
            owned_python,
            [str(owned_python), str(Path(__file__).resolve()), *sys.argv[1:]],
            environment,
        )
    raise

STAGES: tuple[str, ...] = (
    "discover",
    "snapshot",
    "parse",
    "classify",
    "reconcile",
    "distill",
    "validate",
    "render",
    "receipt",
)

SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,191}$")
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
PUBLIC_REFERENCE = re.compile(r"^[a-z][a-z0-9+.-]*:(?://)?[A-Za-z0-9][A-Za-z0-9._~:/#-]{0,255}$")
SENSITIVE_NAME = re.compile(
    r"(?:^|_)(?:auth|cookie|credential|key|password|secret|token)(?:_|$)",
    re.IGNORECASE,
)
SENSITIVE_TEXT = re.compile(
    r"(?:/Users/|/home/|\.limen-private|"
    r"(?:auth|cookie|credential|key|password|secret|token)(?::|=))",
    re.IGNORECASE,
)
READINESS_DEBT_FIELDS: tuple[str, ...] = (
    "unresolved_blockers",
    "quarantines",
    "missing_requirements",
    "citation_debt",
    "incomplete_predicates",
)
READINESS_STATUSES = {
    "incomplete",
    "blocked",
    "ready",
    "closed_with_owner_routed_debt",
}
INPUT_KINDS = {"predecessor_output", "snapshot_anchor"}
PRE_PROOF_BUNDLE_CONTRACT = "governance-snapshot-bundle-pre-proof.v1"
FINAL_BUNDLE_FILENAME = "governance-snapshot-bundle.v1.json"
PRE_PROOF_BUNDLE_FIELDS: tuple[str, ...] = (
    "bundle_id",
    "source_census",
    "normalized_events",
    "source_envelopes",
    "assertion_evidence",
    "lineage_graph",
    "governance_testament",
    "coverage",
    "ideal_form_register",
    "node_self_image_set",
    "iceberg_atlas",
    "normalization_parity_receipt",
    "governance_atlas_receipt",
)
ORCHESTRATOR_SEALED_BUNDLE_FIELDS = {
    "contract_name",
    "contract_version",
    "snapshot_id",
    "snapshot_at",
    "snapshot_digest",
    "generated_at",
    "governance_stage_receipts",
    "governance_cadence_receipts",
    "post_proof_idempotence",
    "readiness",
    "digest_algorithm",
    "bundle_digest",
}
REQUIRED_SCHEMA_CONTRACTS = {
    "governance-stage-receipt.v1",
    "governance-snapshot-bundle.v1",
}
MAX_ATTEMPTS = 5
MAX_TIMEOUT_SECONDS = 86_400
MAX_ITEMS = 10_000_000
MAX_BYTES = 1 << 34
RUNTIME_ENVIRONMENT = {
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "PATH": os.defpath,
    "PYTHONHASHSEED": "0",
    "TZ": "UTC",
}


class CadenceError(RuntimeError):
    """A fail-closed cadence configuration or execution error."""


@dataclass(frozen=True)
class ArtifactSpec:
    artifact_id: str
    reference: str
    path: Path
    contract: str | None = None
    input_kind: str | None = None
    anchor_snapshot_id: str | None = None
    anchor_snapshot_digest: str | None = None


@dataclass(frozen=True)
class PredicateSpec:
    predicate_id: str
    command: tuple[str, ...]
    receipt_command: str
    expected_result: str
    revision: OwnerRevision

    def public(self) -> dict[str, str]:
        return {
            "predicate_id": self.predicate_id,
            "command": self.receipt_command,
            "expected_result": self.expected_result,
        }


@dataclass(frozen=True)
class OwnerRevision:
    value: str
    kind: str
    path: Path | None = None


@dataclass(frozen=True)
class SchemaCatalog:
    root: Path
    schemas: dict[str, dict[str, Any]]
    digests: dict[str, str]
    paths: dict[str, Path]


@dataclass(frozen=True)
class ExecutionProfile:
    max_items: int
    timeout_seconds: int
    max_attempts: int
    max_log_bytes: int
    max_artifact_bytes: int

    def public(self) -> dict[str, int]:
        return {
            "max_items": self.max_items,
            "timeout_seconds": self.timeout_seconds,
            "max_attempts": self.max_attempts,
            "max_log_bytes": self.max_log_bytes,
            "max_artifact_bytes": self.max_artifact_bytes,
        }

    def receipt_limits(self) -> dict[str, int]:
        return {
            "max_work_items": self.max_items,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_attempts - 1,
            "max_output_bytes": self.max_artifact_bytes,
        }


@dataclass(frozen=True)
class StageSpec:
    stage: str
    owner_reference: str
    owner_revision: OwnerRevision
    predicate: PredicateSpec
    receipt_target: str
    cwd: Path
    command: tuple[str, ...]
    env: dict[str, str]
    inputs: tuple[ArtifactSpec, ...]
    outputs: tuple[ArtifactSpec, ...]
    readiness_evidence: ArtifactSpec
    schema_catalog: SchemaCatalog
    profile: ExecutionProfile


@dataclass(frozen=True)
class RunStats:
    invoked_stages: tuple[str, ...]
    executed_stages: tuple[str, ...]
    skipped_stages: tuple[str, ...]
    attempts: int
    new_events: int
    changed_receipts: int
    replayed_completed_children: int

    def public(self) -> dict[str, Any]:
        return {
            "invoked_stages": list(self.invoked_stages),
            "executed_stages": list(self.executed_stages),
            "skipped_stages": list(self.skipped_stages),
            "attempts": self.attempts,
            "new_events": self.new_events,
            "changed_receipts": self.changed_receipts,
            "replayed_completed_children": self.replayed_completed_children,
        }


@dataclass(frozen=True)
class StageResult:
    receipt: dict[str, Any]
    attempts: int
    invoked: bool
    executed_children: int
    changed_receipt: bool
    emitted_events: int


@dataclass(frozen=True)
class CadenceStats:
    run_one: RunStats
    run_two: RunStats
    aggregate_receipts_written: int

    def public(self) -> dict[str, Any]:
        return {
            "run_one": self.run_one.public(),
            "run_two": self.run_two.public(),
            "aggregate_receipts_written": self.aggregate_receipts_written,
        }


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def digest_value(value: Any) -> str:
    return sha256_bytes(rfc8785.dumps(value))


def digest_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return "sha256:" + digest.hexdigest(), size


def load_document(path: Path) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CadenceError(f"cannot read {path}: {type(exc).__name__}") from exc
    try:
        if path.suffix.lower() in {".yaml", ".yml"}:
            return yaml.safe_load(text)
        return json.loads(text)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise CadenceError(f"invalid cadence document {path}: {type(exc).__name__}") from exc


def parse_snapshot_at(value: str) -> str:
    candidate = value.strip()
    if not candidate:
        raise CadenceError("--snapshot-at must be nonempty")
    normalized = candidate[:-1] + "+00:00" if candidate.endswith("Z") else candidate
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise CadenceError("--snapshot-at must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise CadenceError("--snapshot-at must include a timezone")
    return candidate


def safe_id(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not SAFE_ID.fullmatch(text):
        raise CadenceError(f"{field} must be a stable nonempty identifier")
    return text


def public_reference(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not PUBLIC_REFERENCE.fullmatch(text) or SENSITIVE_TEXT.search(text):
        raise CadenceError(f"{field} must be a public-safe stable reference")
    return text


def public_text(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text or len(text) > 512 or SENSITIVE_TEXT.search(text):
        raise CadenceError(f"{field} must be bounded public-safe text")
    return text


def argv(value: Any, field: str) -> tuple[str, ...]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes))
        or not value
        or not all(isinstance(item, str) and item.strip() for item in value)
    ):
        raise CadenceError(f"{field} must be a nonempty argv array")
    return tuple(value)


def positive_int(
    value: Any,
    field: str,
    *,
    maximum: int,
) -> int:
    if isinstance(value, bool):
        raise CadenceError(f"{field} must be a positive integer")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise CadenceError(f"{field} must be a positive integer") from exc
    if number <= 0 or number > maximum:
        raise CadenceError(f"{field} must be between 1 and {maximum}")
    return number


def expand(value: str, environment: Mapping[str, str]) -> str:
    pattern = re.compile(r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))")

    def replace(match: re.Match[str]) -> str:
        name = match.group(1) or match.group(2) or ""
        if SENSITIVE_NAME.search(name):
            raise CadenceError(f"configuration cannot expand secret-bearing variable {name}")
        if name not in environment:
            raise CadenceError(f"configuration references unset variable {name}")
        return environment[name]

    return pattern.sub(replace, value)


def resolve_path(
    raw: Any,
    *,
    base: Path,
    environment: Mapping[str, str],
) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        raise CadenceError("artifact path must be a nonempty string")
    expanded = Path(expand(raw, environment)).expanduser()
    return expanded.resolve() if expanded.is_absolute() else (base / expanded).resolve()


def command_result(
    command: Sequence[str],
    *,
    cwd: Path,
) -> str:
    try:
        process = subprocess.run(
            list(command),
            cwd=cwd,
            env=RUNTIME_ENVIRONMENT,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CadenceError(f"cannot resolve owner revision: {type(exc).__name__}") from exc
    if process.returncode != 0:
        raise CadenceError("cannot resolve owner revision")
    return process.stdout.strip()


def parse_revision(
    raw: Any,
    *,
    stage: str,
    role: str,
    cwd: Path,
    config_dir: Path,
    environment: Mapping[str, str],
    command: Sequence[str],
) -> OwnerRevision:
    if not isinstance(raw, Mapping):
        raise CadenceError(f"stage {stage} requires an exact {role}_revision object")
    kind = str(raw.get("kind") or "").strip()
    if kind == "git":
        revision = str(raw.get("revision") or "").strip()
        if not GIT_SHA.fullmatch(revision):
            raise CadenceError(f"stage {stage} git {role}_revision must be an exact 40-character SHA")
        if raw.get("require_clean") is not True:
            raise CadenceError(f"stage {stage} git {role}_revision must require a clean worktree")
        result = command_result(("git", "rev-parse", "HEAD"), cwd=cwd)
        if result != revision:
            raise CadenceError(f"stage {stage} {role} revision does not match the live Git HEAD")
        if command_result(("git", "status", "--porcelain", "--untracked-files=all"), cwd=cwd):
            raise CadenceError(f"stage {stage} {role} worktree is not clean")
        return OwnerRevision(value=f"git:{revision}", kind=kind)
    if kind == "file":
        digest = str(raw.get("digest") or "").strip()
        if not SHA256.fullmatch(digest):
            raise CadenceError(f"stage {stage} file {role}_revision requires an exact sha256 digest")
        path = resolve_path(raw.get("path"), base=config_dir, environment=environment)
        try:
            path.relative_to(cwd)
        except ValueError as exc:
            raise CadenceError(f"stage {stage} {role} revision file must remain under cwd") from exc
        if not path.is_file() or digest_file(path)[0] != digest:
            raise CadenceError(f"stage {stage} {role} revision file does not match its digest")
        resolved_args = {
            str(Path(item).expanduser().resolve()) for item in command if item.startswith("/") or "/" in item
        }
        if str(path) not in resolved_args:
            raise CadenceError(f"stage {stage} {role} revision file must be an executed command input")
        return OwnerRevision(value=digest, kind=kind, path=path)
    raise CadenceError(f"stage {stage} {role}_revision.kind must be git or file")


def verify_revision(
    revision: OwnerRevision,
    *,
    spec: StageSpec,
    role: str,
) -> None:
    if revision.kind == "git":
        expected = revision.value.removeprefix("git:")
        if command_result(("git", "rev-parse", "HEAD"), cwd=spec.cwd) != expected:
            raise CadenceError(f"stage {spec.stage} {role} revision changed")
        if command_result(("git", "status", "--porcelain", "--untracked-files=all"), cwd=spec.cwd):
            raise CadenceError(f"stage {spec.stage} {role} worktree became dirty")
        return
    if revision.path is None or digest_file(revision.path)[0] != revision.value:
        raise CadenceError(f"stage {spec.stage} {role} revision changed")


def verify_stage_revisions(spec: StageSpec) -> None:
    verify_revision(spec.owner_revision, spec=spec, role="owner")
    verify_revision(spec.predicate.revision, spec=spec, role="predicate")


def artifact_spec(
    raw: Any,
    *,
    index: int,
    kind: str,
    base: Path,
    environment: Mapping[str, str],
    snapshot_id: str,
    snapshot_digest: str,
    is_input: bool,
) -> ArtifactSpec:
    if not isinstance(raw, Mapping):
        raise CadenceError(f"{kind}[{index}] must be an artifact reference object")
    artifact_id = safe_id(raw.get("artifact_id"), f"{kind}[{index}].artifact_id")
    reference = public_reference(raw.get("reference"), f"{kind}[{index}].reference")
    path = resolve_path(raw.get("path"), base=base, environment=environment)
    contract = raw.get("contract")
    if contract is not None:
        contract = safe_id(contract, f"{kind}[{index}].contract")
    input_kind: str | None = None
    anchor_snapshot_id: str | None = None
    anchor_snapshot_digest: str | None = None
    if is_input:
        input_kind = str(raw.get("input_kind") or "").strip()
        if input_kind not in INPUT_KINDS:
            raise CadenceError(f"{kind}[{index}].input_kind must be predecessor_output or snapshot_anchor")
        if input_kind == "snapshot_anchor":
            anchor_snapshot_id = str(raw.get("snapshot_id") or "").strip()
            anchor_snapshot_digest = str(raw.get("snapshot_digest") or "").strip()
            if anchor_snapshot_id != snapshot_id or anchor_snapshot_digest != snapshot_digest:
                raise CadenceError(f"{kind}[{index}] snapshot anchor must bind the exact frozen snapshot")
        elif "snapshot_id" in raw or "snapshot_digest" in raw:
            raise CadenceError(f"{kind}[{index}] predecessor output cannot carry snapshot anchor fields")
    elif any(field in raw for field in ("input_kind", "snapshot_id", "snapshot_digest")):
        raise CadenceError(f"{kind}[{index}] output cannot declare input-only fields")
    return ArtifactSpec(
        artifact_id=artifact_id,
        reference=reference,
        path=path,
        contract=contract,
        input_kind=input_kind,
        anchor_snapshot_id=anchor_snapshot_id,
        anchor_snapshot_digest=anchor_snapshot_digest,
    )


def parse_profile(raw: Any, stage: str) -> ExecutionProfile:
    if not isinstance(raw, Mapping):
        raise CadenceError(f"stage {stage} requires an execution_profile object")
    return ExecutionProfile(
        max_items=positive_int(
            raw.get("max_items"),
            f"{stage}.execution_profile.max_items",
            maximum=MAX_ITEMS,
        ),
        timeout_seconds=positive_int(
            raw.get("timeout_seconds"),
            f"{stage}.execution_profile.timeout_seconds",
            maximum=MAX_TIMEOUT_SECONDS,
        ),
        max_attempts=positive_int(
            raw.get("max_attempts"),
            f"{stage}.execution_profile.max_attempts",
            maximum=MAX_ATTEMPTS,
        ),
        max_log_bytes=positive_int(
            raw.get("max_log_bytes"),
            f"{stage}.execution_profile.max_log_bytes",
            maximum=MAX_BYTES,
        ),
        max_artifact_bytes=positive_int(
            raw.get("max_artifact_bytes"),
            f"{stage}.execution_profile.max_artifact_bytes",
            maximum=MAX_BYTES,
        ),
    )


def parse_schema_catalog(
    raw: Any,
    *,
    config_dir: Path,
    environment: Mapping[str, str],
) -> SchemaCatalog:
    if not isinstance(raw, Mapping):
        raise CadenceError("cadence config requires a public schema_catalog object")
    root = resolve_path(raw.get("root"), base=config_dir, environment=environment)
    if not root.is_dir():
        raise CadenceError("schema_catalog.root must be an available directory")
    contracts = raw.get("contracts")
    if not isinstance(contracts, Mapping):
        raise CadenceError("schema_catalog.contracts must be an object")
    missing = sorted(REQUIRED_SCHEMA_CONTRACTS - set(contracts))
    if missing:
        raise CadenceError(f"schema_catalog is missing required public contracts: {missing}")
    schemas: dict[str, dict[str, Any]] = {}
    digests: dict[str, str] = {}
    paths: dict[str, Path] = {}
    for contract_name, raw_path in contracts.items():
        if not isinstance(contract_name, str) or not contract_name.strip():
            raise CadenceError("schema_catalog contract names must be nonempty")
        path = resolve_path(raw_path, base=root, environment=environment)
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise CadenceError(f"schema_catalog contract {contract_name} must remain under its root") from exc
        document = load_document(path)
        if not isinstance(document, dict):
            raise CadenceError(f"schema_catalog contract {contract_name} must contain a JSON Schema object")
        try:
            Draft202012Validator.check_schema(document)
        except SchemaError as exc:
            raise CadenceError(f"schema_catalog contract {contract_name} is not a valid JSON Schema") from exc
        contract_rule = document.get("properties", {}).get("contract_name", {})
        if not isinstance(contract_rule, Mapping) or contract_rule.get("const") != contract_name:
            raise CadenceError(f"schema_catalog contract {contract_name} must constrain contract_name")
        schemas[contract_name] = document
        digests[contract_name] = digest_file(path)[0]
        paths[contract_name] = path
    return SchemaCatalog(
        root=root,
        schemas=schemas,
        digests=digests,
        paths=paths,
    )


def validate_public_contract(
    document: Any,
    *,
    contract_name: str,
    catalog: SchemaCatalog,
) -> None:
    schema = catalog.schemas.get(contract_name)
    path = catalog.paths.get(contract_name)
    if schema is None or path is None:
        raise CadenceError(f"public schema catalog has no validator for {contract_name}")
    try:
        live_digest = digest_file(path)[0]
    except OSError as exc:
        raise CadenceError(f"public schema catalog contract {contract_name} became unavailable") from exc
    if live_digest != catalog.digests[contract_name]:
        raise CadenceError(f"public schema catalog contract {contract_name} changed during execution")
    errors = sorted(
        Draft202012Validator(
            schema,
            format_checker=FormatChecker(),
        ).iter_errors(document),
        key=lambda error: tuple(str(item) for item in error.absolute_path),
    )
    if errors:
        first = errors[0]
        location = "/".join(str(item) for item in first.absolute_path) or "$"
        raise CadenceError(f"{contract_name} public schema validation failed at {location}: {first.message}")


def parse_stage(
    stage: str,
    raw: Any,
    *,
    config_dir: Path,
    run_root: Path,
    base_environment: Mapping[str, str],
    snapshot_id: str,
    snapshot_digest: str,
    schema_catalog: SchemaCatalog,
) -> StageSpec:
    if not isinstance(raw, Mapping):
        raise CadenceError(f"stage {stage} must be an object")
    owner_reference = public_reference(raw.get("owner_reference"), f"{stage}.owner_reference")
    raw_predicate = raw.get("predicate")
    if not isinstance(raw_predicate, Mapping):
        raise CadenceError(f"stage {stage} requires a typed predicate object")
    predicate_id = public_reference(raw_predicate.get("predicate_id"), f"{stage}.predicate.predicate_id")
    predicate_command = argv(raw_predicate.get("command"), f"{stage}.predicate.command")
    receipt_command = public_reference(
        raw_predicate.get("receipt_command"),
        f"{stage}.predicate.receipt_command",
    )
    expected_result = public_text(
        raw_predicate.get("expected_result"),
        f"{stage}.predicate.expected_result",
    )
    receipt_target = public_reference(raw.get("receipt_target"), f"{stage}.receipt_target")
    cwd = resolve_path(
        raw.get("cwd", str(config_dir)),
        base=config_dir,
        environment=base_environment,
    )
    if not cwd.is_dir():
        raise CadenceError(f"stage {stage} cwd is not a directory")
    command = argv(raw.get("command"), f"{stage}.command")
    raw_env = raw.get("env", {})
    if not isinstance(raw_env, Mapping) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in raw_env.items()
    ):
        raise CadenceError(f"stage {stage} env must be a string map")
    if any(SENSITIVE_NAME.search(key) for key in raw_env):
        raise CadenceError(f"stage {stage} env cannot carry secret-bearing names")
    if any(SENSITIVE_TEXT.search(value) for value in raw_env.values()):
        raise CadenceError(f"stage {stage} env cannot carry private paths or secret literals")
    stage_environment = dict(base_environment)
    stage_environment.update({key: expand(value, stage_environment) for key, value in raw_env.items()})
    expanded_command = tuple(expand(item, stage_environment) for item in command)
    expanded_predicate_command = tuple(expand(item, stage_environment) for item in predicate_command)
    if expanded_command == expanded_predicate_command:
        raise CadenceError(f"stage {stage} predicate command must be independent from the owner command")
    owner_revision = parse_revision(
        raw.get("owner_revision"),
        stage=stage,
        role="owner",
        cwd=cwd,
        config_dir=config_dir,
        environment=stage_environment,
        command=expanded_command,
    )
    predicate_revision = parse_revision(
        raw_predicate.get("revision"),
        stage=stage,
        role="predicate",
        cwd=cwd,
        config_dir=config_dir,
        environment=stage_environment,
        command=expanded_predicate_command,
    )
    if (
        owner_revision.kind == "file"
        and predicate_revision.kind == "file"
        and owner_revision.path == predicate_revision.path
    ):
        raise CadenceError(f"stage {stage} owner and predicate file revisions must be independent")
    predicate = PredicateSpec(
        predicate_id=predicate_id,
        command=expanded_predicate_command,
        receipt_command=receipt_command,
        expected_result=expected_result,
        revision=predicate_revision,
    )
    inputs_raw = raw.get("inputs", [])
    outputs_raw = raw.get("outputs")
    if not isinstance(inputs_raw, list) or not inputs_raw or not isinstance(outputs_raw, list) or not outputs_raw:
        raise CadenceError(f"stage {stage} requires nonempty inputs[] and outputs[]")
    inputs = tuple(
        artifact_spec(
            item,
            index=index,
            kind=f"{stage}.inputs",
            base=config_dir,
            environment=stage_environment,
            snapshot_id=snapshot_id,
            snapshot_digest=snapshot_digest,
            is_input=True,
        )
        for index, item in enumerate(inputs_raw)
    )
    outputs = tuple(
        artifact_spec(
            item,
            index=index,
            kind=f"{stage}.outputs",
            base=run_root,
            environment=stage_environment,
            snapshot_id=snapshot_id,
            snapshot_digest=snapshot_digest,
            is_input=False,
        )
        for index, item in enumerate(outputs_raw)
    )
    input_ids = [item.artifact_id for item in inputs]
    if len(input_ids) != len(set(input_ids)):
        raise CadenceError(f"stage {stage} input artifact IDs must be unique")
    output_ids = [item.artifact_id for item in outputs]
    if len(output_ids) != len(set(output_ids)):
        raise CadenceError(f"stage {stage} output artifact IDs must be unique")
    for output in outputs:
        try:
            output.path.relative_to(run_root)
        except ValueError as exc:
            raise CadenceError(f"stage {stage} output must remain under --run-root") from exc
    raw_readiness_evidence = raw.get("readiness_evidence")
    if not isinstance(raw_readiness_evidence, Mapping):
        raise CadenceError(f"stage {stage} requires a readiness_evidence object")
    readiness_artifact_id = safe_id(
        raw_readiness_evidence.get("artifact_id"),
        f"{stage}.readiness_evidence.artifact_id",
    )
    readiness_outputs = [output for output in outputs if output.artifact_id == readiness_artifact_id]
    if len(readiness_outputs) != 1:
        raise CadenceError(f"stage {stage} readiness evidence must name exactly one declared output")
    return StageSpec(
        stage=stage,
        owner_reference=owner_reference,
        owner_revision=owner_revision,
        predicate=predicate,
        receipt_target=receipt_target,
        cwd=cwd,
        command=expanded_command,
        env={key: expand(value, stage_environment) for key, value in raw_env.items()},
        inputs=inputs,
        outputs=outputs,
        readiness_evidence=readiness_outputs[0],
        schema_catalog=schema_catalog,
        profile=parse_profile(raw.get("execution_profile"), stage),
    )


def load_config(
    config_path: Path,
    *,
    snapshot_id: str,
    snapshot_at: str,
    run_root: Path,
) -> tuple[dict[str, Any], tuple[StageSpec, ...], str, str, str]:
    document = load_document(config_path)
    if not isinstance(document, Mapping):
        raise CadenceError("cadence config root must be an object")
    if document.get("contract_name") != "governance-cadence-config.v1":
        raise CadenceError("cadence config contract_name must be governance-cadence-config.v1")
    cadence_id = safe_id(document.get("cadence_id"), "cadence_id")
    owner_reference = public_reference(document.get("owner_reference"), "owner_reference")
    snapshot_digest = str(document.get("snapshot_digest") or "")
    if not SHA256.fullmatch(snapshot_digest):
        raise CadenceError("cadence config snapshot_digest must be sha256:<64 lowercase hex>")
    raw_stages = document.get("stages")
    if not isinstance(raw_stages, Mapping):
        raise CadenceError("cadence config requires a stages object")
    if set(raw_stages) != set(STAGES):
        missing = sorted(set(STAGES) - set(raw_stages))
        extra = sorted(set(raw_stages) - set(STAGES))
        raise CadenceError(f"cadence stages must be exact; missing={missing}, extra={extra}")
    config_dir = config_path.parent.resolve()
    environment = dict(os.environ)
    environment.update(
        {
            "LIMEN_GOV_SNAPSHOT_ID": snapshot_id,
            "LIMEN_GOV_SNAPSHOT_AT": snapshot_at,
            "LIMEN_GOV_RUN_ROOT": str(run_root),
            "LIMEN_GOV_CONFIG": str(config_path),
        }
    )
    schema_catalog = parse_schema_catalog(
        document.get("schema_catalog"),
        config_dir=config_dir,
        environment=environment,
    )
    stages = tuple(
        parse_stage(
            stage,
            raw_stages[stage],
            config_dir=config_dir,
            run_root=run_root,
            base_environment={**environment, "LIMEN_GOV_STAGE": stage},
            snapshot_id=snapshot_id,
            snapshot_digest=snapshot_digest,
            schema_catalog=schema_catalog,
        )
        for stage in STAGES
    )
    all_output_ids: list[str] = []
    for index, item in enumerate(stages):
        all_output_ids.extend(artifact.artifact_id for artifact in item.outputs)
        if index == 0:
            if any(artifact.input_kind != "snapshot_anchor" for artifact in item.inputs):
                raise CadenceError("stage discover inputs must be snapshot-bound external anchors")
            continue
        predecessor_outputs = {
            (
                artifact.artifact_id,
                artifact.reference,
                artifact.path,
                artifact.contract,
            )
            for artifact in stages[index - 1].outputs
        }
        predecessor_inputs = {
            (
                artifact.artifact_id,
                artifact.reference,
                artifact.path,
                artifact.contract,
            )
            for artifact in item.inputs
            if artifact.input_kind == "predecessor_output"
        }
        if predecessor_inputs != predecessor_outputs:
            raise CadenceError(
                f"stage {item.stage} predecessor inputs must exactly cover every output "
                f"of stage {stages[index - 1].stage}"
            )
        if any(artifact.input_kind not in INPUT_KINDS for artifact in item.inputs):
            raise CadenceError(f"stage {item.stage} contains an untyped extra input")
    if len(all_output_ids) != len(set(all_output_ids)):
        raise CadenceError("cadence output artifact IDs must be globally unique")
    receipt_bundle_outputs = [
        artifact for artifact in stages[-1].outputs if artifact.contract == PRE_PROOF_BUNDLE_CONTRACT
    ]
    if len(receipt_bundle_outputs) != 1 or stages[-1].readiness_evidence != receipt_bundle_outputs[0]:
        raise CadenceError(
            "stage receipt must expose exactly one governance snapshot pre-proof "
            "bundle output as its readiness evidence"
        )
    public_config = {
        "contract_name": "governance-cadence-config.v1",
        "cadence_id": cadence_id,
        "owner_reference": owner_reference,
        "snapshot_digest": snapshot_digest,
        "schema_catalog": {
            "contracts": dict(sorted(schema_catalog.digests.items())),
        },
        "stages": [
            {
                "stage": item.stage,
                "owner_reference": item.owner_reference,
                "owner_revision": item.owner_revision.value,
                "predicate": item.predicate.public(),
                "predicate_revision": item.predicate.revision.value,
                "receipt_target": item.receipt_target,
                "command_digest": digest_value(list(item.command)),
                "predicate_command_digest": digest_value(list(item.predicate.command)),
                "environment_digest": digest_value(item.env),
                "inputs": [
                    {
                        "artifact_id": artifact.artifact_id,
                        "reference": artifact.reference,
                        **({"contract": artifact.contract} if artifact.contract else {}),
                        "input_kind": artifact.input_kind,
                        **(
                            {
                                "snapshot_id": artifact.anchor_snapshot_id,
                                "snapshot_digest": artifact.anchor_snapshot_digest,
                            }
                            if artifact.input_kind == "snapshot_anchor"
                            else {}
                        ),
                    }
                    for artifact in item.inputs
                ],
                "outputs": [
                    {
                        "artifact_id": artifact.artifact_id,
                        "reference": artifact.reference,
                        **({"contract": artifact.contract} if artifact.contract else {}),
                    }
                    for artifact in item.outputs
                ],
                "readiness_evidence": {
                    "artifact_id": item.readiness_evidence.artifact_id,
                    "reference": item.readiness_evidence.reference,
                },
                "execution_profile": item.profile.public(),
            }
            for item in stages
        ],
    }
    return public_config, stages, digest_value(public_config), snapshot_digest, owner_reference


def artifact_observation(
    artifact: ArtifactSpec,
    *,
    max_bytes: int,
    required: bool = True,
) -> dict[str, Any] | None:
    if not artifact.path.is_file():
        if required:
            raise CadenceError(f"artifact {artifact.artifact_id} is missing")
        return None
    digest, size = digest_file(artifact.path)
    if size > max_bytes:
        raise CadenceError(f"artifact {artifact.artifact_id} exceeds its byte limit")
    return {
        "artifact_id": artifact.artifact_id,
        "reference": artifact.reference,
        **({"contract": artifact.contract} if artifact.contract else {}),
        "digest": digest,
        "size_bytes": size,
    }


def observe_artifacts(
    artifacts: Sequence[ArtifactSpec],
    *,
    max_each_bytes: int,
    max_total_bytes: int | None = None,
) -> list[dict[str, Any]]:
    observed = [
        artifact_observation(
            artifact,
            max_bytes=max_each_bytes,
        )
        for artifact in artifacts
    ]
    observations = [item for item in observed if item is not None]
    if max_total_bytes is not None and sum(int(item["size_bytes"]) for item in observations) > max_total_bytes:
        raise CadenceError("declared stage outputs exceed the aggregate byte limit")
    return observations


def stage_input_digest(
    spec: StageSpec,
    *,
    config_digest: str,
    snapshot_id: str,
    snapshot_digest: str,
    snapshot_at: str,
    predecessor_receipt_digest: str | None,
) -> tuple[str, list[dict[str, Any]]]:
    verify_stage_revisions(spec)
    observed = observe_artifacts(
        spec.inputs,
        max_each_bytes=spec.profile.max_artifact_bytes,
    )
    payload = {
        "stage": spec.stage,
        "snapshot_id": snapshot_id,
        "snapshot_digest": snapshot_digest,
        "snapshot_at": snapshot_at,
        "config_digest": config_digest,
        "predecessor_receipt_digest": predecessor_receipt_digest,
        "owner_revision": spec.owner_revision.value,
        "predicate_revision": spec.predicate.revision.value,
        "command_digest": digest_value(list(spec.command)),
        "predicate_command_digest": digest_value(list(spec.predicate.command)),
        "predicate": spec.predicate.public(),
        "environment_digest": digest_value(spec.env),
        "execution_profile": spec.profile.public(),
        "inputs": observed,
    }
    return digest_value(payload), observed


def receipt_path(run_root: Path, stage: str) -> Path:
    index = STAGES.index(stage) + 1
    return run_root / "receipts" / f"{index:02d}-{stage}.governance-stage-receipt.v1.json"


def metrics_path(run_root: Path, stage: str) -> Path:
    return run_root / "metrics" / f"{stage}.json"


def stage_receipts_collection_path(run_root: Path) -> Path:
    return run_root / "governance-stage-receipts.v1.json"


def read_json_object(path: Path) -> dict[str, Any]:
    document = load_document(path)
    if not isinstance(document, dict):
        raise CadenceError(f"{path} must contain an object")
    return document


def load_metrics(
    path: Path,
    *,
    profile: ExecutionProfile,
) -> dict[str, Any]:
    metrics = read_json_object(path)
    resume_token = metrics.get("resume_token")
    completed_child_ids = metrics.get("completed_child_ids")
    pending_child_ids = metrics.get("pending_child_ids")
    child_receipts = metrics.get("child_receipts")
    emitted_events = metrics.get("emitted_events")
    if resume_token is not None and (
        not isinstance(resume_token, str) or not resume_token.strip() or len(resume_token) > 512
    ):
        raise CadenceError("stage metrics resume_token must be null or a bounded string")
    for name, values in (
        ("completed_child_ids", completed_child_ids),
        ("pending_child_ids", pending_child_ids),
    ):
        if (
            not isinstance(values, list)
            or len(values) != len(set(values))
            or not all(isinstance(item, str) and item.strip() for item in values)
        ):
            raise CadenceError(f"stage metrics {name} must be a unique nonempty-string list")
    if len(completed_child_ids) + len(pending_child_ids) > profile.max_items:
        raise CadenceError("stage metrics children exceed the finite work limit")
    if set(completed_child_ids) & set(pending_child_ids):
        raise CadenceError("stage metrics completed and pending children overlap")
    if not isinstance(child_receipts, list) or not child_receipts:
        raise CadenceError("stage metrics child_receipts must be nonempty")
    statuses = {"completed", "skipped_completed", "blocked", "failed"}
    child_ids: list[str] = []
    normalized_children: list[dict[str, Any]] = []
    for index, child in enumerate(child_receipts):
        if not isinstance(child, Mapping):
            raise CadenceError(f"stage metrics child_receipts[{index}] must be an object")
        child_id = str(child.get("child_id") or "")
        status = str(child.get("status") or "")
        input_digest = str(child.get("input_digest") or "")
        output_digest = str(child.get("output_digest") or "")
        if (
            not child_id
            or status not in statuses
            or not SHA256.fullmatch(input_digest)
            or not SHA256.fullmatch(output_digest)
        ):
            raise CadenceError(f"stage metrics child_receipts[{index}] is invalid")
        normalized = {
            "child_id": child_id,
            "status": status,
            "input_digest": input_digest,
            "output_digest": output_digest,
        }
        prior = child.get("prior_receipt_digest")
        if status == "skipped_completed":
            if not isinstance(prior, str) or not SHA256.fullmatch(prior):
                raise CadenceError("skipped child receipt requires prior_receipt_digest")
            normalized["prior_receipt_digest"] = prior
        child_ids.append(child_id)
        normalized_children.append(normalized)
    if len(child_ids) != len(set(child_ids)):
        raise CadenceError("stage metrics child receipt IDs must be unique")
    if set(child_ids) != set(completed_child_ids) | set(pending_child_ids):
        raise CadenceError("stage metrics child receipts must cover the cursor exactly")
    if isinstance(emitted_events, bool) or not isinstance(emitted_events, int) or emitted_events < 0:
        raise CadenceError("stage metrics emitted_events must be a nonnegative integer")
    counts = {
        "attempted": sum(child["status"] != "skipped_completed" for child in normalized_children),
        "completed": sum(child["status"] == "completed" for child in normalized_children),
        "skipped_completed": sum(child["status"] == "skipped_completed" for child in normalized_children),
        "failed": sum(child["status"] == "failed" for child in normalized_children),
        "blocked": sum(child["status"] == "blocked" for child in normalized_children),
    }
    if pending_child_ids or counts["failed"] or counts["blocked"]:
        raise CadenceError("completed stage metrics contain pending, failed, or blocked children")
    if resume_token is not None:
        raise CadenceError("completed stage metrics must clear the resume token")
    return {
        "cursor": {
            "resume_token": resume_token,
            "completed_child_ids": completed_child_ids,
            "pending_child_ids": pending_child_ids,
        },
        "child_receipts": normalized_children,
        "counts": counts,
        "emitted_events": emitted_events,
    }


def normalize_readiness(value: Any, *, owner: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise CadenceError(f"{owner} readiness evidence must be an object")
    exact_all = value.get("exact_all")
    ready = value.get("ready")
    status = value.get("status")
    if not isinstance(exact_all, bool) or not isinstance(ready, bool):
        raise CadenceError(f"{owner} readiness exact_all and ready must be booleans")
    if status not in READINESS_STATUSES:
        raise CadenceError(f"{owner} readiness status is invalid")
    normalized: dict[str, Any] = {"exact_all": exact_all}
    for field in READINESS_DEBT_FIELDS:
        debt = value.get(field)
        if (
            not isinstance(debt, list)
            or len(debt) != len(set(debt))
            or not all(
                isinstance(item, str) and item.strip() and len(item) <= 512 and not SENSITIVE_TEXT.search(item)
                for item in debt
            )
        ):
            raise CadenceError(f"{owner} readiness {field} must be a unique public-safe debt list")
        normalized[field] = sorted(debt)
    computed_ready = exact_all and not any(normalized[field] for field in READINESS_DEBT_FIELDS)
    if ready is not computed_ready:
        raise CadenceError(f"{owner} readiness ready must equal exact_all with zero declared debt")
    if (ready and status != "ready") or (not ready and status == "ready"):
        raise CadenceError(f"{owner} readiness status contradicts ready")
    normalized.update({"ready": ready, "status": status})
    return normalized


def stage_owner_readiness(
    spec: StageSpec,
    *,
    snapshot_id: str,
    snapshot_digest: str,
    snapshot_at: str,
) -> dict[str, Any]:
    document = read_json_object(spec.readiness_evidence.path)
    readiness = normalize_readiness(
        document.get("readiness"),
        owner=f"stage {spec.stage}",
    )
    if spec.stage == "receipt":
        load_pre_proof_bundle(
            spec,
            snapshot_id=snapshot_id,
            snapshot_digest=snapshot_digest,
            snapshot_at=snapshot_at,
        )
    return readiness


def aggregate_owner_readiness(
    stages: Sequence[StageSpec],
    *,
    snapshot_id: str,
    snapshot_digest: str,
    snapshot_at: str,
) -> dict[str, Any]:
    owner_evidence = [
        stage_owner_readiness(
            spec,
            snapshot_id=snapshot_id,
            snapshot_digest=snapshot_digest,
            snapshot_at=snapshot_at,
        )
        for spec in stages
    ]
    aggregate: dict[str, Any] = {
        "exact_all": all(item["exact_all"] is True for item in owner_evidence),
    }
    for field in READINESS_DEBT_FIELDS:
        aggregate[field] = sorted({debt for evidence in owner_evidence for debt in evidence[field]})
    aggregate["ready"] = bool(
        aggregate["exact_all"]
        and not any(aggregate[field] for field in READINESS_DEBT_FIELDS)
        and all(item["ready"] is True for item in owner_evidence)
    )
    aggregate["status"] = "ready" if aggregate["ready"] else "blocked"
    return aggregate


def validate_existing_receipt(
    path: Path,
    spec: StageSpec,
    *,
    run_id: str,
    snapshot_id: str,
    snapshot_digest: str,
    snapshot_at: str,
    predecessor_receipt_digest: str | None,
    input_digest: str,
) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        receipt = read_json_object(path)
        validate_public_contract(
            receipt,
            contract_name="governance-stage-receipt.v1",
            catalog=spec.schema_catalog,
        )
        payload = {key: value for key, value in receipt.items() if key != "receipt_digest"}
        if (
            receipt.get("contract_name") != "governance-stage-receipt.v1"
            or receipt.get("run_id") != run_id
            or receipt.get("stage") != spec.stage
            or receipt.get("snapshot_id") != snapshot_id
            or receipt.get("snapshot_digest") != snapshot_digest
            or receipt.get("started_at") != snapshot_at
            or receipt.get("completed_at") != snapshot_at
            or receipt.get("predecessor_receipt_digest") != predecessor_receipt_digest
            or receipt.get("input_digest") != input_digest
            or receipt.get("owner_reference") != spec.owner_reference
            or receipt.get("predicate") != spec.predicate.public()
            or receipt.get("receipt_target") != spec.receipt_target
            or receipt.get("execution_limits") != spec.profile.receipt_limits()
            or receipt.get("status") != "completed"
            or receipt.get("receipt_digest") != digest_value(payload)
        ):
            return None
        outputs = observe_artifacts(
            spec.outputs,
            max_each_bytes=spec.profile.max_artifact_bytes,
            max_total_bytes=spec.profile.max_artifact_bytes,
        )
        if receipt.get("outputs") != outputs or receipt.get("output_digest") != digest_value(outputs):
            return None
        metrics = load_metrics(metrics_path(path.parents[1], spec.stage), profile=spec.profile)
        if receipt.get("cursor") != metrics["cursor"]:
            return None
        if receipt.get("child_receipts") != metrics["child_receipts"]:
            return None
        if receipt.get("counts") != metrics["counts"]:
            return None
        return receipt
    except (CadenceError, OSError, ValueError):
        return None


def write_if_changed(path: Path, content: str) -> bool:
    try:
        if path.read_text(encoding="utf-8") == content:
            return False
    except OSError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)
    return True


def bounded_command(
    command: Sequence[str],
    *,
    spec: StageSpec,
    environment: Mapping[str, str],
    log_path: Path,
) -> tuple[int, str]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("wb") as log:
        process = subprocess.Popen(
            list(command),
            cwd=spec.cwd,
            env=dict(environment),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        if process.stdout is None:
            raise CadenceError(f"stage {spec.stage} command log pipe is unavailable")
        log_limit_exceeded = threading.Event()
        reader_failures: list[BaseException] = []

        def drain_output() -> None:
            try:
                remaining = spec.profile.max_log_bytes
                while chunk := process.stdout.read(64 * 1024):
                    accepted_size = min(len(chunk), remaining)
                    if accepted_size:
                        accepted = chunk[:accepted_size]
                        log.write(accepted)
                        remaining -= accepted_size
                    if accepted_size < len(chunk):
                        log_limit_exceeded.set()
            except BaseException as exc:  # pragma: no cover - OS pipe failure
                reader_failures.append(exc)

        reader = threading.Thread(
            target=drain_output,
            name=f"governance-cadence-{spec.stage}-log",
            daemon=True,
        )
        reader.start()
        deadline = time.monotonic() + spec.profile.timeout_seconds
        diagnostic = "nonzero-exit"
        return_code: int | None = None
        while return_code is None:
            return_code = process.poll()
            if return_code is not None:
                break
            if log_limit_exceeded.is_set():
                diagnostic = "log-byte-limit-exceeded"
                return_code = 125
                break
            if time.monotonic() >= deadline:
                diagnostic = "timeout"
                return_code = 124
                break
            time.sleep(0.05)
        if return_code in {124, 125}:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
        else:
            return_code = process.wait()
        reader.join(timeout=2)
        if reader.is_alive():
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            reader.join(timeout=2)
            return 125, "log-drain-timeout"
        if reader_failures:
            return 125, "log-drain-failed"
        if log_limit_exceeded.is_set():
            return 125, "log-byte-limit-exceeded"
    return return_code, "ok" if return_code == 0 else diagnostic


def execution_environment(
    spec: StageSpec,
    *,
    attempt: int,
    traversal: int,
    run_root: Path,
    snapshot_id: str,
    snapshot_at: str,
    predecessor_receipt_digest: str | None,
    metric_path: Path,
    prior_stage_receipt: Path | None,
) -> dict[str, str]:
    environment = dict(RUNTIME_ENVIRONMENT)
    environment.update(spec.env)
    environment.update(
        {
            "LIMEN_GOV_SNAPSHOT_ID": snapshot_id,
            "LIMEN_GOV_SNAPSHOT_AT": snapshot_at,
            "LIMEN_GOV_RUN_ROOT": str(run_root),
            "LIMEN_GOV_STAGE": spec.stage,
            "LIMEN_GOV_STAGE_ATTEMPT": str(attempt),
            "LIMEN_GOV_TRAVERSAL": str(traversal),
            "LIMEN_GOV_PROOF_MODE": "1" if traversal >= 2 else "0",
            "LIMEN_GOV_STAGE_METRICS_OUT": str(metric_path),
            "LIMEN_GOV_STAGE_RECEIPTS": str(stage_receipts_collection_path(run_root)),
            "LIMEN_GOV_PREDECESSOR_RECEIPT_DIGEST": predecessor_receipt_digest or "",
            "LIMEN_GOV_PRIOR_STAGE_RECEIPT": str(prior_stage_receipt or ""),
            "LIMEN_GOV_MAX_ITEMS": str(spec.profile.max_items),
        }
    )
    return environment


def execute_once(
    spec: StageSpec,
    *,
    attempt: int,
    traversal: int,
    run_root: Path,
    snapshot_id: str,
    snapshot_at: str,
    predecessor_receipt_digest: str | None,
    metric_path: Path,
    prior_stage_receipt: Path | None,
) -> tuple[int, str, Mapping[str, str]]:
    metric_path.parent.mkdir(parents=True, exist_ok=True)
    metric_path.unlink(missing_ok=True)
    environment = execution_environment(
        spec,
        attempt=attempt,
        traversal=traversal,
        run_root=run_root,
        snapshot_id=snapshot_id,
        snapshot_at=snapshot_at,
        predecessor_receipt_digest=predecessor_receipt_digest,
        metric_path=metric_path,
        prior_stage_receipt=prior_stage_receipt,
    )
    return_code, diagnostic = bounded_command(
        spec.command,
        spec=spec,
        environment=environment,
        log_path=run_root / "logs" / f"traversal-{traversal}" / f"{spec.stage}.attempt-{attempt}.log",
    )
    return return_code, diagnostic, environment


def execute_predicate(
    spec: StageSpec,
    *,
    attempt: int,
    traversal: int,
    run_root: Path,
    environment: Mapping[str, str],
) -> None:
    predicate_environment = {
        **environment,
        "LIMEN_GOV_PREDICATE_MODE": "1",
    }
    return_code, diagnostic = bounded_command(
        spec.predicate.command,
        spec=spec,
        environment=predicate_environment,
        log_path=run_root / "logs" / f"traversal-{traversal}" / f"{spec.stage}.predicate-{attempt}.log",
    )
    if return_code != 0:
        raise CadenceError(f"stage {spec.stage} predicate failed: {diagnostic}")


def child_receipt_digest(child: Mapping[str, Any]) -> str:
    return digest_value(
        {
            "child_id": child["child_id"],
            "status": child["status"],
            "input_digest": child["input_digest"],
            "output_digest": child["output_digest"],
        }
    )


def validate_proof_metrics(
    metrics: Mapping[str, Any],
    prior_receipt: Mapping[str, Any],
) -> None:
    prior_children = {
        str(child["child_id"]): child for child in prior_receipt.get("child_receipts", []) if isinstance(child, Mapping)
    }
    proof_children = {
        str(child["child_id"]): child for child in metrics.get("child_receipts", []) if isinstance(child, Mapping)
    }
    if set(proof_children) != set(prior_children):
        raise CadenceError("proof traversal child set differs from the completed owner cursor")
    for child_id, proof in proof_children.items():
        prior = prior_children[child_id]
        if (
            proof.get("status") != "skipped_completed"
            or proof.get("input_digest") != prior.get("input_digest")
            or proof.get("output_digest") != prior.get("output_digest")
            or proof.get("prior_receipt_digest") != child_receipt_digest(prior)
        ):
            raise CadenceError("proof traversal did not bind an exact completed child receipt")
    if metrics.get("emitted_events") != 0:
        raise CadenceError("proof traversal emitted new events")
    counts = metrics.get("counts", {})
    if (
        counts.get("attempted") != 0
        or counts.get("completed") != 0
        or counts.get("skipped_completed") != len(prior_children)
    ):
        raise CadenceError("proof traversal replayed completed owner work")


def execute_stage(
    spec: StageSpec,
    *,
    traversal: int,
    run_root: Path,
    run_id: str,
    snapshot_id: str,
    snapshot_digest: str,
    snapshot_at: str,
    config_digest: str,
    predecessor_receipt_digest: str | None,
) -> StageResult:
    input_digest, inputs = stage_input_digest(
        spec,
        config_digest=config_digest,
        snapshot_id=snapshot_id,
        snapshot_digest=snapshot_digest,
        snapshot_at=snapshot_at,
        predecessor_receipt_digest=predecessor_receipt_digest,
    )
    target = receipt_path(run_root, spec.stage)
    existing = validate_existing_receipt(
        target,
        spec,
        run_id=run_id,
        snapshot_id=snapshot_id,
        snapshot_digest=snapshot_digest,
        snapshot_at=snapshot_at,
        predecessor_receipt_digest=predecessor_receipt_digest,
        input_digest=input_digest,
    )
    if existing is not None and traversal == 1:
        return StageResult(
            receipt=existing,
            attempts=0,
            invoked=False,
            executed_children=0,
            changed_receipt=False,
            emitted_events=0,
        )
    if traversal >= 2 and existing is None:
        raise CadenceError(f"stage {spec.stage} has no valid completed receipt for proof traversal")

    if traversal >= 2:
        prior_outputs = observe_artifacts(
            spec.outputs,
            max_each_bytes=spec.profile.max_artifact_bytes,
            max_total_bytes=spec.profile.max_artifact_bytes,
        )
        proof_metrics_path = run_root / "metrics" / "proof" / f"{spec.stage}.json"
        attempt = 1
        return_code, diagnostic, environment = execute_once(
            spec,
            attempt=attempt,
            traversal=traversal,
            run_root=run_root,
            snapshot_id=snapshot_id,
            snapshot_at=snapshot_at,
            predecessor_receipt_digest=predecessor_receipt_digest,
            metric_path=proof_metrics_path,
            prior_stage_receipt=target,
        )
        outputs_after_owner = observe_artifacts(
            spec.outputs,
            max_each_bytes=spec.profile.max_artifact_bytes,
            max_total_bytes=spec.profile.max_artifact_bytes,
        )
        if outputs_after_owner != prior_outputs or outputs_after_owner != existing.get("outputs"):
            raise CadenceError(f"stage {spec.stage} proof attempt changed governed owner output bytes")
        if return_code != 0:
            raise CadenceError(f"stage {spec.stage} proof failed on its first attempt: {diagnostic}")
        metrics = load_metrics(proof_metrics_path, profile=spec.profile)
        validate_proof_metrics(metrics, existing)
        verify_stage_revisions(spec)
        predicate_error: CadenceError | None = None
        try:
            execute_predicate(
                spec,
                attempt=attempt,
                traversal=traversal,
                run_root=run_root,
                environment=environment,
            )
        except CadenceError as exc:
            predicate_error = exc
        outputs_after_predicate = observe_artifacts(
            spec.outputs,
            max_each_bytes=spec.profile.max_artifact_bytes,
            max_total_bytes=spec.profile.max_artifact_bytes,
        )
        if outputs_after_predicate != prior_outputs:
            raise CadenceError(f"stage {spec.stage} proof predicate changed governed owner output bytes")
        if predicate_error is not None:
            raise predicate_error
        verify_stage_revisions(spec)
        stage_owner_readiness(
            spec,
            snapshot_id=snapshot_id,
            snapshot_digest=snapshot_digest,
            snapshot_at=snapshot_at,
        )
        return StageResult(
            receipt=existing,
            attempts=1,
            invoked=True,
            executed_children=0,
            changed_receipt=False,
            emitted_events=0,
        )

    last_diagnostic = "not-run"
    attempts_used = 0
    for attempt in range(1, spec.profile.max_attempts + 1):
        attempts_used = attempt
        return_code, diagnostic, environment = execute_once(
            spec,
            attempt=attempt,
            traversal=traversal,
            run_root=run_root,
            snapshot_id=snapshot_id,
            snapshot_at=snapshot_at,
            predecessor_receipt_digest=predecessor_receipt_digest,
            metric_path=metrics_path(run_root, spec.stage),
            prior_stage_receipt=None,
        )
        last_diagnostic = diagnostic
        if return_code != 0:
            continue
        try:
            metrics = load_metrics(metrics_path(run_root, spec.stage), profile=spec.profile)
            outputs = observe_artifacts(
                spec.outputs,
                max_each_bytes=spec.profile.max_artifact_bytes,
                max_total_bytes=spec.profile.max_artifact_bytes,
            )
            execute_predicate(
                spec,
                attempt=attempt,
                traversal=traversal,
                run_root=run_root,
                environment=environment,
            )
            verify_stage_revisions(spec)
            stage_owner_readiness(
                spec,
                snapshot_id=snapshot_id,
                snapshot_digest=snapshot_digest,
                snapshot_at=snapshot_at,
            )
        except CadenceError as exc:
            last_diagnostic = str(exc)
            continue
        payload: dict[str, Any] = {
            "contract_name": "governance-stage-receipt.v1",
            "contract_version": 1,
            "stage_receipt_id": f"{run_id}:{spec.stage}",
            "run_id": run_id,
            "snapshot_id": snapshot_id,
            "snapshot_digest": snapshot_digest,
            "stage": spec.stage,
            "owner_reference": spec.owner_reference,
            "predicate": spec.predicate.public(),
            "receipt_target": spec.receipt_target,
            "status": "completed",
            "started_at": snapshot_at,
            "completed_at": snapshot_at,
            "predecessor_receipt_digest": predecessor_receipt_digest,
            "inputs": inputs,
            "outputs": outputs,
            "input_digest": input_digest,
            "output_digest": digest_value(outputs),
            "execution_limits": spec.profile.receipt_limits(),
            "cursor": metrics["cursor"],
            "child_receipts": metrics["child_receipts"],
            "counts": metrics["counts"],
            "digest_algorithm": "sha256-rfc8785-excluding-self-digest-v1",
        }
        receipt = {**payload, "receipt_digest": digest_value(payload)}
        validate_public_contract(
            receipt,
            contract_name="governance-stage-receipt.v1",
            catalog=spec.schema_catalog,
        )
        changed = write_if_changed(target, json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        return StageResult(
            receipt=receipt,
            attempts=attempts_used,
            invoked=True,
            executed_children=int(metrics["counts"]["attempted"]),
            changed_receipt=changed,
            emitted_events=int(metrics["emitted_events"]),
        )
    raise CadenceError(f"stage {spec.stage} failed after {attempts_used} finite attempt(s): {last_diagnostic}")


def cadence_readiness(
    *,
    run_number: int,
    fixed_point_proven: bool,
    owner_readiness: Mapping[str, Any],
) -> dict[str, Any]:
    readiness = {
        "exact_all": bool(owner_readiness["exact_all"]),
        **{field: list(owner_readiness[field]) for field in READINESS_DEBT_FIELDS},
    }
    if run_number == 1:
        readiness["exact_all"] = False
        readiness["missing_requirements"] = sorted(
            {
                *readiness["missing_requirements"],
                "cadence:run-two-fixed-point-proof",
            }
        )
        readiness.update(
            {
                "ready": False,
                "status": "incomplete",
            }
        )
        return readiness
    if not fixed_point_proven:
        readiness["incomplete_predicates"] = sorted(
            {
                *readiness["incomplete_predicates"],
                "predicate:cadence-fixed-point",
            }
        )
    ready = bool(
        fixed_point_proven
        and readiness["exact_all"]
        and not any(readiness[field] for field in READINESS_DEBT_FIELDS)
        and owner_readiness["ready"] is True
    )
    readiness.update(
        {
            "ready": ready,
            "status": "ready" if ready else "blocked",
        }
    )
    return readiness


def aggregate_receipt(
    *,
    cadence_id: str,
    owner_reference: str,
    run_number: int,
    snapshot_id: str,
    snapshot_digest: str,
    snapshot_at: str,
    config_digest: str,
    stage_receipts: Sequence[Mapping[str, Any]],
    previous_cadence_receipt_digest: str | None,
    previous_output_digest: str | None,
    new_event_count: int,
    changed_byte_count: int,
    replayed_completed_children: int,
    owner_readiness: Mapping[str, Any],
) -> dict[str, Any]:
    ordered = [
        {
            "stage": stage,
            "stage_receipt_id": receipt["stage_receipt_id"],
            "reference": receipt["receipt_target"],
            "status": receipt["status"],
            "receipt_digest": receipt["receipt_digest"],
            "predecessor_receipt_digest": receipt["predecessor_receipt_digest"],
        }
        for stage, receipt in zip(STAGES, stage_receipts, strict=True)
    ]
    output_digest = digest_value([receipt["output_digest"] for receipt in stage_receipts])
    output_digest_matches_previous = previous_output_digest == output_digest
    fixed_point_proven = (
        run_number == 2
        and previous_cadence_receipt_digest is not None
        and new_event_count == 0
        and changed_byte_count == 0
        and replayed_completed_children == 0
        and output_digest_matches_previous
    )
    readiness = cadence_readiness(
        run_number=run_number,
        fixed_point_proven=fixed_point_proven,
        owner_readiness=owner_readiness,
    )
    payload: dict[str, Any] = {
        "contract_name": "governance-cadence-receipt.v1",
        "contract_version": 1,
        "cadence_receipt_id": f"{cadence_id}:{snapshot_id}:run-{run_number}",
        "run_id": f"{cadence_id}:{snapshot_id}:run-{run_number}",
        "run_number": run_number,
        "snapshot_id": snapshot_id,
        "snapshot_digest": snapshot_digest,
        "owner_reference": owner_reference,
        "started_at": snapshot_at,
        "completed_at": snapshot_at,
        "input_digest": digest_value(
            {
                "snapshot_id": snapshot_id,
                "snapshot_digest": snapshot_digest,
                "config_digest": config_digest,
            }
        ),
        "output_digest": output_digest,
        "previous_cadence_receipt_digest": previous_cadence_receipt_digest,
        "stage_receipts": ordered,
        "fixed_point": {
            "status": ("proven" if fixed_point_proven else "not_applicable" if run_number == 1 else "changed"),
            "previous_output_digest": previous_output_digest,
            "new_event_count": new_event_count,
            "changed_byte_count": changed_byte_count,
            "replayed_completed_children": replayed_completed_children,
            "output_digest_matches_previous": output_digest_matches_previous,
        },
        "readiness": readiness,
        "digest_algorithm": "sha256-rfc8785-excluding-self-digest-v1",
    }
    return {**payload, "receipt_digest": digest_value(payload)}


def cadence_receipt_path(run_root: Path, run_number: int) -> Path:
    return run_root / "receipts" / f"governance-cadence-receipt.run-{run_number}.v1.json"


def validate_cadence_receipt(
    path: Path,
    *,
    expected_run_number: int,
    snapshot_id: str,
    snapshot_digest: str,
    stage_receipts: Sequence[Mapping[str, Any]],
    owner_readiness: Mapping[str, Any],
) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        receipt = read_json_object(path)
        payload = {key: value for key, value in receipt.items() if key != "receipt_digest"}
        expected_output = digest_value([item["output_digest"] for item in stage_receipts])
        fixed_point = receipt.get("fixed_point")
        if (
            receipt.get("contract_name") != "governance-cadence-receipt.v1"
            or receipt.get("run_number") != expected_run_number
            or receipt.get("snapshot_id") != snapshot_id
            or receipt.get("snapshot_digest") != snapshot_digest
            or receipt.get("output_digest") != expected_output
            or not isinstance(fixed_point, Mapping)
            or fixed_point.get("previous_output_digest") != (None if expected_run_number == 1 else expected_output)
            or receipt.get("readiness")
            != cadence_readiness(
                run_number=expected_run_number,
                fixed_point_proven=(fixed_point.get("status") == "proven"),
                owner_readiness=owner_readiness,
            )
            or receipt.get("receipt_digest") != digest_value(payload)
        ):
            return None
        expected_stage_digests = [item["receipt_digest"] for item in stage_receipts]
        observed_stage_digests = [
            item.get("receipt_digest") for item in receipt.get("stage_receipts", []) if isinstance(item, Mapping)
        ]
        if observed_stage_digests != expected_stage_digests:
            return None
        return receipt
    except (CadenceError, OSError, ValueError):
        return None


def traverse_stages(
    stages: Sequence[StageSpec],
    *,
    traversal: int,
    run_root: Path,
    stage_run_id: str,
    snapshot_id: str,
    snapshot_digest: str,
    snapshot_at: str,
    config_digest: str,
) -> tuple[list[dict[str, Any]], RunStats, int]:
    receipts: list[dict[str, Any]] = []
    invoked: list[str] = []
    executed: list[str] = []
    skipped: list[str] = []
    attempts = 0
    new_events = 0
    changed_receipts = 0
    replayed_completed_children = 0
    predecessor: str | None = None
    for spec in stages:
        result = execute_stage(
            spec,
            traversal=traversal,
            run_root=run_root,
            run_id=stage_run_id,
            snapshot_id=snapshot_id,
            snapshot_digest=snapshot_digest,
            snapshot_at=snapshot_at,
            config_digest=config_digest,
            predecessor_receipt_digest=predecessor,
        )
        receipt = result.receipt
        receipts.append(receipt)
        predecessor = str(receipt["receipt_digest"])
        attempts += result.attempts
        if result.invoked:
            invoked.append(spec.stage)
        if result.executed_children:
            executed.append(spec.stage)
        else:
            skipped.append(spec.stage)
        new_events += result.emitted_events
        replayed_completed_children += result.executed_children
        changed_receipts += int(result.changed_receipt)

    governed_changed_bytes = sum(
        int(output["size_bytes"])
        for receipt in receipts
        for output in receipt["outputs"]
        if receipt["stage"] in executed
    )
    return (
        receipts,
        RunStats(
            invoked_stages=tuple(invoked),
            executed_stages=tuple(executed),
            skipped_stages=tuple(skipped),
            attempts=attempts,
            new_events=new_events,
            changed_receipts=changed_receipts,
            replayed_completed_children=replayed_completed_children,
        ),
        governed_changed_bytes,
    )


def _run_cadence_unprotected(
    *,
    snapshot_id: str,
    snapshot_at: str,
    config_path: Path,
    run_root: Path,
) -> tuple[dict[str, Any], CadenceStats]:
    snapshot_id = safe_id(snapshot_id, "snapshot_id")
    snapshot_at = parse_snapshot_at(snapshot_at)
    config_path = config_path.expanduser().resolve()
    run_root = run_root.expanduser().resolve()
    run_root.mkdir(parents=True, exist_ok=True)
    public_config, stages, config_digest, snapshot_digest, owner_reference = load_config(
        config_path,
        snapshot_id=snapshot_id,
        snapshot_at=snapshot_at,
        run_root=run_root,
    )
    cadence_id = str(public_config["cadence_id"])
    stage_run_id = f"{cadence_id}:{snapshot_id}:stage-chain"
    aggregate_receipts_written = 0

    run_one_receipts, run_one_stats, run_one_changed_bytes = traverse_stages(
        stages,
        traversal=1,
        run_root=run_root,
        stage_run_id=stage_run_id,
        snapshot_id=snapshot_id,
        snapshot_digest=snapshot_digest,
        snapshot_at=snapshot_at,
        config_digest=config_digest,
    )
    aggregate_receipts_written += int(
        write_if_changed(
            stage_receipts_collection_path(run_root),
            json.dumps(run_one_receipts, indent=2, sort_keys=True) + "\n",
        )
    )
    owner_readiness = aggregate_owner_readiness(
        stages,
        snapshot_id=snapshot_id,
        snapshot_digest=snapshot_digest,
        snapshot_at=snapshot_at,
    )
    run_one_path = cadence_receipt_path(run_root, 1)
    run_one = validate_cadence_receipt(
        run_one_path,
        expected_run_number=1,
        snapshot_id=snapshot_id,
        snapshot_digest=snapshot_digest,
        stage_receipts=run_one_receipts,
        owner_readiness=owner_readiness,
    )
    if run_one is None:
        run_one = aggregate_receipt(
            cadence_id=cadence_id,
            owner_reference=owner_reference,
            run_number=1,
            snapshot_id=snapshot_id,
            snapshot_digest=snapshot_digest,
            snapshot_at=snapshot_at,
            config_digest=config_digest,
            stage_receipts=run_one_receipts,
            previous_cadence_receipt_digest=None,
            previous_output_digest=None,
            new_event_count=run_one_stats.new_events,
            changed_byte_count=run_one_changed_bytes,
            replayed_completed_children=run_one_stats.replayed_completed_children,
            owner_readiness=owner_readiness,
        )
        aggregate_receipts_written += int(
            write_if_changed(run_one_path, json.dumps(run_one, indent=2, sort_keys=True) + "\n")
        )

    # The proof traversal happens immediately and revalidates the exact stage
    # chain. Any owner execution, emitted event, changed stage receipt, replayed
    # child, or changed governed output makes run two non-fixed.
    run_two_receipts, run_two_stats, run_two_changed_bytes = traverse_stages(
        stages,
        traversal=2,
        run_root=run_root,
        stage_run_id=stage_run_id,
        snapshot_id=snapshot_id,
        snapshot_digest=snapshot_digest,
        snapshot_at=snapshot_at,
        config_digest=config_digest,
    )
    if run_two_receipts != run_one_receipts:
        raise CadenceError("proof traversal changed the full stage receipt collection")
    owner_readiness = aggregate_owner_readiness(
        stages,
        snapshot_id=snapshot_id,
        snapshot_digest=snapshot_digest,
        snapshot_at=snapshot_at,
    )
    run_two = aggregate_receipt(
        cadence_id=cadence_id,
        owner_reference=owner_reference,
        run_number=2,
        snapshot_id=snapshot_id,
        snapshot_digest=snapshot_digest,
        snapshot_at=snapshot_at,
        config_digest=config_digest,
        stage_receipts=run_two_receipts,
        previous_cadence_receipt_digest=str(run_one["receipt_digest"]),
        previous_output_digest=str(run_one["output_digest"]),
        new_event_count=run_two_stats.new_events,
        changed_byte_count=run_two_changed_bytes,
        replayed_completed_children=run_two_stats.replayed_completed_children,
        owner_readiness=owner_readiness,
    )
    run_two_path = cadence_receipt_path(run_root, 2)
    aggregate_receipts_written += int(
        write_if_changed(run_two_path, json.dumps(run_two, indent=2, sort_keys=True) + "\n")
    )
    cadence_receipts = [run_one, run_two]
    aggregate_path = run_root / "governance-cadence-receipts.v1.json"
    if write_if_changed(
        aggregate_path,
        json.dumps(cadence_receipts, indent=2, sort_keys=True) + "\n",
    ):
        aggregate_receipts_written += 1
    return run_two, CadenceStats(
        run_one=run_one_stats,
        run_two=run_two_stats,
        aggregate_receipts_written=aggregate_receipts_written,
    )


def stage_chain_is_complete(
    stages: Sequence[StageSpec],
    *,
    run_root: Path,
    stage_run_id: str,
    snapshot_id: str,
    snapshot_digest: str,
    snapshot_at: str,
    config_digest: str,
) -> bool:
    predecessor: str | None = None
    try:
        for spec in stages:
            input_digest, _inputs = stage_input_digest(
                spec,
                config_digest=config_digest,
                snapshot_id=snapshot_id,
                snapshot_digest=snapshot_digest,
                snapshot_at=snapshot_at,
                predecessor_receipt_digest=predecessor,
            )
            receipt = validate_existing_receipt(
                receipt_path(run_root, spec.stage),
                spec,
                run_id=stage_run_id,
                snapshot_id=snapshot_id,
                snapshot_digest=snapshot_digest,
                snapshot_at=snapshot_at,
                predecessor_receipt_digest=predecessor,
                input_digest=input_digest,
            )
            if receipt is None:
                return False
            predecessor = str(receipt["receipt_digest"])
    except CadenceError:
        return False
    return True


def cadence_marker(
    *,
    contract_name: str,
    snapshot_id: str,
    snapshot_digest: str,
    config_digest: str,
) -> str:
    return (
        json.dumps(
            {
                "contract_name": contract_name,
                "snapshot_id": snapshot_id,
                "snapshot_digest": snapshot_digest,
                "config_digest": config_digest,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def invalidate_cadence(
    *,
    run_root: Path,
    snapshot_id: str,
    snapshot_digest: str,
    config_digest: str,
) -> None:
    content = cadence_marker(
        contract_name="governance-cadence-invalidated.v1",
        snapshot_id=snapshot_id,
        snapshot_digest=snapshot_digest,
        config_digest=config_digest,
    )
    write_if_changed(run_root / "governance-cadence-invalidated.v1.json", content)
    write_if_changed(run_root / "governance-cadence-receipts.v1.json", content)
    (run_root / "post-proof-idempotence.v1.json").unlink(missing_ok=True)
    (run_root / FINAL_BUNDLE_FILENAME).unlink(missing_ok=True)


def run_cadence(
    *,
    snapshot_id: str,
    snapshot_at: str,
    config_path: Path,
    run_root: Path,
) -> tuple[dict[str, Any], CadenceStats]:
    snapshot_id = safe_id(snapshot_id, "snapshot_id")
    snapshot_at = parse_snapshot_at(snapshot_at)
    config_path = config_path.expanduser().resolve()
    run_root = run_root.expanduser().resolve()
    run_root.mkdir(parents=True, exist_ok=True)
    active_path = run_root / "governance-cadence-active.v1.json"
    invalidated_path = run_root / "governance-cadence-invalidated.v1.json"
    try:
        config_source_digest = digest_file(config_path)[0]
    except OSError:
        config_source_digest = sha256_bytes(str(config_path).encode("utf-8"))
    write_if_changed(
        active_path,
        cadence_marker(
            contract_name="governance-cadence-active.v1",
            snapshot_id=snapshot_id,
            snapshot_digest="unresolved",
            config_digest=config_source_digest,
        ),
    )
    try:
        public_config, stages, config_digest, snapshot_digest, _owner_reference = load_config(
            config_path,
            snapshot_id=snapshot_id,
            snapshot_at=snapshot_at,
            run_root=run_root,
        )
    except Exception:
        invalidate_cadence(
            run_root=run_root,
            snapshot_id=snapshot_id,
            snapshot_digest="unresolved",
            config_digest=config_source_digest,
        )
        active_path.unlink(missing_ok=True)
        raise
    write_if_changed(
        active_path,
        cadence_marker(
            contract_name="governance-cadence-active.v1",
            snapshot_id=snapshot_id,
            snapshot_digest=snapshot_digest,
            config_digest=config_digest,
        ),
    )
    cadence_id = str(public_config["cadence_id"])
    already_complete = stage_chain_is_complete(
        stages,
        run_root=run_root,
        stage_run_id=f"{cadence_id}:{snapshot_id}:stage-chain",
        snapshot_id=snapshot_id,
        snapshot_digest=snapshot_digest,
        snapshot_at=snapshot_at,
        config_digest=config_digest,
    )
    if not already_complete:
        invalidate_cadence(
            run_root=run_root,
            snapshot_id=snapshot_id,
            snapshot_digest=snapshot_digest,
            config_digest=config_digest,
        )
    try:
        receipt, stats = _run_cadence_unprotected(
            snapshot_id=snapshot_id,
            snapshot_at=snapshot_at,
            config_path=config_path,
            run_root=run_root,
        )
    except Exception:
        invalidate_cadence(
            run_root=run_root,
            snapshot_id=snapshot_id,
            snapshot_digest=snapshot_digest,
            config_digest=config_digest,
        )
        active_path.unlink(missing_ok=True)
        raise
    if stats.aggregate_receipts_written or not already_complete:
        (run_root / "post-proof-idempotence.v1.json").unlink(missing_ok=True)
        (run_root / FINAL_BUNDLE_FILENAME).unlink(missing_ok=True)
    invalidated_path.unlink(missing_ok=True)
    active_path.unlink(missing_ok=True)
    return receipt, stats


def validate_only(
    *,
    snapshot_id: str,
    snapshot_at: str,
    config_path: Path,
    run_root: Path,
) -> dict[str, Any]:
    snapshot_id = safe_id(snapshot_id, "snapshot_id")
    snapshot_at = parse_snapshot_at(snapshot_at)
    public_config, stages, config_digest, snapshot_digest, _owner_reference = load_config(
        config_path.expanduser().resolve(),
        snapshot_id=snapshot_id,
        snapshot_at=snapshot_at,
        run_root=run_root.expanduser().resolve(),
    )
    return {
        "status": "validated",
        "snapshot_id": snapshot_id,
        "snapshot_at": snapshot_at,
        "snapshot_digest": snapshot_digest,
        "cadence_id": public_config["cadence_id"],
        "config_digest": config_digest,
        "stages": [stage.stage for stage in stages],
    }


def post_proof_idempotence(
    receipt: Mapping[str, Any],
    stats: CadenceStats,
) -> dict[str, Any] | None:
    traversals = (stats.run_one, stats.run_two)
    if (
        receipt.get("run_number") != 2
        or stats.run_two.invoked_stages != STAGES
        or any(run.executed_stages for run in traversals)
        or any(run.new_events != 0 for run in traversals)
        or any(run.changed_receipts != 0 for run in traversals)
        or any(run.replayed_completed_children != 0 for run in traversals)
        or stats.aggregate_receipts_written != 0
    ):
        return None
    return {
        "probe_id": f"{receipt['cadence_receipt_id']}:idempotence",
        "invoked_at": receipt["completed_at"],
        "cadence_receipt_digest": receipt["receipt_digest"],
        "output_digest": receipt["output_digest"],
        "status": "proven",
        "new_event_count": 0,
        "changed_byte_count": 0,
        "replayed_completed_children": 0,
        "emitted_receipt_count": 0,
    }


def load_pre_proof_bundle(
    spec: StageSpec,
    *,
    snapshot_id: str,
    snapshot_digest: str,
    snapshot_at: str,
) -> dict[str, Any]:
    document = read_json_object(spec.readiness_evidence.path)
    if (
        document.get("contract_name") != PRE_PROOF_BUNDLE_CONTRACT
        or document.get("contract_version") != 1
        or document.get("snapshot_id") != snapshot_id
        or document.get("snapshot_digest") != snapshot_digest
        or document.get("snapshot_at") != snapshot_at
    ):
        raise CadenceError("receipt-stage pre-proof bundle must bind the exact frozen snapshot")
    normalize_readiness(document.get("readiness"), owner="receipt-stage pre-proof")
    payload = document.get("bundle_payload")
    if not isinstance(payload, dict):
        raise CadenceError("receipt-stage pre-proof bundle_payload must be an object")
    missing = [field for field in PRE_PROOF_BUNDLE_FIELDS if not payload.get(field)]
    if missing:
        raise CadenceError(f"receipt-stage pre-proof bundle is missing nonempty fields: {missing}")
    extra = sorted(set(payload) - set(PRE_PROOF_BUNDLE_FIELDS))
    if extra:
        raise CadenceError(f"receipt-stage pre-proof bundle has undeclared fields: {extra}")
    sealed_fields = sorted(ORCHESTRATOR_SEALED_BUNDLE_FIELDS & set(payload))
    if sealed_fields:
        raise CadenceError(
            f"receipt-stage pre-proof bundle cannot predeclare orchestrator-sealed fields: {sealed_fields}"
        )
    return payload


def cadence_reference(receipt: Mapping[str, Any]) -> dict[str, Any]:
    fixed_point = receipt.get("fixed_point")
    readiness = receipt.get("readiness")
    if not isinstance(fixed_point, Mapping) or not isinstance(readiness, Mapping):
        raise CadenceError("cadence receipt is missing fixed-point or readiness evidence")
    return {
        "contract_name": "governance-cadence-receipt.v1",
        "receipt_id": receipt["cadence_receipt_id"],
        "reference": f"receipt:governance-cadence:{receipt['run_id']}",
        "run_number": receipt["run_number"],
        "snapshot_id": receipt["snapshot_id"],
        "digest": receipt["receipt_digest"],
        "previous_receipt_digest": receipt["previous_cadence_receipt_digest"],
        "output_digest": receipt["output_digest"],
        "fixed_point_status": fixed_point["status"],
        "new_event_count": fixed_point["new_event_count"],
        "changed_byte_count": fixed_point["changed_byte_count"],
        "replayed_completed_children": fixed_point["replayed_completed_children"],
        "ready": readiness["ready"],
    }


def seal_snapshot_bundle(
    *,
    snapshot_id: str,
    snapshot_at: str,
    config_path: Path,
    run_root: Path,
    final_cadence_receipt: Mapping[str, Any],
    post_proof: Mapping[str, Any],
) -> tuple[dict[str, Any], bool]:
    public_config, stages, _config_digest, snapshot_digest, _owner_reference = load_config(
        config_path.expanduser().resolve(),
        snapshot_id=snapshot_id,
        snapshot_at=snapshot_at,
        run_root=run_root.expanduser().resolve(),
    )
    cadence_id = str(public_config["cadence_id"])
    run_one = read_json_object(cadence_receipt_path(run_root, 1))
    run_two = read_json_object(cadence_receipt_path(run_root, 2))
    if (
        run_two != final_cadence_receipt
        or run_one.get("run_number") != 1
        or run_one.get("readiness", {}).get("ready") is not False
        or run_one.get("readiness", {}).get("exact_all") is not False
        or run_two.get("run_number") != 2
        or run_two.get("previous_cadence_receipt_digest") != run_one.get("receipt_digest")
        or run_one.get("fixed_point", {}).get("previous_output_digest") is not None
        or run_two.get("fixed_point", {}).get("previous_output_digest") != run_one.get("output_digest")
        or post_proof.get("cadence_receipt_digest") != run_two.get("receipt_digest")
        or post_proof.get("output_digest") != run_two.get("output_digest")
        or post_proof.get("status") != "proven"
        or any(
            post_proof.get(field) != 0
            for field in (
                "new_event_count",
                "changed_byte_count",
                "replayed_completed_children",
                "emitted_receipt_count",
            )
        )
    ):
        raise CadenceError(
            "final snapshot bundle requires incomplete run one, a fixed-point run two, "
            "and the exact post-proof observation"
        )
    bundle_payload = load_pre_proof_bundle(
        stages[-1],
        snapshot_id=snapshot_id,
        snapshot_digest=snapshot_digest,
        snapshot_at=snapshot_at,
    )
    full_stage_receipts = load_document(stage_receipts_collection_path(run_root))
    if not isinstance(full_stage_receipts, list) or len(full_stage_receipts) != len(STAGES):
        raise CadenceError("full governance stage receipt collection must contain exactly nine receipts")
    expected_full_stage_receipts = [read_json_object(receipt_path(run_root, stage)) for stage in STAGES]
    if full_stage_receipts != expected_full_stage_receipts:
        raise CadenceError("full governance stage receipt collection differs from its owner receipts")
    aggregate_stage_digests = [
        item.get("receipt_digest") for item in run_two.get("stage_receipts", []) if isinstance(item, Mapping)
    ]
    if aggregate_stage_digests != [
        item.get("receipt_digest") for item in full_stage_receipts if isinstance(item, Mapping)
    ]:
        raise CadenceError("cadence receipt does not bind the full governance stage receipt collection")
    stage_references = [
        {
            "contract_name": "governance-stage-receipt.v1",
            "stage": item["stage"],
            "receipt_id": item["stage_receipt_id"],
            "reference": item["receipt_target"],
            "snapshot_id": snapshot_id,
            "digest": item["receipt_digest"],
            "status": item["status"],
        }
        for item in full_stage_receipts
    ]
    readiness = cadence_readiness(
        run_number=2,
        fixed_point_proven=True,
        owner_readiness=aggregate_owner_readiness(
            stages,
            snapshot_id=snapshot_id,
            snapshot_digest=snapshot_digest,
            snapshot_at=snapshot_at,
        ),
    )
    if readiness != run_two["readiness"]:
        raise CadenceError("owner readiness changed before final snapshot bundle sealing")
    payload: dict[str, Any] = {
        "contract_name": "governance-snapshot-bundle.v1",
        "contract_version": 1,
        **bundle_payload,
        "snapshot_id": snapshot_id,
        "snapshot_at": snapshot_at,
        "snapshot_digest": snapshot_digest,
        "generated_at": snapshot_at,
        "governance_stage_receipts": stage_references,
        "governance_cadence_receipts": [
            cadence_reference(run_one),
            cadence_reference(run_two),
        ],
        "post_proof_idempotence": dict(post_proof),
        "readiness": readiness,
        "digest_algorithm": "sha256-rfc8785-excluding-self-digest-v1",
    }
    bundle = {**payload, "bundle_digest": digest_value(payload)}
    if bundle["bundle_id"] != f"{cadence_id}:{snapshot_id}:bundle":
        raise CadenceError("receipt-stage bundle_id must be the cadence and snapshot bound bundle ID")
    validate_public_contract(
        bundle,
        contract_name="governance-snapshot-bundle.v1",
        catalog=stages[-1].schema_catalog,
    )
    target = run_root / FINAL_BUNDLE_FILENAME
    changed = write_if_changed(
        target,
        json.dumps(bundle, indent=2, sort_keys=True) + "\n",
    )
    return bundle, changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument("--snapshot-at", required=True)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--run-root", required=True, type=Path)
    parser.add_argument("--write", action="store_true", help="execute stages and write typed receipts")
    parser.add_argument("--strict", action="store_true", help="fail closed on any incomplete predicate")
    parser.add_argument("--json", action="store_true", help="print the aggregate receipt and run stats")
    args = parser.parse_args(argv)
    try:
        if args.write:
            receipt, stats = run_cadence(
                snapshot_id=args.snapshot_id,
                snapshot_at=args.snapshot_at,
                config_path=args.config,
                run_root=args.run_root,
            )
            post_proof = post_proof_idempotence(receipt, stats)
            snapshot_bundle: dict[str, Any] | None = None
            snapshot_bundle_changed = False
            if post_proof is not None:
                write_if_changed(
                    args.run_root.expanduser().resolve() / "post-proof-idempotence.v1.json",
                    json.dumps(post_proof, indent=2, sort_keys=True) + "\n",
                )
                try:
                    snapshot_bundle, snapshot_bundle_changed = seal_snapshot_bundle(
                        snapshot_id=args.snapshot_id,
                        snapshot_at=args.snapshot_at,
                        config_path=args.config,
                        run_root=args.run_root,
                        final_cadence_receipt=receipt,
                        post_proof=post_proof,
                    )
                except CadenceError:
                    invalidate_cadence(
                        run_root=args.run_root.expanduser().resolve(),
                        snapshot_id=args.snapshot_id,
                        snapshot_digest=str(receipt.get("snapshot_digest") or "unresolved"),
                        config_digest=digest_file(args.config.expanduser().resolve())[0],
                    )
                    raise
            output = {
                "receipt": receipt,
                "run": stats.public(),
                "post_proof_idempotence": post_proof,
                "snapshot_bundle": snapshot_bundle,
                "snapshot_bundle_changed": snapshot_bundle_changed,
                "stage_receipts_path": str(stage_receipts_collection_path(args.run_root.expanduser().resolve())),
            }
            fixed_point = receipt.get("fixed_point", {})
            readiness = receipt.get("readiness", {})
            if args.strict and (
                receipt.get("run_number") != 2
                or fixed_point.get("status") != "proven"
                or fixed_point.get("new_event_count") != 0
                or fixed_point.get("changed_byte_count") != 0
                or readiness.get("ready") is not True
                or post_proof is None
                or snapshot_bundle is None
            ):
                raise CadenceError("strict cadence requires a separate unchanged post-proof invocation")
        else:
            output = validate_only(
                snapshot_id=args.snapshot_id,
                snapshot_at=args.snapshot_at,
                config_path=args.config,
                run_root=args.run_root,
            )
    except CadenceError as exc:
        print(f"governance-memory-cadence: FAIL: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(output, indent=2, sort_keys=True))
    elif args.write:
        stats = output["run"]
        print(
            "governance-memory-cadence: complete; "
            f"run_one_executed={len(stats['run_one']['executed_stages'])}; "
            f"run_two_executed={len(stats['run_two']['executed_stages'])}; "
            f"run_two_events={stats['run_two']['new_events']}; "
            f"aggregate_writes={stats['aggregate_receipts_written']}; "
            f"post_proof={'proven' if output['post_proof_idempotence'] else 'pending'}"
        )
    else:
        print(
            f"governance-memory-cadence: config valid; snapshot={output['snapshot_id']}; stages={len(output['stages'])}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

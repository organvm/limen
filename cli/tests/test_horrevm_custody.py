from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "horrevm-custody.py"
FIXED_NOW = datetime(2026, 7, 16, 18, 0, tzinfo=timezone.utc)


def _load():
    spec = importlib.util.spec_from_file_location("horrevm_custody_uut", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def custody(monkeypatch, tmp_path: Path):
    ssh_keygen = shutil.which("ssh-keygen")
    if not ssh_keygen:
        pytest.skip("ssh-keygen is required for signed HORREVM receipt fixtures")
    mod = _load()
    remote = "rail-zeta-73"
    source = tmp_path / "payload source" / "ciphertext"
    source.mkdir(parents=True)
    (source / "opaque-17.enc").write_bytes(b"sealed-payload-17")
    kernel_source = tmp_path / "kernel inputs" / "flame-zeta.md"
    kernel_source.parent.mkdir(parents=True)
    kernel_source.write_text("continuity-zeta\n", encoding="utf-8")
    arca = tmp_path / "tools" / "arca arbitrary.sh"
    arca.parent.mkdir(parents=True)
    arca.write_text("cmd_seal() { :; }\n", encoding="utf-8")
    config = tmp_path / "config with spaces" / "rclone.conf"
    config.parent.mkdir(parents=True)
    config.write_text("[rail-zeta-73]\ntype = memory\n", encoding="utf-8")
    signing_key = tmp_path / "domus horrevm test authority"
    subprocess.run(
        [ssh_keygen, "-q", "-t", "ed25519", "-N", "", "-f", str(signing_key)],
        check=True,
        capture_output=True,
    )
    public_key = signing_key.with_suffix(".pub").read_text(encoding="utf-8").split()
    allowed_signers = tmp_path / "domus owned allowed-signers"
    allowed_signers.write_text(
        f"keeper-citrine {public_key[0]} {public_key[1]}\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr(mod, "LOG", tmp_path / "state" / "horrevm.json")
    monkeypatch.setattr(mod, "ARCA", arca)
    monkeypatch.setattr(mod, "RCLONE_CONF", config)
    monkeypatch.setattr(
        mod,
        "PAYLOADS",
        {
            remote: [
                {"name": "vault-zeta", "type": "dir-mirror", "src": str(source)},
                {"name": "kernel", "type": "kernel"},
            ]
        },
    )
    monkeypatch.setattr(mod, "KERNEL_CANDIDATES", [str(kernel_source)])
    monkeypatch.setattr(mod, "BUDGET_GB", {remote: 1.0})
    monkeypatch.setattr(mod, "STATE_RAIL_IDS", {})
    monkeypatch.setattr(mod, "OWNER_ALLOWED_SIGNERS", allowed_signers)
    monkeypatch.setattr(mod, "now", lambda: FIXED_NOW)
    monkeypatch.setattr(mod, "_TEST_SIGNING_KEY", signing_key, raising=False)
    monkeypatch.setattr(mod, "_TEST_ALLOWED_SIGNERS", allowed_signers, raising=False)
    monkeypatch.setenv("LIMEN_HORREVM_APPLY", "1")
    return mod, remote, tmp_path


def _snapshot(root: Path) -> tuple[tuple[str, ...], dict[str, bytes]]:
    paths = tuple(sorted(path.relative_to(root).as_posix() for path in root.rglob("*")))
    files = {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*") if path.is_file()}
    return paths, files


def _write_receipt(
    mod,
    directory: Path,
    *,
    action: str,
    remote: str,
    attempt_id: str,
    expires_at: datetime | None = None,
    target: str | None = None,
    payload_hash: str | None = None,
    source_manifest_hash: str | None = None,
    content_hashes: dict[str, str] | None = None,
    destinations: list[str] | None = None,
) -> Path:
    plan = mod.action_plan(action, remote, attempt_id)
    issued_at = FIXED_NOW - timedelta(minutes=1)
    value = {
        "schema": mod.RECEIPT_SCHEMA,
        "authorized": True,
        "authorized_by": "keeper-citrine",
        "action": action,
        "destination": target or plan["destination"],
        "destinations": destinations if destinations is not None else plan["destinations"],
        "source_manifest_hash": source_manifest_hash or plan["source_manifest_hash"],
        "content_hashes": content_hashes if content_hashes is not None else plan["content_hashes"],
        "payload_hash": payload_hash or plan["payload_hash"],
        "issued_at": mod._iso(issued_at),
        "expires_at": mod._iso(expires_at or (FIXED_NOW + timedelta(hours=2))),
        "attempt_id": attempt_id,
    }
    path = directory / f"receipt {attempt_id}.json"
    path.write_bytes(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8"))
    subprocess.run(
        [
            "ssh-keygen",
            "-Y",
            "sign",
            "-f",
            str(mod._TEST_SIGNING_KEY),
            "-n",
            mod.SIGNED_RECEIPT_NAMESPACE,
            str(path),
        ],
        check=True,
        capture_output=True,
    )
    return path


def _signature(path: Path) -> Path:
    return Path(f"{path}.sig")


def _signed_args(receipt: Path) -> list[str]:
    return ["--receipt", str(receipt), "--signature", str(_signature(receipt))]


def _resign_receipt(mod, path: Path, value: dict, *, namespace: str | None = None) -> None:
    path.write_bytes(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8"))
    _signature(path).unlink(missing_ok=True)
    subprocess.run(
        [
            "ssh-keygen",
            "-Y",
            "sign",
            "-f",
            str(mod._TEST_SIGNING_KEY),
            "-n",
            namespace or mod.SIGNED_RECEIPT_NAMESPACE,
            str(path),
        ],
        check=True,
        capture_output=True,
    )


def _remote_final_writes(commands: list[list[str]], remote: str) -> list[list[str]]:
    writes = []
    prefix = f"{remote}:limen-custody/"
    probe_prefix = f"{remote}:limen-custody/.probe/"
    for command in commands:
        if command[:2] != ["rclone", "copy"] and command[:2] != ["rclone", "copyto"]:
            continue
        for argument in command[2:]:
            if argument.startswith(prefix) and not argument.startswith(probe_prefix):
                writes.append(command)
    return writes


class CommandSpy:
    def __init__(
        self, *, roundtrip_mismatch: bool = False, restore_pull_fails: bool = False, final_copy_fails: bool = False
    ):
        self.roundtrip_mismatch = roundtrip_mismatch
        self.restore_pull_fails = restore_pull_fails
        self.final_copy_fails = final_copy_fails
        self.commands: list[list[str]] = []
        self.remote_objects: dict[str, bytes] = {}

    def __call__(self, command: list[str], timeout: int = 120):
        self.commands.append(list(command))
        if command[0] == "bash":
            verb = command[2]
            if verb == "seal":
                Path(command[4]).write_bytes(b"sealed-kernel-zeta")
                return 0, ""
            if verb == "unseal":
                output = Path(command[4])
                output.mkdir(parents=True)
                (output / "restored-zeta.txt").write_text("restored\n", encoding="utf-8")
                return 0, ""
            raise AssertionError(f"unexpected local command: {command!r}")

        assert command[0] == "rclone"
        verb = command[1]
        args = command[2:]
        if verb == "listremotes":
            return 0, "rail-zeta-73:\n"
        if verb == "about":
            return 0, json.dumps({"total": 10_000_000, "free": 9_000_000})
        if verb == "copyto":
            source, target = args[:2]
            if ":" in target:
                if self.final_copy_fails and "/.probe/" not in target:
                    return 1, "copy refused"
                self.remote_objects[target] = Path(source).read_bytes()
                return 0, ""
            if self.restore_pull_fails and source.endswith("-kernel.tar.enc"):
                return 1, "restore refused"
            Path(target).write_bytes(self.remote_objects[source])
            return 0, ""
        if verb == "copy":
            if self.final_copy_fails:
                return 1, "copy refused"
            return 0, ""
        if verb == "cat":
            if self.roundtrip_mismatch:
                return 0, "not-the-probe\n"
            return 0, self.remote_objects[args[0]].decode("utf-8")
        if verb == "deletefile":
            self.remote_objects.pop(args[0], None)
            return 0, ""
        if verb == "check":
            return 0, ""
        raise AssertionError(f"unexpected rclone command: {command!r}")


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["--check"],
        ["--dry-run"],
        ["--push"],
        ["--push", "--dry-run"],
        ["--probe"],
        ["--probe", "--dry-run"],
        ["--status"],
        ["--doctor"],
    ],
)
def test_every_non_apply_mode_is_zero_write(custody, monkeypatch, argv):
    mod, remote, root = custody
    monkeypatch.setenv("LIMEN_HORREVM_APPLY", "0")
    mod.LOG.parent.mkdir(parents=True)
    mod.LOG.write_text(
        json.dumps({"rails": {remote: {"last_push_attempt": "unchanged-dry-run-marker"}}}),
        encoding="utf-8",
    )
    before = _snapshot(root)
    commands: list[list[str]] = []

    def read_only_spy(command, timeout=120):
        commands.append(list(command))
        if command == ["rclone", "listremotes"]:
            return 0, f"{remote}:\n"
        raise AssertionError(f"non-apply mode attempted a command: {command!r}")

    monkeypatch.setattr(mod, "run", read_only_spy)

    assert mod.main(argv) == 0
    assert _snapshot(root) == before
    assert all(command[1] not in mod.REMOTE_WRITE_VERBS for command in commands)
    assert not any(command[0] in {"b2", "backblaze", "launchctl", "mv", "rsync", "sendmail"} for command in commands)


def test_apply_without_valid_receipt_has_no_effects(custody, monkeypatch):
    mod, remote, root = custody
    calls = []
    monkeypatch.setattr(mod, "run", lambda *args, **kwargs: calls.append(args) or (0, ""))
    before = _snapshot(root)

    assert mod.main(["--push", "--apply"]) == 2

    expired = _write_receipt(
        mod,
        root,
        action="push",
        remote=remote,
        attempt_id="expired-arbitrary-77",
        expires_at=FIXED_NOW - timedelta(seconds=1),
    )
    receipt_snapshot = _snapshot(root)
    assert mod.main(["--push", "--apply", *_signed_args(expired)]) == 2
    assert _snapshot(root) == receipt_snapshot
    assert calls == []
    assert not mod.LOG.exists()
    assert before[1].items() <= receipt_snapshot[1].items()


def test_receipt_requires_explicit_authority_and_bounded_lifetime(custody, monkeypatch):
    mod, remote, root = custody
    receipt = _write_receipt(
        mod,
        root,
        action="probe",
        remote=remote,
        attempt_id="authority-window-arbitrary-71",
    )
    value = json.loads(receipt.read_text(encoding="utf-8"))
    monkeypatch.setattr(
        mod,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("command ran")),
    )

    value["authorized"] = False
    _resign_receipt(mod, receipt, value)
    assert mod.main(["--probe", "--apply", *_signed_args(receipt)]) == 2

    value["authorized"] = True
    value["issued_at"] = mod._iso(FIXED_NOW - timedelta(hours=5))
    _resign_receipt(mod, receipt, value)
    assert mod.main(["--probe", "--apply", *_signed_args(receipt)]) == 2
    assert not mod.LOG.exists()


def test_environment_apply_flag_alone_cannot_authorize_effects(custody, monkeypatch):
    mod, _remote, root = custody
    monkeypatch.setenv("LIMEN_HORREVM_APPLY", "1")
    monkeypatch.setattr(mod, "run", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("command ran")))
    before = _snapshot(root)

    assert mod.main(["--push"]) == 0
    assert _snapshot(root) == before
    assert not mod.LOG.exists()


def test_unset_apply_valve_refuses_signed_receipt_with_zero_commands_and_zero_writes(custody, monkeypatch):
    mod, remote, root = custody
    receipt = _write_receipt(
        mod,
        root,
        action="push",
        remote=remote,
        attempt_id="valve-closed-arbitrary-31",
    )
    monkeypatch.setenv("LIMEN_HORREVM_APPLY", "0")
    monkeypatch.setattr(
        mod.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("signature or remote command ran")),
    )
    commands = []
    monkeypatch.setattr(mod, "run", lambda *args, **kwargs: commands.append((args, kwargs)) or (0, ""))
    before = _snapshot(root)

    assert mod.main(["--push", "--apply", *_signed_args(receipt)]) == 2
    assert commands == []
    assert _snapshot(root) == before
    assert not mod.LOG.exists()


def test_self_asserted_or_forged_json_has_zero_commands_and_zero_writes(custody, monkeypatch):
    mod, remote, root = custody
    receipt = _write_receipt(
        mod,
        root,
        action="push",
        remote=remote,
        attempt_id="forged-json-arbitrary-83",
    )
    forged = json.loads(receipt.read_text(encoding="utf-8"))
    forged["authorized_by"] = "keeper-forged"
    forged["payload_hash"] = "sha256:" + "0" * 64
    receipt.write_bytes(json.dumps(forged, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    commands = []
    monkeypatch.setattr(mod, "run", lambda *args, **_kwargs: commands.append(args) or (0, ""))
    before = _snapshot(root)

    assert mod.main(["--push", "--apply", *_signed_args(receipt)]) == 2
    assert commands == []
    assert _snapshot(root) == before
    assert not mod.LOG.exists()


def test_missing_pinned_trust_root_fails_closed_and_ignores_caller_env(custody, monkeypatch):
    mod, remote, root = custody
    receipt = _write_receipt(
        mod,
        root,
        action="push",
        remote=remote,
        attempt_id="missing-trust-root-arbitrary-47",
    )
    monkeypatch.setattr(mod, "OWNER_ALLOWED_SIGNERS", root / "missing-owner-trust-root")
    monkeypatch.setenv("LIMEN_HORREVM_ALLOWED_SIGNERS", str(mod._TEST_ALLOWED_SIGNERS))
    commands = []
    monkeypatch.setattr(mod, "run", lambda *args, **_kwargs: commands.append(args) or (0, ""))
    before = _snapshot(root)

    assert mod.main(["--push", "--apply", *_signed_args(receipt)]) == 2
    assert commands == []
    assert _snapshot(root) == before
    assert not mod.LOG.exists()


def test_symlinked_state_parent_cannot_redirect_apply_writes(custody, monkeypatch):
    mod, remote, root = custody
    receipt = _write_receipt(
        mod,
        root,
        action="push",
        remote=remote,
        attempt_id="state-parent-escape-arbitrary-61",
    )
    outside = root.parent / f"{root.name}-outside-state"
    outside.mkdir()
    mod.LOG.parent.symlink_to(outside, target_is_directory=True)
    commands = []
    monkeypatch.setattr(mod, "run", lambda *args, **_kwargs: commands.append(args) or (0, ""))
    outside_before = _snapshot(outside)

    assert mod.main(["--push", "--apply", *_signed_args(receipt)]) == 2
    assert commands == []
    assert _snapshot(outside) == outside_before
    assert not list(root.glob(f".{receipt.name}.*.consumed"))


def test_signature_from_another_namespace_cannot_authorize_egress(custody, monkeypatch):
    mod, remote, root = custody
    receipt = _write_receipt(
        mod,
        root,
        action="push",
        remote=remote,
        attempt_id="wrong-namespace-arbitrary-53",
    )
    value = json.loads(receipt.read_text(encoding="utf-8"))
    _resign_receipt(mod, receipt, value, namespace="limen.unrelated_receipt.v9")
    commands = []
    monkeypatch.setattr(mod, "run", lambda *args, **_kwargs: commands.append(args) or (0, ""))
    before = _snapshot(root)

    assert mod.main(["--push", "--apply", *_signed_args(receipt)]) == 2
    assert commands == []
    assert _snapshot(root) == before
    assert not mod.LOG.exists()


@pytest.mark.parametrize(
    "field",
    ["target", "payload_hash", "source_manifest_hash", "content_hashes", "destinations", "attempt_id"],
)
def test_receipt_binding_mismatch_refuses_before_commands_or_state(custody, monkeypatch, field):
    mod, remote, root = custody
    attempt = "binding-arbitrary-zeta-901"
    kwargs = {}
    argv = ["--push", "--apply"]
    if field == "target":
        kwargs["target"] = "different-rail:limen-custody"
    elif field == "payload_hash":
        kwargs["payload_hash"] = "sha256:" + "0" * 64
    elif field == "source_manifest_hash":
        kwargs["source_manifest_hash"] = "sha256:" + "1" * 64
    elif field == "content_hashes":
        kwargs["content_hashes"] = {"source.forged": "sha256:" + "2" * 64}
    elif field == "destinations":
        kwargs["destinations"] = [f"{remote}:limen-custody/forged.enc"]
    receipt = _write_receipt(mod, root, action="push", remote=remote, attempt_id=attempt, **kwargs)
    if field == "attempt_id":
        argv.extend(["--attempt-id", "different-attempt-zeta"])
    argv.extend(_signed_args(receipt))
    monkeypatch.setattr(mod, "run", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("command ran")))

    assert mod.main(argv) == 2
    assert not mod.LOG.exists()


def test_action_binding_and_receipt_symlink_fail_before_effects(custody, monkeypatch):
    mod, remote, root = custody
    receipt = _write_receipt(
        mod,
        root,
        action="probe",
        remote=remote,
        attempt_id="probe-not-push-arbitrary-21",
    )
    alias = root / "receipt alias.json"
    alias.symlink_to(receipt)
    monkeypatch.setattr(mod, "run", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("command ran")))

    assert mod.main(["--push", "--apply", *_signed_args(receipt)]) == 2
    assert mod.main(["--probe", "--apply", "--receipt", str(alias), "--signature", str(_signature(receipt))]) == 2
    assert not mod.LOG.exists()


def test_payload_change_invalidates_receipt_before_effects(custody, monkeypatch):
    mod, remote, root = custody
    attempt = "payload-change-arbitrary-37"
    receipt = _write_receipt(mod, root, action="push", remote=remote, attempt_id=attempt)
    payload = root / "payload source" / "ciphertext" / "opaque-17.enc"
    payload.write_bytes(b"changed-after-receipt")
    monkeypatch.setattr(mod, "run", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("command ran")))

    assert mod.main(["--push", "--apply", *_signed_args(receipt)]) == 2
    assert not mod.LOG.exists()


def test_final_egress_uses_receipt_bound_snapshot_not_mutable_live_source(custody, monkeypatch):
    mod, remote, root = custody
    attempt = "snapshot-egress-arbitrary-73"
    receipt_path = _write_receipt(mod, root, action="push", remote=remote, attempt_id=attempt)
    receipt, plan = mod.load_apply_receipt(
        receipt_path,
        _signature(receipt_path),
        "push",
    )
    spy = CommandSpy()
    monkeypatch.setattr(mod, "run", spy)
    workdir = root / "private apply workdir"
    workdir.mkdir()

    staged, kernel = mod._stage_payloads(remote, workdir, receipt, plan)
    live_source = root / "payload source" / "ciphertext"
    mirror = next(path for path, subpath in staged if subpath == "vault-zeta")
    assert mirror != live_source
    assert (mirror / "opaque-17.enc").read_bytes() == b"sealed-payload-17"
    assert kernel is not None

    # A live writer may continue after staging; final rclone input remains the detached,
    # manifest-verified snapshot that was bound by the apply receipt.
    (live_source / "opaque-17.enc").write_bytes(b"changed-after-staging")
    assert mod._copy_payloads(remote, staged, receipt) is True
    final_writes = _remote_final_writes(spy.commands, remote)
    assert any(str(mirror) in command for command in final_writes)
    assert all(str(live_source) not in command for command in final_writes)
    assert (mirror / "opaque-17.enc").read_bytes() == b"sealed-payload-17"


def test_receipt_preview_is_zero_write(custody, monkeypatch):
    mod, remote, root = custody
    receipt = _write_receipt(
        mod,
        root,
        action="push",
        remote=remote,
        attempt_id="preview-receipt-arbitrary-52",
    )
    before = _snapshot(root)
    monkeypatch.setattr(mod, "run", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("command ran")))

    assert mod.main(["--push", *_signed_args(receipt)]) == 0
    assert _snapshot(root) == before
    assert not mod.LOG.exists()


def test_failed_roundtrip_blocks_payload_copy_and_freshness(custody, monkeypatch):
    mod, remote, root = custody
    attempt = "roundtrip-failure-arbitrary-619"
    receipt = _write_receipt(mod, root, action="push", remote=remote, attempt_id=attempt)
    spy = CommandSpy(roundtrip_mismatch=True)
    monkeypatch.setattr(mod, "run", spy)

    assert mod.main(["--push", "--apply", *_signed_args(receipt)]) == 1
    assert _remote_final_writes(spy.commands, remote) == []
    assert not any(command[0] == "bash" for command in spy.commands)
    state = json.loads(mod.LOG.read_text(encoding="utf-8"))
    rail = state["rails"][remote]
    assert rail["probe_roundtrip_ok"] is False
    assert "last_verified_push" not in rail
    assert "last_restore_test" not in rail
    assert state["attempts"][mod._attempt_key(attempt)]["status"] == "failed_roundtrip"


def test_probe_mutation_requires_and_records_exact_receipt(custody, monkeypatch):
    mod, remote, root = custody
    attempt = "probe-success-arbitrary-283"
    receipt = _write_receipt(mod, root, action="probe", remote=remote, attempt_id=attempt)
    spy = CommandSpy()
    monkeypatch.setattr(mod, "run", spy)

    assert mod.main(["--probe", "--apply", *_signed_args(receipt)]) == 0
    assert _remote_final_writes(spy.commands, remote) == []
    assert all(
        "/.probe/" in argument
        for command in spy.commands
        if command[:2] in (["rclone", "copyto"], ["rclone", "deletefile"])
        for argument in command[2:]
        if argument.startswith(f"{remote}:")
    )
    state = json.loads(mod.LOG.read_text(encoding="utf-8"))
    rail = state["rails"][remote]
    assert rail["probe_roundtrip_ok"] is True
    assert rail["last_probe"] == mod._iso(FIXED_NOW)
    assert "last_verified_push" not in rail
    assert state["attempts"][mod._attempt_key(attempt)]["status"] == "probe_verified"


def test_failed_restore_preflight_blocks_final_copy_and_freshness(custody, monkeypatch):
    mod, remote, root = custody
    attempt = "restore-failure-arbitrary-887"
    receipt = _write_receipt(mod, root, action="push", remote=remote, attempt_id=attempt)
    spy = CommandSpy(restore_pull_fails=True)
    monkeypatch.setattr(mod, "run", spy)

    assert mod.main(["--push", "--apply", *_signed_args(receipt)]) == 1
    assert _remote_final_writes(spy.commands, remote) == []
    state = json.loads(mod.LOG.read_text(encoding="utf-8"))
    rail = state["rails"][remote]
    assert rail["probe_roundtrip_ok"] is True
    assert rail["restore_ok"] is False
    assert "last_verified_push" not in rail
    assert "last_restore_test" not in rail
    assert state["attempts"][mod._attempt_key(attempt)]["status"] == "failed_restore"


def test_failed_final_copy_never_stamps_freshness(custody, monkeypatch):
    mod, remote, root = custody
    attempt = "copy-failure-arbitrary-443"
    receipt = _write_receipt(mod, root, action="push", remote=remote, attempt_id=attempt)
    spy = CommandSpy(final_copy_fails=True)
    monkeypatch.setattr(mod, "run", spy)

    assert mod.main(["--push", "--apply", *_signed_args(receipt)]) == 1
    state = json.loads(mod.LOG.read_text(encoding="utf-8"))
    rail = state["rails"][remote]
    assert rail["restore_ok"] is True
    assert rail["verify_ok"] is False
    assert "last_verified_push" not in rail
    assert "last_restore_test" not in rail
    assert state["attempts"][mod._attempt_key(attempt)]["status"] == "failed_copy_or_integrity"


def test_verified_apply_stamps_exact_attempt_once(custody, monkeypatch):
    mod, remote, root = custody
    attempt = "verified-arbitrary-attempt-509"
    receipt = _write_receipt(mod, root, action="push", remote=remote, attempt_id=attempt)
    spy = CommandSpy()
    monkeypatch.setattr(mod, "run", spy)

    assert mod.main(["--push", "--apply", *_signed_args(receipt), "--attempt-id", attempt]) == 0
    final_writes = _remote_final_writes(spy.commands, remote)
    assert final_writes
    state = json.loads(mod.LOG.read_text(encoding="utf-8"))
    rail = state["rails"][remote]
    assert rail["probe_roundtrip_ok"] is True
    assert rail["restore_ok"] is True
    assert rail["verify_ok"] is True
    assert rail["last_verified_push"] == mod._iso(FIXED_NOW)
    assert rail["last_restore_test"] == mod._iso(FIXED_NOW)
    assert rail["last_attempt_id_hash"] == mod._attempt_key(attempt)
    assert state["attempts"][mod._attempt_key(attempt)]["status"] == "verified"
    assert attempt not in mod.LOG.read_text(encoding="utf-8")
    assert all(command[1] != "delete" for command in spy.commands if command[0] == "rclone")
    assert all(
        command[2].startswith(f"{remote}:limen-custody/.probe/")
        for command in spy.commands
        if command[:2] == ["rclone", "deletefile"]
    )

    command_count = len(spy.commands)
    assert mod.main(["--push", "--apply", *_signed_args(receipt)]) == 2
    assert len(spy.commands) == command_count


def test_owner_adjacent_marker_blocks_replay_after_state_loss(custody, monkeypatch):
    mod, remote, root = custody
    attempt = "external-replay-arbitrary-811"
    receipt = _write_receipt(mod, root, action="probe", remote=remote, attempt_id=attempt)
    spy = CommandSpy()
    monkeypatch.setattr(mod, "run", spy)

    assert mod.main(["--probe", "--apply", *_signed_args(receipt)]) == 0
    markers = list(root.glob(f".{receipt.name}.*.consumed"))
    assert len(markers) == 1
    mod.LOG.unlink()
    command_count = len(spy.commands)

    assert mod.main(["--probe", "--apply", *_signed_args(receipt)]) == 2
    assert len(spy.commands) == command_count


def test_mutating_boundaries_refuse_missing_receipt(custody):
    mod, remote, root = custody
    with pytest.raises(mod.EffectRefused):
        mod.rclone(["copyto", "/arbitrary/source", "rail-x:arbitrary-target"])
    with pytest.raises(mod.EffectRefused):
        mod.rclone(["deletefile", "rail-x:arbitrary-target"])
    with pytest.raises(mod.EffectRefused):
        mod.save_state({"rails": {}})
    with pytest.raises(mod.EffectRefused):
        mod.seal(root / "arbitrary", root / "arbitrary.enc")
    with pytest.raises(mod.EffectRefused):
        mod.build_kernel(root / "kernel-stage")
    with pytest.raises(mod.EffectRefused):
        mod._stage_payloads(remote, root / "payload-stage")


def test_mutating_rclone_boundary_enforces_signed_operation_and_destination(custody, monkeypatch):
    mod, remote, root = custody
    receipt_path = _write_receipt(
        mod,
        root,
        action="push",
        remote=remote,
        attempt_id="effect-boundary-arbitrary-59",
    )
    receipt, _plan = mod.load_apply_receipt(
        receipt_path,
        _signature(receipt_path),
        "push",
    )
    monkeypatch.setattr(
        mod,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("rclone command ran")),
    )
    final_destination = next(value for value in receipt.destinations if "/.probe/" not in value)

    with pytest.raises(mod.EffectRefused, match="not an authorized HORREVM operation"):
        mod.rclone(["sync", str(root), final_destination], receipt=receipt)
    with pytest.raises(mod.EffectRefused, match="restricted to the signed probe object"):
        mod.rclone(["deletefile", final_destination], receipt=receipt)
    with pytest.raises(mod.EffectRefused, match="outside the signed receipt"):
        mod.rclone(["copyto", str(root / "forged.enc"), f"{remote}:limen-custody/forged.enc"], receipt=receipt)
    with pytest.raises(mod.EffectRefused, match="one exact signed remote object"):
        mod.rclone(["deletefile", str(root / "local-file")], receipt=receipt)


def test_mutating_boundary_rechecks_apply_valve(custody, monkeypatch):
    mod, remote, root = custody
    receipt_path = _write_receipt(
        mod,
        root,
        action="probe",
        remote=remote,
        attempt_id="valve-recheck-arbitrary-67",
    )
    receipt, _plan = mod.load_apply_receipt(
        receipt_path,
        _signature(receipt_path),
        "probe",
    )
    monkeypatch.setenv("LIMEN_HORREVM_APPLY", "0")
    monkeypatch.setattr(
        mod,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("rclone command ran")),
    )

    with pytest.raises(mod.EffectRefused, match="LIMEN_HORREVM_APPLY=1"):
        mod.rclone(["copyto", str(root / "source"), receipt.destinations[0]], receipt=receipt)


def test_mutating_boundary_rechecks_receipt_expiry(custody, monkeypatch):
    mod, remote, root = custody
    receipt_path = _write_receipt(
        mod,
        root,
        action="probe",
        remote=remote,
        attempt_id="expires-before-effect-arbitrary-19",
        expires_at=FIXED_NOW + timedelta(minutes=1),
    )
    receipt, _plan = mod.load_apply_receipt(
        receipt_path,
        _signature(receipt_path),
        "probe",
    )
    monkeypatch.setattr(mod, "now", lambda: FIXED_NOW + timedelta(minutes=2))
    monkeypatch.setattr(
        mod,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("subprocess ran")),
    )

    with pytest.raises(mod.EffectRefused, match="expired"):
        mod.rclone(["copyto", str(root / "source"), f"{remote}:target"], receipt=receipt)


def test_gdrive_state_uses_registry_rail_id():
    mod = _load()
    state = {"rails": {}}

    row = mod._rail(state, "gdrive", create=True)
    row["token_ok"] = True

    assert state["rails"] == {"googledrive": {"token_ok": True}}

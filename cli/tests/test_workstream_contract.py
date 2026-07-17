from __future__ import annotations

import json
from pathlib import Path

import pytest

from limen.workstream_contract import (
    AUTHORIZATION,
    ContractError,
    RunwayExpired,
    admit_contract,
    configure_contract,
    packet_contract,
    parse_runway,
    read_contract,
    validate_packet_contract,
)


def test_runway_admission_is_idempotent_inherited_and_expires_at_exact_boundary(tmp_path: Path) -> None:
    path = tmp_path / "workstream.json"
    configured, changed = configure_contract(path, "2d")
    assert changed is True
    assert configured["runway"]["duration_seconds"] == 172_800

    admitted, remaining = admit_contract(path, now_epoch=1_000)
    assert remaining == 172_800
    assert admitted["runway"]["deadline_epoch"] == 173_800
    admitted_bytes = path.read_bytes()

    inherited, inherited_remaining = admit_contract(path, now_epoch=1_001)
    assert inherited_remaining == 172_799
    assert inherited["runway"]["started_epoch"] == 1_000
    assert path.read_bytes() == admitted_bytes

    configured_again, changed_again = configure_contract(path)
    assert changed_again is False
    assert configured_again["runway"]["deadline_epoch"] == 173_800
    assert path.read_bytes() == admitted_bytes

    with pytest.raises(ContractError, match="cannot change an admitted runway"):
        configure_contract(path, "3d")
    with pytest.raises(RunwayExpired, match="exhausted"):
        admit_contract(path, now_epoch=173_800)


@pytest.mark.parametrize("raw", ["", "forever", "0h", "14m", "31d", "-1h", "1.5h"])
def test_runway_rejects_malformed_or_unbounded_values(raw: str) -> None:
    with pytest.raises(ContractError):
        parse_runway(raw)


def test_contract_rejects_authorization_drift_and_packet_contract_is_typed(tmp_path: Path) -> None:
    path = tmp_path / "workstream.json"
    configure_contract(path, "8h")
    tampered = json.loads(path.read_text(encoding="utf-8"))
    tampered["authorization"]["approval_mode"] = "ask"
    path.write_text(json.dumps(tampered), encoding="utf-8")

    with pytest.raises(ContractError, match="authorization"):
        read_contract(path)

    timing_path = tmp_path / "timing.json"
    configure_contract(timing_path, "8h")
    admit_contract(timing_path, now_epoch=10_000)
    timing = json.loads(timing_path.read_text(encoding="utf-8"))
    timing["runway"]["started_at"] = "2099-01-01T00:00:00+00:00"
    timing_path.write_text(json.dumps(timing), encoding="utf-8")
    with pytest.raises(ContractError, match="timing state"):
        read_contract(timing_path)

    packet = packet_contract("8h", now_epoch=12_345)
    assert packet["runway"]["duration_seconds"] == 28_800
    assert packet["runway"]["started_epoch"] == 12_345
    assert packet["runway"]["deadline_epoch"] == 41_145
    assert packet["authorization"] == AUTHORIZATION
    assert packet["authorization"]["mode"] == "full_non_destructive"
    assert packet["conductor"]["mode"] == "route_bounded_packets"

    tampered_packet = json.loads(json.dumps(packet))
    tampered_packet["runway"]["deadline_epoch"] += 1
    with pytest.raises(ContractError, match="timing"):
        validate_packet_contract(tampered_packet)

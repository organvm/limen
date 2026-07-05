from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "verify-recordkeeper-kernel.py"


def load_module():
    spec = importlib.util.spec_from_file_location("verify_recordkeeper_kernel_uut", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_recordkeeper_kernel_gate_defaults_to_deterministic_inner_loop() -> None:
    module = load_module()

    gates = module.gate_plan(ROOT, include_event_proof=False, require_event_proof=False, min_streak=3)

    ids = [gate.id for gate in gates]
    assert "event-proof" not in ids
    assert {"py-compile", "vltima-tests", "tabularius-tests", "writer-audit", "vltima-cli"}.issubset(ids)
    assert all(gate.required for gate in gates)


def test_recordkeeper_kernel_gate_can_run_event_proof_as_advisory() -> None:
    module = load_module()

    gates = module.gate_plan(ROOT, include_event_proof=True, require_event_proof=False, min_streak=7)

    event_gate = next(gate for gate in gates if gate.id == "event-proof")
    assert event_gate.required is False
    assert event_gate.command[-2:] == ("--min-streak", "7")


def test_recordkeeper_kernel_gate_can_require_event_proof() -> None:
    module = load_module()

    gates = module.gate_plan(ROOT, include_event_proof=False, require_event_proof=True, min_streak=5)

    event_gate = next(gate for gate in gates if gate.id == "event-proof")
    assert event_gate.required is True
    assert event_gate.command[-2:] == ("--min-streak", "5")


def test_recordkeeper_kernel_gate_distinguishes_required_and_advisory_failures() -> None:
    module = load_module()
    results = [
        module.GateResult("required-pass", "required pass", ("true",), True, 0, 0.01, "", ""),
        module.GateResult("required-fail", "required fail", ("false",), True, 1, 0.01, "", "no"),
        module.GateResult("advisory-fail", "advisory fail", ("false",), False, 1, 0.01, "", "no"),
    ]

    assert [result.id for result in module.required_failures(results)] == ["required-fail"]
    assert [result.id for result in module.advisory_failures(results)] == ["advisory-fail"]
    payload = module.result_payload(results)
    assert payload["ok"] is False
    assert payload["required_failures"] == ["required-fail"]
    assert payload["advisory_failures"] == ["advisory-fail"]

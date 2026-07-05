import json
import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / "scripts" / "validate-vltima-kernel.py"


def load_validator_module():
    spec = importlib.util.spec_from_file_location("validate_vltima_kernel_uut", VALIDATOR)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def run_validator(*args: str | Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VALIDATOR), *(str(arg) for arg in args)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_vltima_kernel_passes_current_organs():
    result = run_validator("--quiet")
    assert result.returncode == 0, result.stdout + result.stderr


def test_vltima_kernel_rejects_missing_universal_term(tmp_path):
    copy_root = tmp_path / "repo"
    shutil.copytree(ROOT / "organs", copy_root / "organs")
    shutil.copy2(ROOT / "organ-ladder.json", copy_root / "organ-ladder.json")
    kernel = copy_root / "organs" / "vltima" / "KERNEL.md"
    kernel.write_text(kernel.read_text().replace("Entitlement", "Access").replace("entitlement", "access"))

    result = run_validator("--root", copy_root)

    assert result.returncode == 1
    assert "organs/vltima/KERNEL.md is missing term(s): Entitlement" in result.stderr


def test_vltima_kernel_rejects_registry_missing_required_primitive(tmp_path):
    copy_root = tmp_path / "repo"
    shutil.copytree(ROOT / "organs", copy_root / "organs")
    shutil.copy2(ROOT / "organ-ladder.json", copy_root / "organ-ladder.json")
    registry = copy_root / "organs" / "vltima" / "kernel.yaml"
    data = yaml.safe_load(registry.read_text())
    data["layers"]["value"] = [item for item in data["layers"]["value"] if item["label"] != "Entitlement"]
    registry.write_text(yaml.safe_dump(data, sort_keys=False))

    result = run_validator("--root", copy_root)

    assert result.returncode == 1
    assert "organs/vltima/kernel.yaml missing required primitive(s): Entitlement" in result.stderr


def test_vltima_kernel_rejects_registry_unknown_source(tmp_path):
    copy_root = tmp_path / "repo"
    shutil.copytree(ROOT / "organs", copy_root / "organs")
    shutil.copy2(ROOT / "organ-ladder.json", copy_root / "organ-ladder.json")
    registry = copy_root / "organs" / "vltima" / "kernel.yaml"
    data = yaml.safe_load(registry.read_text())
    data["layers"]["institutional"][0]["sources"] = ["missing-source"]
    registry.write_text(yaml.safe_dump(data, sort_keys=False))

    result = run_validator("--root", copy_root)

    assert result.returncode == 1
    assert "primitive member references unknown source(s): missing-source" in result.stderr


def test_vltima_kernel_rejects_projection_unknown_primitive(tmp_path):
    copy_root = tmp_path / "repo"
    shutil.copytree(ROOT / "organs", copy_root / "organs")
    shutil.copy2(ROOT / "organ-ladder.json", copy_root / "organ-ladder.json")
    registry = copy_root / "organs" / "vltima" / "kernel.yaml"
    data = yaml.safe_load(registry.read_text())
    data["projection"]["value_proof"] = ["exchange", "missing-primitive"]
    registry.write_text(yaml.safe_dump(data, sort_keys=False))

    result = run_validator("--root", copy_root)

    assert result.returncode == 1
    assert "projection.value_proof references unknown primitive(s): missing-primitive" in result.stderr


def test_vltima_kernel_emits_derived_projection_json():
    result = run_validator("--json-output")

    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    assert data["kind"] == "vltima.kernel-projection"
    assert data["schema_version"] == 1
    assert data["projections"]["organ_kernel"][0] == {"id": "member", "label": "Member"}
    assert data["projections"]["record_proof"] == [
        {"id": "event", "label": "Event"},
        {"id": "record", "label": "Record"},
        {"id": "standing", "label": "Standing"},
    ]
    by_id = {primitive["id"]: primitive for primitive in data["primitives"]}
    assert by_id["governance"]["sources"] == ["actor", "agent", "system", "record", "covenant"]
    assert {"from": "record", "to": "standing", "type": "source"} in data["edges"]
    assert {"from": "covenant", "to": "governance", "type": "source"} in data["edges"]
    graph_nodes = {node["id"]: node for node in data["graph"]["nodes"]}
    assert graph_nodes["layer:lower"]["kind"] == "layer"
    assert graph_nodes["primitive:record"]["kind"] == "primitive"
    assert graph_nodes["projection:organ_kernel"]["kind"] == "projection"
    assert graph_nodes["organ:legal"]["kind"] == "organ"
    assert {"from": "layer:lower", "to": "primitive:record", "type": "contains"} in data["graph"]["edges"]
    assert {"from": "organ:legal", "to": "projection:organ_kernel", "type": "implements"} in data["graph"]["edges"]
    assert {"from": "projection:record_proof", "to": "primitive:record", "type": "projects"} in data["graph"]["edges"]
    assert {"from": "primitive:record", "to": "primitive:standing", "type": "source"} in data["graph"]["edges"]
    assert any(organ["pillar"] == "legal" and organ["organ_kernel"] for organ in data["organs"])


def test_vltima_graph_validation_rejects_dangling_edges():
    module = load_validator_module()

    errors = module._validate_graph(
        {
            "nodes": [{"id": "primitive:record", "kind": "primitive"}],
            "edges": [{"from": "primitive:record", "to": "primitive:missing", "type": "source"}],
        }
    )

    assert errors == ["vltima graph edge[0] references missing target node: primitive:missing"]


def test_vltima_projection_contract_rejects_wrong_kind_and_missing_graph():
    module = load_validator_module()

    errors = module._validate_projection_contract(
        {
            "kind": "wrong",
            "schema_version": 1,
            "primitives": [{"id": "record"}],
            "edges": [],
            "layers": {},
            "projections": {},
            "organs": [{"pillar": "legal"}],
        }
    )

    assert "vltima projection kind must be 'vltima.kernel-projection'" in errors
    assert "vltima projection graph must be a mapping" in errors


def test_vltima_kernel_rejects_organ_missing_projection(tmp_path):
    copy_root = tmp_path / "repo"
    shutil.copytree(ROOT / "organs", copy_root / "organs")
    shutil.copy2(ROOT / "organ-ladder.json", copy_root / "organ-ladder.json")
    kernel = copy_root / "organs" / "hr" / "KERNEL.md"
    kernel.write_text("# HR\n\nMember Mandate Standard Governance\n\nMACRO deployment\n\nMICRO deployment\n")

    result = run_validator("--root", copy_root)

    assert result.returncode == 1
    assert "hr: organs/hr/KERNEL.md missing primitive(s): Standing" in result.stderr

#!/usr/bin/env python3
"""Validate the VLTIMA universal kernel and each organ's institutional projection."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_UNIVERSAL_TERMS = (
    "Object",
    "Subject",
    "Agent",
    "Actor",
    "System",
    "Event",
    "Record",
    "Covenant",
    "Member",
    "Mandate",
    "Standing",
    "Standard",
    "Governance",
    "Exchange",
    "Entitlement",
    "Obligation",
)

REQUIRED_ORGAN_TERMS = ("Member", "Mandate", "Standing", "Standard", "Governance")


def _missing_terms(text: str, terms: tuple[str, ...]) -> list[str]:
    return [term for term in terms if term.lower() not in text.lower()]


def _load_kernel_registry(root: Path) -> tuple[dict[str, object] | None, list[str]]:
    path = root / "organs" / "vltima" / "kernel.yaml"
    if not path.exists():
        return None, ["organs/vltima/kernel.yaml is missing"]
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except Exception as exc:  # noqa: BLE001
        return None, [f"organs/vltima/kernel.yaml is unreadable: {exc}"]
    if not isinstance(data, dict):
        return None, ["organs/vltima/kernel.yaml must contain a mapping"]
    return data, []


def _registry_terms(registry: dict[str, object]) -> tuple[dict[str, str], dict[str, list[str]], list[str]]:
    errors: list[str] = []
    labels_by_id: dict[str, str] = {}
    layer_ids: dict[str, list[str]] = {}
    layers = registry.get("layers")
    if not isinstance(layers, dict):
        return labels_by_id, layer_ids, ["organs/vltima/kernel.yaml missing layers mapping"]
    for layer_name, raw_items in layers.items():
        if not isinstance(raw_items, list):
            errors.append(f"organs/vltima/kernel.yaml layer {layer_name} must be a list")
            continue
        ids: list[str] = []
        for index, item in enumerate(raw_items):
            if not isinstance(item, dict):
                errors.append(f"organs/vltima/kernel.yaml layer {layer_name}[{index}] must be a mapping")
                continue
            primitive_id = str(item.get("id") or "").strip()
            label = str(item.get("label") or "").strip()
            meaning = str(item.get("meaning") or "").strip()
            if not primitive_id or not label or not meaning:
                errors.append(f"organs/vltima/kernel.yaml layer {layer_name}[{index}] needs id, label, and meaning")
                continue
            if primitive_id in labels_by_id:
                errors.append(f"organs/vltima/kernel.yaml duplicate primitive id: {primitive_id}")
                continue
            labels_by_id[primitive_id] = label
            ids.append(primitive_id)
        layer_ids[str(layer_name)] = ids

    missing = [term for term in REQUIRED_UNIVERSAL_TERMS if term not in labels_by_id.values()]
    if missing:
        errors.append(f"organs/vltima/kernel.yaml missing required primitive(s): {', '.join(missing)}")

    for required_layer in ("lower", "institutional", "value"):
        if required_layer not in layer_ids:
            errors.append(f"organs/vltima/kernel.yaml missing layer: {required_layer}")

    known_ids = set(labels_by_id)
    for layer_name, raw_items in layers.items():
        if not isinstance(raw_items, list):
            continue
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            primitive_id = str(item.get("id") or "").strip()
            sources = item.get("sources") or []
            if sources and (not isinstance(sources, list) or any(not isinstance(source, str) for source in sources)):
                errors.append(f"organs/vltima/kernel.yaml primitive {primitive_id} sources must be a string list")
                continue
            unknown = [source for source in sources if source not in known_ids]
            if unknown:
                errors.append(
                    f"organs/vltima/kernel.yaml primitive {primitive_id} references unknown source(s): "
                    f"{', '.join(unknown)}"
                )

    projection = registry.get("projection")
    if not isinstance(projection, dict):
        errors.append("organs/vltima/kernel.yaml missing projection mapping")
    else:
        for projection_name, raw_projection in projection.items():
            if not isinstance(raw_projection, list) or any(not isinstance(item, str) for item in raw_projection):
                errors.append(f"organs/vltima/kernel.yaml projection.{projection_name} must be a string list")
                continue
            unknown = [item for item in raw_projection if item not in known_ids]
            if unknown:
                errors.append(
                    f"organs/vltima/kernel.yaml projection.{projection_name} references unknown primitive(s): "
                    + ", ".join(unknown)
                )

        organ_projection = projection.get("organ_kernel")
        if not isinstance(organ_projection, list) or any(not isinstance(item, str) for item in organ_projection):
            errors.append("organs/vltima/kernel.yaml projection.organ_kernel must be a string list")
        else:
            projected_labels = [labels_by_id.get(item, "") for item in organ_projection]
            missing_projected = [term for term in REQUIRED_ORGAN_TERMS if term not in projected_labels]
            if missing_projected:
                errors.append(
                    "organs/vltima/kernel.yaml projection.organ_kernel missing primitive(s): "
                    + ", ".join(missing_projected)
                )

    return labels_by_id, layer_ids, errors


def _load_ladder(root: Path) -> tuple[dict[str, object] | None, list[str]]:
    ladder_path = root / "organ-ladder.json"
    try:
        ladder = json.loads(ladder_path.read_text())
    except Exception as exc:  # noqa: BLE001
        return None, [f"organ-ladder.json is unreadable: {exc}"]
    if not isinstance(ladder, dict):
        return None, ["organ-ladder.json must contain a mapping"]
    return ladder, []


def _primitive_ref(labels_by_id: dict[str, str], primitive_id: str) -> dict[str, str]:
    return {"id": primitive_id, "label": labels_by_id.get(primitive_id, "")}


def build_projection(root: Path) -> tuple[dict[str, object] | None, list[str]]:
    registry, errors = _load_kernel_registry(root)
    if registry is None:
        return None, errors
    labels_by_id, layer_ids, term_errors = _registry_terms(registry)
    errors.extend(term_errors)
    ladder, ladder_errors = _load_ladder(root)
    errors.extend(ladder_errors)
    if errors or ladder is None:
        return None, errors

    projection = registry.get("projection") or {}
    projection_map = {
        name: [_primitive_ref(labels_by_id, primitive_id) for primitive_id in ids]
        for name, ids in projection.items()
        if isinstance(ids, list)
    }

    organs: list[dict[str, object]] = []
    seen_homes: set[str] = set()
    for organ in ladder.get("organs") or []:
        if not isinstance(organ, dict):
            continue
        home = str(organ.get("home") or "")
        if not home or home in seen_homes:
            continue
        seen_homes.add(home)
        organs.append(
            {
                "pillar": str(organ.get("pillar") or ""),
                "home": home,
                "domain_map": str(organ.get("domain_map") or ""),
                "macro": str(organ.get("macro") or ""),
                "micro": str(organ.get("micro") or ""),
                "first_artifact": str(organ.get("first_artifact") or ""),
                "organ_kernel": projection_map.get("organ_kernel", []),
            }
        )

    return {
        "version": registry.get("version"),
        "layers": {
            layer_name: [_primitive_ref(labels_by_id, primitive_id) for primitive_id in ids]
            for layer_name, ids in layer_ids.items()
        },
        "projections": projection_map,
        "organs": organs,
    }, []


def validate(root: Path) -> list[str]:
    errors: list[str] = []
    registry, registry_errors = _load_kernel_registry(root)
    errors.extend(registry_errors)
    labels_by_id: dict[str, str] = {}
    layer_ids: dict[str, list[str]] = {}
    if registry:
        labels_by_id, layer_ids, registry_term_errors = _registry_terms(registry)
        errors.extend(registry_term_errors)
    universal_terms = tuple(labels_by_id.values()) if labels_by_id else REQUIRED_UNIVERSAL_TERMS
    organ_terms = tuple(labels_by_id[item] for item in layer_ids.get("institutional", []) if item in labels_by_id)
    if not organ_terms:
        organ_terms = REQUIRED_ORGAN_TERMS

    kernel = root / "organs" / "vltima" / "KERNEL.md"
    if not kernel.exists():
        errors.append("organs/vltima/KERNEL.md is missing")
    else:
        missing = _missing_terms(kernel.read_text(), universal_terms)
        if missing:
            errors.append(f"organs/vltima/KERNEL.md is missing term(s): {', '.join(missing)}")

    ladder, ladder_errors = _load_ladder(root)
    if ladder_errors:
        return errors + ladder_errors
    assert ladder is not None

    seen_homes: set[str] = set()
    for organ in ladder.get("organs") or []:
        if not isinstance(organ, dict):
            continue
        pillar = str(organ.get("pillar") or "<missing-pillar>")
        home = str(organ.get("home") or "")
        if not home or home in seen_homes:
            continue
        seen_homes.add(home)

        for field in ("domain_map", "macro", "micro", "first_artifact"):
            if not str(organ.get(field) or "").strip():
                errors.append(f"{pillar}: organ-ladder.json missing {field}")

        organ_kernel = root / home / "KERNEL.md"
        if not organ_kernel.exists():
            errors.append(f"{pillar}: {home}KERNEL.md is missing")
            continue
        text = organ_kernel.read_text()
        missing = _missing_terms(text, organ_terms)
        if missing:
            errors.append(f"{pillar}: {home}KERNEL.md missing primitive(s): {', '.join(missing)}")
        if "macro" not in text.lower():
            errors.append(f"{pillar}: {home}KERNEL.md missing MACRO deployment")
        if "micro" not in text.lower():
            errors.append(f"{pillar}: {home}KERNEL.md missing MICRO deployment")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--json-output", action="store_true", help="Emit the derived kernel projection as JSON.")
    args = parser.parse_args()

    root = args.root.resolve()
    errors = validate(root)
    if errors:
        print(f"vltima-kernel: blocked with {len(errors)} issue(s)", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    if args.json_output:
        projection, projection_errors = build_projection(root)
        if projection_errors:
            print(f"vltima-kernel: blocked with {len(projection_errors)} issue(s)", file=sys.stderr)
            for error in projection_errors:
                print(f"  - {error}", file=sys.stderr)
            return 1
        print(json.dumps(projection, indent=2, sort_keys=True))
        return 0

    if not args.quiet:
        print("vltima-kernel: universal kernel and organ projections valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

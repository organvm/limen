#!/usr/bin/env python3
"""lane-fitness — shadow-only provider-route fitness from verified trajectories.

Reads atomic terminal ``limen.execution_trajectory.v1`` attempt records, computes shadow
per-(provider_route, frozen_task_class) conversion rates, and writes the observable
``logs/lane-fitness.json`` report.  Dispatch may record what this report *would*
recommend, but it must not steer work until attribution fixtures establish authority.

Named params (env-overridable, declared in institutio/governance/parameters.yaml):
  LIMEN_FITNESS_MIN_N       (default 5)    min attempts before a pair is judged fit/unfit
  LIMEN_FITNESS_UNFIT_RATE  (default 0.25) conversion rate below which a pair is "unfit"
  LIMEN_FITNESS_WINDOW_DAYS (default 30)   rolling window in days for terminal attempts

No task-board events are consumed. PII-clean: only frozen task classes and keeper/route ids.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
SCRIPT_ROOT = Path(__file__).resolve().parents[1]
# The default/--check path is a zero-write inspection, including incidental import bytecode.
sys.dont_write_bytecode = True
sys.path.insert(0, str(SCRIPT_ROOT / "cli" / "src"))

from limen.execution_trajectory import ReceiptAuthority, load_trajectory_source, verified_value_credit  # noqa: E402


TRAJECTORIES = ROOT / "logs" / "execution-trajectories" / "attempts"
FITNESS_JSON = ROOT / "logs" / "lane-fitness.json"


def _env_int(name: str, default: int) -> int:
    try:
        v = int(os.environ.get(name, default))
        return v if v > 0 else default
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        v = float(os.environ.get(name, default))
        return v if 0.0 <= v <= 1.0 else default
    except (TypeError, ValueError):
        return default


def compute(
    *,
    min_attempts: int,
    unfit_rate: float,
    window_days: int,
    trajectories_path: Path | None = None,
    now: datetime | None = None,
    receipt_authority: ReceiptAuthority | None = None,
) -> dict:
    """Compute shadow route fitness and separate keeper credit from unique attempts."""

    generated_at = now or datetime.now(timezone.utc)
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=timezone.utc)
    cutoff = generated_at - timedelta(days=window_days)
    corpus = load_trajectory_source(trajectories_path or TRAJECTORIES)

    # tallies[provider_route][frozen_task_class] = [verified_value, attempted]
    tallies: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    keeper_tallies: dict[str, list[int]] = defaultdict(lambda: [0, 0])

    considered_attempts = 0
    for trajectory in corpus.records:
        if trajectory.ended_at < cutoff:
            continue
        considered_attempts += 1
        value = verified_value_credit(trajectory, receipt_authority=receipt_authority)
        keeper_tallies[trajectory.executing_keeper][1] += 1
        keeper_tallies[trajectory.executing_keeper][0] += value
        classes = (trajectory.classification.task_type, *trajectory.classification.labels)
        for task_class in classes:
            tallies[trajectory.provider_route][task_class][1] += 1
            tallies[trajectory.provider_route][task_class][0] += value

    pairs: dict[str, dict[str, dict]] = {}
    unfit_pairs: list[dict] = []

    for provider_route, classes in sorted(tallies.items()):
        pairs[provider_route] = {}
        for cls, (verified, attempted) in sorted(classes.items(), key=lambda item: -item[1][1]):
            rate = round(verified / attempted, 4) if attempted else 0.0
            if receipt_authority is None or attempted < min_attempts:
                fit: bool | None = None
            elif rate < unfit_rate:
                fit = False
            else:
                fit = True
            pairs[provider_route][cls] = {
                "verified_value": verified,
                "attempted": attempted,
                "rate": rate,
                "fit": fit,
            }
            if fit is False:
                unfit_pairs.append(
                    {
                        "provider_route": provider_route,
                        "task_class": cls,
                        "verified_value": verified,
                        "attempted": attempted,
                        "rate": rate,
                    }
                )

    unfit_pairs.sort(key=lambda x: -x["attempted"])
    route_count = len([route for route in pairs if any(v["fit"] is False for v in pairs[route].values())])
    summary = f"{len(unfit_pairs)} shadow-unfit pairs across {route_count} provider routes"

    keeper_credit = {}
    for keeper, (verified, attempted) in sorted(keeper_tallies.items()):
        keeper_credit[keeper] = {
            "verified_value": verified,
            "attempted": attempted,
            "rate": round(verified / attempted, 4) if attempted else 0.0,
        }

    return {
        "schema": "limen.lane_fitness_shadow.v1",
        "mode": "shadow",
        "authoritative": False,
        "steering_enabled": False,
        "value_authority": {
            "ready": receipt_authority is not None,
            "adapter": getattr(receipt_authority, "__name__", None) if receipt_authority is not None else None,
            "reason": (
                "owner-native receipt adapter supplied"
                if receipt_authority is not None
                else "board receipt claims are evidence only; owner-native acceptance adapter is unavailable"
            ),
        },
        "source_schema": "limen.execution_trajectory.v1",
        "generated": generated_at.isoformat(),
        "params": {
            "min_attempts": min_attempts,
            "unfit_rate": unfit_rate,
            "window_days": window_days,
        },
        "pairs": pairs,
        "keeper_credit": keeper_credit,
        "unfit_pairs": unfit_pairs,
        "considered_attempts": considered_attempts,
        "corpus": corpus.summary(),
        "summary": summary,
    }


def _print_table(data: dict) -> None:
    params = data.get("params", {})
    print(f"=== LANE FITNESS SHADOW ({data.get('summary', '?')}) ===")
    print("mode: shadow-only (observable; never dispatch authority)")
    print(
        f"params: min_attempts={params.get('min_attempts')} "
        f"unfit_rate={params.get('unfit_rate')} "
        f"window_days={params.get('window_days')}"
    )
    print()
    unfit = data.get("unfit_pairs", [])
    print(
        f"TOP SHADOW-UNFIT PAIRS (>={params.get('min_attempts')} attempts, "
        f"<{int((params.get('unfit_rate') or 0) * 100)}% verified-value rate):"
    )
    for u in unfit[:30]:
        print(
            f"  {u['provider_route']:20} {u['task_class']:36} {u['verified_value']}/{u['attempted']} = {u['rate']:.1%}"
        )
    if len(unfit) > 30:
        print(f"  ... and {len(unfit) - 30} more")
    print()
    print(f"generated: {data.get('generated')}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Compute shadow provider-route fitness from execution trajectories")
    ap.add_argument("--check", action="store_true", help="Print table only, no write (the default)")
    ap.add_argument("--write", action="store_true", help="Explicitly publish logs/lane-fitness.json")
    ap.add_argument(
        "--trajectories",
        type=Path,
        default=TRAJECTORIES,
        help="atomic trajectory directory (legacy JSONL fixture paths remain readable)",
    )
    args = ap.parse_args()

    min_attempts = _env_int("LIMEN_FITNESS_MIN_N", 5)
    unfit_rate = _env_float("LIMEN_FITNESS_UNFIT_RATE", 0.25)
    window_days = _env_int("LIMEN_FITNESS_WINDOW_DAYS", 30)

    data = compute(
        min_attempts=min_attempts,
        unfit_rate=unfit_rate,
        window_days=window_days,
        trajectories_path=args.trajectories,
    )
    _print_table(data)

    if args.check and args.write:
        ap.error("--check and --write are mutually exclusive")

    if args.write:
        FITNESS_JSON.parent.mkdir(exist_ok=True)
        try:
            FITNESS_JSON.write_text(json.dumps(data, indent=2))
            print(f"wrote {FITNESS_JSON}")
        except OSError as e:
            print(f"lane-fitness: could not write {FITNESS_JSON} ({e})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

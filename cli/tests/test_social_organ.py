import importlib.util
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / "organs" / "social" / "validate-social.py"
BRIEF = ROOT / "organs" / "social" / "scripts" / "relationship-brief.py"
TRIAGE = ROOT / "organs" / "social" / "scripts" / "triage-dashboard.py"
DEREK = ROOT / "organs" / "social" / "engagements" / "derek.yaml"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def _run(script: Path, *args: str | Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *(str(arg) for arg in args)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_social_fleet_validator_passes():
    result = _run(VALIDATOR, "--fleet", "--quiet")
    assert result.returncode == 0, result.stdout + result.stderr


def test_social_validator_rejects_missing_human_gate(tmp_path: Path):
    broken = tmp_path / "broken.yaml"
    broken.write_text(
        """
member:
  name: Test
mandate:
  relationship: test relationship
standing:
  current: ACTIVE
standard:
  reciprocity_norm: care
governance:
  manual_mode: true
  never_autonomous:
    - Sending messages
artifacts:
  next_reviewable_output: review
  evidence:
    - real field evidence
""".lstrip(),
        encoding="utf-8",
    )

    result = _run(VALIDATOR, broken)
    assert result.returncode == 1
    assert "human_gates must name at least one human gate" in result.stdout


def test_relationship_brief_is_reproducible():
    import yaml

    brief = _load("social_relationship_brief_test", BRIEF)
    doc = yaml.safe_load(DEREK.read_text(encoding="utf-8"))
    out = brief.generate_brief(doc, DEREK, generated_at="2026-07-04T10:21:37Z")

    assert "**Generated:** 2026-07-04T10:21:37Z" in out
    assert "## 5. Governance (authority and consent)" in out
    assert "creative-deliverable-review" in out


def test_triage_dashboard_orders_repair_before_active(tmp_path: Path):
    social = tmp_path / "social"
    engagements = social / "engagements"
    engagements.mkdir(parents=True)
    (engagements / "active.yaml").write_text(
        """
member: {name: Active Person, identifier: active}
mandate: {relationship: collaborator}
standing: {current: ACTIVE, warmth: current}
standard:
  owed_replies: [Reply to active thread]
  care_pattern: Stay current
governance:
  manual_mode: true
  human: Anthony
  human_gates: [review]
  never_autonomous: [Sending messages]
artifacts: {next_reviewable_output: active brief}
updated: "2026-07-04T10:21:37Z"
""".lstrip(),
        encoding="utf-8",
    )
    (engagements / "strained.yaml").write_text(
        """
member: {name: Strained Person, identifier: strained}
mandate: {relationship: collaborator}
standing: {current: STRAINED, warmth: low}
standard:
  owed_replies: [Repair note]
  care_pattern: Repair only after review
governance:
  manual_mode: true
  human: Anthony
  human_gates: [repair-review]
  never_autonomous: [Sending messages]
artifacts: {next_reviewable_output: repair packet}
updated: "2026-07-04T10:21:37Z"
""".lstrip(),
        encoding="utf-8",
    )

    triage = _load("social_triage_dashboard_test", TRIAGE)
    out = triage.generate_dashboard(social, generated_at="2026-07-04T10:21:37Z")

    assert "**Generated:** 2026-07-04T10:21:37Z" in out
    assert out.index("Strained Person") < out.index("Active Person")
    assert "repair-review" in out
    assert "draft-only; no autonomous messages" in out

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / "organs" / "legal" / "validate-legal.py"


def run_validator(*args: str | Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VALIDATOR), *(str(arg) for arg in args)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_legal_matter_fleet_passes():
    result = run_validator("--fleet", "--quiet")
    assert result.returncode == 0, result.stdout + result.stderr


def test_legal_validator_rejects_missing_counsel_gate(tmp_path):
    matter_dir = tmp_path / "matter"
    matter_dir.mkdir()
    (matter_dir / "drafts").mkdir()

    marker = "DRAFT - COUNSEL REVIEW ONLY - NOT LEGAL ADVICE\n\nBROKEN-CUST-001\n"
    for name in [
        "posture.md",
        "chain-of-custody.md",
        "elements-map.md",
        "deadlines.md",
        "ethics-log.md",
    ]:
        (matter_dir / name).write_text(marker)
    (matter_dir / "drafts" / "note.md").write_text(marker)
    (matter_dir / "framework.md").write_text(marker)
    (matter_dir / "evidence-index.csv").write_text(
        "\n".join(
            [
                "evidence_id,title,source_path,source_type,record_date,ingested_at,provenance_owner,custody_status,custody_entry,evidence_role,linked_elements,confidentiality,review_status,notes",
                "BROKEN-001,Kernel source,organs/legal/KERNEL.md,institutional_source_not_primary_case_evidence,2026-07-04,2026-07-04T00:00:00Z,repo,repo-controlled copy,BROKEN-CUST-001,boundary,governance,internal,client-confirmed,real source",
            ]
        )
        + "\n"
    )
    (matter_dir / "matter.yaml").write_text(
        """
schema_version: legal-matter-v1
id: broken
name: Broken matter
member:
  client: Test client
mandate:
  matter_type: operations packet
standing:
  current: COUNSEL_REVIEW
standard:
  source_records:
    - organs/legal/KERNEL.md
governance:
  counsel_review_required: true
  draft_only: true
  no_autonomous_external_action: true
  no_independent_attorney_client_relationship: true
  forbidden_acts:
    - legal advice
    - filing
    - service
    - sending external communications
    - settlement authority
    - legal judgment
human_gates:
  - Anthony controls primary records.
artifacts:
  posture: posture.md
  evidence_index: evidence-index.csv
  chain_of_custody: chain-of-custody.md
  elements_map: elements-map.md
  deadlines: deadlines.md
  ethics_log: ethics-log.md
  review_note: drafts/note.md
  framework_deck: framework.md
""".lstrip()
    )

    result = run_validator(matter_dir / "matter.yaml")
    assert result.returncode == 1
    assert "Rule #2 violation: human_gates must include counsel review" in result.stdout

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


def write_minimal_packet(path: Path) -> None:
    path.mkdir()
    boundary = "This does not give legal advice and counsel owns review.\n"
    for name in [
        "README.md",
        "intake.md",
        "posture.md",
        "deadlines.md",
        "ethics-log.md",
    ]:
        (path / name).write_text(boundary, encoding="utf-8")
    (path / "chain-of-custody.md").write_text(
        "Custody record for counsel review.\n",
        encoding="utf-8",
    )
    (path / "MICAH-FRAMEWORK-DECK.md").write_text(
        boundary
        + "organs/legal/matters/anthony-ada-employment/\n"
        + "posture.md\n"
        + "evidence-index.csv\n"
        + "chain-of-custody.md\n"
        + "ethics-log.md\n",
        encoding="utf-8",
    )
    (path / "evidence-index.csv").write_text(
        "\n".join(
            [
                "evidence_id,date_or_range,source_kind,source_or_location,"
                "custodian_or_source,artifact_type,provenance,chain_of_custody,"
                "operational_use,review_status,privilege_confidentiality,notes",
                "L-1,2026-07-03,repo,file.md,repo,doc,git,repo to review,"
                "structure,structure_ready,public,not case evidence",
                "L-2,unprovided,client,records,client,docs,not ingested,"
                "privileged intake needed,chronology,missing_input,privileged,"
                "needed source category",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    drafts = path / "drafts"
    drafts.mkdir()
    (drafts / "note.md").write_text(
        "# DRAFT - NOT SENT\n\nDo not send without counsel review.\n",
        encoding="utf-8",
    )


def test_legal_matter_fleet_passes() -> None:
    result = run_validator("--fleet", "--quiet")
    assert result.returncode == 0, result.stdout + result.stderr


def test_legal_validator_rejects_missing_chain_of_custody(tmp_path: Path) -> None:
    packet = tmp_path / "matter"
    write_minimal_packet(packet)
    text = (packet / "evidence-index.csv").read_text(encoding="utf-8")
    text = text.replace("repo to review", "")
    (packet / "evidence-index.csv").write_text(text, encoding="utf-8")

    result = run_validator(packet)

    assert result.returncode == 1
    assert "has empty 'chain_of_custody'" in result.stdout


def test_legal_validator_rejects_unmarked_outbound_draft(tmp_path: Path) -> None:
    packet = tmp_path / "matter"
    write_minimal_packet(packet)
    (packet / "drafts" / "note.md").write_text(
        "Please send this after review.\n",
        encoding="utf-8",
    )

    result = run_validator(packet)

    assert result.returncode == 1
    assert "missing 'DRAFT - NOT SENT'" in result.stdout

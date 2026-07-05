import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / "scripts" / "validate-vltima-kernel.py"


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


def test_vltima_kernel_rejects_organ_missing_projection(tmp_path):
    copy_root = tmp_path / "repo"
    shutil.copytree(ROOT / "organs", copy_root / "organs")
    shutil.copy2(ROOT / "organ-ladder.json", copy_root / "organ-ladder.json")
    kernel = copy_root / "organs" / "hr" / "KERNEL.md"
    kernel.write_text("# HR\n\nMember Mandate Standard Governance\n\nMACRO deployment\n\nMICRO deployment\n")

    result = run_validator("--root", copy_root)

    assert result.returncode == 1
    assert "hr: organs/hr/KERNEL.md missing primitive(s): Standing" in result.stderr

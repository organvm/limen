import importlib.util
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "session-blockers-ledger.py"


def _load():
    spec = importlib.util.spec_from_file_location("session_blockers_ledger", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_fmt_bytes():
    ledger = _load()
    assert ledger.fmt_bytes(500) == "500 B"
    assert ledger.fmt_bytes(1024) == "1.0 KiB"
    assert ledger.fmt_bytes(1536) == "1.5 KiB"
    assert ledger.fmt_bytes(1048576) == "1.0 MiB"


def test_states_text():
    ledger = _load()
    assert ledger.states_text({}) == "none"
    assert ledger.states_text({"idle": 2, "active": 5}) == "active 5, idle 2"


def test_relpath():
    ledger = _load()
    # Test with a path inside home
    home = Path.home()
    test_path = home / "test_dir" / "file.txt"
    assert ledger.relpath(test_path) == "~/test_dir/file.txt"

    # Test with root path (outside home)
    root_path = Path("/tmp")
    assert ledger.relpath(root_path) == "/tmp"

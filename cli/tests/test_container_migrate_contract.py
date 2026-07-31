from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATE = ROOT / "container" / "migrate.sh"


def test_committed_plist_is_source_and_deployed_plist_is_destination() -> None:
    text = MIGRATE.read_text(encoding="utf-8")

    assert 'CANONICAL_PLIST="$CONT/launchd/com.limen.heartbeat.plist"' in text
    assert 'cp "$CANONICAL_PLIST" "$PLIST"' in text
    assert 'cp -p "$PLIST" "$CONT/launchd/$LABEL.plist"' not in text
    assert '[ -f "$CANONICAL_PLIST" ] || die "committed canonical plist missing:' in text

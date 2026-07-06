import importlib.util
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "mail-story-ledger.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("mail_story_ledger_uut", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _ts(year: int, month: int, day: int) -> int:
    return int(datetime(year, month, day, 12, 0, tzinfo=timezone.utc).timestamp())


def _mail_index(tmp_path: Path) -> Path:
    db = tmp_path / "Envelope Index"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE messages (
            ROWID INTEGER PRIMARY KEY,
            global_message_id INTEGER NOT NULL,
            conversation_id INTEGER NOT NULL,
            date_received INTEGER,
            flagged INTEGER NOT NULL DEFAULT 0,
            flag_color INTEGER,
            read INTEGER NOT NULL DEFAULT 0,
            deleted INTEGER NOT NULL DEFAULT 0,
            sender INTEGER,
            subject INTEGER,
            summary INTEGER,
            mailbox INTEGER
        );
        CREATE TABLE addresses (
            ROWID INTEGER PRIMARY KEY,
            address TEXT NOT NULL,
            comment TEXT NOT NULL
        );
        CREATE TABLE subjects (
            ROWID INTEGER PRIMARY KEY,
            subject TEXT NOT NULL
        );
        CREATE TABLE summaries (
            ROWID INTEGER PRIMARY KEY,
            summary TEXT NOT NULL
        );
        CREATE TABLE mailboxes (
            ROWID INTEGER PRIMARY KEY,
            url TEXT NOT NULL
        );
        CREATE TABLE message_global_data (
            ROWID INTEGER PRIMARY KEY,
            message_id_header TEXT
        );
        """
    )
    conn.executemany(
        "INSERT INTO addresses VALUES (?, ?, ?)",
        [
            (1, "notifications@stripe.example.test", "Stripe Private"),
            (2, "no_reply@email.apple.com", "Apple"),
            (3, "alerts@nelnet.studentaid.gov", "Nelnet"),
            (4, "friend@gmail.com", "Private Friend"),
            (5, "billing@mail.anthropic.com", "Anthropic"),
            (6, "info@hostinger.com", "Hostinger"),
            (7, "recruiter@stage4solutions.com", "Stage 4 Solutions"),
            (8, "notices@docusign.net", "DocuSign"),
            (9, "alerts@santanderbank.com", "Santander"),
            (10, "no-reply@mychart.example.test", "Patient Portal"),
            (11, "digest@socket.dev", "Socket"),
            (12, "tickets@laughingbuddhacomedy.com", "Laughing Buddha"),
            (13, "security@cloudflare.com", "Cloudflare"),
        ],
    )
    conn.executemany(
        "INSERT INTO subjects VALUES (?, ?)",
        [
            (1, "KYC verify identity for private@example.test account 123456 should not leak"),
            (2, "Billing Problem"),
            (3, "Student Loan Default Notice"),
            (4, "Security alert should not be processed in flagged scope"),
            (5, "Deleted flagged notice should not count"),
            (6, "Anthropic billing payment failed"),
            (7, "Hostinger domain DNS custody warning"),
            (8, "UX Specialist recruiting opportunity"),
            (9, "DocuSign court government benefit notice"),
            (10, "Santander fraud alert"),
            (11, "Health appointment lab follow-up"),
            (12, "Socket release newsletter"),
            (13, "Laughing Buddha comedy ticket order complete"),
            (14, "Personal reminder return context"),
            (15, "Cloudflare security alert"),
        ],
    )
    conn.executemany(
        "INSERT INTO summaries VALUES (?, ?)",
        [
            (1, "private body-ish summary should stay private"),
            (2, "Your payment method needs attention."),
            (3, "Your student loan needs review."),
            (4, "Your domain records need review."),
            (5, "A recruiting role needs a reply."),
            (6, "A legal document needs review."),
            (7, "A care appointment requires follow-up."),
        ],
    )
    conn.executemany(
        "INSERT INTO mailboxes VALUES (?, ?)",
        [
            (1, "imap://fixture/%5BGmail%5D/All%20Mail"),
            (2, "imap://fixture/INBOX"),
        ],
    )
    conn.executemany(
        "INSERT INTO message_global_data VALUES (?, ?)",
        [
            (101, "<stripe-private@example.test>"),
            (102, "<apple-billing@example.test>"),
            (103, "<nelnet-default@example.test>"),
            (104, "<friend-security@example.test>"),
            (105, "<deleted@example.test>"),
            (106, "<anthropic-billing@example.test>"),
            (107, "<hostinger-domain@example.test>"),
            (108, "<stage4-role@example.test>"),
            (109, "<docusign-legal@example.test>"),
            (110, "<santander-fraud@example.test>"),
            (111, "<health-appointment@example.test>"),
            (112, "<socket-newsletter@example.test>"),
            (113, "<ticket-event@example.test>"),
            (114, "<friend-personal@example.test>"),
            (115, "<cloudflare-security@example.test>"),
        ],
    )
    conn.executemany(
        """
        INSERT INTO messages (
            ROWID, global_message_id, conversation_id, date_received, flagged,
            flag_color, read, deleted, sender, subject, summary, mailbox
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (1, 101, 1001, _ts(2026, 7, 6), 1, 1, 1, 0, 1, 1, 1, 1),
            (2, 102, 1002, _ts(2026, 7, 5), 1, 1, 0, 0, 2, 2, 2, 2),
            (3, 103, 1003, _ts(2025, 6, 1), 1, 1, 1, 0, 3, 3, 3, 1),
            (4, 104, 1004, _ts(2024, 3, 1), 0, None, 1, 0, 4, 4, None, 1),
            (5, 105, 1005, _ts(2023, 1, 1), 1, 1, 1, 1, 4, 5, None, 1),
            (6, 106, 1006, _ts(2026, 6, 30), 1, 1, 1, 0, 5, 6, 2, 1),
            (7, 107, 1007, _ts(2026, 6, 29), 1, 1, 1, 0, 6, 7, 4, 1),
            (8, 108, 1008, _ts(2026, 6, 28), 1, 1, 1, 0, 7, 8, 5, 1),
            (9, 109, 1009, _ts(2026, 6, 27), 1, 1, 1, 0, 8, 9, 6, 2),
            (10, 110, 1010, _ts(2026, 6, 26), 1, 1, 1, 0, 9, 10, None, 2),
            (11, 111, 1011, _ts(2026, 6, 25), 1, 1, 1, 0, 10, 11, 7, 2),
            (12, 112, 1012, _ts(2026, 6, 24), 1, 1, 1, 0, 11, 12, None, 1),
            (13, 113, 1013, _ts(2026, 6, 23), 1, 1, 1, 0, 12, 13, None, 1),
            (14, 114, 1014, _ts(2026, 6, 22), 1, 1, 1, 0, 4, 14, None, 1),
            (15, 115, 1015, _ts(2026, 6, 21), 1, 1, 1, 0, 13, 15, None, 1),
        ],
    )
    conn.commit()
    conn.close()
    return db


def test_build_snapshot_uses_unix_dates_and_classifies_flagged_atoms(tmp_path):
    module = _load_module()
    db = _mail_index(tmp_path)

    snapshot, atoms = module.build_snapshot(db)

    assert snapshot["stats"]["total_messages"] == 15
    assert snapshot["stats"]["not_deleted_messages"] == 14
    assert snapshot["stats"]["flagged_non_deleted"] == 13
    assert snapshot["stats"]["last_received_at"].startswith("2026-07-06")
    assert not snapshot["stats"]["last_received_at"].startswith("2057")
    assert snapshot["atom_count"] == 13
    assert snapshot["reconciliation"]["no_silent_drops"] is True
    split = {(row["account"], row["mailbox"]): row["messages"] for row in snapshot["stats"]["flagged_by_mailbox"]}
    assert split == {("gmail", "all_mail"): 9, ("icloud", "inbox"): 4}
    assert {atom["cluster_id"] for atom in atoms} >= {
        "identity-compliance",
        "billing-continuity",
        "debt-default-navigation",
        "infra-custody",
        "career-routing",
        "legal-government-accountability",
        "security-risk",
        "health-admin",
        "platform-intelligence",
        "life-creative-logistics",
        "relationship-personal-admin",
    }
    assert all(atom["evidence_scope"] in {"metadata", "metadata_summary"} for atom in atoms)
    assert all(atom["status"] == "hot_flagged" for atom in atoms)
    assert all(atom["redacted_subject"] for atom in atoms)
    assert {atom["next_action"] for atom in atoms} <= {
        "human_review",
        "needs_thread_read",
        "obligation",
        "parked",
        "product_research",
    }
    assert all("candidate_products" in row for row in snapshot["clusters"])

    stripe = next(atom for atom in atoms if atom["sender_domain"] == "stripe.example.test")
    assert stripe["blocker_type"] == "identity"
    assert "private@example.test" not in stripe["redacted_subject"]
    assert "123456" not in stripe["redacted_subject"]
    assert stripe["private_evidence"]["subject"].startswith("KYC verify identity")


def test_all_scope_emits_historical_candidates(tmp_path):
    module = _load_module()
    db = _mail_index(tmp_path)

    snapshot, atoms = module.build_snapshot(db, scope="all", baseline=None)

    assert snapshot["atom_count"] == 14
    assert {atom["status"] for atom in atoms} == {"historical_candidate", "hot_flagged"}
    assert sum(1 for atom in atoms if atom["status"] == "historical_candidate") == 1


def test_connect_readonly_rejects_sqlite_writes(tmp_path):
    module = _load_module()
    db = _mail_index(tmp_path)

    with module.connect_readonly(db) as conn:
        assert conn.execute("PRAGMA query_only").fetchone()[0] == 1
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("CREATE TABLE should_fail (id INTEGER)")


def test_markdown_is_redacted_while_private_atoms_keep_source(tmp_path):
    module = _load_module()
    db = _mail_index(tmp_path)
    doc = tmp_path / "docs" / "mail-story-ledger.md"
    log = tmp_path / "logs" / "mail-story-ledger.json"
    private_atoms = tmp_path / ".limen-private" / "mail-story" / "inventory" / "atoms.jsonl"
    private_snapshot = tmp_path / ".limen-private" / "mail-story" / "inventory" / "snapshot.json"

    snapshot, atoms = module.build_snapshot(db)
    markdown = module.render_markdown(snapshot)
    module.write_outputs(
        snapshot,
        atoms,
        markdown,
        doc_path=doc,
        log_path=log,
        private_atoms=private_atoms,
        private_snapshot=private_snapshot,
    )

    public_text = doc.read_text(encoding="utf-8")
    private_text = private_atoms.read_text(encoding="utf-8")
    log_payload = json.loads(log.read_text(encoding="utf-8"))

    for forbidden in (
        "notifications@stripe.example.test",
        "Stripe Private",
        "private@example.test",
        "should not leak",
        "private body-ish summary",
        "friend@gmail.com",
    ):
        assert forbidden not in markdown
        assert forbidden not in public_text

    assert "@" not in public_text
    assert "stripe.example.test" in public_text
    assert "notifications@stripe.example.test" in private_text
    assert "private body-ish summary should stay private" in private_text
    assert log_payload["privacy"]["raw_mail_in_git"] is False
    assert log_payload["reconciliation"]["no_silent_drops"] is True

#!/usr/bin/env python3
"""Build a private mail-story atom ledger plus a redacted public summary.

This is the C_MAIL story-mining surface: Apple Mail's Envelope Index supplies a
read-only metadata inventory, ignored `.limen-private/mail-story/` receives the
raw-ish atom stream, and `docs/mail-story-ledger.md` receives only redacted
cluster/count evidence.

The script never changes Mail, Gmail, labels, flags, archives, drafts, or
`tasks.yaml`. Full thread/body enrichment is deliberately modeled as a next
action, not performed here.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import unquote


ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
DOC_PATH = ROOT / "docs" / "mail-story-ledger.md"
LOG_PATH = ROOT / "logs" / "mail-story-ledger.json"
PRIVATE_ROOT = Path(os.environ.get("LIMEN_PRIVATE_MAIL_STORY", ROOT / ".limen-private" / "mail-story"))
PRIVATE_ATOMS = PRIVATE_ROOT / "inventory" / "mail-story-atoms.jsonl"
PRIVATE_SNAPSHOT = PRIVATE_ROOT / "inventory" / "mail-story-snapshot.json"
MAIL_INDEX = Path(
    os.environ.get(
        "LIMEN_MAIL_ENVELOPE_INDEX",
        Path.home() / "Library" / "Mail" / "V10" / "MailData" / "Envelope Index",
    )
)

SCHEMA = "limen.mail_story.v1"

BASELINE_RECONCILIATION: dict[str, Any] = {
    "source": "user_brief_2026-07-06",
    "apple_total_messages": 81541,
    "apple_flagged_non_deleted": 108,
    "apple_gmail_all_mail_flagged": 97,
    "apple_icloud_inbox_flagged": 11,
    "gmail_starred_messages": 97,
    "gmail_starred_threads": 96,
}


CLUSTERS: dict[str, dict[str, Any]] = {
    "billing-continuity": {
        "blocker_type": "billing",
        "title": "Billing continuity",
        "recurring_pattern": "Payment, renewal, card, invoice, and subscription notices arrive across vendors.",
        "personal_consequence": "A renewal, card, invoice, or subscription problem can silently break an account or workflow.",
        "universal_pain_point": "People are expected to monitor scattered payment warnings across vendors and inboxes.",
        "software_thesis": "A custody layer should turn billing and renewal mail into one verified account-continuity queue.",
        "affected_life_domains": ["money", "work", "infrastructure"],
        "existing_tools_involved": ["vendor billing portals", "card networks", "email flags"],
        "failure_modes": ["late notice", "card decline", "account suspension", "renewal surprise"],
        "candidate_products": ["billing custody ledger", "renewal exception router"],
        "market_ux_thesis": "The user wants one obligation queue, not a scavenger hunt across billing portals.",
    },
    "debt-default-navigation": {
        "blocker_type": "debt",
        "title": "Debt and default navigation",
        "recurring_pattern": "Loan, tax, repayment, and default notices create a fragmented case history.",
        "personal_consequence": "Loan, tax, or repayment notices create high-stakes ambiguity without a clear action path.",
        "universal_pain_point": "Debt systems expose consequences faster than they expose trustworthy next steps.",
        "software_thesis": "A debt-navigation copilot should map notices into verified options, deadlines, and escalation paths.",
        "affected_life_domains": ["money", "legal", "career"],
        "existing_tools_involved": ["loan servicers", "tax vendors", "government portals", "email"],
        "failure_modes": ["unclear deadline", "threat without path", "servicer fragmentation"],
        "candidate_products": ["debt case file", "repayment option navigator"],
        "market_ux_thesis": "People need procedural clarity and proof, not another generic finance dashboard.",
    },
    "identity-compliance": {
        "blocker_type": "identity",
        "title": "Identity and compliance gates",
        "recurring_pattern": "KYC, account review, and verification requests block access until evidence is assembled.",
        "personal_consequence": "KYC, verification, and account-review requests block money movement or platform access.",
        "universal_pain_point": "Compliance workflows arrive as email fragments instead of an explainable case file.",
        "software_thesis": "A compliance dossier should collect requests, evidence, deadline state, and safe verification routes.",
        "affected_life_domains": ["money", "identity", "platform access"],
        "existing_tools_involved": ["KYC portals", "payment processors", "identity forms", "email"],
        "failure_modes": ["opaque review", "duplicate evidence asks", "blocked payout"],
        "candidate_products": ["compliance dossier", "verification request tracker"],
        "market_ux_thesis": "The durable product is a user-owned evidence vault with state, not a one-off upload helper.",
    },
    "legal-government-accountability": {
        "blocker_type": "legal",
        "title": "Legal and government accountability",
        "recurring_pattern": "Legal, government, benefits, and signature notices carry procedural obligations.",
        "personal_consequence": "Legal, benefits, government, and accountability notices carry consequences that are hard to sequence.",
        "universal_pain_point": "Institutional email makes citizens assemble their own procedural memory.",
        "software_thesis": "A civic/legal organizer should translate notices into timelines, obligations, and evidence packets.",
        "affected_life_domains": ["legal", "government", "money"],
        "existing_tools_involved": ["court portals", "government portals", "signature tools", "email"],
        "failure_modes": ["missed procedural step", "lost evidence", "opaque institution state"],
        "candidate_products": ["civic case ledger", "legal notice timeline"],
        "market_ux_thesis": "The UX should feel like a case file with receipts, not a to-do list.",
    },
    "career-routing": {
        "blocker_type": "career",
        "title": "Career routing",
        "recurring_pattern": "Recruiter, opportunity, interview, and role messages mix signal with staffing noise.",
        "personal_consequence": "Recruiting and opportunity messages need evaluation without swallowing the day.",
        "universal_pain_point": "Opportunity inboxes mix real leads, staffing noise, and identity fit with little ranking help.",
        "software_thesis": "A career router should score fit, extract next steps, and preserve opportunity history.",
        "affected_life_domains": ["career", "money", "identity"],
        "existing_tools_involved": ["recruiting platforms", "staffing firms", "resume systems", "email"],
        "failure_modes": ["low-fit lead", "missed good lead", "context lost across threads"],
        "candidate_products": ["career opportunity router", "fit-and-next-step extractor"],
        "market_ux_thesis": "The value is fast triage with memory of prior fit, not another job board.",
    },
    "infra-custody": {
        "blocker_type": "infra",
        "title": "Infrastructure and domain custody",
        "recurring_pattern": "Cloud, domain, DNS, API, and developer platform notices become ownership risk.",
        "personal_consequence": "Cloud, domain, developer, and platform notices can break production or ownership if missed.",
        "universal_pain_point": "Solo operators hold production custody through vendor emails instead of a coherent control plane.",
        "software_thesis": "An operator custody ledger should unify infra notices, owners, renewals, and blast-radius state.",
        "affected_life_domains": ["infrastructure", "money", "product"],
        "existing_tools_involved": ["cloud consoles", "domain registrars", "developer platforms", "email"],
        "failure_modes": ["resource expiry", "API break", "ownership drift", "unread blast-radius notice"],
        "candidate_products": ["operator custody ledger", "domain and cloud notice router"],
        "market_ux_thesis": "Operators need a cockpit that converts vendor mail into resource state and risk.",
    },
    "security-risk": {
        "blocker_type": "security",
        "title": "Security and fraud risk",
        "recurring_pattern": "Security, fraud, login, and password alerts demand action but resemble phishing.",
        "personal_consequence": "Fraud, login, and account-security alerts demand fast action but are spoof-prone.",
        "universal_pain_point": "Security email mixes real incidents with phish-like UX and no trusted verification path.",
        "software_thesis": "A verify-first security queue should route alerts through safe channels and preserve audit receipts.",
        "affected_life_domains": ["security", "money", "identity"],
        "existing_tools_involved": ["bank portals", "password managers", "account security pages", "email"],
        "failure_modes": ["spoofed link", "alert fatigue", "missed incident", "unverified recovery path"],
        "candidate_products": ["verify-first security queue", "fraud alert receipt locker"],
        "market_ux_thesis": "The product should slow the click and speed the safe verification route.",
    },
    "health-admin": {
        "blocker_type": "health",
        "title": "Health administration",
        "recurring_pattern": "Appointment, lab, pharmacy, insurance, and portal notices require careful follow-up.",
        "personal_consequence": "Health notices can carry real care consequences while being scattered across portals and reminders.",
        "universal_pain_point": "Patients are expected to coordinate care logistics from fragmented notification systems.",
        "software_thesis": "A health admin ledger should turn notices into private follow-up loops with strict privacy boundaries.",
        "affected_life_domains": ["health", "time", "money"],
        "existing_tools_involved": ["patient portals", "pharmacies", "insurers", "email"],
        "failure_modes": ["missed appointment", "lost lab follow-up", "coverage ambiguity", "privacy leak"],
        "candidate_products": ["private care follow-up ledger", "health notice router"],
        "market_ux_thesis": "The market wedge is privacy-safe coordination, not medical advice.",
    },
    "life-creative-logistics": {
        "blocker_type": "creative_life",
        "title": "Life and creative logistics",
        "recurring_pattern": "Tickets, events, creative commitments, and life receipts accumulate operational context.",
        "personal_consequence": "Events, creative practice, and life logistics become another operational queue.",
        "universal_pain_point": "Calendar-adjacent life mail is not treated as part of a personal operating system.",
        "software_thesis": "A life-logistics layer should connect tickets, commitments, receipts, and story context.",
        "affected_life_domains": ["creative_life", "time", "relationships"],
        "existing_tools_involved": ["ticket platforms", "calendar tools", "receipts", "email"],
        "failure_modes": ["lost receipt", "missed event context", "unlinked calendar state"],
        "candidate_products": ["life logistics ledger", "creative commitment tracker"],
        "market_ux_thesis": "The UX should preserve lived context without making every event a productivity chore.",
    },
    "relationship-personal-admin": {
        "blocker_type": "relationship",
        "title": "Relationship and personal administration",
        "recurring_pattern": "Human-origin messages and self-reminders carry relationship context beside vendor noise.",
        "personal_consequence": "Human-origin messages and self-sent reminders carry context that generic triage loses.",
        "universal_pain_point": "Personal administration is structurally mixed with automated vendor mail.",
        "software_thesis": "A relationship memory layer should separate human context from institutional noise.",
        "affected_life_domains": ["relationships", "time", "personal admin"],
        "existing_tools_involved": ["Gmail", "Apple Mail", "contacts", "calendar"],
        "failure_modes": ["human context buried", "owed reply lost", "automated mail overwhelms relationship mail"],
        "candidate_products": ["relationship memory ledger", "owed-reply router"],
        "market_ux_thesis": "People will trust a tool that preserves context while refusing to send on its own.",
    },
    "platform-intelligence": {
        "blocker_type": "platform",
        "title": "Platform and developer ecosystem intelligence",
        "recurring_pattern": "AI, developer, release, newsletter, and platform notices become product intelligence.",
        "personal_consequence": "Platform updates, AI/vendor notices, and developer ecosystem signals shape product decisions.",
        "universal_pain_point": "Operators need a way to convert ecosystem noise into strategic intelligence.",
        "software_thesis": "A platform-intelligence digest should cluster vendor signals into product and risk theses.",
        "affected_life_domains": ["product", "career", "infrastructure"],
        "existing_tools_involved": ["developer newsletters", "platform changelogs", "vendor dashboards", "email"],
        "failure_modes": ["signal lost in volume", "missed deprecation", "unconnected product clue"],
        "candidate_products": ["platform intelligence digest", "vendor signal graph"],
        "market_ux_thesis": "The product should convert noisy updates into decision support with provenance.",
    },
    "uncategorized-pressure": {
        "blocker_type": "other",
        "title": "Uncategorized pressure",
        "recurring_pattern": "Flagged mail without a confident class still carries enough pressure to preserve.",
        "personal_consequence": "Flagged mail without a clear class still carries enough pressure to be preserved.",
        "universal_pain_point": "People flag uncertainty because inbox tools do not support partial understanding.",
        "software_thesis": "A story-mining workflow should park ambiguous mail with evidence and a next read action.",
        "affected_life_domains": ["unknown"],
        "existing_tools_involved": ["email flags", "manual memory"],
        "failure_modes": ["ambiguous pressure", "silent drop", "premature deletion"],
        "candidate_products": ["parked evidence queue", "uncertainty triage ledger"],
        "market_ux_thesis": "The first useful UX is honest parking with the next smallest evidence step.",
    },
}


PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "identity-compliance",
        (
            r"\bkyc\b",
            r"provide information",
            r"action required",
            r"verify (your )?(identity|account|information)",
            r"account review",
            r"\bstripe\b",
        ),
    ),
    (
        "security-risk",
        (
            r"\bfraud\b",
            r"security alert",
            r"suspicious",
            r"new sign-?in",
            r"password",
            r"login",
            r"\bsantander\b",
        ),
    ),
    (
        "debt-default-navigation",
        (
            r"student ?loan",
            r"\bnelnet\b",
            r"\bstudentaid\b",
            r"\bdebt\b",
            r"\bdefault\b",
            r"\btaxrise\b",
            r"auto pay",
        ),
    ),
    (
        "billing-continuity",
        (
            r"billing",
            r"payment",
            r"invoice",
            r"renew(al|ing)?",
            r"subscription",
            r"receipt",
            r"card",
            r"declin",
            r"charge",
            r"\bamazon\b",
            r"\banthropic\b",
            r"\bgithub\b",
            r"\bapple\b",
        ),
    ),
    (
        "infra-custody",
        (
            r"domain",
            r"\bcloud\b",
            r"\bdns\b",
            r"hostinger",
            r"cloudflare",
            r"google cloud",
            r"openai",
            r"api",
            r"developer",
        ),
    ),
    (
        "legal-government-accountability",
        (
            r"\blegal\b",
            r"\bcourt\b",
            r"\bdocusign\b",
            r"\blongo\b",
            r"social security",
            r"\bssa\b",
            r"government",
            r"accountability",
            r"\bbenefit",
        ),
    ),
    (
        "health-admin",
        (
            r"\bhealth\b",
            r"\bmedical\b",
            r"\bdoctor\b",
            r"\bappointment\b",
            r"\binsurance\b",
            r"\bpharmacy\b",
            r"\bprescription\b",
            r"\blab\b",
            r"\bmychart\b",
            r"\bcvs\b",
            r"\bwalgreens\b",
        ),
    ),
    (
        "career-routing",
        (
            r"\brecruit",
            r"\binterview\b",
            r"\brole\b",
            r"\bjob\b",
            r"\bcareer\b",
            r"\bresume\b",
            r"\bopportunity\b",
            r"ux specialist",
            r"stage4solutions",
        ),
    ),
    (
        "life-creative-logistics",
        (
            r"\bticket",
            r"\bcomedy\b",
            r"\bevent\b",
            r"order complete",
            r"laughing buddha",
        ),
    ),
    (
        "platform-intelligence",
        (
            r"\bsocket\b",
            r"\bnewsletter\b",
            r"release",
            r"platform",
            r"\bai\b",
            r"developer ecosystem",
        ),
    ),
    (
        "relationship-personal-admin",
        (
            r"\bgmail\.com\b",
            r"\breturn\b",
            r"personal",
            r"reminder",
        ),
    ),
)

TYPE_WEIGHT = {
    "security": 5,
    "identity": 5,
    "debt": 5,
    "billing": 4,
    "legal": 4,
    "infra": 4,
    "health": 4,
    "career": 2,
    "platform": 2,
    "relationship": 2,
    "creative_life": 1,
    "other": 1,
}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def iso_from_unix(value: int | None) -> str | None:
    if not value:
        return None
    try:
        return dt.datetime.fromtimestamp(int(value), tz=dt.timezone.utc).isoformat().replace("+00:00", "Z")
    except (OSError, OverflowError, ValueError):
        return None


def sha(prefix: str, *parts: Any, length: int = 16) -> str:
    material = "|".join(str(part or "") for part in parts)
    return f"{prefix}_{hashlib.sha256(material.encode('utf-8')).hexdigest()[:length]}"


def connect_readonly(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(f"Apple Mail Envelope Index not found: {path}")
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    conn.execute("PRAGMA query_only = ON")
    conn.row_factory = sqlite3.Row
    return conn


EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
LONG_NUMBER_RE = re.compile(r"\b\d{4,}\b")


def redact_text(value: str | None, *, max_len: int = 96) -> str:
    text = " ".join(str(value or "").split())
    if not text:
        return ""
    text = EMAIL_RE.sub("[email]", text)
    text = LONG_NUMBER_RE.sub("[number]", text)
    if len(text) > max_len:
        text = f"{text[: max_len - 3].rstrip()}..."
    return text


def normalize_domain(address: str | None) -> str:
    if not address or "@" not in address:
        return "unknown"
    domain = address.rsplit("@", 1)[-1].strip().strip(">[]).,;:'\"").lower()
    return domain or "unknown"


def mailbox_parts(url: str | None) -> dict[str, str]:
    decoded = unquote(url or "").lower()
    if "[gmail]/all mail" in decoded:
        return {"account": "gmail", "mailbox": "all_mail", "scope": "gmail/all-mail"}
    if "[gmail]/sent mail" in decoded or decoded.endswith("/sent"):
        return {"account": "gmail", "mailbox": "sent", "scope": "gmail/sent"}
    if "icloud" in decoded:
        return {"account": "icloud", "mailbox": "mailbox", "scope": "icloud"}
    if decoded.endswith("/inbox") or "/inbox" in decoded:
        return {"account": "icloud", "mailbox": "inbox", "scope": "icloud/inbox"}
    if "archive" in decoded:
        return {"account": "unknown", "mailbox": "archive", "scope": "archive"}
    if "trash" in decoded or "deleted" in decoded:
        return {"account": "unknown", "mailbox": "trash", "scope": "trash"}
    if "junk" in decoded or "spam" in decoded:
        return {"account": "unknown", "mailbox": "junk", "scope": "junk"}
    return {"account": "unknown", "mailbox": "mailbox", "scope": "mailbox"}


def mailbox_scope(url: str | None) -> str:
    return mailbox_parts(url)["scope"]


def searchable_text(row: sqlite3.Row) -> str:
    return " ".join(
        str(row[key] or "")
        for key in ("sender_address", "sender_name", "subject", "summary", "mailbox_url")
        if key in row.keys()
    ).lower()


def classify(row: sqlite3.Row) -> tuple[str, list[str], float]:
    text = searchable_text(row)
    hits: list[str] = []
    chosen = "uncategorized-pressure"
    for cluster_id, patterns in PATTERNS:
        cluster_hits = [pattern for pattern in patterns if re.search(pattern, text, re.IGNORECASE)]
        if cluster_hits:
            chosen = cluster_id
            hits = cluster_hits[:5]
            break
    confidence = 0.56 if chosen == "uncategorized-pressure" else min(0.96, 0.7 + 0.05 * len(hits))
    return chosen, hits, confidence


def next_action(cluster_id: str, confidence: float) -> str:
    blocker_type = CLUSTERS[cluster_id]["blocker_type"]
    if confidence < 0.65:
        return "needs_thread_read"
    if blocker_type in {"health", "security"}:
        return "human_review"
    if blocker_type in {"billing", "debt", "identity", "legal", "infra"}:
        return "obligation" if confidence >= 0.8 else "human_review"
    if blocker_type in {"career", "platform", "creative_life", "relationship"}:
        return "product_research"
    return "parked"


def atom_from_row(row: sqlite3.Row, *, scope: str) -> dict[str, Any]:
    cluster_id, hits, confidence = classify(row)
    cluster = CLUSTERS[cluster_id]
    sender_domain = normalize_domain(row["sender_address"])
    subject = str(row["subject"] or "")
    mailbox = mailbox_parts(row["mailbox_url"])
    status = "hot_flagged" if int(row["flagged"] or 0) == 1 else "historical_candidate"
    atom_id = sha(
        "ms",
        row["apple_rowid"],
        row["global_message_id"],
        row["message_id_header"],
        row["date_received"],
        row["sender_address"],
        subject,
    )
    return {
        "schema": SCHEMA,
        "stable_id": atom_id,
        "status": status,
        "scope": scope,
        "source_refs": {
            "apple_rowid": row["apple_rowid"],
            "global_message_id": row["global_message_id"],
            "conversation_id": row["conversation_id"],
            "mailbox_url": row["mailbox_url"],
            "mailbox_account": mailbox["account"],
            "mailbox_name": mailbox["mailbox"],
            "mailbox_scope": mailbox["scope"],
            "message_id_header_hash": sha("mid", row["message_id_header"]) if row["message_id_header"] else None,
        },
        "received_at": iso_from_unix(row["date_received"]),
        "account": mailbox["account"],
        "mailbox": mailbox["mailbox"],
        "sender_domain": sender_domain,
        "redacted_subject": redact_text(subject),
        "subject_hash": sha("subject", subject),
        "labels": {
            "flagged": bool(row["flagged"]),
            "flag_color": row["flag_color"],
            "read": bool(row["read"]),
            "deleted": bool(row["deleted"]),
        },
        "blocker_type": cluster["blocker_type"],
        "cluster_id": cluster_id,
        "cluster_title": cluster["title"],
        "classification_hits": hits,
        "immediate_fact": f"{status} metadata from {sender_domain} matched {cluster['title']}.",
        "personal_consequence": cluster["personal_consequence"],
        "universal_pain_point": cluster["universal_pain_point"],
        "software_thesis": cluster["software_thesis"],
        "confidence": round(confidence, 2),
        "evidence_scope": "metadata_summary" if row["summary"] else "metadata",
        "privacy_level": "private_only",
        "next_action": next_action(cluster_id, confidence),
        "private_evidence": {
            "sender_address": row["sender_address"],
            "sender_name": row["sender_name"],
            "subject": subject,
            "summary": row["summary"],
        },
    }


def fetch_message_rows(conn: sqlite3.Connection, *, scope: str, limit: int | None) -> list[sqlite3.Row]:
    where = "m.deleted = 0"
    if scope == "flagged":
        where += " AND m.flagged = 1"
    sql = f"""
        SELECT
            m.ROWID AS apple_rowid,
            m.global_message_id,
            mgd.message_id_header,
            m.conversation_id,
            m.date_received,
            m.flagged,
            m.flag_color,
            m.read,
            m.deleted,
            a.address AS sender_address,
            a.comment AS sender_name,
            s.subject AS subject,
            sm.summary AS summary,
            mb.url AS mailbox_url
        FROM messages m
        LEFT JOIN addresses a ON a.ROWID = m.sender
        LEFT JOIN subjects s ON s.ROWID = m.subject
        LEFT JOIN summaries sm ON sm.ROWID = m.summary
        LEFT JOIN mailboxes mb ON mb.ROWID = m.mailbox
        LEFT JOIN message_global_data mgd ON mgd.ROWID = m.global_message_id
        WHERE {where}
        ORDER BY m.date_received DESC, m.ROWID DESC
    """
    params: list[Any] = []
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)
    return list(conn.execute(sql, params))


def _single_row(conn: sqlite3.Connection, sql: str) -> dict[str, Any]:
    row = conn.execute(sql).fetchone()
    return dict(row) if row else {}


def mail_stats(conn: sqlite3.Connection) -> dict[str, Any]:
    totals = _single_row(
        conn,
        """
        SELECT
            COUNT(*) AS total_messages,
            SUM(CASE WHEN deleted = 0 THEN 1 ELSE 0 END) AS not_deleted_messages,
            SUM(CASE WHEN flagged = 1 AND deleted = 0 THEN 1 ELSE 0 END) AS flagged_non_deleted,
            COUNT(DISTINCT CASE WHEN deleted = 0 AND flagged = 1 THEN global_message_id END) AS flagged_distinct_messages,
            COUNT(DISTINCT CASE WHEN deleted = 0 AND flagged = 1 THEN conversation_id END) AS flagged_distinct_threads,
            MIN(datetime(date_received, 'unixepoch')) AS first_received_at,
            MAX(datetime(date_received, 'unixepoch')) AS last_received_at
        FROM messages
        """,
    )
    by_year = [
        {"year": row["year"], "messages": row["messages"]}
        for row in conn.execute(
            """
            SELECT strftime('%Y', datetime(date_received, 'unixepoch')) AS year, COUNT(*) AS messages
            FROM messages
            WHERE deleted = 0
            GROUP BY year
            ORDER BY year DESC
            """
        )
    ]
    flagged_by_year = [
        {"year": row["year"], "messages": row["messages"]}
        for row in conn.execute(
            """
            SELECT strftime('%Y', datetime(date_received, 'unixepoch')) AS year, COUNT(*) AS messages
            FROM messages
            WHERE deleted = 0 AND flagged = 1
            GROUP BY year
            ORDER BY year DESC
            """
        )
    ]
    flagged_by_mailbox = [
        {
            "account": mailbox_parts(row["mailbox_url"])["account"],
            "mailbox": mailbox_parts(row["mailbox_url"])["mailbox"],
            "mailbox_scope": mailbox_scope(row["mailbox_url"]),
            "mailbox_url": row["mailbox_url"],
            "messages": row["messages"],
            "distinct_messages": row["distinct_messages"],
            "distinct_threads": row["distinct_threads"],
        }
        for row in conn.execute(
            """
            SELECT
                mb.url AS mailbox_url,
                COUNT(*) AS messages,
                COUNT(DISTINCT m.global_message_id) AS distinct_messages,
                COUNT(DISTINCT m.conversation_id) AS distinct_threads
            FROM messages m
            LEFT JOIN mailboxes mb ON mb.ROWID = m.mailbox
            WHERE m.deleted = 0 AND m.flagged = 1
            GROUP BY mb.url
            ORDER BY messages DESC, mb.url
            """
        )
    ]
    return {
        **totals,
        "by_year": by_year,
        "flagged_by_year": flagged_by_year,
        "flagged_by_mailbox": flagged_by_mailbox,
    }


def priority_label(score: int) -> str:
    if score >= 220:
        return "critical"
    if score >= 150:
        return "high"
    if score >= 80:
        return "medium"
    return "low"


def cluster_summary(atoms: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_cluster: dict[str, list[dict[str, Any]]] = {}
    for atom in atoms:
        by_cluster.setdefault(atom["cluster_id"], []).append(atom)
    rows: list[dict[str, Any]] = []
    for cluster_id, cluster_atoms in by_cluster.items():
        cluster = CLUSTERS[cluster_id]
        domains = Counter(atom["sender_domain"] for atom in cluster_atoms).most_common(8)
        actions = Counter(atom["next_action"] for atom in cluster_atoms)
        priority = len(cluster_atoms) * 10 + TYPE_WEIGHT.get(cluster["blocker_type"], 1) * 15
        rows.append(
            {
                "cluster_id": cluster_id,
                "title": cluster["title"],
                "blocker_type": cluster["blocker_type"],
                "recurring_pattern": cluster["recurring_pattern"],
                "atom_count": len(cluster_atoms),
                "priority": priority,
                "priority_label": priority_label(priority),
                "top_domains": [{"domain": domain, "messages": count} for domain, count in domains],
                "next_actions": dict(sorted(actions.items())),
                "example_atom_ids": [atom["stable_id"] for atom in cluster_atoms[:5]],
                "affected_life_domains": cluster["affected_life_domains"],
                "existing_tools_involved": cluster["existing_tools_involved"],
                "failure_modes": cluster["failure_modes"],
                "candidate_products": cluster["candidate_products"],
                "personal_consequence": cluster["personal_consequence"],
                "universal_pain_point": cluster["universal_pain_point"],
                "software_thesis": cluster["software_thesis"],
                "market_ux_thesis": cluster["market_ux_thesis"],
            }
        )
    return sorted(rows, key=lambda row: (-row["priority"], -row["atom_count"], row["cluster_id"]))


def _mailbox_count(stats: dict[str, Any], *, account: str, mailbox: str, key: str = "messages") -> int:
    for row in stats.get("flagged_by_mailbox", []):
        if row.get("account") == account and row.get("mailbox") == mailbox:
            return int(row.get(key) or 0)
    return 0


def _check_row(label: str, expected: int | None, actual: int | None, *, note: str = "") -> dict[str, Any]:
    if expected is None:
        status = "observed"
        delta = None
    elif actual is None:
        status = "not_checked"
        delta = None
    else:
        delta = actual - expected
        status = "match" if delta == 0 else "drift"
    return {
        "label": label,
        "expected": expected,
        "actual": actual,
        "delta": delta,
        "status": status,
        "note": note,
    }


def build_reconciliation(
    stats: dict[str, Any],
    atoms: list[dict[str, Any]],
    *,
    scope: str,
    baseline: dict[str, Any] | None,
) -> dict[str, Any]:
    local_gmail_messages = _mailbox_count(stats, account="gmail", mailbox="all_mail")
    local_gmail_threads = _mailbox_count(stats, account="gmail", mailbox="all_mail", key="distinct_threads")
    local_icloud_messages = _mailbox_count(stats, account="icloud", mailbox="inbox")
    inventory_target = int(stats.get("flagged_non_deleted") or 0) if scope == "flagged" else len(atoms)
    checks = [
        _check_row(
            "Apple Mail total indexed messages",
            baseline.get("apple_total_messages") if baseline else None,
            int(stats.get("total_messages") or 0),
        ),
        _check_row(
            "Apple Mail flagged non-deleted",
            baseline.get("apple_flagged_non_deleted") if baseline else None,
            int(stats.get("flagged_non_deleted") or 0),
        ),
        _check_row(
            "Gmail All Mail flagged locally",
            baseline.get("apple_gmail_all_mail_flagged") if baseline else None,
            local_gmail_messages,
        ),
        _check_row(
            "iCloud Inbox flagged locally",
            baseline.get("apple_icloud_inbox_flagged") if baseline else None,
            local_icloud_messages,
        ),
        _check_row(
            "Gmail connector STARRED messages",
            baseline.get("gmail_starred_messages") if baseline else None,
            local_gmail_messages,
            note="compared to local Gmail All Mail flags; connector bodies/labels were not touched",
        ),
        _check_row(
            "Gmail connector STARRED threads",
            baseline.get("gmail_starred_threads") if baseline else None,
            local_gmail_threads,
            note="compared to local Gmail flagged conversation ids; connector was not read in this pass",
        ),
    ]
    no_silent_drops = len(atoms) == inventory_target
    return {
        "baseline_source": baseline.get("source") if baseline else None,
        "scope": scope,
        "local": {
            "atom_count": len(atoms),
            "inventory_target": inventory_target,
            "gmail_all_mail_flagged": local_gmail_messages,
            "gmail_all_mail_flagged_threads": local_gmail_threads,
            "icloud_inbox_flagged": local_icloud_messages,
        },
        "no_silent_drops": no_silent_drops,
        "checks": checks,
        "status": "drift" if any(row["status"] == "drift" for row in checks) else "match",
    }


def build_snapshot(
    mail_index: Path,
    *,
    scope: str = "flagged",
    limit: int | None = None,
    baseline: dict[str, Any] | None = BASELINE_RECONCILIATION,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    with connect_readonly(mail_index) as conn:
        stats = mail_stats(conn)
        rows = fetch_message_rows(conn, scope=scope, limit=limit)
    atoms = [atom_from_row(row, scope=scope) for row in rows]
    top_domains = Counter(atom["sender_domain"] for atom in atoms).most_common(25)
    by_type = Counter(atom["blocker_type"] for atom in atoms)
    generated_at = utc_now()
    snapshot = {
        "schema": SCHEMA,
        "generated_at": generated_at,
        "mode": {
            "source": "apple_mail_envelope_index",
            "mail_index": str(mail_index),
            "scope": scope,
            "limit": limit,
            "read_only": True,
            "mailbox_mutations": False,
            "body_reads": False,
            "gmail_writes": False,
        },
        "privacy": {
            "private_root": str(PRIVATE_ROOT),
            "tracked_report": str(DOC_PATH),
            "raw_mail_in_git": False,
            "public_report_redacted": True,
        },
        "stats": stats,
        "atom_count": len(atoms),
        "top_domains": [{"domain": domain, "messages": count} for domain, count in top_domains],
        "by_blocker_type": dict(sorted(by_type.items())),
        "reconciliation": build_reconciliation(stats, atoms, scope=scope, baseline=baseline),
        "clusters": cluster_summary(atoms),
    }
    return snapshot, atoms


def md_table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        out.append("| " + " | ".join(str(cell).replace("\n", " ") for cell in row) + " |")
    return out


def render_markdown(snapshot: dict[str, Any]) -> str:
    stats = snapshot["stats"]
    reconciliation = snapshot["reconciliation"]
    lines = [
        "# Mail Story Ledger",
        "",
        "Redacted control-plane view over the local mail story corpus. Raw/private atoms stay in the ignored",
        "`.limen-private/mail-story/` cartridge; this tracked report keeps only counts, domains, hashes,",
        "cluster ids, and synthesized pain-point theses.",
        "",
        "## Snapshot",
        "",
        f"- Generated: `{snapshot['generated_at']}`",
        "- Source: Apple Mail Envelope Index, opened read-only.",
        f"- Processed scope: `{snapshot['mode']['scope']}`",
        f"- Body/thread reads: `{str(snapshot['mode']['body_reads']).lower()}`",
        f"- Mailbox mutations: `{str(snapshot['mode']['mailbox_mutations']).lower()}`",
        "- Private atom store: `.limen-private/mail-story/inventory/mail-story-atoms.jsonl`",
        "",
        "## Corpus Counts",
        "",
        f"- Total indexed messages: `{stats.get('total_messages', 0)}`",
        f"- Non-deleted messages: `{stats.get('not_deleted_messages', 0)}`",
        f"- Flagged non-deleted messages: `{stats.get('flagged_non_deleted', 0)}`",
        f"- First received: `{stats.get('first_received_at') or 'unknown'}`",
        f"- Last received: `{stats.get('last_received_at') or 'unknown'}`",
        f"- Atoms emitted in this run: `{snapshot['atom_count']}`",
        f"- No silent drops: `{str(reconciliation['no_silent_drops']).lower()}`",
        "",
        "## Reconciliation",
        "",
        f"- Baseline source: `{reconciliation.get('baseline_source') or 'none'}`",
        f"- Reconciliation status: `{reconciliation['status']}`",
        "",
    ]
    lines += md_table(
        ["check", "expected", "actual", "delta", "status", "note"],
        [
            [
                row["label"],
                row["expected"] if row["expected"] is not None else "-",
                row["actual"] if row["actual"] is not None else "-",
                row["delta"] if row["delta"] is not None else "-",
                row["status"],
                row["note"] or "-",
            ]
            for row in reconciliation["checks"]
        ],
    )
    lines += [
        "",
        "## Pain Point Clusters",
        "",
    ]
    cluster_rows = [
        [
            row["title"],
            row["blocker_type"],
            row["atom_count"],
            f"{row['priority_label']} ({row['priority']})",
            ", ".join(f"{k}:{v}" for k, v in row["next_actions"].items()) or "-",
            row["recurring_pattern"],
            ", ".join(row["candidate_products"]),
            row["market_ux_thesis"],
        ]
        for row in snapshot["clusters"]
    ]
    lines += md_table(
        [
            "cluster",
            "type",
            "atoms",
            "priority",
            "next actions",
            "recurring pattern",
            "candidate products",
            "market/UX thesis",
        ],
        cluster_rows or [["-", "-", 0, 0, "-", "-", "-", "-"]],
    )
    lines += [
        "",
        "## Cluster Details",
        "",
    ]
    for row in snapshot["clusters"]:
        lines += [
            f"### {row['title']}",
            "",
            f"- Universal pain point: {row['universal_pain_point']}",
            f"- Software thesis: {row['software_thesis']}",
            f"- Affected domains: {', '.join(row['affected_life_domains'])}",
            f"- Existing tools involved: {', '.join(row['existing_tools_involved'])}",
            f"- Failure modes: {', '.join(row['failure_modes'])}",
            f"- Example atom ids: {', '.join(row['example_atom_ids'])}",
            "",
        ]
    lines += [
        "",
        "## Top Sender Domains In Processed Scope",
        "",
    ]
    lines += md_table(
        ["domain", "messages"],
        [[row["domain"], row["messages"]] for row in snapshot["top_domains"][:20]] or [["-", 0]],
    )
    lines += [
        "",
        "## Flagged By Mailbox",
        "",
    ]
    lines += md_table(
        ["account", "mailbox", "scope", "messages", "threads"],
        [
            [row["account"], row["mailbox"], row["mailbox_scope"], row["messages"], row["distinct_threads"]]
            for row in stats.get("flagged_by_mailbox", [])
        ]
        or [["-", "-", "-", 0, 0]],
    )
    lines += [
        "",
        "## Flagged By Year",
        "",
    ]
    lines += md_table(
        ["year", "messages"],
        [[row["year"], row["messages"]] for row in stats.get("flagged_by_year", [])] or [["-", 0]],
    )
    lines += [
        "",
        "## Privacy Boundary",
        "",
        "- No message body text is read by this pass.",
        "- Full sender addresses, sender display names, subjects, summaries, and Apple row ids stay in ignored private JSON.",
        "- Private atoms expose a redacted subject plus hashes at top level; raw metadata is nested under `private_evidence`.",
        "- The tracked report intentionally exposes only domains, counts, cluster names, atom ids, and synthesized theses.",
        "- Gmail thread enrichment is a later gated action for atoms whose `next_action` requires it.",
        "",
        "## Commands",
        "",
        "- Preview the hot flagged pass: `python3 scripts/mail-story-ledger.py`",
        "- Refresh the redacted report and ignored private atoms: `python3 scripts/mail-story-ledger.py --write`",
        "- Process all non-deleted indexed mail privately: `python3 scripts/mail-story-ledger.py --scope all --write`",
        "",
    ]
    return "\n".join(lines)


def write_outputs(
    snapshot: dict[str, Any],
    atoms: list[dict[str, Any]],
    markdown: str,
    *,
    doc_path: Path = DOC_PATH,
    log_path: Path = LOG_PATH,
    private_atoms: Path = PRIVATE_ATOMS,
    private_snapshot: Path = PRIVATE_SNAPSHOT,
) -> None:
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    doc_path.write_text(markdown, encoding="utf-8")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
    private_atoms.parent.mkdir(parents=True, exist_ok=True)
    private_atoms.write_text("".join(json.dumps(atom, sort_keys=True) + "\n" for atom in atoms), encoding="utf-8")
    private_snapshot.parent.mkdir(parents=True, exist_ok=True)
    private_snapshot.write_text(json.dumps({**snapshot, "atoms": atoms}, indent=2, sort_keys=True), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the redacted Limen mail story ledger.")
    parser.add_argument("--mail-index", type=Path, default=MAIL_INDEX, help="Apple Mail Envelope Index path")
    parser.add_argument("--scope", choices=("flagged", "all"), default="flagged", help="messages to emit as atoms")
    parser.add_argument("--limit", type=int, default=None, help="optional atom limit for previews/tests")
    parser.add_argument("--write", action="store_true", help="write docs, logs, and ignored private atom files")
    parser.add_argument(
        "--no-baseline",
        action="store_true",
        help="omit the built-in 2026-07-06 brief baseline from reconciliation",
    )
    parser.add_argument("--doc", type=Path, default=DOC_PATH, help="tracked redacted Markdown output")
    parser.add_argument("--log", type=Path, default=LOG_PATH, help="ignored structured public-ish snapshot")
    parser.add_argument(
        "--private-atoms",
        type=Path,
        default=PRIVATE_ATOMS,
        help="ignored private atom JSONL output",
    )
    parser.add_argument(
        "--private-snapshot",
        type=Path,
        default=PRIVATE_SNAPSHOT,
        help="ignored private snapshot JSON output",
    )
    args = parser.parse_args()
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be positive")
    return args


def baseline_from_args(args: argparse.Namespace) -> dict[str, Any] | None:
    return None if args.no_baseline else BASELINE_RECONCILIATION


def main() -> int:
    args = parse_args()
    snapshot, atoms = build_snapshot(
        args.mail_index,
        scope=args.scope,
        limit=args.limit,
        baseline=baseline_from_args(args),
    )
    markdown = render_markdown(snapshot)
    if args.write:
        write_outputs(
            snapshot,
            atoms,
            markdown,
            doc_path=args.doc,
            log_path=args.log,
            private_atoms=args.private_atoms,
            private_snapshot=args.private_snapshot,
        )
        print(f"mail-story-ledger: {len(atoms)} atoms over scope={args.scope}; wrote {args.doc}")
    else:
        print(markdown)
        print(f"mail-story-ledger: {len(atoms)} atoms over scope={args.scope}; preview only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

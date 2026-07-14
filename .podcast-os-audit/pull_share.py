"""Pull a shared ChatGPT conversation live via the desktop-app local session.

Usage: PYTHONPATH=src python3 pull_share.py <share_id> [--full]
Resolves share -> conversation_id, fetches live detail, prints transcript
+ completion status of the final message.
"""
import json
import sys
import urllib.error

from conversation_corpus_engine.chatgpt_local_session import (
    CHATGPT_HOST,
    build_chatgpt_session,
    fetch_json,
)
from conversation_corpus_engine.import_chatgpt_export_corpus import (
    extract_node_text,
    walk_mapping_tree,
)

share_id = sys.argv[1]
full = "--full" in sys.argv

session = build_chatgpt_session()

conversation_id = None
share_detail = None
try:
    share_detail = fetch_json(session, f"https://{CHATGPT_HOST}/backend-api/share/{share_id}")
    conversation_id = share_detail.get("backing_conversation_id") or share_detail.get("conversation_id")
except urllib.error.HTTPError as exc:
    print(f"share endpoint: HTTP {exc.code}", file=sys.stderr)

if not conversation_id:
    listing = fetch_json(
        session,
        f"https://{CHATGPT_HOST}/backend-api/shared_conversations?order=created&limit=50",
    )
    for item in listing.get("items", []):
        if item.get("id") == share_id:
            conversation_id = item.get("conversation_id")
            break

if not conversation_id:
    print("FATAL: could not resolve share -> conversation_id", file=sys.stderr)
    sys.exit(1)

detail = fetch_json(session, f"https://{CHATGPT_HOST}/backend-api/conversation/{conversation_id}")
nodes = walk_mapping_tree(detail.get("mapping", {}))

print(f"conversation_id: {conversation_id}")
print(f"title: {detail.get('title')}")
print(f"update_time: {detail.get('update_time')}")
print(f"nodes: {len(nodes)}")

rendered = []
last_meaningful = None
for node in nodes:
    msg = node.get("message") or {}
    role = (msg.get("author") or {}).get("role", "?")
    status = msg.get("status", "?")
    end_turn = msg.get("end_turn")
    text = extract_node_text(node)
    if not text.strip():
        continue
    rendered.append((role, status, end_turn, text))
    last_meaningful = (role, status, end_turn, len(text))

print(f"messages_with_text: {len(rendered)}")
if last_meaningful:
    role, status, end_turn, nchars = last_meaningful
    print(f"LAST: role={role} status={status} end_turn={end_turn} chars={nchars}")

print("=" * 70)
for role, status, end_turn, text in rendered:
    body = text if full else (text[:1500] + f"\n...[truncated {len(text) - 1500} chars]" if len(text) > 1500 else text)
    print(f"\n----- [{role}] (status={status} end_turn={end_turn}) -----")
    print(body)

"""Show tail-node state of the live conversation to judge generation completeness.

Usage: PYTHONPATH=src python3 tail_status.py <conversation_id> [n_tail]
Prints update_time (ISO), last-user-message index, and every node after it:
role, status, end_turn, recipient, content-type, chars.
Exit 0 if the tail looks settled (no in_progress after last user msg and the
final assistant node has end_turn=True), exit 3 if still running.
"""
import datetime
import sys

from conversation_corpus_engine.chatgpt_local_session import (
    CHATGPT_HOST,
    build_chatgpt_session,
    fetch_json,
)
from conversation_corpus_engine.import_chatgpt_export_corpus import (
    extract_node_text,
    walk_mapping_tree,
)

cid = sys.argv[1]
session = build_chatgpt_session()
detail = fetch_json(session, f"https://{CHATGPT_HOST}/backend-api/conversation/{cid}")
nodes = walk_mapping_tree(detail.get("mapping", {}))

ut = detail.get("update_time")
print(f"update_time: {ut} ({datetime.datetime.fromtimestamp(ut, datetime.timezone.utc).isoformat()})")
print(f"nodes: {len(nodes)}")

last_user_idx = None
for i, node in enumerate(nodes):
    msg = node.get("message") or {}
    if (msg.get("author") or {}).get("role") == "user":
        last_user_idx = i

print(f"last_user_idx: {last_user_idx}")
tail = nodes[last_user_idx:] if last_user_idx is not None else nodes[-12:]

settled = True
final_assistant_end_turn = None
for i, node in enumerate(tail, start=last_user_idx or 0):
    msg = node.get("message") or {}
    role = (msg.get("author") or {}).get("role", "?")
    status = msg.get("status", "?")
    end_turn = msg.get("end_turn")
    recipient = msg.get("recipient", "")
    ctype = ((msg.get("content") or {}).get("content_type", "?"))
    text = extract_node_text(node)
    print(f"[{i}] role={role} status={status} end_turn={end_turn} recipient={recipient} ctype={ctype} chars={len(text.strip())}")
    if status == "in_progress":
        settled = False
    if role == "assistant":
        final_assistant_end_turn = end_turn

if final_assistant_end_turn is not True:
    settled = False
print(f"SETTLED: {settled}")
sys.exit(0 if settled else 3)

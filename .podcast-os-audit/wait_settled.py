"""Block until the ChatGPT conversation finishes generating, then exit.

Exit 0: settled (last node is assistant text end_turn=True, update_time stable 2 polls)
Exit 4: update_time frozen >=3 polls without a terminal node (aborted/stuck)
Exit 5: 60-minute cap reached while still moving
"""
import sys
import time

from conversation_corpus_engine.chatgpt_local_session import (
    CHATGPT_HOST,
    build_chatgpt_session,
    fetch_json,
)
from conversation_corpus_engine.import_chatgpt_export_corpus import walk_mapping_tree

cid = sys.argv[1]
session = build_chatgpt_session()

prev_ut = None
stable_terminal = 0
stable_frozen = 0
deadline = time.time() + 3600

while time.time() < deadline:
    try:
        detail = fetch_json(session, f"https://{CHATGPT_HOST}/backend-api/conversation/{cid}")
    except Exception as exc:  # transient API failure must not kill the watch
        print(f"poll_error: {exc}", flush=True)
        time.sleep(30)
        continue
    nodes = walk_mapping_tree(detail.get("mapping", {}))
    ut = detail.get("update_time")
    last = (nodes[-1].get("message") or {}) if nodes else {}
    role = (last.get("author") or {}).get("role")
    ctype = (last.get("content") or {}).get("content_type")
    terminal = (
        role == "assistant"
        and last.get("end_turn") is True
        and last.get("status") == "finished_successfully"
        and ctype == "text"
    )
    moved = prev_ut is not None and ut != prev_ut
    if terminal and ut == prev_ut:
        stable_terminal += 1
    else:
        stable_terminal = 0
    if not terminal and ut == prev_ut:
        stable_frozen += 1
    else:
        stable_frozen = 0
    print(f"poll: nodes={len(nodes)} ut={ut} terminal={terminal} moved={moved}", flush=True)
    if stable_terminal >= 2:
        print("DONE_SETTLED", flush=True)
        sys.exit(0)
    if stable_frozen >= 30:
        print("DONE_FROZEN_NONTERMINAL", flush=True)
        sys.exit(4)
    prev_ut = ut
    time.sleep(30)

print("DONE_TIMECAP_STILL_MOVING", flush=True)
sys.exit(5)

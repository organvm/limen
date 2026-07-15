"""Download the sandbox starter-pack zip from the conversation's interpreter output."""
import json
import sys
import urllib.request

from conversation_corpus_engine.chatgpt_local_session import (
    CHATGPT_HOST,
    build_chatgpt_session,
    build_cookie_header,
    fetch_json,
    _auth_headers,
)

cid = "6a543ef4-5fec-83ea-92bc-c7acb87c1bf6"
sandbox_path = "/mnt/data/" + sys.argv[2]
out_path = sys.argv[1]

session = build_chatgpt_session()
detail = fetch_json(session, f"https://{CHATGPT_HOST}/backend-api/conversation/{cid}")

msg_id = None
for node_id, node in (detail.get("mapping") or {}).items():
    msg = node.get("message") or {}
    parts = ((msg.get("content") or {}).get("parts")) or []
    text = " ".join(p for p in parts if isinstance(p, str))
    meta = msg.get("metadata") or {}
    agg = json.dumps(meta) if meta else ""
    if sys.argv[2] in text or sys.argv[2] in agg:
        msg_id = msg.get("id") or node_id
        print(f"candidate node: {node_id} role={(msg.get('author') or {}).get('role')}")

if not msg_id:
    print("FATAL: no node references the zip")
    sys.exit(1)

url = (
    f"https://{CHATGPT_HOST}/backend-api/conversation/{cid}/interpreter/download"
    f"?message_id={msg_id}&sandbox_path={urllib.parse.quote(sandbox_path, safe='')}"
)
try:
    payload = fetch_json(session, url)
except Exception as exc:
    print(f"interpreter/download failed: {exc}")
    sys.exit(2)

download_url = payload.get("download_url")
print(f"download_url: {str(download_url)[:120]}")
req = urllib.request.Request(download_url)
req.add_header("Cookie", build_cookie_header(session.cookies, download_url))
for k, v in _auth_headers(session).items():
    req.add_header(k, v)
with urllib.request.urlopen(req, timeout=60) as resp, open(out_path, "wb") as fh:
    fh.write(resp.read())
print(f"saved: {out_path}")

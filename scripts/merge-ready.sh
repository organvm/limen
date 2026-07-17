#!/usr/bin/env bash
# merge-ready.sh — compatibility front door for the receipt-bound merge organs.
#
# Default invocation is a zero-write preview produced by merge-ready.py.  An apply invocation is
# delegated intact to merge-drain.py, whose only targets come from short-lived exact-head
# limen.merge_authorization.v1 receipts.  merge-drain re-runs both merge-policy.sh and the live
# limen.pr_review_gate.v1 predicate immediately before a head-pinned squash merge.
#
# This wrapper never manufactures a self-comment review, never interprets mergeStateStatus=CLEAN as
# acceptance, and never invokes the GitHub merge effect itself. Source-branch cleanup remains a separate
# receipt-backed accepted reap.
#
# Usage:
#   bash scripts/merge-ready.sh
#   bash scripts/merge-ready.sh --scan 80
#   bash scripts/merge-ready.sh --apply \
#     --authorization-receipt /private/path/merge-organvm-limen-123.json \
#     --allowed-signers /domus-owned/path/allowed-signers
set -euo pipefail

ROOT="${LIMEN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
APPLY=0
APPLY_SEEN=0
DRY_SEEN=0
SCAN=80
LIMIT="${LIMEN_MERGE_LIMIT:-10}"
ALLOWED_SIGNERS=""
receipts=()

while [ "$#" -gt 0 ]; do
  case "$1" in
    --apply)
      APPLY=1
      APPLY_SEEN=1
      shift
      ;;
    --dry-run)
      APPLY=0
      DRY_SEEN=1
      shift
      ;;
    --scan)
      [ "$#" -ge 2 ] || { echo "merge-ready: --scan requires a value" >&2; exit 2; }
      SCAN="$2"
      shift 2
      ;;
    --scan=*)
      SCAN="${1#*=}"
      shift
      ;;
    --limit)
      [ "$#" -ge 2 ] || { echo "merge-ready: --limit requires a value" >&2; exit 2; }
      LIMIT="$2"
      shift 2
      ;;
    --limit=*)
      LIMIT="${1#*=}"
      shift
      ;;
    --authorization-receipt)
      [ "$#" -ge 2 ] || {
        echo "merge-ready: --authorization-receipt requires a path" >&2
        exit 2
      }
      receipts+=("$2")
      shift 2
      ;;
    --authorization-receipt=*)
      receipts+=("${1#*=}")
      shift
      ;;
    --allowed-signers)
      [ "$#" -ge 2 ] || { echo "merge-ready: --allowed-signers requires a path" >&2; exit 2; }
      ALLOWED_SIGNERS="$2"
      shift 2
      ;;
    --allowed-signers=*)
      ALLOWED_SIGNERS="${1#*=}"
      shift
      ;;
    -h|--help)
      sed -n '2,18p' "$0"
      exit 0
      ;;
    *)
      echo "merge-ready: unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

if [ "$APPLY_SEEN" -eq 1 ] && [ "$DRY_SEEN" -eq 1 ]; then
  echo "merge-ready: --apply and --dry-run are mutually exclusive" >&2
  exit 2
fi

if [ "$APPLY" -eq 0 ]; then
  if [ "${#receipts[@]}" -gt 0 ]; then
    echo "merge-ready: --authorization-receipt requires --apply" >&2
    exit 2
  fi
  if [ -n "$ALLOWED_SIGNERS" ]; then
    echo "merge-ready: --allowed-signers requires --apply" >&2
    exit 2
  fi
  exec python3 "$ROOT/scripts/merge-ready.py" --scan "$SCAN"
fi

if [ "${#receipts[@]}" -eq 0 ]; then
  echo "merge-ready: REFUSED — --apply requires --authorization-receipt for each exact target" >&2
  exit 2
fi

args=(--apply --limit "$LIMIT")
if [ -n "$ALLOWED_SIGNERS" ]; then
  args+=(--allowed-signers "$ALLOWED_SIGNERS")
fi
for receipt in "${receipts[@]}"; do
  args+=(--authorization-receipt "$receipt")
done
exec python3 "$ROOT/scripts/merge-drain.py" "${args[@]}"

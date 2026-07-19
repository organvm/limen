#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  scripts/start-worktree-session.sh [--autonomous] [--codex] [--shell] [--check] [--from <branch-or-ref>] [--prompt <text>] [--prompt-file <path>] [--runway <duration>] [--worktree-root <path>] [--workstream <handle>] <repo-or-alias> <slug>

Examples:
  scripts/start-worktree-session.sh portvs triptych-story
  scripts/start-worktree-session.sh --codex portvs triptych-story
  scripts/start-worktree-session.sh --autonomous --codex --runway 8h --prompt-file /tmp/next-session.md limen next-epoch
  scripts/start-worktree-session.sh --shell --prompt-file /tmp/prompt.md domus package-map
  scripts/start-worktree-session.sh --workstream contributions --prompt 'drain the code lane' limen contrib-run
  scripts/start-worktree-session.sh --check --worktree-root /tmp/limen-worktrees limen next-epoch

--workstream pins the worker to ONE purpose channel (contributions/correspondence/… — see
docs/lanes/). It is stamped into the kickoff packet so the session stays single-purpose.

--runway sets the finite workstream admission window (15m..30d; default 1d). The clock starts at the
first kickstart, survives successor sessions, and is never silently reset by a rerender.

--autonomous requires an explicit prompt and turns the README into the initial Codex prompt. The
packet defines live probes and completion/switch predicates; it never predeclares the ending.

--worktree-root explicitly selects the checkout pool. Without it (or LIMEN_WORKTREE_ROOT), the
launcher requires a mounted writable /Volumes/Scratch and uses /Volumes/Scratch/limen-worktrees.
There is no silent internal fallback. --check validates the same plan without any filesystem or Git
mutation.

Aliases:
  portvs, portus  /Users/4jp/Workspace/4444J99/portvs
  limen           /Users/4jp/Workspace/limen
  domus           /Users/4jp/Workspace/domus-genoma
  relpipe         /Users/4jp/Workspace/4444J99/relationship-pipeline

Creates or reuses:
  <worktree-root>/<slug> on branch work/<slug>
  <worktree-root>/<slug>/.limen-workstream/README.md as a thin prompt index
  <worktree-root>/<slug>/.limen-workstream/{manifest,intent,runtime,closeout}.md
  <worktree-root>/<slug>/docs/continuations/<slug>/workstream.json as a tracked redacted receipt

The target repo's .git/info/exclude is updated so the private capsule never appears as Git noise.
The receipt remains visible for commit and remote custody.
USAGE
}

autonomous=0
launch_codex=0
launch_shell=0
from_ref=""
prompt_text=""
prompt_file=""
runway=""
runway_explicit=0
workstream=""
write_readme=1
worktree_root=""
check_only=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --autonomous)
      autonomous=1
      shift
      ;;
    --codex)
      launch_codex=1
      shift
      ;;
    --shell)
      launch_shell=1
      shift
      ;;
    --from)
      if [[ $# -lt 2 ]]; then
        echo "missing value for --from" >&2
        usage >&2
        exit 2
      fi
      from_ref="$2"
      shift 2
      ;;
    --prompt)
      if [[ $# -lt 2 ]]; then
        echo "missing value for --prompt" >&2
        usage >&2
        exit 2
      fi
      prompt_text="$2"
      shift 2
      ;;
    --prompt-file)
      if [[ $# -lt 2 ]]; then
        echo "missing value for --prompt-file" >&2
        usage >&2
        exit 2
      fi
      prompt_file="$2"
      shift 2
      ;;
    --runway)
      if [[ $# -lt 2 ]]; then
        echo "missing value for --runway" >&2
        usage >&2
        exit 2
      fi
      runway="$2"
      runway_explicit=1
      shift 2
      ;;
    --worktree-root)
      if [[ $# -lt 2 ]]; then
        echo "missing value for --worktree-root" >&2
        usage >&2
        exit 2
      fi
      worktree_root="$2"
      shift 2
      ;;
    --check)
      check_only=1
      shift
      ;;
    --workstream|--ws)
      if [[ $# -lt 2 ]]; then
        echo "missing value for --workstream" >&2
        usage >&2
        exit 2
      fi
      workstream="$2"
      shift 2
      ;;
    --no-readme)
      write_readme=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      break
      ;;
    -*)
      echo "unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
    *)
      break
      ;;
  esac
done

if [[ $# -ne 2 ]]; then
  usage >&2
  exit 2
fi

if [[ "$autonomous" -eq 1 && "$write_readme" -ne 1 ]]; then
  echo "--autonomous cannot be combined with --no-readme" >&2
  exit 2
fi
if [[ "$launch_codex" -eq 1 && "$write_readme" -ne 1 ]]; then
  echo "--codex cannot be combined with --no-readme because launch requires a validated contract" >&2
  exit 2
fi
if [[ "$autonomous" -eq 1 && -z "$prompt_text" && -z "$prompt_file" ]]; then
  echo "--autonomous requires --prompt or --prompt-file" >&2
  exit 2
fi
if [[ -n "$prompt_file" && ! -f "$prompt_file" ]]; then
  echo "prompt file not found: $prompt_file" >&2
  exit 1
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
contract_helper="$script_dir/../cli/src/limen/workstream_contract.py"
if [[ ! -f "$contract_helper" ]]; then
  echo "workstream contract helper not found: $contract_helper" >&2
  exit 1
fi
if [[ "$runway_explicit" -eq 1 ]]; then
  if ! normalized_runway="$(python3 "$contract_helper" normalize "$runway")"; then
    exit 2
  fi
  runway="${normalized_runway%%:*}"
fi

repo_arg="$1"
raw_slug="$2"

case "$repo_arg" in
  portvs|portus)
    repo="/Users/4jp/Workspace/4444J99/portvs"
    ;;
  limen)
    repo="/Users/4jp/Workspace/limen"
    ;;
  domus|domus-genoma)
    repo="/Users/4jp/Workspace/domus-genoma"
    ;;
  relationship-pipeline|relpipe|maddie)
    repo="/Users/4jp/Workspace/4444J99/relationship-pipeline"
    ;;
  *)
    if [[ -d "$repo_arg" ]]; then
      repo="$repo_arg"
    elif [[ -d "/Users/4jp/Workspace/$repo_arg" ]]; then
      repo="/Users/4jp/Workspace/$repo_arg"
    elif [[ -d "/Users/4jp/Workspace/4444J99/$repo_arg" ]]; then
      repo="/Users/4jp/Workspace/4444J99/$repo_arg"
    else
      echo "repo not found: $repo_arg" >&2
      exit 1
    fi
    ;;
esac

repo="$(cd "$repo" && pwd -P)"
if ! git -C "$repo" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "not a git repo: $repo" >&2
  exit 1
fi

slug="$(
  printf '%s' "$raw_slug" \
    | tr '[:upper:]' '[:lower:]' \
    | sed -E 's/[^a-z0-9._-]+/-/g; s/^-+//; s/-+$//'
)"
if [[ -z "$slug" ]]; then
  echo "slug collapsed to empty: $raw_slug" >&2
  exit 1
fi

if [[ -n "$workstream" ]]; then
  workstream="$(
    printf '%s' "$workstream" \
      | tr '[:upper:]' '[:lower:]' \
      | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//'
  )"
fi

branch="work/$slug"
if ! worktree_root="$(
  PYTHONPATH="$script_dir/../cli/src${PYTHONPATH:+:$PYTHONPATH}" \
    python3 - "$worktree_root" <<'PY'
import sys
from limen.worktree_roots import workstream_worktree_root

try:
    print(workstream_worktree_root(sys.argv[1] or None))
except RuntimeError as exc:
    print(exc, file=sys.stderr)
    raise SystemExit(2)
PY
)"; then
  exit 2
fi
wt="$worktree_root/$slug"

expected_common_dir="$(git -C "$repo" rev-parse --path-format=absolute --git-common-dir)"
if [[ -e "$wt" ]]; then
  if [[ ! -d "$wt" ]] || ! git -C "$wt" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "worktree-root collision: path exists but is not a git worktree: $wt" >&2
    exit 1
  fi
  actual_common_dir="$(git -C "$wt" rev-parse --path-format=absolute --git-common-dir)"
  if [[ "$actual_common_dir" != "$expected_common_dir" ]]; then
    echo "worktree-root collision: $wt belongs to a different repository" >&2
    exit 1
  fi
fi

if [[ "$check_only" -eq 1 ]]; then
  if [[ -e "$worktree_root" && ! -d "$worktree_root" ]]; then
    echo "worktree root exists but is not a directory: $worktree_root" >&2
    exit 1
  fi
  echo "check ok (zero writes)"
  echo "worktree: $wt"
  echo "branch: $branch"
  echo "source: ${from_ref:-auto}"
  exit 0
fi

git_info_dir="$(git -C "$repo" rev-parse --path-format=absolute --git-path info)"
mkdir -p "$git_info_dir"
exclude_file="$git_info_dir/exclude"
touch "$exclude_file"
if ! grep -qxF ".limen-workstream/" "$exclude_file"; then
  {
    printf '\n'
    printf '.limen-workstream/\n'
  } >> "$exclude_file"
fi

if [[ -z "$from_ref" ]]; then
  origin_head="$(git -C "$repo" symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null || true)"
  if [[ -n "$origin_head" ]]; then
    from_ref="$origin_head"
  elif git -C "$repo" show-ref --verify --quiet refs/remotes/origin/main; then
    from_ref="origin/main"
  else
    from_ref="$(git -C "$repo" branch --show-current)"
  fi
fi

mkdir -p "$(dirname "$wt")"

if [[ -d "$wt" ]]; then
  if ! git -C "$wt" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "path exists but is not a git worktree: $wt" >&2
    exit 1
  fi
  created="reused"
elif git -C "$repo" show-ref --verify --quiet "refs/heads/$branch"; then
  git -C "$repo" worktree add "$wt" "$branch" >/dev/null
  created="created"
else
  git -C "$repo" worktree add -b "$branch" "$wt" "$from_ref" >/dev/null
  created="created"
fi

echo "$created worktree: $wt"
echo "branch: $branch"
[[ -n "$workstream" ]] && echo "workstream: $workstream"

if [[ "$write_readme" -eq 1 ]]; then
  capsule_dir="$wt/.limen-workstream"
  readme="$capsule_dir/README.md"

  if [[ -n "$prompt_file" ]]; then
    prompt_payload="$(cat "$prompt_file")"
  elif [[ -n "$prompt_text" ]]; then
    prompt_payload="$prompt_text"
  else
    prompt_payload="No explicit prompt was supplied. Add one bounded objective and its owner contract before execution."
  fi

  # shellcheck source=scripts/lib/workstream-capsule.sh
  source "$script_dir/lib/workstream-capsule.sh"
  render_workstream_capsule \
    "$wt" "$repo" "$slug" "$branch" "$workstream" "$from_ref" "$autonomous" \
    "$prompt_payload" "$script_dir/../spec/continuation-capsule" "$runway" "$contract_helper"
fi

if [[ "$launch_codex" -eq 1 ]]; then
  exec bash "$kickstart"
fi

if [[ "$launch_shell" -eq 1 ]]; then
  cd "$wt"
  exec "${SHELL:-/bin/zsh}" -l
fi

echo
echo "Next:"
echo "  cd $wt"
echo "  codex"

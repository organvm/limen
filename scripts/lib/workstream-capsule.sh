#!/usr/bin/env bash

workstream_native_binary() {
  local agent="$1"
  local registry_binary="$2"
  local env_suffix env_key override candidate

  env_suffix="$(printf '%s' "$agent" | tr '[:lower:]-' '[:upper:]_')"
  env_key="LIMEN_${env_suffix}_BIN"
  override="$(printenv "$env_key" 2>/dev/null || true)"
  for candidate in "$override" "$agent" "$registry_binary"; do
    if [[ -n "$candidate" ]] && command -v "$candidate" >/dev/null 2>&1; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

workstream_export_context() {
  local agent="$1"
  local wt="$2"
  local capsule_dir="$3"
  local slug="$4"
  local workstream="$5"
  local capabilities="$6"
  local inherited_agent inherited_session generated_session conductor_agent_default conductor_session_default

  inherited_agent="${LIMEN_AGENT:-}"
  inherited_session="${LIMEN_SESSION_ID:-}"
  generated_session="workstream-${slug}-$(date -u +'%Y%m%dT%H%M%SZ')-$$"
  conductor_agent_default="$agent"
  conductor_session_default="$generated_session"
  if [[ -n "$inherited_agent" && -n "$inherited_session" ]]; then
    conductor_agent_default="$inherited_agent"
    conductor_session_default="$inherited_session"
  fi

  export LIMEN_AGENT="$agent"
  export LIMEN_SURFACE="workstream"
  export LIMEN_WORKTREE="$wt"
  export LIMEN_WORKSTREAM="$workstream"
  export LIMEN_AGENT_CAPABILITIES="$capabilities"
  export LIMEN_CAPSULE_ID="$slug"
  export LIMEN_CAPSULE_DIR="$capsule_dir"
  export LIMEN_CAPSULE_README="$capsule_dir/README.md"
  export LIMEN_SESSION_ID="${LIMEN_WORKSTREAM_SESSION_ID:-$generated_session}"
  export LIMEN_RUN_ID="${LIMEN_RUN_ID:-$LIMEN_SESSION_ID}"
  export LIMEN_ROOT_RUN_ID="${LIMEN_ROOT_RUN_ID:-$LIMEN_RUN_ID}"
  export LIMEN_PARENT_RUN_ID="${LIMEN_PARENT_RUN_ID:-}"
  export LIMEN_CONDUCTOR_AGENT="${LIMEN_CONDUCTOR_AGENT:-$conductor_agent_default}"
  export LIMEN_CONDUCTOR_SESSION_ID="${LIMEN_CONDUCTOR_SESSION_ID:-$conductor_session_default}"
  export LIMEN_TASK_ID="${LIMEN_TASK_ID:-}"
  export LIMEN_LEASE_GENERATION="${LIMEN_LEASE_GENERATION:-}"
  export LIMEN_EXECUTION_HASH="${LIMEN_EXECUTION_HASH:-}"
}

workstream_register_conduct_session() {
  local agent="$1"
  local wt="$2"
  local capabilities="$3"
  local limen_binary="${LIMEN_CLI_BIN:-limen}"
  local register_rc=0
  local capability
  local capability_args=()

  if ! command -v "$limen_binary" >/dev/null 2>&1; then
    unset LIMEN_CONDUCT_TOKEN
    printf 'conduct registration requires the limen CLI (set LIMEN_CLI_BIN to its path)\n' >&2
    return 127
  fi

  for capability in $capabilities; do
    capability_args+=(--capability "$capability")
  done

  if "$limen_binary" conduct register \
    --agent "$agent" \
    --surface workstream \
    --session-id "$LIMEN_SESSION_ID" \
    --origin direct \
    "${capability_args[@]}" \
    --worktree "$wt" \
    --human-protected \
    --concurrency 1 >/dev/null; then
    :
  else
    register_rc=$?
  fi
  # The broker client consumes its credential; the native model process must not inherit it.
  unset LIMEN_CONDUCT_TOKEN
  if [[ "$register_rc" -ne 0 ]]; then
    return "$register_rc"
  fi
  export LIMEN_HUMAN_PROTECTED=1
  printf 'registered protected conduct session: %s (%s)\n' "$LIMEN_SESSION_ID" "$agent"
}

workstream_launch_native_agent() {
  local agent="$1"
  local registry_binary="$2"
  local autonomous="$3"
  local readme="$4"
  local allow_shell_fallback="$5"
  local binary capsule_prompt=""

  if ! binary="$(workstream_native_binary "$agent" "$registry_binary")"; then
    if [[ "$allow_shell_fallback" -eq 1 ]]; then
      printf 'native %s CLI not found; opening a login shell\n' "$agent" >&2
      exec "${SHELL:-/bin/zsh}" -l
    fi
    printf 'native CLI not found for canonical lane %s\n' "$agent" >&2
    return 127
  fi

  if [[ "$autonomous" -eq 1 ]]; then
    IFS= read -r -d '' capsule_prompt < "$readme" || true
    case "$agent" in
      opencode)
        exec "$binary" --prompt "$capsule_prompt"
        ;;
      agy|gemini)
        exec "$binary" --prompt-interactive "$capsule_prompt"
        ;;
      *)
        exec "$binary" "$capsule_prompt"
        ;;
    esac
  fi

  # Agy has no argument-free interactive session. Seed its native interactive mode
  # with the capsule index when one is available.
  if [[ "$agent" == "agy" && -s "$readme" ]]; then
    IFS= read -r -d '' capsule_prompt < "$readme" || true
    exec "$binary" --prompt-interactive "$capsule_prompt"
  fi
  exec "$binary"
}

# Render one modular continuation capsule. The caller owns worktree creation and launch behavior.
render_workstream_capsule() {
  local wt="$1"
  local repo="$2"
  local slug="$3"
  local branch="$4"
  local workstream="$5"
  local from_ref="$6"
  local autonomous="$7"
  local prompt_payload="$8"
  local spec_dir="$9"
  local agent="${10}"
  local registry_binary="${11}"
  local conduct="${12}"
  local allow_shell_fallback="${13}"
  local agent_capabilities="${14}"
  local capsule_dir="$wt/.limen-workstream"
  local readme="$capsule_dir/README.md"
  local manifest="$capsule_dir/manifest.md"
  local intent="$capsule_dir/intent.md"
  local runtime="$capsule_dir/runtime.md"
  local closeout="$capsule_dir/closeout.md"
  local kickstart="$capsule_dir/kickstart.sh"
  local runtime_template="$spec_dir/runtime-interactive.md"
  local required_template created_at head_short upstream_ref origin_url status_line readme_action launch_helpers
  local capsule_changed=0

  mkdir -p "$capsule_dir"
  if [[ "$autonomous" -eq 1 ]]; then
    runtime_template="$spec_dir/runtime-autonomous.md"
  fi
  for required_template in "$runtime_template" "$spec_dir/closeout.md"; do
    if [[ ! -f "$required_template" ]]; then
      echo "capsule template not found: $required_template" >&2
      return 1
    fi
  done

  created_at=""
  if [[ -f "$manifest" ]]; then
    # shellcheck disable=SC2016
    created_at="$(sed -n 's/^- Created: `\(.*\)`$/\1/p' "$manifest" | head -n 1)"
  fi
  if [[ -z "$created_at" && -f "$readme" ]]; then
    created_at="$(sed -n 's/^Created: //p' "$readme" | head -n 1)"
  fi
  if [[ -z "$created_at" ]]; then
    created_at="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  fi
  head_short="$(git -C "$wt" rev-parse --short HEAD)"
  upstream_ref="$(git -C "$wt" rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || true)"
  origin_url="$(git -C "$repo" remote get-url origin 2>/dev/null || true)"
  status_line="$(git -C "$wt" status --short --branch | head -n 1)"
  launch_helpers="$(
    declare -f \
      workstream_native_binary \
      workstream_export_context \
      workstream_register_conduct_session \
      workstream_launch_native_agent
  )"

  _capsule_write_module() {
    local destination="$1"
    local temporary="${destination}.tmp.$$"
    cat > "$temporary"
    if [[ -f "$destination" ]] && cmp -s "$temporary" "$destination"; then
      rm -f "$temporary"
    else
      mv "$temporary" "$destination"
      capsule_changed=1
    fi
  }

  _capsule_write_module "$manifest" <<EOF
# Capsule manifest

- Created: \`$created_at\`
- Repo: \`$repo\`
- Worktree: \`$wt\`
- Branch: \`$branch\`
- Workstream: \`${workstream:-unassigned}\`
- Base ref: \`$from_ref\`
- HEAD at capsule write: \`$head_short\`
- Upstream: \`${upstream_ref:-none yet}\`
- Origin: \`${origin_url:-none}\`
- Status at capsule write: \`$status_line\`
- Autonomous: \`$([[ "$autonomous" -eq 1 ]] && printf yes || printf no)\`
- Agent: \`$agent\`
- Agent capabilities: \`$agent_capabilities\`
- Conduct: \`$([[ "$conduct" -eq 1 ]] && printf yes || printf no)\`

This is a historical snapshot. The runtime module requires fresh probes before action.
EOF
  _capsule_write_module "$intent" <<EOF
$prompt_payload
EOF
  _capsule_write_module "$runtime" < "$runtime_template"
  _capsule_write_module "$closeout" < "$spec_dir/closeout.md"
  _capsule_write_module "$readme" <<EOF
# Continuation capsule: $slug

This README is the initial prompt index, not a concatenated brief. Before acting, read these local
modules in order:

1. \`.limen-workstream/manifest.md\` — historical location and custody snapshot;
2. \`.limen-workstream/intent.md\` — objective and owner-specific context;
3. \`.limen-workstream/runtime.md\` — live probes and boundary decision contract;
4. \`.limen-workstream/closeout.md\` — receipt and successor rules.

Resolve them from \`$wt\`. Missing, unreadable, stale, or contradictory modules make the capsule
invalid; stop rather than guessing. The intent fixes scope. Live evidence determines the lane and
ending.

## Launch command

\`\`\`bash
bash "$kickstart"
\`\`\`

For a plain shell, use \`cd "$wt"\` and then \`\${SHELL:-/bin/zsh} -l\`.
EOF
  _capsule_write_module "$kickstart" <<EOF
#!/usr/bin/env bash
set -euo pipefail
$launch_helpers

cd "$wt"
for module in "$manifest" "$intent" "$runtime" "$closeout"; do
  if [[ ! -s "\$module" ]]; then
    printf 'invalid capsule: missing or empty module %s\n' "\$module" >&2
    exit 2
  fi
done
if git remote get-url origin >/dev/null 2>&1; then
  git fetch --prune
fi
git status --short --branch
workstream_export_context "$agent" "$wt" "$capsule_dir" "$slug" "$workstream" "$agent_capabilities"
if [[ "$conduct" -eq 1 ]]; then
  workstream_register_conduct_session "$agent" "$wt" "$agent_capabilities"
fi
workstream_launch_native_agent \
  "$agent" "$registry_binary" "$autonomous" "$readme" "$allow_shell_fallback"
EOF
  if [[ ! -x "$kickstart" ]]; then
    chmod +x "$kickstart"
    capsule_changed=1
  fi

  if [[ "$capsule_changed" -eq 1 ]]; then
    readme_action="wrote"
  else
    readme_action="unchanged"
  fi
  unset -f _capsule_write_module

  echo "capsule index: $readme ($readme_action)"
  echo "capsule modules: $manifest $intent $runtime $closeout"
  echo "kickstart command: bash $kickstart"
}

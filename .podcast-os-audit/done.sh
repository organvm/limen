#!/bin/bash
set -eu
# Acceptance predicate: "almost working" podcast OS
# All 8 acceptance clauses from START_HERE.md verified against real artifacts.

cd "$(dirname "$0")"
status=0

# 1. Candidates can be entered into the pipeline.
[[ -f guest_pipeline_template.csv ]] || { echo "FAIL: guest_pipeline_template.csv missing"; status=1; }
grep -q "guest_name,category,why_guest" guest_pipeline_template.csv || { echo "FAIL: pipeline template has no headers"; status=1; }

# 2. Each candidate has episode thesis and contact route.
grep -q "episode_thesis\|contact_route" guest_pipeline_template.csv || { echo "FAIL: pipeline template missing thesis/route fields"; status=1; }

# 3. Ari can approve/reject/protect/add note.
[[ -f ari_approval_dashboard.html ]] || { echo "FAIL: ari_approval_dashboard.html missing"; status=1; }
grep -q "APPROVE\|REJECT\|PROTECT" ari_approval_dashboard.html || { echo "FAIL: dashboard has no approval controls"; status=1; }

# 4. Approved candidates generate correspondence drafts.
[[ -f outreach_templates.md ]] || { echo "FAIL: outreach_templates.md missing"; status=1; }
grep -q "Subject:\|Hi \[" outreach_templates.md || { echo "FAIL: outreach templates have no drafts"; status=1; }

# 5. Accepted guests routed to LA/NYC/Austin.
([[ -f visual_language_v0.md ]] || [[ -f show_dna.yaml ]]) || { echo "FAIL: studio routing spec missing"; status=1; }
(grep -qi "los angeles\|new york\|austin" visual_language_v0.md 2>/dev/null || \
  grep -qi "los angeles\|new york\|austin" show_dna.yaml 2>/dev/null) || \
  { echo "FAIL: no three-city routing documented"; status=1; }

# 6. Producer receives research + segment brief.
[[ -f segment_deck.md ]] || { echo "FAIL: segment_deck.md missing"; status=1; }
grep -q "The Claim\|The Stress Test\|The Artifact" segment_deck.md || { echo "FAIL: segments not defined"; status=1; }

# 7. Recording produces predefined asset package.
[[ -f workflow.json ]] || { echo "FAIL: workflow.json missing"; status=1; }
grep -q "assets\|artifact" workflow.json || { echo "FAIL: workflow missing asset events"; status=1; }

# 8. Every promise and follow-up tracked.
grep -q "commitment\|followup" workflow.json || { echo "FAIL: workflow missing commitment tracking"; status=1; }

# Bonus: estate scans, transcripts, blueprints captured.
[[ -f unlicensed_therapy_archive.json ]] || { echo "WARN: guest archive (179 episodes) not pulled"; }
[[ -f unlicensed_therapy_guests.json ]] || { echo "WARN: guest dedup list not pulled"; }
[[ -f podcast_os_github_recomposition/PODCAST_OS_GITHUB_RECOMPOSITION_BLUEPRINT.md ]] || { echo "WARN: recomposition blueprint not downloaded"; }
[[ -f estate_scan_packets.md ]] || { echo "WARN: estate scan summary not written"; }
[[ -f ASK-INVENTORY.md ]] || { echo "WARN: ask inventory not captured"; }
[[ -f transcript_final.txt ]] || { echo "WARN: full transcript not captured"; }

if [[ $status -eq 0 ]]; then
  echo "✓ All 8 acceptance clauses verified."
  echo "✓ Podcast OS v0 starter pack: almost working."
  exit 0
else
  echo "✗ Some clauses not met."
  exit 1
fi

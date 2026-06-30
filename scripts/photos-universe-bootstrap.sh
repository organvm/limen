#!/usr/bin/env bash
set -Eeuo pipefail

STAMP="$(date +%Y%m%d-%H%M%S)"
REPO="$PWD"
WORKTREE_PARENT="${WORKTREE_PARENT:-$HOME/Workspace}"
WORKTREE_NAME="photos-universe-$STAMP"
FULL_HOME_SCAN="${FULL_HOME_SCAN:-0}"
HASH_DUPES="${HASH_DUPES:-0}"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --repo)
      REPO="$2"
      shift 2
      ;;
    --worktree-parent)
      WORKTREE_PARENT="$2"
      shift 2
      ;;
    --full-home-scan)
      FULL_HOME_SCAN=1
      shift
      ;;
    --hash-dupes)
      HASH_DUPES=1
      shift
      ;;
    *)
      echo "unknown arg: $1" >&2
      exit 2
      ;;
  esac
done

mkdir -p "$WORKTREE_PARENT"
WORKTREE="$WORKTREE_PARENT/$WORKTREE_NAME"
REPORT="$WORKTREE/reports/photos-universe-$STAMP"

if git -C "$REPO" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  BRANCH="work/photos-universe-$STAMP"
  git -C "$REPO" worktree add -b "$BRANCH" "$WORKTREE" HEAD
else
  mkdir -p "$WORKTREE"
  echo "not a git repo: created plain workspace at $WORKTREE"
fi

mkdir -p "$REPORT/raw" "$REPORT/generated"

capture() {
  local out="$1"
  shift
  {
    echo "# $*"
    echo "# generated: $(date -u +%FT%TZ)"
    "$@" 2>&1 || true
  } > "$REPORT/raw/$out"
}

capture "system.txt" sw_vers
capture "uname.txt" uname -a
capture "df-H.txt" df -H
capture "mount.txt" mount
capture "diskutil-list.txt" diskutil list
capture "diskutil-external-physical.txt" diskutil list external physical
capture "system-profiler-storage.txt" system_profiler SPStorageDataType
capture "system-profiler-usb-thunderbolt.txt" system_profiler SPUSBDataType SPThunderboltDataType
capture "screencapture-location.txt" defaults read com.apple.screencapture location
capture "screencapture-type.txt" defaults read com.apple.screencapture type

python3 - "$REPORT" "$FULL_HOME_SCAN" "$HASH_DUPES" <<'PY'
import csv
import hashlib
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

report = Path(sys.argv[1])
full_home = sys.argv[2] == "1"
hash_dupes = sys.argv[3] == "1"
home = Path.home()

image_ext = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".gif", ".tif", ".tiff", ".bmp", ".webp"}
raw_ext = {".dng", ".cr2", ".cr3", ".nef", ".arw", ".raf", ".rw2", ".orf", ".srw"}
video_ext = {".mov", ".mp4", ".m4v", ".avi", ".mts", ".m2ts", ".3gp"}
sidecar_ext = {".xmp", ".aae"}
media_ext = image_ext | raw_ext | video_ext | sidecar_ext

roots = []
for label, path in [
    ("desktop", home / "Desktop"),
    ("downloads", home / "Downloads"),
    ("pictures", home / "Pictures"),
    ("movies", home / "Movies"),
    ("documents", home / "Documents"),
    ("icloud_drive", home / "Library/Mobile Documents/com~apple~CloudDocs"),
]:
    if path.exists():
        roots.append((label, path))

volumes = Path("/Volumes")
if volumes.exists():
    for path in sorted(volumes.iterdir()):
        if path.is_dir():
            roots.append((f"volume:{path.name}", path))

if full_home:
    roots.append(("home_full", home))

seen = set()
scan_roots = []
for label, root in roots:
    try:
        real = root.resolve()
    except OSError:
        continue
    if real in seen:
        continue
    seen.add(real)
    scan_roots.append((label, root))

skip_names = {".git", "node_modules", ".Trash", "Library", "Caches", "DerivedData"}
if full_home:
    skip_names = {".git", "node_modules", ".Trash", "Caches", "DerivedData"}

def media_kind(ext):
    if ext in image_ext:
        return "image"
    if ext in raw_ext:
        return "raw"
    if ext in video_ext:
        return "video"
    if ext in sidecar_ext:
        return "sidecar"
    return "other"

libraries = []
rows = []
summary = defaultdict(lambda: {"count": 0, "bytes": 0})
size_groups = defaultdict(list)
live_pairs = defaultdict(set)

for label, root in scan_roots:
    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        current = Path(dirpath)
        kept = []
        for name in dirnames:
            path = current / name
            if name.endswith(".photoslibrary"):
                libraries.append(str(path))
                continue
            if name in skip_names:
                continue
            kept.append(name)
        dirnames[:] = kept

        for name in filenames:
            path = current / name
            ext = path.suffix.lower()
            if ext not in media_ext:
                continue
            try:
                st = path.stat()
            except OSError:
                continue
            kind = media_kind(ext)
            row = {
                "root": label,
                "kind": kind,
                "ext": ext,
                "bytes": st.st_size,
                "mtime": int(st.st_mtime),
                "path": str(path),
            }
            rows.append(row)
            summary[(label, kind, ext)]["count"] += 1
            summary[(label, kind, ext)]["bytes"] += st.st_size
            if st.st_size > 0:
                size_groups[st.st_size].append(str(path))
            if ext in {".heic", ".heif", ".mov"}:
                live_pairs[str(path.with_suffix(""))].add(ext)

with (report / "media-inventory.tsv").open("w", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=["root", "kind", "ext", "bytes", "mtime", "path"], delimiter="\t")
    writer.writeheader()
    writer.writerows(rows)

with (report / "media-summary.tsv").open("w", newline="") as handle:
    writer = csv.writer(handle, delimiter="\t")
    writer.writerow(["root", "kind", "ext", "count", "bytes"])
    for (root, kind, ext), value in sorted(summary.items()):
        writer.writerow([root, kind, ext, value["count"], value["bytes"]])

with (report / "photos-libraries.txt").open("w") as handle:
    for path in sorted(set(libraries)):
        handle.write(path + "\n")

with (report / "largest-media.tsv").open("w", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=["bytes", "kind", "ext", "root", "path"], delimiter="\t")
    writer.writeheader()
    for row in sorted(rows, key=lambda item: item["bytes"], reverse=True)[:500]:
        writer.writerow({key: row[key] for key in ["bytes", "kind", "ext", "root", "path"]})

dupes = []
if hash_dupes:
    for size, paths in size_groups.items():
        if len(paths) < 2:
            continue
        hashes = defaultdict(list)
        for path in paths:
            digest = hashlib.sha256()
            try:
                with open(path, "rb") as handle:
                    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                        digest.update(chunk)
                hashes[digest.hexdigest()].append(path)
            except OSError:
                continue
        for digest, group in hashes.items():
            if len(group) > 1:
                dupes.append({"bytes": size, "sha256": digest, "paths": group})
else:
    for size, paths in size_groups.items():
        if len(paths) > 1:
            dupes.append({"bytes": size, "sha256": "not-hashed", "paths": paths[:50]})

with (report / "duplicate-candidates.json").open("w") as handle:
    json.dump(dupes, handle, indent=2)

with (report / "live-photo-sidecar-candidates.tsv").open("w") as handle:
    handle.write("stem\texts\n")
    for stem, exts in sorted(live_pairs.items()):
        if ".mov" in exts and (".heic" in exts or ".heif" in exts):
            handle.write(f"{stem}\t{','.join(sorted(exts))}\n")

universe = {
    "roots_scanned": [{"label": label, "path": str(path)} for label, path in scan_roots],
    "media_files": len(rows),
    "photos_libraries": sorted(set(libraries)),
    "duplicate_candidate_groups": len(dupes),
    "hash_dupes": hash_dupes,
    "full_home_scan": full_home,
}
with (report / "universe-summary.json").open("w") as handle:
    json.dump(universe, handle, indent=2)
PY

cat > "$REPORT/UNIVERSE-INTERACTIONS.md" <<'MD'
# Photos Universe Interaction Map

Read-only assessment. Do not edit `Photos Library.photoslibrary` directly.

Decision surfaces to account for before moving/importing anything:

- Attached SSDs and `/Volumes/*`: capacity, filesystem, ownership, duplicates, Time Machine or archive role.
- Current screenshot/screen-recording location: `defaults read com.apple.screencapture location`.
- Photos libraries: local, external, old backups, and iCloud-backed libraries.
- iCloud Photos: imports may upload originals and affect cloud storage.
- Live Photos: `.HEIC/.MOV` pairs must stay together.
- RAW+JPEG pairs and `.XMP` sidecars must stay together.
- `.AAE` iOS edit sidecars should not be orphaned.
- Duplicate candidates are not deletion proof unless hashed.
- Photos imports should happen through Photos/AppleScript/Shortcuts, not database edits.
- Full Disk Access/TCC may hide files until granted.
- Archive policy comes before cleanup: import, verify, then optionally archive originals.
MD

cat > "$REPORT/generated/install-screen-capture-importer.sh" <<'INSTALL'
#!/usr/bin/env bash
set -Eeuo pipefail

CAPTURE_DIR="${CAPTURE_DIR:-$HOME/Pictures/Screen Captures}"
IMPORTER="$HOME/.local/bin/photos-screen-capture-importer.sh"
STATE_DIR="$HOME/Library/Application Support/photos-screen-capture-importer"
STATE="$STATE_DIR/imported.txt"
PLIST="$HOME/Library/LaunchAgents/com.user.photos-screen-capture-importer.plist"

mkdir -p "$CAPTURE_DIR" "$HOME/.local/bin" "$STATE_DIR"

defaults write com.apple.screencapture location "$CAPTURE_DIR"
killall SystemUIServer >/dev/null 2>&1 || true

cat > "$IMPORTER" <<'SCRIPT'
#!/usr/bin/env bash
set -Eeuo pipefail

CAPTURE_DIR="${CAPTURE_DIR:-$HOME/Pictures/Screen Captures}"
STATE_DIR="$HOME/Library/Application Support/photos-screen-capture-importer"
STATE="$STATE_DIR/imported.txt"
mkdir -p "$STATE_DIR"
touch "$STATE"

TMP="$(mktemp)"
NEW="$(mktemp)"
trap 'rm -f "$TMP" "$NEW"' EXIT

find "$CAPTURE_DIR" -maxdepth 1 -type f \( \
  -iname '*.png' -o -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.heic' -o \
  -iname '*.mov' -o -iname '*.mp4' -o -iname '*.m4v' \
\) -print | sort > "$TMP"

python3 - "$STATE" "$TMP" "$NEW" <<'PY'
import sys
state, src, out = sys.argv[1:4]
seen = set(open(state, errors="ignore").read().splitlines())
new = [p.strip() for p in open(src, errors="ignore") if p.strip() and p.strip() not in seen]
open(out, "w").write("\n".join(new) + ("\n" if new else ""))
PY

[ -s "$NEW" ] || exit 0

osascript - "$NEW" <<'APPLESCRIPT'
on run argv
  set listFile to item 1 of argv
  set txt to read POSIX file listFile
  set importFiles to {}
  repeat with p in paragraphs of txt
    if p is not "" then set end of importFiles to POSIX file p
  end repeat
  if (count of importFiles) > 0 then
    tell application "Photos"
      import importFiles skip check duplicates yes
    end tell
  end if
end run
APPLESCRIPT

cat "$NEW" >> "$STATE"
SCRIPT

chmod +x "$IMPORTER"

cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.user.photos-screen-capture-importer</string>
  <key>ProgramArguments</key>
  <array><string>$IMPORTER</string></array>
  <key>WatchPaths</key>
  <array><string>$CAPTURE_DIR</string></array>
  <key>RunAtLoad</key><true/>
  <key>ThrottleInterval</key><integer>20</integer>
  <key>StandardOutPath</key><string>$STATE_DIR/out.log</string>
  <key>StandardErrorPath</key><string>$STATE_DIR/err.log</string>
</dict>
</plist>
PLIST

plutil -lint "$PLIST"
launchctl bootout "gui/$(id -u)" "$PLIST" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl kickstart -k "gui/$(id -u)/com.user.photos-screen-capture-importer"

echo "Screenshots now save to: $CAPTURE_DIR"
echo "Importer installed: $IMPORTER"
INSTALL

chmod +x "$REPORT/generated/install-screen-capture-importer.sh"

cat > "$REPORT/NEXT-ACTIONS.md" <<MD
# Next Actions

1. Review:
   - media-summary.tsv
   - photos-libraries.txt
   - duplicate-candidates.json
   - UNIVERSE-INTERACTIONS.md

2. If the report looks sane, install screenshot/screen-recording import:

   bash "$REPORT/generated/install-screen-capture-importer.sh"

3. For deeper duplicate proof, rerun with:

   HASH_DUPES=1 bash "$0" --repo "$REPO" --worktree-parent "$WORKTREE_PARENT"

4. For broader home scan, rerun with:

   FULL_HOME_SCAN=1 bash "$0" --repo "$REPO" --worktree-parent "$WORKTREE_PARENT"
MD

echo
echo "Created worktree/workspace: $WORKTREE"
echo "Report: $REPORT"
echo "Start with: $REPORT/NEXT-ACTIONS.md"

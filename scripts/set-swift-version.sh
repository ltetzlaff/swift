#!/usr/bin/env bash
#
# Rewrite the default swift-version everywhere it is declared: the action, the
# two reusable workflows and the README inputs table. Used by the weekly Swift
# release check; safe to run by hand.
#
#   scripts/set-swift-version.sh 6.4.1
set -euo pipefail

NEW="${1:?usage: set-swift-version.sh <version>}"
if [[ ! "$NEW" =~ ^[0-9]+\.[0-9]+(\.[0-9]+)?$ ]]; then
  echo "error: '$NEW' is not a Swift release version" >&2
  exit 1
fi

cd "$(dirname "$0")/.."

CURRENT=$(awk '/^  swift-version:/ { f = 1 } f && /default:/ { gsub(/"/, "", $2); print $2; exit }' action.yaml)
[[ -n "$CURRENT" ]] || { echo "error: no swift-version default in action.yaml" >&2; exit 1; }

for f in action.yaml .github/workflows/build.yaml .github/workflows/test.yaml; do
  sed -i.bak "s/default: \"${CURRENT//./\\.}\"/default: \"${NEW}\"/" "$f"
  rm -f "$f.bak"
  grep -q "default: \"${NEW}\"" "$f" || { echo "error: $f was not updated" >&2; exit 1; }
done

# Keep the table column width: the cell is padded to 10 characters.
CELL=$(printf '%-10s' "\`${NEW}\`")
sed -i.bak -E "s/^(\| \`swift-version\` +\| )\`[^\`]+\` */\1${CELL}/" README.md
rm -f README.md.bak

echo "swift-version: ${CURRENT} -> ${NEW}"

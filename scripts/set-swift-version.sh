#!/usr/bin/env bash
#
# Rewrite the default swift-version: the action (its input default and the
# fallback for an empty input) and the README inputs table. The reusable
# workflows defer to the action and are left alone, which keeps this script
# within what GITHUB_TOKEN may push: it can never change .github/workflows/.
# Used by the weekly Swift release check; safe to run by hand.
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

CUR_RE="${CURRENT//./\\.}"
sed -i.bak -e "s/default: \"${CUR_RE}\"/default: \"${NEW}\"/" \
  -e "s/REQUESTED:-${CUR_RE}}/REQUESTED:-${NEW}}/" action.yaml
rm -f action.yaml.bak
for want in "default: \"${NEW}\"" "REQUESTED:-${NEW}}"; do
  grep -qF "$want" action.yaml || { echo "error: action.yaml has no '$want'" >&2; exit 1; }
done

# Keep the table column width: the cell is padded to 10 characters.
CELL=$(printf '%-10s' "\`${NEW}\`")
sed -i.bak -E "s/^(\| \`swift-version\` +\| )\`[^\`]+\` */\1${CELL}/" README.md
rm -f README.md.bak

echo "swift-version: ${CURRENT} -> ${NEW}"

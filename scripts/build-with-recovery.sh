#!/usr/bin/env bash
#
# Build a Swift package, discarding the restored .build and rebuilding cold if
# the build fails the way a stale cache makes it fail.
#
# Why this exists: the .build cache is keyed on Package.resolved + commit SHA
# and falls back, within one dependency graph, to whatever cache is newest.
# That fallback is the point — it is what makes ordinary commits incremental.
# But it also means first-party sources in the restored .build can predate the
# checkout, and llbuild does not always recompile every dependent of a module
# whose ABI moved. When it misses one, freshly compiled modules link against
# stale objects and the build dies at link time on a symbol that no longer
# exists.
#
# Scoping restore-keys fixed this for the dependency graph (see the
# Package.resolved hash in the cache key): a changed graph builds cold.
# First-party sources cannot be fixed that way, because they change on almost
# every commit — keying on them would mean a cold build every time and no
# cache at all. So the first-party axis is handled here instead: let the
# incremental build try, and when it fails with a stale-artifact signature,
# throw the cache away and build cold once.
#
# This also stops one poisoned cache from wedging a repository. A failed run
# saves no cache, so without recovery the stale entry stays the newest one and
# every later build restores it and fails the same way, until someone deletes
# it by hand through the API.
set -uo pipefail

: "${ACTION_PATH:?ACTION_PATH must be set to the action directory}"
: "${CONFIGURATION:?CONFIGURATION must be set}"

# Link-time and module-format failures only. Ordinary compile errors ("cannot
# find 'x' in scope") are never retried: they come from the source, so a cold
# rebuild would burn another full build and fail identically. These signatures,
# by contrast, essentially cannot occur when valid sources are built cold.
STALE_SIGNATURES='undefined reference to|Undefined symbols for architecture|duplicate symbol|error: link command failed|module file was created by a different version|is not a valid Swift module'

FLAGS=""
[[ "${STATIC_STDLIB:-false}" == "true" ]] && FLAGS+=" --static-swift-stdlib"
[[ -n "${PRODUCT:-}" ]] && FLAGS+=" --product ${PRODUCT}"
[[ "${JEMALLOC:-false}" == "true" ]] && FLAGS+=" -Xlinker -ljemalloc"

LOG="$(mktemp)"
trap 'rm -f "$LOG"' EXIT

run_build() {
  # Word splitting on FLAGS/EXTRA_FLAGS is intended: both carry multiple flags.
  # shellcheck disable=SC2086
  swift build --configuration "$CONFIGURATION" $FLAGS ${EXTRA_FLAGS:-} 2>&1 | tee "$LOG"
  return "${PIPESTATUS[0]}"
}

emit() {
  [[ -n "${GITHUB_OUTPUT:-}" ]] && echo "recovered=$1" >>"$GITHUB_OUTPUT"
  return 0
}

if run_build; then
  emit false
  exit 0
fi

# A build that started cold has no stale cache to blame.
if [[ -z "${CACHE_MATCHED_KEY:-}" ]]; then
  echo "::error::Build failed and no .build cache was restored, so the failure is in the sources."
  emit false
  exit 1
fi

if ! grep -qE "$STALE_SIGNATURES" "$LOG"; then
  echo "::error::Build failed without a stale-cache signature; not retrying. Re-run with the cache deleted if you suspect otherwise."
  emit false
  exit 1
fi

echo "::warning::Build failed at link time after restoring .build cache '${CACHE_MATCHED_KEY}'. That is the signature of stale objects linked against freshly compiled modules. Discarding the cache and rebuilding cold."

# .build/checkouts goes with it, so dependencies must be re-resolved, and the
# new checkouts re-stamped or the next run sees every dependency as changed.
rm -rf .build
swift package resolve
python3 "$ACTION_PATH/scripts/normalize-mtimes.py"

if run_build; then
  echo "::notice::Cold rebuild succeeded. The restored cache was stale; the cache saved by this run replaces it."
  emit true
  exit 0
fi

echo "::error::Cold rebuild failed too, so the failure is in the sources rather than the cache."
emit false
exit 1

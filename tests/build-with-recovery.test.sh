#!/usr/bin/env bash
#
# Exercises scripts/build-with-recovery.sh against a stubbed `swift`, so the
# recovery decisions are checked without a Swift toolchain or a real package.
#
# Each case stubs `swift` to fail (or succeed) with chosen output and asserts
# the exit status, how many builds ran, and the reported `recovered` output.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$HERE/../scripts/build-with-recovery.sh"

pass=0
fail=0

# Creates a sandbox with a stubbed `swift` on PATH, runs the script, and
# asserts. FAIL_OUTPUT is emitted by every `swift build` that should fail;
# SUCCEED_ON is the 1-based build attempt that starts succeeding (0 = never).
check() {
  local name="$1" succeed_on="$2" fail_output="$3" matched_key="$4"
  local want_status="$5" want_builds="$6" want_recovered="$7"

  local dir
  dir="$(mktemp -d)"
  mkdir -p "$dir/bin" "$dir/pkg" "$dir/action/scripts"
  cp "$SCRIPT" "$dir/action/scripts/build-with-recovery.sh"
  # The real normalize step is irrelevant here; recovery only needs it to exist.
  echo 'print("stub normalize")' >"$dir/action/scripts/normalize-mtimes.py"

  cat >"$dir/bin/swift" <<STUB
#!/usr/bin/env bash
if [[ "\$1" == "build" ]]; then
  n=\$(( \$(cat "$dir/count" 2>/dev/null || echo 0) + 1 ))
  echo "\$n" > "$dir/count"
  if [[ "$succeed_on" != "0" && "\$n" -ge "$succeed_on" ]]; then
    echo "Build complete!"
    exit 0
  fi
  echo "$fail_output"
  exit 1
fi
# swift package resolve, and anything else the script calls, succeeds quietly.
# No backticks in this heredoc: the delimiter is unquoted so $dir expands, which
# means backticks would run on the test shell instead of landing in the stub.
exit 0
STUB
  chmod +x "$dir/bin/swift"

  local out status builds recovered
  out="$(cd "$dir/pkg" && env \
    PATH="$dir/bin:$PATH" \
    ACTION_PATH="$dir/action" \
    CONFIGURATION=debug \
    CACHE_MATCHED_KEY="$matched_key" \
    GITHUB_OUTPUT="$dir/gh_output" \
    bash "$dir/action/scripts/build-with-recovery.sh" 2>&1)"
  status=$?
  builds="$(cat "$dir/count" 2>/dev/null || echo 0)"
  recovered="$(sed -n 's/^recovered=//p' "$dir/gh_output" 2>/dev/null | tail -1)"

  if [[ "$status" == "$want_status" && "$builds" == "$want_builds" && "$recovered" == "$want_recovered" ]]; then
    echo "ok   — $name"
    pass=$((pass + 1))
  else
    echo "FAIL — $name"
    echo "       want: status=$want_status builds=$want_builds recovered=$want_recovered"
    echo "       got:  status=$status builds=$builds recovered=$recovered"
    while IFS= read -r line; do echo "       | $line"; done <<<"$out"
    fail=$((fail + 1))
  fi
  rm -rf "$dir"
}

#     name                                        succeed_on  fail_output                              matched_key  status  builds  recovered
check "green build does not retry"                1           ""                                       "some-key"   0       1       false
check "stale link error recovers cold"            2           "undefined reference to '\$s4Demo3FooV'"  "some-key"   0       2       true
check "macOS stale signature recovers"            2           "Undefined symbols for architecture"     "some-key"   0       2       true
check "duplicate symbol recovers"                 2           "duplicate symbol '_foo'"                "some-key"   0       2       true
check "stale signature that fails cold too"       0           "undefined reference to '\$s4Demo3FooV'"  "some-key"   1       2       false
check "ordinary compile error never retries"      0           "error: cannot find 'x' in scope"        "some-key"   1       1       false
check "cold build failure never retries"          0           "undefined reference to '\$s4Demo3FooV'"  ""           1       1       false

echo
echo "passed=$pass failed=$fail"
[[ "$fail" == "0" ]]

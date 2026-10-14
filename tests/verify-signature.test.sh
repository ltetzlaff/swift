#!/usr/bin/env bash
#
# Exercises scripts/verify-signature.sh with throwaway keys, so the pinning
# rules are checked without downloading a toolchain: only a good signature
# from the pinned key passes; tampering, a different key, an expired key that
# signed after expiry, or a revoked key all fail.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$HERE/../scripts/verify-signature.sh"

pass=0
fail=0

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
export GNUPGHOME="$WORK/gnupg"
mkdir -p "$GNUPGHOME" && chmod 700 "$GNUPGHOME"

# Make a key, export its public half, and print its fingerprint.
mkkey() {
  local name="$1"
  gpg --batch --quiet --passphrase '' --quick-gen-key "$name <$name@test.invalid>" rsa2048 sign 1d 2>/dev/null
  gpg --batch --armor --export "$name@test.invalid" > "$WORK/$name.asc"
  gpg --batch --with-colons --fingerprint "$name@test.invalid" 2>/dev/null | awk -F: '/^fpr/ { print $10; exit }'
}
sign() { gpg --batch --quiet --yes --local-user "$1@test.invalid" --detach-sign -o "$3" "$2"; }

check() {
  local name="$1" want="$2"; shift 2
  local got=0
  ( unset GNUPGHOME; bash "$SCRIPT" "$@" ) >"$WORK/out" 2>&1 || got=$?
  if { [[ "$want" == pass ]] && (( got == 0 )); } || { [[ "$want" == fail ]] && (( got != 0 )); }; then
    pass=$((pass + 1)); echo "ok   $name: $(tail -n1 "$WORK/out")"
  else
    fail=$((fail + 1)); echo "FAIL $name (want $want, exit $got)"; sed 's/^/     /' "$WORK/out"
  fi
}

PINNED=$(mkkey pinned)
OTHER=$(mkkey other)
echo "toolchain" > "$WORK/file"
sign pinned "$WORK/file" "$WORK/file.sig"
sign other "$WORK/file" "$WORK/file.other.sig"

check "good signature from the pinned key"            pass "$WORK/file" "$WORK/file.sig"       "$WORK/pinned.asc" "$PINNED"
check "lowercase fingerprint is accepted"             pass "$WORK/file" "$WORK/file.sig"       "$WORK/pinned.asc" "$(tr '[:upper:]' '[:lower:]' <<< "$PINNED")"
cp "$WORK/file" "$WORK/file.tampered"; echo x >> "$WORK/file.tampered"
check "tampered file"                                 fail "$WORK/file.tampered" "$WORK/file.sig" "$WORK/pinned.asc" "$PINNED"
check "signed by another key, pinned key file"        fail "$WORK/file" "$WORK/file.other.sig" "$WORK/pinned.asc" "$PINNED"
cat "$WORK/pinned.asc" "$WORK/other.asc" > "$WORK/both.asc"
check "key file smuggles in a second key"             fail "$WORK/file" "$WORK/file.other.sig" "$WORK/both.asc"   "$PINNED"
check "fingerprint of the wrong key"                  fail "$WORK/file" "$WORK/file.sig"       "$WORK/pinned.asc" "$OTHER"
check "malformed fingerprint"                         fail "$WORK/file" "$WORK/file.sig"       "$WORK/pinned.asc" "not-a-fingerprint"
check "garbage signature"                             fail "$WORK/file" "$WORK/file"           "$WORK/pinned.asc" "$PINNED"

# Revoked: apply the key's own revocation certificate and re-export.
REV="$GNUPGHOME/openpgp-revocs.d/$PINNED.rev"
sed 's/^:-----/-----/' "$REV" | gpg --batch --quiet --import 2>/dev/null
gpg --batch --armor --export "pinned@test.invalid" > "$WORK/pinned-revoked.asc"
check "revoked pinned key"                            fail "$WORK/file" "$WORK/file.sig"       "$WORK/pinned-revoked.asc" "$PINNED"

echo
echo "passed=$pass failed=$fail"
(( fail == 0 ))

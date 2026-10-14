#!/usr/bin/env bash
#
# Verify a detached OpenPGP signature against one pinned key.
#
#   verify-signature.sh <file> <file.sig> <public-key.asc> <fingerprint>
#
# Succeeds only if the signature is cryptographically good AND was made by the
# key whose primary fingerprint is <fingerprint> (or one of its subkeys). The
# keyring is a fresh temporary GNUPGHOME holding just that key, so nothing in
# the runner's own keyring, and nothing else in the key file, is trusted.
set -euo pipefail

FILE="${1:?usage: verify-signature.sh <file> <sig> <key.asc> <fingerprint>}"
SIG="${2:?missing signature}"
KEY="${3:?missing public key}"
FPR="${4:?missing fingerprint}"
FPR="$(tr "[:lower:]" "[:upper:]" <<< "$FPR")"
if [[ ! "$FPR" =~ ^[0-9A-F]{40}$ ]]; then
  echo "error: fingerprint must be 40 hex characters" >&2
  exit 2
fi

GNUPGHOME="$(mktemp -d)"
export GNUPGHOME
trap 'rm -rf "$GNUPGHOME"' EXIT

gpg --batch --quiet --import "$KEY" 2>/dev/null

# gpg's exit status alone is not enough: it is 0 for a good signature from ANY
# key in the keyring. Read the machine-readable status instead.
STATUS="$(gpg --batch --status-fd 1 --verify "$SIG" "$FILE" 2>/dev/null || true)"

# VALIDSIG <signing-key-fpr> ... <primary-key-fpr> as the 10th field.
PRIMARY="$(awk '$1 == "[GNUPG:]" && $2 == "VALIDSIG" { print $NF }' <<< "$STATUS")"
if [[ "$PRIMARY" != "$FPR" ]]; then
  echo "error: $(basename "$FILE") is not validly signed by ${FPR}" >&2
  grep -E 'BADSIG|ERRSIG|NO_PUBKEY|VALIDSIG' <<< "$STATUS" >&2 || true
  exit 1
fi
# Revoked keys never count. Expired ones do: Swift keeps serving old releases
# signed while their key was valid, and gpg still checks the signature itself.
if grep -q 'REVKEYSIG' <<< "$STATUS"; then
  echo "error: signing key ${FPR} has been revoked" >&2
  exit 1
fi

echo "Good signature on $(basename "$FILE") from ${FPR}"

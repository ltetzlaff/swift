# Security policy

This action runs inside other people's CI with their secrets, so it is treated
as supply-chain code.

## Reporting a vulnerability

Please report privately via **Security → Report a vulnerability** on this
repository (GitHub private vulnerability reporting). Do not open a public issue
or PR for anything exploitable.

## Supported versions

Only the latest release, which the floating `v1` tag always points to, gets
fixes. Pin to a full commit SHA if you need a frozen version, and let
Dependabot move it.

## What the action guarantees

- The Swift toolchain is installed only if its detached signature verifies
  against a release key **vendored in [`keys/`](keys/README.md) and pinned by
  fingerprint**. Keys are never fetched from the server that serves the tarball.
- Every third-party action, here and in the workflows, is pinned to a full
  commit SHA. Dependabot proposes updates after a 7-day cooldown.
- Inputs never get interpolated into shell scripts; they reach scripts as
  environment variables, and `swift-version` must look like a release number.
- Workflows run with least-privilege `GITHUB_TOKEN` permissions, and only the
  steps that push hold credentials. [zizmor](https://docs.zizmor.sh) audits
  every PR.

## Known limits

- A toolchain restored from the `actions/cache` toolchain cache is not
  re-verified. Cache entries are scoped to the consuming repository, and only
  workflow runs in that repository can write them.
- SwiftPM resolves your package's dependencies from `Package.resolved` as
  written; this action does not audit them.

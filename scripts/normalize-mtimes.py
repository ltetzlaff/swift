#!/usr/bin/env python3
"""Normalize source file mtimes for deterministic llbuild change detection.

Problem: actions/checkout sets all file timestamps to "now", which differs
between CI runs. llbuild (SwiftPM's underlying build engine) uses mtime to
detect changes — so every CI run sees every file as "modified", triggering
a full rebuild even when the .build cache is properly restored.

Fix: set each file's mtime to a deterministic value derived from its content
hash. Same content → same mtime across any CI run, any machine.

Stamps must always land in the past. Build outputs are written with the real
clock, so a source dated after its own output inverts every input/output
comparison in the build graph, and tar warns on every cached file. Seconds
come from a fixed window below ANCHOR; the nanosecond field carries the rest
of the hash so distinct contents still get distinct stamps.

Run from the Swift package root (where Package.swift lives), AFTER
`swift package resolve` and BEFORE `swift build` / `swift test`.
"""
import hashlib
import os

ANCHOR = 1577836800  # 2020-01-01T00:00:00Z — no stamp is ever newer than this
WINDOW = 40 * 365 * 24 * 3600  # spread stamps over the 40 years below ANCHOR
NSEC = 1_000_000_000


def stamp(fp: str) -> int:
    """Set fp's mtime from its content hash. Returns 1 on success, 0 if unreadable."""
    try:
        with open(fp, "rb") as f:
            h = hashlib.md5(f.read()).hexdigest()
        secs = ANCHOR - int(h[:8], 16) % WINDOW
        nsecs = int(h[8:16], 16) % NSEC
        os.utime(fp, ns=(secs * NSEC + nsecs,) * 2)
        return 1
    except OSError:
        return 0


def normalize(path: str) -> int:
    return sum(
        stamp(os.path.join(root, name))
        for root, _, files in os.walk(path)
        for name in files
    )


total = 0

# Standard SwiftPM source directories
for d in ["Sources", "Tests", "Plugins"]:
    if os.path.isdir(d):
        total += normalize(d)

# Package manifest files (including version-specific variants)
for f in os.listdir("."):
    if f.startswith("Package") and f.endswith(".swift"):
        total += stamp(f)

if os.path.isfile("Package.resolved"):
    total += stamp("Package.resolved")

# Dependency checkouts (also source files from llbuild's perspective)
co = os.path.join(".build", "checkouts")
if os.path.isdir(co):
    total += normalize(co)

print(f"Normalized {total} file timestamps")

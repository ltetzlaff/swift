#!/usr/bin/env python3
"""Normalize source file mtimes for deterministic llbuild change detection.

Problem: actions/checkout sets all file timestamps to "now", which differs
between CI runs. llbuild (SwiftPM's underlying build engine) uses mtime to
detect changes — so every CI run sees every file as "modified", triggering
a full rebuild even when the .build cache is properly restored.

Fix: set each file's mtime to a deterministic value derived from its content
hash. Same content → same mtime across any CI run, any machine.

Run from the Swift package root (where Package.swift lives), AFTER
`swift package resolve` and BEFORE `swift build` / `swift test`.
"""
import hashlib
import os

EPOCH_OFFSET = 1577836800  # 2020-01-01T00:00:00Z


def normalize(path: str) -> int:
    count = 0
    for root, _, files in os.walk(path):
        for name in files:
            fp = os.path.join(root, name)
            try:
                h = hashlib.md5(open(fp, "rb").read()).hexdigest()[:8]
                ts = int(h, 16) + EPOCH_OFFSET
                os.utime(fp, (ts, ts))
                count += 1
            except (IOError, OSError):
                pass
    return count


total = 0

# Standard SwiftPM source directories
for d in ["Sources", "Tests", "Plugins"]:
    if os.path.isdir(d):
        total += normalize(d)

# Package manifest files (including version-specific variants)
for f in os.listdir("."):
    if f.startswith("Package") and f.endswith(".swift"):
        h = hashlib.md5(open(f, "rb").read()).hexdigest()[:8]
        ts = int(h, 16) + EPOCH_OFFSET
        os.utime(f, (ts, ts))
        total += 1

if os.path.isfile("Package.resolved"):
    h = hashlib.md5(open("Package.resolved", "rb").read()).hexdigest()[:8]
    ts = int(h, 16) + EPOCH_OFFSET
    os.utime("Package.resolved", (ts, ts))
    total += 1

# Dependency checkouts (also source files from llbuild's perspective)
co = os.path.join(".build", "checkouts")
if os.path.isdir(co):
    total += normalize(co)

print(f"Normalized {total} file timestamps")

#!/usr/bin/env python3
"""Delete the root package's own build outputs from a restored .build.

Why: the .build cache is reused across commits within one Package.resolved, so
a restored .build holds first-party objects compiled from older sources. The
incremental build is expected to recompile whatever changed, but it does not
always recompile every dependent of a changed module. When it misses one whose
use of a changed type is only a matter of size or layout, nothing fails: the
stale object still links, and the binary is wrong at runtime. Recovery in
build-with-recovery.sh cannot see that, because there is no build error.

Deleting the root package's outputs makes every first-party module compile
from scratch while dependency outputs, which Package.resolved pins, stay
cached. That is the slow part of a cold build kept fast and the risky part
made deterministic.

What goes: for every target and product the root manifest declares, its
<name>.build directory, its module files (.swiftmodule, .swiftdoc, ...), its
-tool host variant, and its linked product. Matching is by exact name, so
dependency outputs are never touched. Checkouts, artifacts, plugin outputs and
the build databases stay; llbuild re-runs every command whose outputs are gone.

Run from the Swift package root, after `swift package resolve`.
Usage: discard-root-outputs.py [--manifest FILE] [--build-dir DIR]
  --manifest   `swift package dump-package` JSON (default: run it)
  --build-dir  scratch path (default: .build)
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

# Top-level .build entries that never hold compiled first-party outputs.
SKIP_TOP = {"checkouts", "repositories", "artifacts", "plugins", "prebuilts"}

# Suffixes SwiftPM appends to a target or product name.
NAME_SUFFIXES = ("-tool", "-entitlement")


def c99name(name: str) -> str:
    """Module name SwiftPM derives from a target name."""
    return re.sub(r"[^A-Za-z0-9_]", "_", name)


def root_names(manifest: dict) -> set:
    names = set()
    for target in manifest.get("targets", []):
        names.add(target["name"])
        names.add(c99name(target["name"]))
    for product in manifest.get("products", []):
        names.add(product["name"])
    package = manifest.get("name")
    if package:
        # Synthesized test runner and discovery targets.
        for suffix in ("PackageTests", "PackageDiscoveredTests"):
            names.add(package + suffix)
    return names


def base_name(entry: str) -> str:
    """Strip extensions and SwiftPM suffixes: 'Foo-tool.build' -> 'Foo'."""
    base = entry.split(".", 1)[0]
    changed = True
    while changed:
        changed = False
        for suffix in NAME_SUFFIXES:
            if base.endswith(suffix) and len(base) > len(suffix):
                base = base[: -len(suffix)]
                changed = True
    return base


def config_dirs(build_dir: str):
    """Yield <build>/<triple>/<configuration> directories, not symlinks."""
    for top in sorted(os.listdir(build_dir)):
        top_path = os.path.join(build_dir, top)
        if top in SKIP_TOP or os.path.islink(top_path) or not os.path.isdir(top_path):
            continue
        for conf in sorted(os.listdir(top_path)):
            conf_path = os.path.join(top_path, conf)
            if not os.path.islink(conf_path) and os.path.isdir(conf_path):
                yield conf_path


def discard(build_dir: str, names: set) -> list:
    removed = []
    for conf in config_dirs(build_dir):
        dirs = [conf] + [
            os.path.join(conf, d)
            for d in sorted(os.listdir(conf))
            if d.startswith("Modules") and os.path.isdir(os.path.join(conf, d))
        ]
        for d in dirs:
            for entry in sorted(os.listdir(d)):
                if base_name(entry) not in names:
                    continue
                path = os.path.join(d, entry)
                if os.path.isdir(path) and not os.path.islink(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
                removed.append(os.path.relpath(path, build_dir))
    return removed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest")
    parser.add_argument("--build-dir", default=".build")
    args = parser.parse_args()

    if not os.path.isdir(args.build_dir):
        print(f"No {args.build_dir}; nothing to discard.")
        return 0

    if args.manifest:
        with open(args.manifest) as f:
            manifest = json.load(f)
    else:
        out = subprocess.run(
            ["swift", "package", "dump-package"],
            check=True, capture_output=True, text=True,
        ).stdout
        manifest = json.loads(out)

    names = root_names(manifest)
    if not names:
        print("::error::Root manifest declares no targets; refusing to guess.")
        return 1

    removed = discard(args.build_dir, names)
    print(f"Discarded {len(removed)} first-party build outputs "
          f"for {len(manifest.get('targets', []))} targets; dependencies stay cached.")
    for path in removed:
        print(f"  {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

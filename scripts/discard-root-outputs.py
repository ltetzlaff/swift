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

Two layouts are handled, and a .build may hold both:

- SwiftPM's native build system (the default up to Swift 6.3) writes
  .build/<triple>/<config>/: per target a <name>.build directory, module files
  under Modules*/, -tool host variants, and the linked products.
- Swift Build (the default from Swift 6.4) writes .build/out/: products and
  module files flat in Products/<Config>-<platform>-<arch>/ (<Target>.o,
  <Module>.swiftmodule, <Product>, lib<Product>.a, <Tests>.so,
  <Tests>-test-runner) and intermediates per package in
  Intermediates.noindex/<PackageName>.build/. The root package's
  intermediates directory goes whole; its name is the manifest name.

What goes: for every target and product the root manifest declares, the
outputs named after it. Matching is by exact name, so dependency outputs are
never touched. Checkouts, artifacts, plugin outputs and the build databases
stay; the build system re-runs every command whose outputs are gone.

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

# Top-level .build entries that never hold native-layout first-party outputs.
# "out" is Swift Build's, handled by discard_swift_build().
SKIP_TOP = {"checkouts", "repositories", "artifacts", "plugins", "prebuilts", "out"}

# Suffixes SwiftPM and Swift Build append to a target or product name.
NAME_SUFFIXES = ("-tool", "-entitlement", "-test-runner", "_test_runner")

# Swift Build's generated module maps add this to the target name: My-Lib-Swift.h.
MODULE_MAP_SUFFIX = "-Swift"


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
        # Static and dynamic library products: libFoo.a, libFoo.so.
        names.add("lib" + product["name"])
    package = manifest.get("name")
    if package:
        # Synthesized test runner and discovery targets.
        for suffix in ("PackageTests", "PackageDiscoveredTests"):
            names.add(package + suffix)
    return names


def base_name(entry: str, suffixes=NAME_SUFFIXES) -> str:
    """Strip extensions and SwiftPM suffixes: 'Foo-tool.build' -> 'Foo'."""
    base = entry.split(".", 1)[0]
    changed = True
    while changed:
        changed = False
        for suffix in suffixes:
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


def subdirs(parent: str):
    """Yield real (non-symlink) directories directly under parent."""
    if not os.path.isdir(parent):
        return
    for entry in sorted(os.listdir(parent)):
        path = os.path.join(parent, entry)
        if not os.path.islink(path) and os.path.isdir(path):
            yield path


def remove(path: str, build_dir: str, removed: list):
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path)
    else:
        os.remove(path)
    removed.append(os.path.relpath(path, build_dir))


def discard_matching(d: str, names: set, build_dir: str, removed: list, suffixes=NAME_SUFFIXES):
    for entry in sorted(os.listdir(d)):
        if base_name(entry, suffixes) in names:
            remove(os.path.join(d, entry), build_dir, removed)


def discard_native(build_dir: str, names: set, removed: list):
    for conf in config_dirs(build_dir):
        dirs = [conf] + [
            os.path.join(conf, d)
            for d in sorted(os.listdir(conf))
            if d.startswith("Modules") and os.path.isdir(os.path.join(conf, d))
        ]
        for d in dirs:
            discard_matching(d, names, build_dir, removed)


def discard_swift_build(build_dir: str, names: set, package: str, removed: list):
    out = os.path.join(build_dir, "out")
    # Products/<Config>-<platform>-<arch>/ holds every package's products and
    # module files side by side, so only exact root names go.
    for conf in subdirs(os.path.join(out, "Products")):
        discard_matching(conf, names, build_dir, removed)
    intermediates = os.path.join(out, "Intermediates.noindex")
    # Every root target's and product's intermediates, and nothing else.
    if package:
        root = os.path.join(intermediates, package + ".build")
        if os.path.isdir(root) and not os.path.islink(root):
            remove(root, build_dir, removed)
    for maps in subdirs(intermediates):
        if os.path.basename(maps).startswith("GeneratedModuleMaps"):
            discard_matching(maps, names, build_dir, removed,
                             NAME_SUFFIXES + (MODULE_MAP_SUFFIX,))


def discard(build_dir: str, names: set, package: str = "") -> list:
    removed = []
    discard_native(build_dir, names, removed)
    discard_swift_build(build_dir, names, package, removed)
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

    removed = discard(args.build_dir, names, manifest.get("name", ""))
    print(f"Discarded {len(removed)} first-party build outputs "
          f"for {len(manifest.get('targets', []))} targets; dependencies stay cached.")
    for path in removed:
        print(f"  {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

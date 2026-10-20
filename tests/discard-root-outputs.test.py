#!/usr/bin/env python3
"""Tests for scripts/discard-root-outputs.py against real .build layouts.

tests/discard-root-outputs/ holds trimmed listings of two real .build
directories of the same package, root "Server" (targets App, My-Lib,
MyLibTests; products Server, RootKit) depending on package "Dep" (Dep,
DepTool):

  native.txt       swift build with 6.3.3, SwiftPM's native build system
  swift-build.txt  swift build with 6.4.1, Swift Build (debug and release)

One path per line; a trailing "/" is a directory whose contents were trimmed,
"a -> b" a symlink. Regenerate by building such a package in the
swift:<version>-noble image and listing .build.
Usage: python3 tests/discard-root-outputs.test.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(HERE, "discard-root-outputs")
SCRIPT = os.path.join(HERE, "..", "scripts", "discard-root-outputs.py")
MANIFEST = os.path.join(FIXTURES, "manifest.json")

NATIVE_REMOVED = [
    "x86_64-unknown-linux-gnu/release/" + p for p in [
        "App.build",
        "Modules/App.swiftdoc", "Modules/App.swiftmodule", "Modules/App.swiftsourceinfo",
        "Modules/MyLibTests.swiftdoc", "Modules/MyLibTests.swiftmodule",
        "Modules/MyLibTests.swiftsourceinfo",
        "Modules/My_Lib.swiftdoc", "Modules/My_Lib.swiftmodule", "Modules/My_Lib.swiftsourceinfo",
        "Modules/ServerPackageDiscoveredTests.swiftdoc",
        "Modules/ServerPackageDiscoveredTests.swiftmodule",
        "Modules/ServerPackageDiscoveredTests.swiftsourceinfo",
        "Modules/ServerPackageTests.swiftdoc", "Modules/ServerPackageTests.swiftmodule",
        "Modules/ServerPackageTests.swiftsourceinfo",
        "MyLibTests.build", "My_Lib.build", "RootKit.product", "Server", "Server.product",
        "ServerPackageDiscoveredTests.build", "ServerPackageDiscoveredTests.derived",
        "ServerPackageTests.build", "ServerPackageTests.derived", "ServerPackageTests.product",
        "ServerPackageTests.xctest", "libRootKit.a",
    ]
]

SWIFT_BUILD_REMOVED = [
    f"out/Products/{conf}-linux-aarch64/{p}"
    for conf in ("Debug", "Release")
    for p in [
        "My-Lib.o", "My_Lib.swiftmodule", "MyLibTests-test-runner", "MyLibTests.so",
        "MyLibTests.swiftmodule", "MyLibTests_test_runner.swiftmodule", "Server",
        "libRootKit.a",
    ]
] + [
    "out/Intermediates.noindex/Server.build",
    "out/Intermediates.noindex/GeneratedModuleMaps-linux-aarch64/My-Lib-Swift.h",
    "out/Intermediates.noindex/GeneratedModuleMaps-linux-aarch64/My-Lib.modulemap",
]


def materialize(listing: str, build: str) -> None:
    with open(listing) as f:
        lines = [line.rstrip("\n") for line in f if line.strip()]
    for line in lines:
        path, _, target = line.partition(" -> ")
        full = os.path.join(build, path)
        os.makedirs(os.path.dirname(full.rstrip("/")), exist_ok=True)
        if target:
            # Listings applied later win, as a newer toolchain repoints them.
            if os.path.islink(full):
                os.remove(full)
            os.symlink(target, full)
        elif path.endswith("/"):
            os.makedirs(full, exist_ok=True)
        else:
            open(full, "w").close()


def tree(build: str) -> set:
    """Every file, symlink and empty directory, relative to build."""
    out = set()
    for root, dirs, files in os.walk(build):
        for name in files + [d for d in dirs if os.path.islink(os.path.join(root, d))]:
            out.add(os.path.relpath(os.path.join(root, name), build))
        if not dirs and not files:
            out.add(os.path.relpath(root, build) + "/")
    return out


def under(path: str, prefixes) -> bool:
    return any(path.rstrip("/") == p or path.startswith(p + "/") for p in prefixes)


def run(build: str, manifest: str = MANIFEST) -> list:
    out = subprocess.run(
        [sys.executable, SCRIPT, "--manifest", manifest, "--build-dir", build],
        check=True, capture_output=True, text=True,
    ).stdout
    print(out, end="")
    return sorted(line.strip() for line in out.splitlines() if line.startswith("  "))


def check(name: str, listings, want_removed) -> None:
    print(f"== {name}")
    d = tempfile.mkdtemp()
    try:
        build = os.path.join(d, ".build")
        for listing in listings:
            materialize(os.path.join(FIXTURES, listing), build)
        before = tree(build)
        removed = run(build)
        after = tree(build)
        assert removed == sorted(want_removed), (
            f"{name}: unexpected removals\n"
            f"  extra:   {sorted(set(removed) - set(want_removed))}\n"
            f"  missing: {sorted(set(want_removed) - set(removed))}")
        want_left = {p for p in before if not under(p, want_removed)}
        assert after == want_left, (
            f"{name}: tree differs\n"
            f"  gone:  {sorted(want_left - after)}\n"
            f"  extra: {sorted(after - want_left)}")
        # Dependency outputs, by name, must all survive.
        for p in after | before:
            if "Dep" in p and "Server" not in p and not under(p, want_removed):
                assert p in after, f"{name}: dependency output {p} was removed"
        # A second run finds nothing left to discard.
        assert run(build) == [], f"{name}: second run still discarded something"
    finally:
        shutil.rmtree(d)


def check_synthetic() -> None:
    """-tool host variants, hyphenated targets and lookalike names (native)."""
    print("== synthetic native")
    d = tempfile.mkdtemp()
    try:
        conf = os.path.join(d, ".build", "x86_64-unknown-linux-gnu", "release")
        os.makedirs(os.path.join(conf, "Modules"))
        os.symlink(conf, os.path.join(d, ".build", "release"))
        files = ["App.build/main.swift.o", "App-tool.build/x.o", "App", "App.product/x",
                 "Modules/App.swiftmodule", "Modules/My_Lib.swiftmodule", "My-Lib.build/a.o",
                 "HelloPackageTests.product/x",
                 "Dep.build/a.o", "Modules/Dep.swiftmodule", "Application.build/a.o",
                 "libApplication.a", "description.json"]
        for f in files:
            p = os.path.join(conf, f)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "w").close()
        manifest = os.path.join(d, "m.json")
        with open(manifest, "w") as f:
            json.dump({"name": "Hello", "targets": [{"name": "App"}, {"name": "My-Lib"}],
                       "products": [{"name": "App"}]}, f)
        run(os.path.join(d, ".build"), manifest)
        left = sorted(os.path.relpath(os.path.join(r, n), conf)
                      for r, _, ns in os.walk(conf) for n in ns)
        want = ["Application.build/a.o", "Dep.build/a.o", "Modules/Dep.swiftmodule",
                "description.json", "libApplication.a"]
        assert left == want, left
    finally:
        shutil.rmtree(d)


def main() -> int:
    check_synthetic()
    check("native (6.3.3)", ["native.txt"], NATIVE_REMOVED)
    check("swift build (6.4.1)", ["swift-build.txt"], SWIFT_BUILD_REMOVED)
    # A cache saved by 6.3 and then built by 6.4 holds both layouts.
    check("both layouts", ["native.txt", "swift-build.txt"],
          NATIVE_REMOVED + SWIFT_BUILD_REMOVED)
    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())

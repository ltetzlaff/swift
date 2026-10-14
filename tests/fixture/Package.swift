// swift-tools-version:6.0
// Minimal package the self-test and the Swift release check build with the
// action, to prove a toolchain installs and links end to end.
import PackageDescription

let package = Package(
    name: "Hello",
    targets: [.executableTarget(name: "Hello")]
)

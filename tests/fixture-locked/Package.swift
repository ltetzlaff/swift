// swift-tools-version:6.0
// Package with one dependency and a committed Package.resolved, for the
// locked-dependencies self-test.
import PackageDescription

let package = Package(
    name: "Locked",
    dependencies: [
        .package(url: "https://github.com/apple/swift-argument-parser", from: "1.5.0"),
    ],
    targets: [
        .executableTarget(
            name: "Locked",
            dependencies: [.product(name: "ArgumentParser", package: "swift-argument-parser")]
        ),
    ]
)

# Swift release signing keys

The public keys the action trusts to sign Swift toolchain tarballs. They are
vendored instead of fetched at run time, so whoever controls swift.org (which
also serves the tarballs) cannot swap the key and the tarball together.

| File            | Fingerprint                                | Signs      |
| --------------- | ------------------------------------------ | ---------- |
| `swift-6.x.asc` | `52BB7E3DE28A71BE22EC05FFEF80A866B47A981F` | Swift 6.x  |
| `swift-5.x.asc` | `A62AE125BBBFBB96A6E042EC925CC1CCED3D1561` | Swift 5.x  |

Fetched from `https://www.swift.org/keys/release-key-swift-<N>.x.asc` and
cross-checked against the `SWIFT_SIGNING_KEY` pinned in the official
Dockerfiles in [swiftlang/swift-docker](https://github.com/swiftlang/swift-docker).
The fingerprints are pinned a second time in `action.yaml`: a signature only
counts if it was made by exactly that primary key.

When Swift rotates a key (a new major, or an expiry), the weekly Swift release
check fails its smoke test. Add the new key here only after checking its
fingerprint against both sources above.

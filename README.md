# Swift Build Action

GitHub Actions for building Swift packages on Linux with **proper incremental compilation caching**.

## Why?

SwiftPM's build engine (llbuild) uses file modification times to detect changes. `actions/checkout` sets all timestamps to the current time, making every CI run look like a full source change — **complete rebuild even with a cached `.build` directory**.

This action normalizes file mtimes to deterministic content-based hashes. Same content → same mtime → llbuild skips unchanged modules → **true incremental builds**.

## Usage

```yaml
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - uses: ltetzlaff/swift@v1
```

That's it. Installs Swift, resolves dependencies, normalizes timestamps, and builds in release mode.

### Testing

```yaml
- uses: actions/checkout@v5
- uses: ltetzlaff/swift@v1
- run: swift test
```

### Build a specific product

```yaml
- uses: actions/checkout@v5
- uses: ltetzlaff/swift@v1
  with:
    product: MyServer
```

### Private dependencies

```yaml
- uses: actions/checkout@v5
- uses: ltetzlaff/swift@v1
  with:
    ssh-key: ${{ secrets.DEPLOY_SSH_KEY }}
```

### Build + push to ECR

```yaml
- uses: actions/checkout@v5
- uses: ltetzlaff/swift@v1
  id: build
  with:
    product: MyServer
    static-swift-stdlib: "true"

- run: cp "${{ steps.build.outputs.bin-path }}/MyServer" .
- uses: docker/setup-buildx-action@v3
- uses: aws-actions/configure-aws-credentials@v4
  with:
    aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
    aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
    aws-region: ${{ vars.AWS_REGION }}
- uses: aws-actions/amazon-ecr-login@v2
  id: ecr
- uses: docker/build-push-action@v6
  with:
    push: true
    context: .
    tags: ${{ steps.ecr.outputs.registry }}/my-server:${{ github.sha }}
    cache-from: type=gha
    cache-to: type=gha,mode=max
```

## Inputs

| Input                 | Default   | Description                                     |
| --------------------- | --------- | ----------------------------------------------- |
| `swift-version`       | `6.2`     | Swift toolchain version                         |
| `path`                | `.`       | Path to the Swift package                       |
| `ssh-key`             | _(empty)_ | SSH private key for private dependency repos    |
| `configuration`       | `release` | `debug` or `release`                            |
| `product`             | _(empty)_ | Specific product to build (all by default)      |
| `static-swift-stdlib` | `true`    | Statically link the Swift standard library      |
| `extra-swift-flags`   | _(empty)_ | Additional flags passed to `swift build`        |
| `cache-key-prefix`    | `swiftpm` | Cache key prefix for the `.build` directory     |
| `cache-suffix`        | _(empty)_ | Change to abandon existing caches and build cold |
| `jemalloc`            | `false`   | Install and link jemalloc                       |
| `build`               | `true`    | Set to `false` to skip build (e.g. for testing) |

## Outputs

| Output            | Description                                                        |
| ----------------- | ------------------------------------------------------------------ |
| `cache-hit`       | Whether the `.build` cache was an exact match                      |
| `cache-recovered` | Whether a stale `.build` was discarded and rebuilt cold            |
| `bin-path`        | Absolute path to the build output directory                        |

## How Caching Works

1. **Swift toolchain** — cached by version + OS + arch
2. **SwiftPM `.build` directory** — cached by `Package.resolved` hash + commit SHA. An earlier commit's cache is reused only when the `Package.resolved` hash matches: a `.build` from a different dependency graph would link stale objects against freshly compiled dependencies, so a changed graph always builds cold.
3. **Mtime normalization** — file timestamps are set to deterministic content-based hashes so llbuild sees unchanged files as unchanged. Stamps always land in the past (a fixed 40-year window before 2020) so that no source ever appears newer than the outputs built from it.
4. **Stale-cache recovery** — within one dependency graph the cache is still reused across commits, so a restored `.build` holds first-party objects older than the checkout. When a first-party module's ABI moves, llbuild does not reliably recompile every dependent, and the build dies at link time on a symbol that no longer exists. On that signature the action discards the cache, rebuilds cold once, and reports `cache-recovered: true`.

   This axis cannot be fixed by narrowing the cache key the way the dependency graph was. First-party sources change on nearly every commit, so keying on them would mean a cold build every time — no cache at all. Recovery keeps builds incremental and makes the rare stale link self-healing instead of fatal.

   Recovery also matters because a failed run saves no cache. Without it, one stale entry stays the newest for its key and every later build restores it and fails identically, until someone deletes it through the API.

### When recovery does *and* does not trigger

Only link-time and module-format failures are retried:

- `undefined reference to` / `Undefined symbols for architecture`
- `duplicate symbol`
- `error: link command failed`
- `module file was created by a different version` / `is not a valid Swift module`

Ordinary compile errors are never retried — they come from the source, so a second full build would just fail again and double the wait. A build that started cold is never retried either: there is no cache to blame.

## License

MIT

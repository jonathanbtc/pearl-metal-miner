# No Xcode: shaders are compiled at runtime from source

The build plan originally listed the missing `metal` compiler as a hard blocker requiring a
full Xcode install (~10 GB, Apple ID, and a version ceiling imposed by macOS
14.4.1). It is not a blocker. macOS ships the Metal shader compiler inside the
Metal framework itself, so `newLibraryWithSource:` compiles MSL at runtime with
no developer tools installed, and the Command Line Tools SDK already carries the
Metal and Foundation headers needed to build the host code.

Verified on this machine on 2026-08-02 by `tools/metal_probe.mm`, which builds
with `clang++` from the Command Line Tools alone and compiles and runs a kernel.

So: no `.metallib` build step, no `xcrun metal`, no Xcode. Shader source is
embedded in the host library and compiled at process start. This costs about a
second of startup and is invisible against a mining run.

> **Amended 2026-08-04.** The original reasoning for skipping a precompiled
> shader library was that a private, personal project has no distribution
> scenario ([ADR-0003](0003-private-repo-and-no-dev-fee.md)). That premise is gone — the
> project is published under
> [ADR-0005](0005-public-apache-2-built-from-isc-upstream.md) — but the decision is
> **strengthened, not weakened**, and for a better reason than the original one.
>
> Runtime compilation is now load-bearing. Tile dimensions, rank and the pattern
> may be dictated by the pool, so nothing about the job's shape can be hardcoded
> ([ADR-0006](0006-built-for-other-people-to-run.md)). Compiling at process start lets
> those arrive as Metal **function constants**, which the shader compiler folds
> into the generated code exactly as if they had been literals — portability at
> no cost in the hottest loop in the project. A precompiled `.metallib` could
> not do this. It also means a distributed build needs no toolchain on the
> user's machine beyond what macOS already ships, which is precisely what a
> miner other people run wants.

Phase 0 accordingly shrinks to installing Rust, which is still genuinely
required: `py-pearl-mining` provides both the Merkle commitment this design
depends on ([ADR-0001](0001-metal-port-covers-the-hot-loop-only.md)) and the local proof
verifier.

## Consequences

Shader syntax errors surface at runtime rather than build time. Mitigate by
compiling every kernel in a startup smoke test, so failures appear immediately
and in one place rather than at first dispatch.

Without Xcode there is no GPU debugger and no Metal System Trace. That was
comfortable when optimisation was ruled out entirely; under the amended
[ADR-0002](0002-backend-a-only.md) optimisation is authorised if a measured bar is missed,
and profiling blind is a poor way to spend that time. Installing Xcode 15.4
remains the escape hatch, and it becomes the *expected* move if the bar is
missed rather than a last resort. Nothing about the shipped artifact changes —
the build still requires only the Command Line Tools.

## Hardware facts established by the same probe

Recorded here because they are design constraints, not trivia:

- Apple M1 Max, 32 GPU cores, unified memory, Metal 3, GPU family **Apple7**
  (not Apple8).
- **Threadgroup memory: 32,768 bytes.** The binding constraint on tiling.
- Max threads per threadgroup: 1024.
- `MTLCreateSystemDefaultDevice()` returns **nil** for a plain command-line
  binary here. Use `MTLCopyAllDevices()[0]`. The originally planned skeleton
  would have failed on this at first run.
- An int8 × int8 → int32 multiply-accumulate over the full K = 4096 with every
  operand at ±127 returns exactly 66,064,384 — the worst case in the design, and
  the exact value §3.2 shows fp32 cannot represent. Backend A's arithmetic is
  confirmed on the hardware, not merely argued.

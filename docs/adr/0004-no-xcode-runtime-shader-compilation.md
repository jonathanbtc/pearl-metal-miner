# No Xcode: shaders are compiled at runtime from source

`Plan.md` §0.3 lists the missing `metal` compiler as a hard blocker requiring a
full Xcode install (~10 GB, Apple ID, and a version ceiling imposed by macOS
14.4.1). It is not a blocker. macOS ships the Metal shader compiler inside the
Metal framework itself, so `newLibraryWithSource:` compiles MSL at runtime with
no developer tools installed, and the Command Line Tools SDK already carries the
Metal and Foundation headers needed to build the host code.

Verified on this machine on 2026-08-02 by `tools/metal_probe.mm`, which builds
with `clang++` from the Command Line Tools alone and compiles and runs a kernel.

So: no `.metallib` build step, no `xcrun metal`, no Xcode. Shader source is
embedded in the host library and compiled at process start. This costs about a
second of startup and is invisible against a mining run. Because the project
stays private and personal ([[0003-private-repo-and-no-dev-fee]]) there is no
distribution scenario where a precompiled shader library would have earned its
keep.

Phase 0 accordingly shrinks to installing Rust, which is still genuinely
required: `py-pearl-mining` provides both the Merkle commitment this design
depends on ([[0001-metal-port-covers-the-hot-loop-only]]) and the local proof
verifier.

## Consequences

Shader syntax errors surface at runtime rather than build time. Mitigate by
compiling every kernel in a startup smoke test, so failures appear immediately
and in one place rather than at first dispatch.

Without Xcode there is no GPU debugger and no Metal System Trace. Acceptable
while there is no optimisation phase ([[0002-backend-a-only]]); if a kernel ever
becomes mysteriously slow or wrong, installing Xcode 15.4 is the escape hatch.

## Hardware facts established by the same probe

Recorded here because they are design constraints, not trivia:

- Apple M1 Max, 32 GPU cores, unified memory, Metal 3, GPU family **Apple7**
  (not Apple8).
- **Threadgroup memory: 32,768 bytes.** The binding constraint on tiling.
- Max threads per threadgroup: 1024.
- `MTLCreateSystemDefaultDevice()` returns **nil** for a plain command-line
  binary here. Use `MTLCopyAllDevices()[0]`. The skeleton in `Plan.md` §4 would
  have failed on this at first run.
- An int8 × int8 → int32 multiply-accumulate over the full K = 4096 with every
  operand at ±127 returns exactly 66,064,384 — the worst case in the design, and
  the exact value §3.2 shows fp32 cannot represent. Backend A's arithmetic is
  confirmed on the hardware, not merely argued.

# Local AI operator contract

This repository deploys a narrow, local inference stack. Prefer plain C, Bash,
systemd, small reversible patches, explicit errors, and pinned dependencies.

1. Direct Over Abstract
Favor direct, linear solutions over layered abstractions.

If a problem can be solved with a script, do not build a framework.

Configuration files are acceptable only when they reduce repetition – not when they replace clear code.

2. One Working Path
There must be one clear, executable path from input to output.

No fallbacks, no conditional inference pipelines, no dynamic backend selection unless absolutely required by hardware constraints.

If a model fails, fail fast and clearly. Do not silently degrade.

3. Minimal Dependencies
Prefer ctypes, ffi, or direct C/C++ bindings over heavy Python wrappers when performance matters.

For inference, prefer llama.cpp, whisper.cpp, or similar self-contained C++ runtimes.

Avoid PyTorch/TensorFlow if a quantized GGUF or ONNX runtime suffices.

4. No Magic
Every important operation must be transparent.

Log token counts, prompt sizes, inference times, and memory usage.

Do not hide system calls, GPU/CPU fallbacks, or memory allocations behind opaque helpers.

5. Local First, Offline Always
No external API calls unless explicitly enabled by the user.

All models, tokenizers, and configurations must be stored locally.

The agent must never assume network availability.

6. Reproducible & Self-Contained
A single run.sh or Makefile must be able to rebuild and run the entire project.

Store model hashes and quantization parameters in plain text next to the binary.

Avoid global Python environments – use venv, conda, or statically linked binaries.

7. Human-Readable State
Save inference state (context, history, sampler settings) as JSON or plain text.

Prefer stdin/stdout over GUI or web interfaces for core functionality.

Interactive modes are optional – batch mode must always work.

8. Performance by Design
Optimize for latency and memory first, then for throughput.

Use memory-mapped files for large models where possible.

Precompute token embeddings and KV caches when appropriate.

9. No Staging, No Migration
Each version is standalone.

Do not write converters, migrators, or compatibility layers.

If a format changes, update all files at once or document the breaking change clearly.

10. Build for the Machine You Have
Assume limited resources (4–8 GB VRAM, 16 GB RAM, 4–8 CPU cores).

Test on low-end hardware before assuming high-end performance.

Provide runtime flags for --threads, --batch-size, --gpu-layers.

11. Code as Documentation
Keep functions short and self-explanatory.

Use explicit variable names over comments.

Prefer assertion checks over silent type coercion.

12. Failure is Data
When inference fails, dump the full context (seed, prompt, temp, top-k, etc.) to a .debug.json file.

Do not catch exceptions unless you re-raise with actionable context.

13. Ship It
A working minimal version today is better than a perfect system tomorrow.

Release early, iterate locally.

Every commit should produce a runnable artifact.

14. Antirez Rule
"Simplicity is the ultimate sophistication, but only if it works."

If a simplification removes edge cases, it is good.

If a simplification hides necessary complexity, it is bad.

15. DS4 Principle
"Direct Solution, Direct Strategy – solve the problem once, solve it directly, and move on."

Do not over-engineer.

Do not under-solve.

Solve it completely, then stop.



## Mandatory workflow

`DISCOVER -> PLAN -> HUMAN_GATE -> PATCH -> VERIFY -> SECURITY_REVIEW -> CHECKPOINT`

- Read before editing. Keep each work unit path-scoped and reversible.
- Only one builder may modify files at a time.
- Scouts, verifiers, and security reviewers are read-only.
- Network access, downloads, package installation, `sudo`, service changes,
  firewall changes, deletion, publication, and remote operations require a
  human approval gate.
- A failed mutating operation may be retried without a new human gate only
  after recording its evidence, identifying and correcting the specific cause,
  and confirming that the target scope is unchanged and the retry is
  idempotent or reversible. Stop if the cause is unknown, scope expands, or a
  retry repeats the same failure.
- Never add an arbitrary-shell MCP tool or expose secrets in arguments/logs.
- Never run two huge model processes concurrently unless the operator approved
  the RAM/VRAM impact for that exact test.

## Release path

- DS4 native CUDA is a canary until correctness, two-GPU activity, stability,
  performance, and rollback gates pass.
- `llama.cpp` remains the fallback. Do not remove its working service path.
- Build only locked commits. Verify model SHA-256 before linking or starting it.
- CUDA target for RTX A4500 is explicit `sm_86`; do not silently use `native`.
- Native DS4 binds to loopback. Remote access is through an approved SSH or
  tailnet path, never an unauthenticated public listener.

## Verification

Run the smallest relevant checks first, then `tests/run.sh` on Linux/WSL.
Report exact commands, results, residual risk, and whether target-hardware
validation is still pending.

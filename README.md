# CPU Inference

Small, CPU-only OpenAI-compatible inference service for an AMD CPU, 128 GB
RAM and GGUF models. The sole inference runtime is `llama-server` from a
locally built `llama.cpp`; it does not install Python, PyTorch, Oobabooga,
Ollama or LiteLLM.

This repository never downloads a model or opens a public listener by itself.
Put a reviewed GGUF model in `models/`, record its checksum in the service
environment, then start the server on loopback.

## Layout

- `scripts/build-llama.sh` builds a supplied local `llama.cpp` checkout with
  CPU-native optimization and OpenBLAS when available.
- `scripts/run-server.sh` validates the model checksum and launches the API.
- `config/cpu-inference.env.example` is the complete runtime configuration.
- `deploy/cpu-inference.service` runs the server through systemd on loopback.

## Offline setup

1. Obtain the `llama.cpp` source and a GGUF model through the approved
   acquisition process. Do not place either in Git.
2. Copy the source checkout to `vendor/llama.cpp` and the GGUF to `models/`.
3. Create the configuration and record the exact SHA-256.

   ```bash
   cp config/cpu-inference.env.example config/cpu-inference.env
   sha256sum models/MODEL.gguf
   ${EDITOR:-vi} config/cpu-inference.env
   ```

4. Build and run locally.

   ```bash
   scripts/build-llama.sh
   scripts/run-server.sh
   ```

The default endpoint is `http://127.0.0.1:8080/v1`. `llama-server` supplies
the OpenAI-compatible API directly, so an extra proxy is unnecessary for one
model. The supplied production configuration deliberately listens on `0.0.0.0`
and requires a key through `--api-key-file`; it does not expose an unauthenticated
endpoint.

## CPU guidance

Start with a Q4_K_M GGUF. For a 128 GB host, leave at least 20 GB for the OS,
the page cache and the KV cache. Increase `CTX_SIZE` only after measuring
memory use and prompt throughput. `THREADS=0` lets llama.cpp select the CPU
count; set it explicitly once benchmarked.

`CPU_TARGET=native` tunes the binary for this machine. For a portable binary,
set a target supported by the deployed CPU instead. Build flags and model
digests are deliberately visible in the repository configuration.

## Check

With the server running:

```bash
curl --fail --silent --show-error http://127.0.0.1:8080/health
curl --fail --silent --show-error -H "Authorization: Bearer YOUR_KEY" http://127.0.0.1:8080/v1/models
```

No service is enabled or started by this repository.

## Deployment to `llmm`

`config/llmm.env` pins the existing Qwen3-Coder 30B GGUF on `10.25.13.22`.
The `llmm` installer builds a CPU-native binary with OpenBLAS, writes the
systemd service, disables the active PDS4 lanes and creates the API key file
if it does not exist:

```bash
scripts/install-llmm.sh
```

Retrieve the generated key only from the server's trusted console, then use it
as `Authorization: Bearer KEY`. The installer intentionally does not print it.

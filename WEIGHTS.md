# Weight Installation and Execution

## Pinned family

`MODEL_MANIFEST.json` is authoritative. The current family uses official Qwen2.5 Instruct GGUF
repositories and Q4_K_M quantization:

- `Qwen/Qwen2.5-1.5B-Instruct-GGUF`
  - revision `91cad51170dc346986eccefdc2dd33a9da36ead9`
  - one file, approximately 1.1 GB
- `Qwen/Qwen2.5-7B-Instruct-GGUF`
  - revision `bb5d59e06d9551d752d08b292a50eb208b07ab1f`
  - two split files, approximately 4.7 GB total
- `Qwen/Qwen2.5-32B-Instruct-GGUF`
  - revision `a15e3cc10f8bbb2c0af6f8f1f34a32e3b060c09d`
  - five split files, approximately 19.9 GB total

The downloader passes both the exact filename and the pinned repository revision to Hugging Face.
After download, every file is SHA-256 hashed into a local `weights.lock.json`.
Before every real inference load, the runtime re-hashes that tier and rejects any lock mismatch.

## Windows and RTX 4090

Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
python -m pip install huggingface-hub
```

Install `llama-cpp-python` with CUDA support. Prebuilt CUDA wheels, when available for the installed
Python and CUDA versions, are documented by the llama-cpp-python project. A source build can be
requested with:

```powershell
$env:CMAKE_ARGS = "-DGGML_CUDA=on"
$env:FORCE_CMAKE = "1"
python -m pip install --upgrade --force-reinstall llama-cpp-python
```

This compilation requires Visual Studio C++ Build Tools, CMake, and a compatible CUDA toolkit.

Then download:

```powershell
.\scripts\download_weights.ps1 -Tier all
```

Check disk, local files, llama.cpp, and GPU-offload readiness:

```powershell
python -m oims doctor
```

Run:

```powershell
.\scripts\run_all_weights.ps1 `
  -Prompt "Run a governed family conformance probe." `
  -MaxTokens 256
```

## Memory behavior

The family runner is deliberately sequential. It loads ISO-1B, writes and seals its receipt,
releases that backend, then repeats for ISO-7B and ISO-30B.

The 32B Q4_K_M files occupy approximately 19.9 GB before runtime overhead. The manifest defaults
that tier to a 2,048-token context to keep a 24 GB GPU practical. If complete GPU offload is too
tight, reduce the number of GPU layers:

```bash
python -m oims family \
  --prompt "conformance probe" \
  --n-gpu-layers 45 \
  --n-ctx 2048
```

Lower layers move computation to system RAM and reduce GPU memory pressure at the cost of speed.

## Weight checks

Fast presence and lock check:

```bash
python -m oims weights check --tier all
```

Recompute SHA-256 for all 25.7 GB:

```bash
python -m oims weights check --tier all --full-hash
```

The weight folders and generated artifacts are ignored by Git.

## Evidence boundary

CI uses a deterministic fixture because public hosted CI cannot download or execute 25.7 GB of
weights on every commit. Fixture receipts say `TEST_OR_INCOMPLETE`. Only a complete local family
run through llama.cpp can emit `weight_execution_verified: true` and `evidence_class:
WEIGHT_BACKED`.

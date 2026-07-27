# Weight Installation and Execution

## Pinned heterogeneous family

`MODEL_MANIFEST.json` is authoritative.

| Tier | GGUF repository | Revision | File | Bytes | SHA-256 |
| --- | --- | --- | --- | ---: | --- |
| ISO-1B | `Qwen/Qwen2.5-1.5B-Instruct-GGUF` | `91cad511...6ead9` | `qwen2.5-1.5b-instruct-q4_k_m.gguf` | 1,117,320,736 | `6a1a2eb6...e9407e` |
| ISO-7B | `bartowski/Mistral-7B-Instruct-v0.3-GGUF` | `61fd4167...4db48` | `Mistral-7B-Instruct-v0.3-Q4_K_M.gguf` | 4,372,812,000 | `1270d22c...e562b6` |
| ISO-30B | `bartowski/moonshotai_Kimi-Linear-48B-A3B-Instruct-GGUF` | `228dbe47...8a1c5` | `moonshotai_Kimi-Linear-48B-A3B-Instruct-Q3_K_M.gguf` | 22,680,802,720 | `d63efc0d...dc146d` |

The full hashes are stored in the manifest. The downloader supplies the exact revision and
filename, hashes the downloaded bytes, and refuses to create a lock if size or SHA-256 differs
from the pinned upstream LFS identity. Every real load re-hashes the tier and checks both the
manifest and local lock.

The Qwen GGUF is official upstream. The Mistral and Kimi GGUFs are community conversions by
bartowski; their base-model provenance and conversion status are explicit in the manifest.

## Windows and RTX 4090

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[weights]"
```

Install the current CUDA build:

```powershell
$env:CMAKE_ARGS = "-DGGML_CUDA=on"
$env:FORCE_CMAKE = "1"
python -m pip install --upgrade --force-reinstall --no-cache-dir "llama-cpp-python>=0.3.34,<0.4"
```

This source-build path requires Visual Studio C++ Build Tools, CMake, and a compatible CUDA
toolkit. The project also publishes CUDA wheels for supported Python/CUDA combinations:
<https://pypi.org/project/llama-cpp-python/>.

Download and verify:

```powershell
.\scripts\download_weights.ps1 -Tier all
python -m oims weights check --tier all --full-hash
python -m oims doctor
```

Run and verify:

```powershell
.\scripts\run_all_weights.ps1 `
  -Prompt "Run a governed heterogeneous-family probe." `
  -MaxTokens 256
```

## Memory behavior

The runtime loads and releases one tier at a time.

- ISO-1B: full GPU offload by default.
- ISO-7B: full GPU offload by default.
- ISO-30B/Kimi: 20 of 27 model layers offloaded by default; remaining work uses system RAM.

The 22.68 GB Kimi GGUF alone nearly fills a 24 GB GPU. Full offload is not the safe default after
KV cache and runtime overhead. Tune only after a successful baseline:

```bash
python -m oims run \
  --tier ISO-30B \
  --prompt "strategy probe" \
  --n-gpu-layers 22 \
  --n-ctx 4096
```

If CUDA allocation fails, lower `--n-gpu-layers`. With 128 GB system RAM the model remains
runnable, though CPU-resident layers reduce speed.

## Evidence boundary

Fast checks validate exact byte sizes and lock lineage. Full checks recompute all 28.17 GB:

```bash
python -m oims weights check --tier all --full-hash
```

CI uses deterministic fixtures and cannot claim real-weight execution. Only the physical family
run can produce `weight_execution_verified: true` and `evidence_class: WEIGHT_BACKED`.

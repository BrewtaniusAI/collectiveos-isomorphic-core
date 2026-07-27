# CollectiveOS Isomorphic Core

One governed runtime contract. Three real local-weight tiers. Auditable family receipts.

CollectiveOS Isomorphic Core is the implementation surface for the Open Isomorphic Model
Standard (OIMS). It binds three instruction-model weight classes to one input-first governance
contract and one conformance-record schema:

| OIMS tier | Bound model | Quantization | Download |
| --- | --- | --- | ---: |
| ISO-1B | Qwen2.5-1.5B-Instruct | Q4_K_M GGUF | 1.1 GB |
| ISO-7B | Qwen2.5-7B-Instruct | Q4_K_M GGUF | 4.7 GB |
| ISO-30B | Qwen2.5-32B-Instruct | Q4_K_M GGUF | 19.9 GB |

The model repositories are official Qwen GGUF releases under Apache-2.0. Every tier is pinned to
an immutable Hugging Face commit in `MODEL_MANIFEST.json`. Weight files stay local and are never
committed to Git.

## What runs

- real GGUF inference through `llama-cpp-python`;
- all three tiers sequentially, so only one model occupies GPU memory at a time;
- pre-inference input governance;
- post-inference output validation;
- per-tier sealed JSON-LD receipts;
- a family conformance report that compares runtime invariants;
- cryptographic hashes for contracts, prompts, outputs, records, and downloaded weight files;
- mandatory weight-lock revalidation before every real model load;
- deterministic fixtures for CI that are always labeled as non-weight evidence.

The ISO-30B name is retained as the OIMS capacity class. Its current weight binding is the
32.5-billion-parameter Qwen2.5-32B model.

## Quick start

Python 3.10 or newer is required.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[weights]"
```

Install a CUDA-enabled `llama-cpp-python` build for NVIDIA GPU offload before running the 7B or
32B tier. Platform-specific instructions are in `WEIGHTS.md`.

Check the machine:

```bash
python -m oims doctor
```

Download and hash all 25.7 GB of pinned weights:

```powershell
.\scripts\download_weights.ps1 -Tier all
```

Run every tier sequentially:

```powershell
.\scripts\run_all_weights.ps1 -Prompt "Explain the OIMS runtime contract."
```

Equivalent Python commands:

```bash
python -m oims weights pull --tier all
python -m oims weights check --tier all
python -m oims family --prompt "Explain the OIMS runtime contract."
```

Run one tier:

```bash
python -m oims run --tier ISO-7B --prompt "Give a bounded systems analysis."
```

Artifacts are written under `artifacts/`:

```text
artifacts/
├── iso-1b-conformance.jsonld
├── iso-7b-conformance.jsonld
├── iso-30b-conformance.jsonld
└── conformance_report.jsonld
```

## Runtime sequence

```text
validate input
  → resolve pinned local weights
  → run one tier
  → validate output
  → seal tier receipt
  → release model memory
  → run next tier
  → compare invariant vectors
  → seal family report
```

Input validation happens before the weight backend is constructed. Wrong input types and
over-length inputs therefore cannot reach model inference.

## Verification

Run the dependency-light test suite:

```bash
python -m unittest discover -v
python -m oims --artifacts-dir artifacts-smoke family \
  --backend fixture \
  --prompt "fixture conformance probe"
```

Fixture output validates governance and receipt mechanics only. A report is labeled
`WEIGHT_BACKED` only when every tier was executed by the real local-weight backend.

## What runtime isomorphism means here

OIMS runtime isomorphism is a bounded engineering claim: every tier must preserve the same
contract hash, contract version, family identity, governance order, and response schema. Runtime
drift is the mismatch ratio across that invariant vector.

It does **not** mean that the three neural networks have identical weights, produce identical
wording, or constitute universal scientific proof. Model-quality and semantic-equivalence
benchmarks remain separate work.

## Repository map

- `oims/` — package runtime, backends, contracts, receipts, and weight management
- `contracts/oims-family.contract.yaml` — shared family contract
- `MODEL_MANIFEST.json` — pinned model and file manifest
- `tests/` — assertive governance, manifest, receipt, and family tests
- `.github/workflows/ci.yml` — Python 3.10/3.12 CI
- `iso-models/` — tier-level release documentation
- `WEIGHTS.md` — download, hardware, CUDA, and troubleshooting guide
- `CLAIMS.md` / `LIMITATIONS.md` — precise evidence boundaries

## License boundary

The bound Qwen2.5 GGUF weights declare Apache-2.0. This repository does not currently declare a
license for the OIMS-authored source code; public visibility alone does not grant reuse rights.
Add the project’s intended custom license before a formal source release.

Associated theoretical context: <https://doi.org/10.5281/zenodo.19477170>

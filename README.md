# CollectiveOS Isomorphic Core

One governed contract. Three different model architectures. Explicit CollectiveOS role bindings.

CollectiveOS Isomorphic Core implements a bounded heterogeneous model family for the Open
Isomorphic Model Standard (OIMS). The family deliberately uses different upstream providers and
architectures so conformance is tested across substrates rather than across sizes of one model
line.

| OIMS tier | Local binding | Architecture | Agent role | Quantization | Exact bytes |
| --- | --- | --- | --- | --- | ---: |
| ISO-1B | Qwen2.5-1.5B-Instruct | Qwen2 | intake/edge | Q4_K_M | 1,117,320,736 |
| ISO-7B | Mistral-7B-Instruct-v0.3 | Mistral | operator | Q4_K_M | 4,372,812,000 |
| ISO-30B | Kimi-Linear-48B-A3B-Instruct | Kimi Linear | strategist | Q3_K_M | 22,680,802,720 |

The ISO-30B name remains the large OIMS capacity class. Its heterogeneous reference binding is
Kimi Linear 48B total / 3B active. The exact local family download is 28,170,935,456 bytes.

## Evidence boundary

OIMS runtime isomorphism means every tier preserves the same contract hash, governance order,
receipt schema, and lawful transition rules. The report also proves that the executed tiers came
from three declared architecture families.

It does not mean the models have identical weights or wording, and it is not independent proof of
semantic equivalence. Fixture runs validate mechanics only. A `WEIGHT_BACKED` report requires all
three pinned GGUF files to be hash-verified and executed locally.

## CollectiveOS roles

`AGENT_MANIFEST.json` binds local roles to tiers:

| Collective role | Default tier |
| --- | --- |
| SYN Edge | ISO-1B |
| Rabbit Ops, Max Device, Muse Creative | ISO-7B |
| Giles Strategist, Cypher Analyst, Lock Security | ISO-30B |

These are explicit `role_binding_only` profiles. The repository makes no autonomous-worker claim.
Collective responses declare the governance route `QC -> GATA -> GATA_PRIME`.

List bindings:

```bash
python -m oims agents
```

Run one CollectiveOS role:

```bash
python -m oims collective \
  --agent Giles \
  --prompt "Create a bounded implementation strategy."
```

The response is emitted as a sealed `CollectiveOIMSResponse` envelope linked to the tier receipt.
File-based requests use `schemas/collective-request.schema.json`:

```bash
python -m oims collective --request-file examples/collective-request.json
```

## Install

Python 3.10 or newer is required.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[weights]"
```

Install a CUDA-enabled `llama-cpp-python>=0.3.34,<0.4`. Current installation options and the
Windows/RTX 4090 path are in `WEIGHTS.md`.

## Download and run the whole family

```powershell
.\scripts\download_weights.ps1 -Tier all
python -m oims doctor
.\scripts\run_all_weights.ps1 -Prompt "Explain the shared OIMS contract."
```

Equivalent commands:

```bash
python -m oims weights pull --tier all
python -m oims weights check --tier all --full-hash
python -m oims mesh --prompt "Explain the shared OIMS contract."
python -m oims verify \
  --path artifacts/conformance_report.jsonld \
  --require-weight-backed
```

Models load sequentially. ISO-1B and ISO-7B default to full GPU offload. Kimi defaults to 20 GPU
layers and uses system RAM for the remainder, which is the safer starting point for a 24 GB GPU.

## ISO-Mesh

`oims mesh` is the explicit mesh surface. It currently provides governed role routing plus
sequential family conformance. Distributed multi-node inference is outside this release.

```text
validate input
  -> resolve exact pinned weight identity
  -> execute Qwen intake tier
  -> release backend
  -> execute Mistral operator tier
  -> release backend
  -> execute Kimi strategist tier
  -> compare shared runtime invariants
  -> seal and verify family report
```

## Artifacts

```text
artifacts/
├── iso-1b-conformance.jsonld
├── iso-7b-conformance.jsonld
├── iso-30b-conformance.jsonld
├── conformance_report.jsonld
└── collective-<request-hash>.jsonld
```

Standalone JSON Schemas live in `schemas/`. `python -m oims verify` checks seals, nested hash
links, manifest identity, contract identity, tier completeness, architecture diversity, agent
bindings, and evidence-class consistency.

## Repository map

- `oims/` — runtime, agents, CollectiveOS bridge, receipts, verification, and weight management
- `MODEL_MANIFEST.json` — heterogeneous model bindings and exact upstream weight identities
- `AGENT_MANIFEST.json` — explicit CollectiveOS role bindings
- `COLLECTIVE_INTEGRATION.md` — request/response and deployment boundary
- `contracts/` — shared runtime contract
- `schemas/` — machine-readable manifests and receipt schemas
- `SCOPE_MATRIX.json` — machine-readable completeness ledger
- `requirements/` / `SBOM.spdx.json` — dependency locks and source SBOM
- `SECURITY.md` / `CONTRIBUTING.md` — trust boundaries and contribution gates
- `tests/` — assertive governance, provenance, role-binding, and receipt tests
- `iso-models/` — tier and mesh release surfaces

## License boundary

The bound model licenses are recorded per tier: Apache-2.0 for Qwen and Mistral; MIT for Kimi
Linear. Community GGUF conversion provenance is explicit in the manifest. OIMS-authored source
still has no declared license; public visibility alone does not grant reuse rights. The owner must
select the intended source license before a formal source release.

Associated theoretical context: <https://doi.org/10.5281/zenodo.19477170>

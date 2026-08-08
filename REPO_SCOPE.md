# Repository Scope

This repository is the implementation and verification surface for the local OIMS heterogeneous
agent family and its CollectiveOS role-binding bridge.

## Included and acceptance-tested

- three locally runnable GGUF tiers from different providers and architecture families;
- immutable GGUF repository revisions, exact filenames, byte counts, and upstream SHA-256 values;
- one shared input-first governance contract;
- explicit agent profiles and CollectiveOS aliases using `role_binding_only` semantics;
- ISO-Mesh role routing and sequential family-conformance execution;
- local llama.cpp inference with per-tier GPU/offload defaults;
- per-tier, family, and CollectiveOS hash-sealed JSON-LD receipts;
- standalone JSON Schemas and a fail-closed artifact verifier;
- deterministic fixture tests that cannot claim weight-backed evidence;
- target-machine diagnostics, download scripts, and a one-command acceptance path;
- strict QMF-bound Forge plans, deterministic training simulation, and receipt replay;
- offline OCI isolation and a non-training RTX 4090 sandbox preflight;
- claims, limitations, reproducibility, review, and release-state documentation.

## Included but not yet physically accepted

- the real 28,170,935,456-byte family download;
- RTX 4090 execution of Qwen, Mistral, and Kimi;
- a final `WEIGHT_BACKED` family report from the target workstation.
- a physical GPT-OSS one-step LoRA memory preflight after exact source, dataset, and toolchain
  admission.

These require the owner's machine and cannot be truthfully completed in hosted CI.

## Deferred external integrations

- cryptographic signing keys and external WORM/Proof Vault anchoring;
- a live CollectiveOS service endpoint or process supervisor;
- distributed multi-node ISO-Mesh execution;
- independent semantic-equivalence and adversarial model-quality evaluation;
- an owner-selected license for OIMS-authored source.

The repository provides stable envelopes and hooks for these integrations but does not claim they
are active.

## Explicitly outside the OIMS claim

- the full theoretical corpus and all research artifacts;
- base-model training, tokenizer construction, or an authorized physical fine-tune;
- identical neural behavior or wording across architectures;
- autonomous workers or unsupervised actuation;
- every possible hardware and deployment configuration;
- `ops/mining/`, which is retained historical repository content and is not part of OIMS runtime,
  conformance, agent, or CollectiveOS evidence.

## Completeness authority

`SCOPE_MATRIX.json` is the machine-readable ledger. `SCOPE_AUDIT.md` explains the current verdict.
Broader theoretical context is separate: <https://doi.org/10.5281/zenodo.19477170>.

# Claims and Scope

## Claim 1: heterogeneous runtime invariance

The repository implements a bounded runtime-invariant family across Qwen2, Mistral, and Kimi
Linear architectures.

Operationally, every tier must:

- enforce the same input-first contract;
- preserve the same governance order and receipt schema;
- use a manifest-pinned GGUF whose bytes match an upstream SHA-256;
- emit a linked, hash-sealed conformance record.

Evidence: `MODEL_MANIFEST.json`, `contracts/`, `oims/runtime.py`, and generated
`artifacts/conformance_report.jsonld`.

Non-claim: this is not proof of identical neural weights, wording, model quality, intrinsic base
model safety, or universal semantic equivalence.

## Claim 2: governed agent role binding

CollectiveOS names resolve to explicit tier and system-role bindings. Activation semantics are
`role_binding_only`, and every response states `autonomous_worker_claim: false`.

Evidence: `AGENT_MANIFEST.json`, `oims/agents.py`, `oims/collective.py`, and sealed
`CollectiveOIMSResponse` artifacts.

Non-claim: declaring a role does not create an autonomous worker, grant external permissions, or
prove that a live CollectiveOS service is connected.

## Claim 3: auditable local execution

The repository is designed for implementation-level scrutiny through exact weight identities,
machine schemas, sealed nested receipts, a fail-closed verifier, tests, and CI.

Evidence: `schemas/`, `oims/verify.py`, `SCOPE_MATRIX.json`, `VERIFICATION.md`, and `tests/`.

Non-claim: hash seals are not signatures and local files are not external WORM storage.

## Claim 4: bounded virtual training environment

Model Forge validates exact QMF-bound plans and can deterministically simulate resource,
checkpoint, telemetry, rollback, and verification flows. Its locked probe state can inspect an
offline RTX 4090 sandbox without loading weights or starting training.

Evidence: `oims/model_forge.py`, `forge/`, `schemas/model-forge-*.json`, `MODEL_FORGE.md`, and
`tests/test_model_forge.py`.

Non-claim: simulated or physical-preflight receipts are not trained models, PEFT adapters,
deployment artifacts, or QMF admission evidence.

# Claims and Scope

This file defines the repository's primary claims, their operational meaning, supporting evidence, and explicit non-claims.

## Claim 1
This repository implements a bounded runtime-invariant model-family architecture.

### Operational meaning
Within this repository, an isomorphic intelligence architecture means a system that:
- enforces constraint-first execution
- maintains deterministic governance transitions within the implemented harness
- validates the same runtime invariant vector across three pinned local-weight tiers
- produces auditable conformance records

### Evidence
See:
- generated `artifacts/conformance_report.jsonld`
- `run_iso_family.py`
- `oims/runtime.py`
- `VERIFICATION.md`

### Non-claim
This does not claim identical neural weights, identical generated language, intrinsic safety of the
base models, universal scientific consensus, or independent proof of model-level isomorphism.

## Claim 2
ISO-1B, ISO-7B, and ISO-30B share input-first runtime governance.

### Operational meaning
The execution path validates input before constructing a weight backend, validates output after
inference, and atomically writes a sealed tier receipt.

### Evidence
See:
- `contracts/oims-family.contract.yaml`
- `oims/contracts.py`
- `oims/runtime.py`

### Non-claim
This does not imply that base-model internals are governed or that every deployment environment is
identical. Governance is enforced by the OIMS runtime boundary.

## Claim 3
The repository is designed to be auditable and scrutiny-ready.

### Evidence
See:
- `LIMITATIONS.md`
- `REPO_SCOPE.md`
- `VERIFICATION.md`
- `REVIEWER_GUIDE.md`

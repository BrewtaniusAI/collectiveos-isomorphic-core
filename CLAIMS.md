# Claims and Scope

This file defines the repository's primary claims, their operational meaning, supporting evidence, and explicit non-claims.

## Claim 1
This repository is the open implementation surface for an isomorphic intelligence architecture.

### Operational meaning
Within this repository, an isomorphic intelligence architecture means a system that:
- enforces constraint-first execution
- maintains deterministic state transitions within the implemented harness
- validates conformance across defined tiers and artifacts
- produces auditable conformance records

### Evidence
See:
- `conformance_report.jsonld`
- `run_iso_family.py`
- `iso-models/iso-1b/runtime.py`
- `VERIFICATION.md`

### Non-claim
This does not claim universal scientific consensus on terminology or full frontier-scale release completeness for all tiers.

## Claim 2
The ISO-1B organism surface is runtime-governed.

### Operational meaning
The included execution path applies runtime behavioral contract checks before emitting the tier-level conformance artifact.

### Evidence
See:
- `contracts/iso-1b.contract.yaml`
- `iso-models/iso-1b/contract_enforcer.py`
- `iso-models/iso-1b/runtime.py`

### Non-claim
This does not imply that all future tiers are already implemented or that every deployment environment is identical.

## Claim 3
The repository is designed to be auditable and scrutiny-ready.

### Evidence
See:
- `LIMITATIONS.md`
- `REPO_SCOPE.md`
- `VERIFICATION.md`
- `REVIEWER_GUIDE.md`

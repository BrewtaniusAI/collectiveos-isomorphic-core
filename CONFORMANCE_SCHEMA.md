# Conformance Schema

This document defines the conformance record structure for OIMS repository artifacts.

## Core fields
- `@context`
- `@type`
- `model`
- `status`
- `is_isomorphic`
- `drift`
- `output`

## Runtime governance fields
- `contract_version`
- `contract_model`
- `enforced_status`

## Constraint signal provenance
Each conformance check may include a `constraint_signals` array and a `proof_vault` object to provide epistemic grounding and lineage metadata.

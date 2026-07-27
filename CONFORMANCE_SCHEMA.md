# Conformance Schemas

Authoritative JSON Schemas:

- `schemas/model-manifest.schema.json`
- `schemas/agent-manifest.schema.json`
- `schemas/collective-request.schema.json`
- `schemas/tier-conformance.schema.json`
- `schemas/family-conformance.schema.json`
- `schemas/collective-response.schema.json`

Tier receipts include manifest-pinned provider, architecture, model lineage, exact GGUF identity,
prompt/contract/output hashes, preflight decision, backend evidence, runtime invariants, optional
agent binding, and a canonical record seal.

Family reports link every tier seal and record the complete tier/provider/architecture vectors,
heterogeneity decision, mesh declaration, runtime drift, real-weight decision, and evidence class.

CollectiveOS responses link the request hash, role binding, tier receipt, activation semantics, and
an explicit false autonomous-worker claim.

Run the semantic and cryptographic verifier:

```bash
python -m oims verify --path artifacts/conformance_report.jsonld
```

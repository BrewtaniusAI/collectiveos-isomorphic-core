# Reviewer Guide

1. Inspect `SCOPE_MATRIX.json` for declared completeness.
2. Inspect `MODEL_MANIFEST.json` for three providers, three architectures, and exact GGUF hashes.
3. Inspect `AGENT_MANIFEST.json` for role-only semantics and explicit tier mappings.
4. Inspect `contracts/oims-family.contract.yaml`.
5. Run `python -m unittest discover -v`.
6. Run the fixture mesh and `oims verify`.
7. On target hardware, full-hash and execute every weight.
8. Require the final report to be both valid and `WEIGHT_BACKED`.

Evaluate the repository as a heterogeneous runtime-invariant and role-binding implementation.
Do not treat zero wrapper drift as semantic identity, fixture output as weight evidence, or a role
binding as an autonomous worker.

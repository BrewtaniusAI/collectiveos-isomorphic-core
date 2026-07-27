# Reviewer Guide

## Fast path

1. Inspect `MODEL_MANIFEST.json` for exact upstream revisions and GGUF files.
2. Inspect `contracts/oims-family.contract.yaml`.
3. Run `python -m unittest discover -v`.
4. Run the fixture family command in `QUICKSTART.md`.
5. On target hardware, download and hash all weights.
6. Run the real family.
7. Verify `artifacts/conformance_report.jsonld` says `WEIGHT_BACKED`.

## Evaluation boundary

Evaluate the repository as a multi-tier runtime-invariant implementation. Do not treat fixture
receipts, documentation, or a zero-drift wrapper vector as proof of semantic identity between
neural models.

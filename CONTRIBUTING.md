# Contributing

Changes must preserve the evidence boundary.

Before opening a pull request:

```bash
python -m unittest discover -v
ruff check .
ruff format --check .
python -m oims --artifacts-dir artifacts-smoke mesh \
  --backend fixture \
  --prompt "contribution smoke probe"
python -m oims verify --path artifacts-smoke/conformance_report.jsonld
```

Model-binding changes must include:

- immutable repository revision;
- exact filename, byte size, and upstream SHA-256;
- provider, architecture, base-model, conversion, quantization, and license provenance;
- a compatible chat-system mode;
- realistic context and GPU-layer defaults;
- updated schemas, tests, documentation, SBOM/locks when dependencies change.

Never label fixture evidence as weight-backed. Never add model weights or generated receipts to
Git. Source-license contributions must wait for the owner-selected OIMS license.

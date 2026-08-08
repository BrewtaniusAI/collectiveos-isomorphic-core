# Reproducibility

Reproduction is anchored by:

- immutable GGUF repository revisions;
- exact filenames, byte counts, and upstream LFS SHA-256 values;
- local locks that must match the manifest;
- `llama-cpp-python>=0.3.34,<0.4` for Kimi Linear support;
- model-specific chat-system handling;
- declared context and GPU-layer defaults;
- one shared contract hash;
- deterministic decoding settings and seed;
- source-commit capture;
- sealed nested receipts and an independent verification command;
- canonical QMF-bound Forge plans, deterministic virtual clocks, and hash-linked synthetic
  checkpoints;
- explicit separation of simulated, physical-preflight, and QMF-admissible evidence classes.

```bash
python -m pip install -e ".[weights]"
python -m oims weights pull --tier all
python -m oims weights check --tier all --full-hash
python -m oims mesh --prompt "family conformance probe"
python -m oims verify \
  --path artifacts/conformance_report.jsonld \
  --require-weight-backed
python -m oims forge simulate \
  --plan forge/examples/gpt-oss-20b-4090-simulation.plan.json \
  --output artifacts/model-forge
```

Generated text can vary across llama.cpp versions, hardware kernels, and floating-point
execution. Receipts record the backend version and execution settings. OIMS distinguishes
governance-transition reproducibility from byte-identical generated output.

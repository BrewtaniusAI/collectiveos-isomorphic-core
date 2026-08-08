# Limitations

- Model weights are downloaded from pinned upstream repositories and are not redistributed.
- The ISO-30B capacity tier binds Kimi Linear 48B total / 3B active at Q3_K_M.
- Mistral and Kimi GGUF files are community conversions; conversion provenance is explicit.
- Kimi defaults to partial GPU offload because 22.68 GB of weights leave insufficient headroom on
  a 24 GB GPU for full runtime overhead.
- Runtime governance wraps inference; it does not formally verify every neural computation.
- Runtime invariance is not semantic identity, equivalent capability, or universal proof.
- Agent profiles are role bindings, not autonomous workers or external actuation authority.
- The CollectiveOS bridge is a local request/response contract, not a deployed service endpoint.
- Receipts are SHA-256 sealed but are not signed or externally WORM-anchored.
- Base-model training data, training, and tokenizer construction remain upstream concerns.
- OIMS-authored source does not yet declare the owner's intended license.
- Model Forge 0.4 simulates training shape and probes the sandbox; it does not load weights,
  execute gradients, merge adapters, publish models, or produce QMF-admissible evidence.
- Distributed multi-node ISO-Mesh execution is deferred beyond 0.4.0.

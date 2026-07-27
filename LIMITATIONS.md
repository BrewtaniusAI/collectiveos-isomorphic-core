# Limitations

- Model weights are downloaded from pinned upstream Qwen repositories and are not redistributed.
- The ISO-30B capacity tier currently binds a 32B-class model.
- CUDA execution requires a compatible local llama.cpp build.
- A 24 GB GPU may require a 2,048-token context or partial CPU offload for ISO-30B.
- Runtime governance wraps model inference; it does not alter or formally verify every internal
  neural computation.
- Runtime-invariant conformance is not semantic identity or universal scientific proof.
- Hash-sealed receipts are tamper-evident files, not yet signed or externally WORM-anchored.
- Training data, base-model training, and tokenizer construction are upstream Qwen concerns.
- The OIMS-authored source code does not yet declare the owner's intended license.

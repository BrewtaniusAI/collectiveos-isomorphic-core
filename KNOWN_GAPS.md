# Known Gaps

This file lists the remaining known gaps between the current repository state and a full public model-family release.

## Current gaps
- OIMS does not redistribute model weights; pinned Apache-2.0 GGUF files are downloaded locally
- Reproducible base-model training recipes are upstream Qwen artifacts, not OIMS artifacts
- Independent semantic-equivalence benchmarks across tiers are not yet included
- CUDA execution depends on a compatible local llama-cpp-python build
- Proof receipts are hash-sealed but are not yet signed or written to external WORM storage
- The OIMS-authored source code still requires the owner's intended license

## Interpretation
These gaps bound the current claim to runtime-invariant conformance. They must be closed before
claiming independent model-level proof or a formal source release.

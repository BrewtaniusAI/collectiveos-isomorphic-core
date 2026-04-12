# Hardening Status

This file summarizes the repository's defensive posture and the remaining gap to a full public model-family release.

## Current hardening layers
- Claims are explicitly defined (`CLAIMS.md`)
- Terms are operationally defined (`TERMS.md`)
- Limitations are stated (`LIMITATIONS.md`)
- Scope is bounded (`REPO_SCOPE.md`)
- Verification surface is separated from external context (`VERIFICATION.md`)
- Runtime contracts exist for ISO-1B
- Conformance artifacts are present
- A runnable reference organism surface exists for ISO-1B

## What this protects against
- vague claims
- terminology drift
- scope confusion
- reproducibility criticism
- misinterpretation of what is and is not verified

## Remaining gap
The repository is hardened as a standard, implementation, and release surface.
The remaining gap to a full public model-family release is the publication of complete tier artifacts such as weights, reproducible training recipes, tokenizer assets, and full tier-level conformance runs.

# Security Policy

## Supported version

The current 0.4.x line is the only supported implementation surface.

## Report handling

Do not publish secrets, model-access tokens, wallet material, private prompts, or exploit details
in a public issue. Use GitHub's private vulnerability-reporting channel if enabled for the
repository. Otherwise contact the repository owner through the GitHub profile before transmitting
sensitive details.

## Trust boundaries

- downloaded weights are untrusted until size and SHA-256 match `MODEL_MANIFEST.json`;
- local locks are not sufficient unless they also match the manifest;
- model output is untrusted until post-inference validation and receipt sealing;
- agent role bindings grant no filesystem, shell, network, or device authority;
- generated receipts are tamper-evident but not signed or externally immutable;
- community GGUF conversions are explicitly distinguished from official upstream GGUFs.
- Model Forge simulations are never QMF-admissible or deployable artifacts;
- physical Forge preflight requires an exact plan hash, explicit unlock, no network, no Linux
  capabilities, no-new-privileges, a read-only root filesystem, and unused swap;
- base weights, datasets, and plans are read-only mounts; only the evidence directory is writable;
- Model Forge 0.4 has no physical training, adapter merge, publication, serving, or promotion state.

## Secret policy

Weights, tokens, virtual environments, local configuration, and generated evidence must remain
outside Git. Never add Hugging Face tokens, private keys, Proof Vault credentials, or wallet
secrets to examples, issues, receipts, or test fixtures.

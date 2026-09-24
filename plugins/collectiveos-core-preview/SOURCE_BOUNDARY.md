# CollectiveOS Source Boundary

This plugin is a host projection, not an authority root.

Canonical source packages live under /skills in this repository. Their machine-readable manifests and behavioral evals are copied into each projected skill under references/ so a host package never erases the richer CollectiveOS contract.

Current release class: preview / non-authorizing.

- Canonical skills remain status: draft and runtime_activation: false.
- The plugin contains no MCP server and no connected app.
- The plugin grants no filesystem, shell, GitHub, network, deployment, financial, or canonical Proof Vault authority.
- Host-selected skill relevance never implies CollectiveOS authorization.
- Any future state-changing adapter must pass the GACES approval boundary and the CollectiveOS trust boundary independently.

The generated package is intended to make OpenAI ChatGPT Work/Codex one possible host for CollectiveOS procedures without moving governance ownership into the host.

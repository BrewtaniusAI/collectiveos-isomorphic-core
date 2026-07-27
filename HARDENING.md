# Hardening Status

Implemented:

- pre-inference input enforcement and post-inference output validation;
- three distinct upstream providers and architecture families;
- immutable GGUF revisions plus exact filenames, sizes, and upstream SHA-256 identities;
- local lock lineage and mandatory full hash validation before real loads;
- model-specific chat-template handling;
- sequential memory release and conservative Kimi partial offload;
- explicit role-only agent bindings with autonomous claims disabled;
- sealed tier, family, and CollectiveOS receipts with nested hash linkage;
- standalone JSON Schemas and fail-closed verification;
- pinned CI/direct target dependency locks and a source SPDX SBOM;
- fixture/weight evidence separation;
- multi-version CI and scope-completeness tests;
- exclusion of weights, secrets, environments, and generated receipts from Git.

Pending:

- target-machine CUDA acceptance;
- signed receipts and external WORM anchoring;
- target-machine capture of the final platform-specific CUDA build and transitive environment;
- independent semantic/adversarial evaluation;
- source-code license selection;
- live CollectiveOS and distributed-mesh deployment hardening.

# Conformance Schema

Tier records use `OIMSModelTierConformanceRecord` version 2 and contain:

- tier, parameter class, and pinned weight source;
- prompt, contract, output, source commit, and sealed-record hashes;
- preflight decision;
- backend identity and real-weight flag;
- local weight inventory;
- runtime invariant vector;
- lawful status and runtime drift.

Family reports use `OIMSFamilyConformanceReport` version 2 and contain:

- all executed tiers;
- tier record hashes;
- shared contract hash;
- invariant mismatch ratio;
- runtime-isomorphic decision;
- independent real-weight execution decision;
- `WEIGHT_BACKED` or `TEST_OR_INCOMPLETE` evidence classification.

The Python implementation is authoritative until a standalone JSON Schema is published.

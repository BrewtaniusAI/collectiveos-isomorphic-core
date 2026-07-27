# Verification

## Verified automatically

- model repositories, GGUF filenames, and immutable revisions are manifest-pinned;
- invalid inputs collapse or idle before backend construction;
- all tiers use the same contract hash, governance order, and receipt schema;
- records are written atomically and sealed with SHA-256;
- record tampering is detected;
- fixture evidence cannot be labeled as weight-backed;
- missing local weight files are reported per tier.

Run:

```bash
python -m unittest discover -v
```

## Verified on a target GPU

A complete local run must execute:

```bash
python -m oims weights check --tier all --full-hash
python -m oims family --prompt "family conformance probe"
```

The resulting family report must state:

```json
{
  "runtime_isomorphic": true,
  "weight_execution_verified": true,
  "evidence_class": "WEIGHT_BACKED"
}
```

## Boundary

Runtime-invariant conformance does not prove identical neural weights, identical wording,
base-model safety, or universal semantic equivalence.

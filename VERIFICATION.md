# Verification

## Automated code/fixture verification

```bash
python -m unittest discover -v
python -m oims --artifacts-dir artifacts-smoke mesh \
  --backend fixture \
  --prompt "heterogeneous fixture probe"
python -m oims verify --path artifacts-smoke/conformance_report.jsonld
```

This verifies manifest diversity, exact expected weight identities, input-first governance,
agent-role bindings, CollectiveOS linkage, receipt seals, nested tier hashes, and fixture evidence
classification. It cannot claim that real weights executed.

## Target workstation acceptance

```powershell
python -m oims weights check --tier all --full-hash
python -m oims mesh --prompt "heterogeneous family acceptance probe"
python -m oims verify `
  --path artifacts/conformance_report.jsonld `
  --require-weight-backed
```

The accepted family report must contain:

```json
{
  "executed_architectures": ["qwen2", "mistral", "kimi-linear"],
  "heterogeneous_architectures_verified": true,
  "runtime_isomorphic": true,
  "weight_execution_verified": true,
  "evidence_class": "WEIGHT_BACKED"
}
```

This proves the bounded runtime invariant and physical execution of the pinned bytes. It does not
prove semantic identity or independent model quality.

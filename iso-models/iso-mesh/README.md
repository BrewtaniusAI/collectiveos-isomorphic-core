# ISO-Mesh

ISO-Mesh 0.3.0 has two explicit local functions:

1. resolve CollectiveOS role aliases to their declared heterogeneous tier;
2. execute Qwen2, Mistral, and Kimi Linear sequentially for family conformance.

```bash
python -m oims mesh --prompt "heterogeneous family probe"
python -m oims collective --agent Cypher --prompt "audit this claim"
```

The family report declares the mesh strategy, member order, providers, architectures, and nested
tier hashes. Distributed node transport, scheduling, identity, and recovery remain future work.

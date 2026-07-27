# ISO-Mesh

ISO-Mesh is implemented as the sequential OIMS family runner:

```bash
python -m oims family --prompt "family conformance probe"
```

It executes ISO-1B, ISO-7B, and ISO-30B one at a time, releases each backend, compares the runtime
invariant vectors, and writes `artifacts/conformance_report.jsonld`.

This is a local sequential mesh. Distributed multi-node execution remains future work.

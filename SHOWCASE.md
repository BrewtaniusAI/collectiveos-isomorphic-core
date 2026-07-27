# Showcase

## Live path

```bash
python -m oims weights pull --tier all
python -m oims family --prompt "Explain constraint-first execution."
```

The runner:

1. validates input before inference;
2. loads ISO-1B from pinned local GGUF files;
3. validates and seals its receipt;
4. releases the model;
5. repeats for ISO-7B and ISO-30B;
6. compares the shared invariant vectors;
7. seals the family report.

The review target is `artifacts/conformance_report.jsonld`. A valid live demonstration requires
`evidence_class: WEIGHT_BACKED`.

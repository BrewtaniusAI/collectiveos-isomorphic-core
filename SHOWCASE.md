# Showcase

## Live path

```bash
python -m oims weights pull --tier all
python -m oims mesh --prompt "Explain constraint-first execution."
python -m oims collective --agent Giles --prompt "Audit the family evidence."
```

The runner:

1. validates input before inference;
2. loads the Qwen2 intake tier from its exact pinned GGUF;
3. validates and seals its receipt;
4. releases the model;
5. repeats for the Mistral operator and Kimi Linear strategist tiers;
6. verifies architecture/provider diversity and shared invariant vectors;
7. seals and independently verifies the family report.

The review target is `artifacts/conformance_report.jsonld`. A valid live demonstration requires
`evidence_class: WEIGHT_BACKED`.

# Stress and Contract Tests

```bash
python -m unittest discover -v
```

The assertive suite covers:

- normal input;
- empty-input idle;
- non-string collapse before backend construction;
- maximum-length boundary;
- empty model-output collapse;
- manifest pinning;
- all-tier invariant comparison;
- fixture/weight evidence separation;
- receipt tamper detection;
- missing weight inventory.

Adversarial semantic and long-duration GPU evaluations remain separate target-hardware work.

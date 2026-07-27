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
- exact upstream weight identity;
- heterogeneous architecture/provider enforcement;
- model-specific chat-system modes;
- all-tier invariant comparison;
- agent alias and role-binding validation;
- CollectiveOS nested receipt verification;
- JSON Schema publication;
- fixture/weight evidence separation;
- receipt tamper detection;
- missing weight inventory.

Adversarial semantic and long-duration GPU evaluations remain separate target-hardware work.

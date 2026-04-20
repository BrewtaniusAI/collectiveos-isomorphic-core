# Stress Tests

This document describes basic stress validation for ISO-1B.

## Purpose

To verify that the system:
- handles edge cases
- maintains lawful output
- collapses or bounds behavior under constraint violations

## How to run

```bash
python -m iso-models.iso-1b.stress_tests
```

## Initial cases
- empty input
- normal input

## Future cases
- forced violation
- drift escalation
- adversarial prompts

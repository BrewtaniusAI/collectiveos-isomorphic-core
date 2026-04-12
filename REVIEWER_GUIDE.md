# Reviewer Guide

This guide is for technical reviewers and skeptics who want the fastest path to evaluate the repository.

## Start here
1. Read `REPO_SCOPE.md`
2. Read `LIMITATIONS.md`
3. Read `VERIFICATION.md`

## Run the system
```bash
python run_iso_family.py
```

## Inspect outputs
- `iso-models/iso-1b/conformance_record.jsonld`
- `conformance_report.jsonld`

## Inspect claims and boundaries
- `CLAIMS.md`
- `TERMS.md`
- `HARDENING.md`
- `KNOWN_GAPS.md`

## Evaluation principle
Evaluate this repository as:
- a standard and implementation surface
- a proof-of-invariant surface
- a bounded executable reference organism

Do not evaluate it as if it already claims a complete public model-family release.

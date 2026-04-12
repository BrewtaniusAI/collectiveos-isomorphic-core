# Verification

This document defines what is verified within this repository and how.

## Verified in this repository
- ISO-1B runtime execution
- Contract enforcement behavior
- Conformance artifact generation

## Verification method
- Direct execution of `run_iso_family.py`
- Inspection of generated JSON artifacts
- Review of contract enforcement logic

## Boundary
This verification applies only to the implemented code surface.

It does not imply:
- full model-family release completeness
- universal correctness for all inputs
- verification of external research claims

## Purpose
To provide a clear, testable boundary between implementation and interpretation.

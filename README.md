# 🧠 CollectiveOS Isomorphic Core
## The First Open Isomorphic Intelligence Model

> One intelligence. Many substrates. Same lawful identity.

CollectiveOS Isomorphic Core is the implementation-facing reference surface for the **Open Isomorphic Model Standard (OIMS)**: a constraint-first architecture for building model families that preserve lawful behavioral identity across scale, substrate, and deployment class. The formal OIMS specification defines the standard as a lawful architectural contract rather than merely a model release.

This repository is designed to be:

- executable
- inspectable
- auditable
- reproducible
- defensible under scrutiny

It is not a generic wrapper, not a vague research dump, and not a claim without artifacts.

---

## What This Repository Is

This repository is the **open implementation and verification surface** for the OIMS architecture.

It currently provides:

- a runnable ISO-1B reference organism
- a root-level runner
- a top-level conformance artifact
- tier-level model family structure
- runtime behavioral contracts
- governance and provenance scaffolding
- release manifests and deployment guides
- explicit claims, limitations, scope, terms, and verification boundaries
- citation and provenance metadata

The project is grounded in the broader OIMS family definition:
- `ISO-1B`
- `ISO-7B`
- `ISO-30B`
- `ISO-Mesh`

---

## Quick Start

Run the current organism surface from the repository root:

```bash
python run_iso_family.py
```

Then inspect:
- `iso-models/iso-1b/conformance_record.jsonld`
- `conformance_report.jsonld`

---

## Current Focus

This repository is currently in the **release-ready architecture + executable reference organism** phase.

Implemented now:
- executable ISO-1B runtime surface
- runtime governance via contracts
- conformance artifact generation
- provenance scaffolding
- model-family release structure
- scrutiny and verification documentation

Not yet complete:
- public weights for all tiers
- tokenizer assets/specs for all tiers
- full executable higher tiers beyond ISO-1B
- complete conformance execution across all tiers

---

## Core Runtime Path

The current ISO-1B organism path is:

```text
model → evaluate → enforce_contract → governed_output → constraint_signals → proof_vault → conformance_record
```

---

## Technical Documentation

- Claims → `CLAIMS.md`
- Limitations → `LIMITATIONS.md`
- Scope → `REPO_SCOPE.md`
- Verification → `VERIFICATION.md`
- Terms → `TERMS.md`
- Hardening → `HARDENING.md`
- Release state → `RELEASE_STATUS.md`
- Release checklist → `RELEASE_CHECKLIST.md`
- Known gaps → `KNOWN_GAPS.md`
- Reviewer guide → `REVIEWER_GUIDE.md`
- Citations → `CITATIONS.md`

---

## Final Position

This repository is the **bounded, executable, auditable, and governed reference surface** for the OIMS architecture.

It is designed to:
- run
- enforce
- explain
- hold shape under scrutiny

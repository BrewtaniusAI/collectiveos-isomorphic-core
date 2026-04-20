# 🧠 CollectiveOS Isomorphic Core
## The First Open Isomorphic Intelligence Model

> One intelligence. Many substrates. Same lawful identity.

CollectiveOS Isomorphic Core is the implementation-facing reference surface for the **Open Isomorphic Model Standard (OIMS)**: a constraint-first architecture for building model families that preserve lawful behavioral identity across scale, substrate, and deployment class.

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
- a tier-level conformance artifact
- runtime behavioral contracts
- governance and provenance scaffolding
- tier-level model-family structure
- scrutiny and verification documentation
- citation and provenance metadata
- baseline mining ops for local-wallet-first operation

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

For the fastest walkthrough, see:
- `QUICKSTART.md`
- `SHOWCASE.md`
- `REVIEWER_GUIDE.md`

---

## Current Focus

This repository is currently in the **release-ready architecture + executable reference organism** phase.

Implemented now:
- executable ISO-1B runtime surface
- runtime governance via contracts
- provenance-aware conformance scaffolding
- model-family release structure
- scrutiny and verification documentation
- baseline mining ops layer

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

## Repository Surface

### Core runtime
- `run_iso_family.py`
- `iso-models/iso-1b/model.py`
- `iso-models/iso-1b/runtime.py`
- `iso-models/iso-1b/contract_enforcer.py`
- `iso-models/iso-1b/provenance.py`

### Tier surface
- `iso-models/iso-1b/README.md`
- `iso-models/iso-1b/STATUS.md`
- `iso-models/iso-1b/DEPLOYMENT.md`
- `iso-models/iso-1b/arch_spec.json`
- `iso-models/iso-1b/conformance_record.jsonld`
- `iso-models/iso-7b/README.md`
- `iso-models/iso-30b/README.md`
- `iso-models/iso-mesh/README.md`

### Contracts and scripts
- `contracts/iso-1b.contract.yaml`
- `scripts/generate_proof_vault.py`

### Scrutiny and verification docs
- `CLAIMS.md`
- `LIMITATIONS.md`
- `REPO_SCOPE.md`
- `VERIFICATION.md`
- `TERMS.md`
- `HARDENING.md`
- `KNOWN_GAPS.md`
- `REVIEWER_GUIDE.md`
- `REPRODUCIBILITY.md`
- `CONFORMANCE_SCHEMA.md`

### Release docs
- `MODEL_MANIFEST.json`
- `RELEASE_STATUS.md`
- `RELEASE_CHECKLIST.md`

### Utility docs
- `QUICKSTART.md`
- `SHOWCASE.md`
- `CITATIONS.md`
- `CITATION.cff`
- `ORIGINALITY.md`

### Mining ops
- `ops/mining/README.md`
- `ops/mining/wallet_setup.md`
- `ops/mining/start_miner.ps1`
- `ops/mining/weekly_offload.md`

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

## Mining Ops

This repository now includes a baseline local-wallet-first mining ops layer under:

- `ops/mining/README.md`
- `ops/mining/wallet_setup.md`
- `ops/mining/start_miner.ps1`
- `ops/mining/weekly_offload.md`

Recommended baseline path:
- coin: Monero (XMR)
- algorithm: RandomX
- miner: XMRig
- payout: direct to local wallet
- weekly offload: handled manually first, then automated later

---

## Final Position

This repository is the **bounded, executable, auditable, and governed reference surface** for the OIMS architecture.

It is designed to:
- run
- enforce
- explain
- hold shape under scrutiny
- support immediate local monetization operations once baseline execution is live

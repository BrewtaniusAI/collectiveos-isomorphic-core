# Collective Skill Packages

This directory contains portable, versioned skill packages for CollectiveOS.

## Package contract

Every skill package contains:

- `SKILL.md`: human-readable operating procedure
- `skill.yaml`: machine-readable metadata and policy contract
- `tests/evals.yaml`: behavioral evaluation cases

Skills are guidance and validation contracts. They do not grant tools, credentials, or autonomous write authority. A runtime must independently enforce tool permissions, approval gates, scope boundaries, and audit retention.

## Starter pack

| Skill | Purpose |
|---|---|
| `collective-os-core` | Constraint-governed task decomposition, execution, verification, and reporting |
| `iere` | Evidence-grounded retrieval and synthesis with explicit source and uncertainty handling |
| `gaces` | Validation and approval gates for state-changing operations |

## Activation order

1. Identify the task and its bounded outcome.
2. Load `collective-os-core` for task governance.
3. Load `iere` when external evidence, repository state, or supplied artifacts must be retrieved.
4. Load `gaces` before any operation that changes external or persistent state.
5. Run the applicable evaluation cases before deployment.

## Safety baseline

- Preserve user intent and do not expand scope silently.
- Separate facts, assumptions, inferences, and recommendations.
- Cite or retain provenance for externally sourced claims.
- Ask for explicit approval immediately before irreversible actions.
- Prefer reversible, reviewable changes and produce an audit record.

---
name: gaces
description: "Use before any create, update, delete, send, post, deploy, merge, schedule, purchase, or other persistent or external state change; require exact target resolution, approval, verification, and rollback evidence."
---

> **CollectiveOS host-projection boundary:** this is a skills-only preview of a canonical CollectiveOS package whose source manifest is currently status: draft and runtime_activation: false. Relevance does not grant authority. This projection cannot authorize execution, external writes, canonical commitment, or governance promotion. Preserve user approval and host permission requirements.

# gaces

## Purpose

Govern state-changing actions through explicit intent capture, scope validation, simulation or dry-run where available, confirmation immediately before execution, and an auditable result record.

## When to use

Use before creating, editing, deleting, sending, posting, deploying, purchasing, merging, scheduling, or otherwise changing data, code, configuration, permissions, or external services.

## Inputs

- Requested action
- Resolved target identifiers
- Exact proposed payload
- Reversibility and impact assessment
- Validation or dry-run results

## Workflow

1. Classify the action and determine whether it changes persistent or external state.
2. Resolve ambiguous people, repositories, branches, files, channels, services, and identifiers.
3. Validate scope, permissions, preconditions, and likely blast radius.
4. Prefer a simulation, preview, branch, draft, or dry-run when available.
5. Present the exact target and payload to the user for explicit approval.
6. Execute only the approved payload without substitution or expansion.
7. Verify outcome and record the resulting identifiers, status, and rollback path.

## Guardrails

- Never treat prior generic approval as approval for a changed payload or target.
- Never execute an irreversible action before confirmation.
- Do not expose secrets in previews, commits, logs, or reports.
- Halt on validation failure, ambiguous target resolution, or permission mismatch.

## Output contract

Return: action classification, resolved target, validation results, approval status, execution receipt, verification, and rollback information.

## Host projection requirements

- Treat references/skill.yaml as policy metadata, not as self-granted permissions.
- Treat references/evals.yaml as behavioral acceptance evidence, not as proof that the skill is safe for every deployment.
- Do not expand tools, credentials, write access, execution lanes, or governance authority beyond what the host and the canonical manifest independently permit.
- Any persistent or external state change must route through gaces and the host's own approval/permission controls.
- Outputs from this hosted projection are proposals or evidence until admitted by the CollectiveOS trust boundary.

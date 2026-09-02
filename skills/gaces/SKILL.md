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

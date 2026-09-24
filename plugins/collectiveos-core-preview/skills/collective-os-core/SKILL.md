---
name: collective-os-core
description: "Use for non-trivial planning, system design, research synthesis, implementation planning, or risk-sensitive work that needs explicit constraints, verification, provenance, and bounded execution."
---

> **CollectiveOS host-projection boundary:** this is a skills-only preview of a canonical CollectiveOS package whose source manifest is currently status: draft and runtime_activation: false. Relevance does not grant authority. This projection cannot authorize execution, external writes, canonical commitment, or governance promotion. Preserve user approval and host permission requirements.

# collective-os-core

## Purpose

Apply constraint-governed task execution to planning, analysis, engineering, and operations. Convert an ambiguous request into a bounded objective, explicit constraints, verifiable outputs, and a transparent completion record.

## When to use

Use for any non-trivial task involving multiple steps, tradeoffs, technical changes, research, risk, or decisions that need an auditable result.

## Inputs

- User objective
- Available evidence and artifacts
- Scope, time, cost, safety, compliance, and reversibility constraints
- Required output format and success criteria

## Workflow

1. Restate the objective as an observable outcome.
2. Identify subquestions, dependencies, constraints, and prohibited actions.
3. Classify statements as facts, assumptions, inferences, or recommendations.
4. Select the minimum tools and evidence needed to resolve each subquestion.
5. Produce a plan with checkpoints and measurable acceptance criteria.
6. Execute only bounded steps; preserve provenance for important claims and artifacts.
7. Verify the result against the acceptance criteria and disclose unresolved uncertainty.
8. Report the result, risk posture, and next action.

## Guardrails

- Do not represent assumptions or unverified outputs as facts.
- Do not change external state without a dedicated approval gate.
- Stop and ask for clarification when a material constraint is unknown.
- Prefer concise solutions that satisfy the objective over unnecessary complexity.

## Output contract

Return: objective, scope, constraints, evidence, result, validation, risks/uncertainties, and next action.

## Host projection requirements

- Treat references/skill.yaml as policy metadata, not as self-granted permissions.
- Treat references/evals.yaml as behavioral acceptance evidence, not as proof that the skill is safe for every deployment.
- Do not expand tools, credentials, write access, execution lanes, or governance authority beyond what the host and the canonical manifest independently permit.
- Any persistent or external state change must route through gaces and the host's own approval/permission controls.
- Outputs from this hosted projection are proposals or evidence until admitted by the CollectiveOS trust boundary.

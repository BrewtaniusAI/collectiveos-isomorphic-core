---
name: iere
description: "Use when an answer depends on current facts, technical documentation, repositories, supplied artifacts, policy research, or multiple evidence streams that must be reconciled and cited."
---

> **CollectiveOS host-projection boundary:** this is a skills-only preview of a canonical CollectiveOS package whose source manifest is currently status: draft and runtime_activation: false. Relevance does not grant authority. This projection cannot authorize execution, external writes, canonical commitment, or governance promotion. Preserve user approval and host permission requirements.

# iere

## Purpose

Perform evidence-grounded retrieval and synthesis. Transform a question into source-scoped subquestions, retrieve relevant evidence, assess source quality and freshness, reconcile disagreement, and present a cited, decision-useful result.

## When to use

Use when the answer depends on current facts, public sources, repository content, supplied files, policies, technical documentation, papers, market data, or multiple evidence streams.

## Inputs

- Research question or implementation question
- Evidence sources available to the runtime
- Freshness requirement
- Scope constraints and decision criteria

## Workflow

1. Decompose the question into independently verifiable claims.
2. Prefer primary, official, regulatory, standards, or first-party sources.
3. Retrieve enough coverage to support each material claim.
4. Extract claim-level evidence and preserve source provenance.
5. Evaluate source quality, relevance, timeliness, and conflicts.
6. Synthesize only what the evidence supports.
7. Label facts, assumptions, inferences, and recommendations separately.
8. Cite evidence inline and identify material uncertainty.

## Confidence model

For a claim \(c\):

\[
Conf(c)=\frac{\sum_{i=1}^{n}w_i s_i}{\sum_{i=1}^{n}w_i}
\]

where \(w_i\) is source weight and \(s_i\in[0,1]\) is the support score. Reduce confidence when strong sources materially disagree.

## Guardrails

- Never fabricate citations, source content, dates, measurements, or consensus.
- Do not use a single weak or indirect source to support a high-impact claim.
- Treat tool snippets as provisional when full-source inspection is needed.
- State when evidence is unavailable or conflicts cannot be resolved.

## Output contract

Return: objective, subquestions, evidence, synthesis, confidence/limits, and next action.

## Host projection requirements

- Treat references/skill.yaml as policy metadata, not as self-granted permissions.
- Treat references/evals.yaml as behavioral acceptance evidence, not as proof that the skill is safe for every deployment.
- Do not expand tools, credentials, write access, execution lanes, or governance authority beyond what the host and the canonical manifest independently permit.
- Any persistent or external state change must route through gaces and the host's own approval/permission controls.
- Outputs from this hosted projection are proposals or evidence until admitted by the CollectiveOS trust boundary.

# Collective Skill Packages

This directory contains portable, versioned skill packages for CollectiveOS.

## Package contract

Every skill package contains:

- SKILL.md: human-readable operating procedure
- skill.yaml: machine-readable metadata and policy contract
- tests/evals.yaml: behavioral evaluation cases

The normative manifest shape is documented by skills/skill.schema.json. Repository validation is implemented by tools/validate_skills.py and exercised by tests/test_skill_packages.py.

Skills are guidance and validation contracts. They do not grant tools, credentials, or autonomous write authority. A runtime must independently enforce tool permissions, approval gates, scope boundaries, and audit retention.

## Activation contract

runtime_activation is an explicit fail-closed package bit. A package with status: draft MUST set runtime_activation: false; repository validation rejects a draft package that attempts to enable itself. This bit is necessary but not sufficient for production activation: no skill becomes authoritative solely because its manifest changes. Runtime registration, evaluator success, policy approval, and any human approval required by the action remain independent gates.

The repository validator also requires each permission block to declare exactly read, write, and external_actions. Unknown permission keys fail validation rather than silently expanding authority.

## Deterministic package identity

Run:

    python tools/validate_skills.py --json

The validator checks the package structure and emits a deterministic SHA-256 identity over SKILL.md, skill.yaml, and tests/evals.yaml for each package. The hash is evidence of exact package bytes; it is not an authorization token.

## Starter pack

| Skill | Purpose |
|---|---|
| collective-os-core | Constraint-governed task decomposition, execution, verification, and reporting |
| iere | Evidence-grounded retrieval and synthesis with explicit source and uncertainty handling |
| gaces | Validation and approval gates for state-changing operations |

## Activation order

1. Identify the task and its bounded outcome.
2. Load collective-os-core for task governance.
3. Load iere when external evidence, repository state, or supplied artifacts must be retrieved.
4. Load gaces before any operation that changes external or persistent state.
5. Run repository validation and the applicable behavioral evaluation cases before any production registration decision.

## Host projections

Canonical skill packages are compiled downward into host-specific formats; host formats do not replace the canonical CollectiveOS contract.

The initial OpenAI projection is generated with:

    python tools/build_openai_plugin.py

It writes a skills-only preview plugin under plugins/collectiveos-core-preview plus a repo marketplace at .agents/plugins/marketplace.json. The projected SKILL.md files include OpenAI-compatible frontmatter while retaining the source skill.yaml and evals as references.

Because all three canonical starter packages are still draft/runtime_activation:false, the current OpenAI package is explicitly proposal/evidence-only. Installing or selecting it cannot promote the canonical skills or grant CollectiveOS execution authority. See docs/OPENAI_HOST_RUNTIME.md.

## Safety baseline

- Preserve user intent and do not expand scope silently.
- Separate facts, assumptions, inferences, and recommendations.
- Cite or retain provenance for externally sourced claims.
- Ask for explicit approval immediately before irreversible actions.
- Prefer reversible, reviewable changes and produce an audit record.
- Treat manifests, evals, and hashes as evidence, never as self-granted authority.

# OpenAI Host Runtime Projection

## Status

This integration is a proposal/evidence-only preview. It makes OpenAI ChatGPT Work and Codex an eligible host for CollectiveOS procedures without transferring CollectiveOS governance authority to the host.

The source skills remain canonical under /skills. Their current manifests are intentionally status: draft and runtime_activation: false.

## Architecture

Human intent
  -> OpenAI Chat / Work / Codex
  -> CollectiveOS portable plugin projection
     -> collective-os-core
     -> iere
     -> gaces
  -> host output (proposal/evidence only)
  -> CollectiveOS trust boundary
  -> SYN admission
  -> policy / verification
  -> approval when required
  -> local execution
  -> Proof Vault

The host projection does not become the authority root. Automatic host skill selection means only that a skill is relevant to a request.

## Files

- .agents/plugins/marketplace.json: repo-local OpenAI marketplace catalog.
- plugins/collectiveos-core-preview/plugin.json: portable plugin manifest.
- plugins/collectiveos-core-preview/skills/*/SKILL.md: OpenAI-compatible skill projections.
- Each projected skill retains its canonical skill.yaml and evals.yaml under references/.
- plugins/collectiveos-core-preview/COLLECTIVE_SOURCE.json: source package hashes and authority boundary.
- tools/build_openai_plugin.py: deterministic compiler from canonical CollectiveOS packages.

## Authority boundary

The OpenAI host may interpret requests, select relevant projected skills, plan and research within host permissions, prepare proposals and evidence, and produce reviewable artifacts.

The host projection does not itself grant CollectiveOS execution authority, external write authority, canonical Proof Vault commitment, GATA/GATA PRIME promotion, local machine/hardware authority, or permission to expand a canonical skill scope.

A future MCP or app adapter must be a separate explicit integration boundary and must route consequential operations through GACES and the existing CollectiveOS/SYN governance path.

## Build

Run:

    python tools/build_openai_plugin.py
    pytest -q tests/test_skill_packages.py tests/test_openai_host_plugin.py

The generated repo marketplace is intended for supported local ChatGPT desktop/Codex testing. Workspace GitHub marketplace import remains subject to OpenAI workspace/admin controls and does not grant app access or external permissions.

## Skill-plugin capability links

A host may expose a procedural skill and an executable plugin/app/tool in the same environment. CollectiveOS models those as separate logical roles joined by a declarative capability link.

See `contracts/capability-link.v1.schema.json` and `docs/CAPABILITY_LINK_GRAPH.md`.

The composition rule is fail-closed:

    A(link(skill, actuator)) <=
      A(skill) intersection A(actuator) intersection A(host) intersection A(policy)

This prevents a skill from inheriting actuator authority merely because the host can route from one to the other. Provider output remains a proposal/candidate/evidence artifact until the declared verifier and promotion path admit it.


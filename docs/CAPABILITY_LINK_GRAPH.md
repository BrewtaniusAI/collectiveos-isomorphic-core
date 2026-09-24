# Capability Link Graph

## Status

This document defines a declarative, non-authorizing composition model for linking a procedural skill to an executable plugin, app, CLI, tool, or provider capability.

A link is not permission. A matching skill may explain how to use a capability, but relevance and procedural knowledge do not grant execution, write, deployment, release, memory, or canonical-state authority.

## Core abstraction

```text
intent
  -> skill            # procedure / operating knowledge
  -> actuator         # plugin / app / CLI / provider capability
  -> artifact         # proposal / candidate / evidence
  -> verifier         # independent admission decision
  -> promotion gate   # governed state transition
```

The authority of a composed link is monotonic and fail-closed:

```text
A(link(skill, actuator)) <=
  A(skill) intersection A(actuator) intersection A(host) intersection A(policy)
```

Composition must never behave as an authority union.

## Why this exists

A live 2026-09-24 Meshy exercise demonstrated the pattern with an installed plugin skill and external execution surface:

1. `meshy-3d-generation` supplied the bounded procedure.
2. Meshy generated and textured a humanoid candidate.
3. An independent local validator rejected the first candidate because it measured 815,786 faces against a 300,000-face rigging ceiling.
4. Meshy remeshed the exact lineage rather than regenerating it.
5. The validator admitted the 103,310-face remesh to the rigging stage while preserving topology warnings.
6. Meshy produced a 24-joint rig plus walking and running clips.
7. Independent structural and numeric validation confirmed skinning attributes, normalized weights, inverse bind matrices, an acyclic skeleton, and identical topology across the rig and locomotion clips.
8. The result remained non-authoritative pending the next declared deformation/visual gate.

The useful unit is therefore not "a plugin" or "a skill" in isolation. It is a typed capability edge with an artifact handoff and an independent verification boundary.

## Link semantics

A capability link MUST name:

- the procedural skill;
- the actuator/provider capability;
- the input artifact class;
- the output artifact class;
- the output authority ceiling;
- the verifier requirement;
- the authority composition rule.

The v1 schema fixes output authority to `proposal`, `candidate`, or `evidence`.

## Authority invariants

A capability link:

- does not create credentials;
- does not install or connect providers;
- does not infer permission from skill relevance;
- does not grant execution authority merely because an actuator can execute;
- does not convert provider output into canonical truth;
- does not grant external-write or canonical-commit authority;
- does not bypass host permission controls;
- does not bypass GACES/SYN or another declared verifier/promotion path.

## Provider independence

Skills and actuators are occupants, not architecture.

Examples of possible links include:

```text
IERE procedure        -> Exa search            -> evidence candidate
product build skill   -> Replit                -> implementation candidate
media workflow skill  -> Runway / Higgsfield   -> media candidate
3D asset skill        -> Meshy                 -> asset candidate
deploy skill          -> Vercel / Railway      -> deployment candidate
state skill           -> Supabase              -> migration candidate
verification skill    -> SYN / local validators -> admission evidence
```

Substitution is valid only when the replacement actuator accepts the declared input contract and produces an artifact accepted by the downstream verifier.

## Relationship to host plugins

An OpenAI plugin may bundle skills and may expose or coexist with executable capabilities. CollectiveOS treats those as separate logical roles even when the host packages them together.

Host-native packaging does not collapse the governance boundary:

```text
host package
  -> skill selected
  -> actuator available
  -> host/user permission
  -> action
  -> candidate artifact
  -> CollectiveOS verification
```

## Promotion rule

No artifact crosses from candidate/evidence into canonical state solely because:

- the skill completed;
- the actuator reported success;
- the host rendered a preview;
- the provider returned a task success state.

Promotion requires the verifier named by the receiving contract and any higher-lane governance required by that transition.

## Capability chains

A single capability link describes one procedural skill, one actuator, one artifact transition, and one verifier boundary. Real workflows compose multiple links. The chain contract at `contracts/capability-chain.v1.schema.json` makes that composition explicit.

A valid chain is artifact-contiguous:

```text
link[n].output_artifact == link[n+1].input_artifact
```

Every link remains independently verifier-gated, and chain authority is bounded by the intersection across every link plus host and policy:

```text
A(chain) <= intersection(A(link_1), ..., A(link_n), A(host), A(policy))
```

The reference example `examples/meshy-game-studio-capability-chain.v1.json` records the sanitized structure of the 2026-09-24 proof:

```text
meshy-3d-generation
  -> Meshy
  -> rigged-character-candidate
  -> rig verifier
  -> game-studio/web-3d-asset-pipeline
  -> glTF Transform
  -> web-glb-projection-candidate
  -> projection verifier
  -> game-studio/three-webgl-game + game-studio/game-playtest
  -> Three.js + Playwright
  -> browser-playback-evidence
```

The chain is intentionally non-authorizing. Successful completion of every step still does not grant canonical commit or governance promotion.

## Procedure and actuator provenance are independent

A capability chain MUST NOT require the skill and actuator to originate from the same plugin or provider.

A procedure may be supplied by one host package while a compatible actuator is supplied by another. Examples include:

- Game Studio asset procedure -> Meshy-generated GLB -> glTF Transform;
- Superpowers verification procedure -> GitHub or local execution evidence;
- deployment procedure -> Vercel or Railway;
- retrieval procedure -> Exa or another evidence provider.

Compatibility is established by the declared input/output artifact contracts and verifier, not by provider identity. A provider name match is neither necessary nor sufficient for authorization.

## Governed path resolution

`tools/resolve_capability_graph.py` resolves the shortest verifier-gated path between artifact classes from a declarative capability graph.

The resolver deliberately ignores bindings that lack:

- `verification_required: true`;
- a non-empty verifier;
- an output authority ceiling of `proposal`, `candidate`, or `evidence`.

Routing is advisory. Finding a path does not execute it and does not grant permissions. The resolved path is a plan candidate that still requires host/user permission, actuator execution, artifact verification, and declared promotion gates at runtime.

The reference graph `examples/capability-graph.meshy-game-studio.v1.json` demonstrates cross-provider routing from `character-spec` to `browser-playback-evidence`.


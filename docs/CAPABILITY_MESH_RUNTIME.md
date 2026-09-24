# Capability Mesh Runtime v1

## Status

This is a declarative, non-authorizing runtime layer above the merged capability-link, capability-chain, and capability-graph contracts.

## Goal

Allow Giles to resolve a governed execution path from current host capabilities without hard-coding provider names and without converting host discovery into authority.

## Core law

Live discovery reports availability only.

It MUST NOT invent:
- artifact semantics;
- verifier requirements;
- authority;
- canonical promotion rights;
- credentials or permissions.

Canonical binding templates define what a procedure/actuator/verifier combination may consume and emit. Runtime discovery only determines whether required occupants are currently available.

## Runtime model

A sanitized inventory contains capability occupants:

- `procedure`: reusable workflow/skill knowledge;
- `actuator`: executable tool/app/CLI/provider capability;
- `verifier`: validation/admission capability.

Each occupant declares:
- stable capability id;
- provider label;
- kind;
- locality: `local`, `remote`, or `hybrid`;
- cost class: `free`, `metered`, or `unknown`;
- availability and connection state;
- non-authorizing authority flags.

No account ids, machine paths, device ids, tokens, URLs with credentials, balances, or user-specific identifiers belong in the public fixture format.

## Binding templates

A binding template names:
- required procedure capability ids;
- required actuator capability ids;
- required verifier capability ids;
- input artifact class;
- output artifact class;
- output authority ceiling;
- locality class;
- cost class.

A template becomes a runtime binding only when every required capability is present, available, and connected when connection is required.

Provider identity is not a compatibility rule. A procedure and actuator may originate from different providers.

## Routing

The runtime compiler emits a non-authorizing capability graph.

The resolver chooses the shortest governed path subject to optional constraints:
- allowed locality;
- maximum cost class;
- required providers;
- denied providers;
- maximum hops.

Unsafe roots, unavailable occupants, undeclared artifact transitions, missing verifiers, and constraint violations fail closed.

Route discovery remains advisory. It never executes a tool.

## Initial public fixture

The public fixture models only sanitized capability classes already demonstrated in the live proof:

- `meshy-3d-generation` procedure;
- `meshy.generate-remesh-rig` actuator;
- `collective-rig-validator` verifier;
- `game-studio/web-3d-asset-pipeline` procedure;
- `gltf-transform` actuator;
- `collective-asset-projection-validator` verifier;
- `game-studio/three-webgl-game` procedure;
- `game-studio/game-playtest` procedure;
- `threejs-playwright` actuator;
- `collective-browser-playback-validator` verifier.

It contains no account-specific state or local host identifiers.

## Non-goals

v1 does not:
- automatically scrape every host tool into public fixtures;
- execute resolved routes;
- store credentials;
- infer permissions from connection state;
- promote artifacts to canonical state;
- choose providers based on subjective quality rankings.

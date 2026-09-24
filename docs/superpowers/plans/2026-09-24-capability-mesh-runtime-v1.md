# Capability Mesh Runtime v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compile sanitized live capability availability against canonical binding templates and resolve the shortest verifier-gated path under routing constraints.

**Architecture:** Keep runtime discovery separate from semantics. `capability_inventory.py` validates sanitized availability records; `compile_capability_mesh.py` activates only canonical templates whose required procedure/actuator/verifier occupants are available; `resolve_capability_graph.py` gains optional routing constraints while remaining non-authorizing.

**Tech Stack:** Python 3.10+, JSON, pytest, Ruff.

**Spec:** `docs/CAPABILITY_MESH_RUNTIME.md`

## Global Constraints

- Discovery reports availability only and never invents artifact semantics or authority.
- Public fixtures contain no account IDs, device IDs, machine paths, credentials, balances, or signed URLs.
- Every compiled binding requires its declared verifier.
- Skill/provider identity and actuator/provider identity may differ.
- Routing is advisory and authorizes no execution, external writes, canonical commit, or governance promotion.
- Existing capability-link/chain/graph contracts remain backward compatible.

## Review Focus

- Inventory records with `available=false` or `connected=false` must not activate a required occupant.
- Missing verifier occupants must remove the binding rather than degrade it.
- `remote` paths must be excluded when locality constraints permit only `local`.
- Metered paths must be excluded under a `free` maximum-cost constraint.
- Unsafe catalog authority/status must remain fail-closed even when runtime constraints are otherwise satisfied.

---

### Task 1: Sanitized runtime inventory

**Files:**
- Create: `contracts/capability-inventory.v1.schema.json`
- Create: `tools/capability_inventory.py`
- Create: `examples/capability-inventory.sanitized.v1.json`
- Test: `tests/test_capability_inventory.py`

**Interfaces:**
- Consumes: JSON-compatible inventory dicts.
- Produces: `validate_inventory(inventory: dict[str, Any]) -> list[str]` and `available_capability_ids(inventory: dict[str, Any]) -> set[str]`.

- [ ] **Step 1: Write failing tests** for valid sanitized inventory, unavailable exclusion, unsafe authority rejection, and forbidden metadata keys.
- [ ] **Step 2: Run tests** and verify failure because `tools.capability_inventory` does not exist.
- [ ] **Step 3: Implement** schema, fixture, validator, and availability helper.
- [ ] **Step 4: Run focused tests** and verify pass.
- [ ] **Step 5: Commit** `feat(mesh): add sanitized capability inventory`.

### Task 2: Canonical binding-template compiler

**Files:**
- Create: `contracts/capability-binding-template.v1.schema.json`
- Create: `examples/capability-binding-templates.v1.json`
- Create: `tools/compile_capability_mesh.py`
- Test: `tests/test_capability_mesh_compiler.py`

**Interfaces:**
- Consumes: validated inventory plus canonical template set.
- Produces: `compile_mesh(inventory: dict[str, Any], templates: dict[str, Any]) -> dict[str, Any]` returning `collective.capability-graph.v1`.

- [ ] **Step 1: Write failing tests** for cross-provider activation, missing actuator exclusion, missing verifier exclusion, and unavailable capability exclusion.
- [ ] **Step 2: Run tests** and verify failure because compiler is absent.
- [ ] **Step 3: Implement** minimal deterministic compiler with sorted bindings.
- [ ] **Step 4: Run focused tests** and verify pass.
- [ ] **Step 5: Commit** `feat(mesh): compile governed runtime bindings`.

### Task 3: Constraint-aware governed routing

**Files:**
- Modify: `tools/resolve_capability_graph.py`
- Test: `tests/test_capability_graph_constraints.py`
- Modify: `docs/CAPABILITY_LINK_GRAPH.md`

**Interfaces:**
- Consumes: `collective.capability-graph.v1` and optional constraints dict.
- Produces: `resolve_path(..., constraints: dict[str, Any] | None = None) -> list[dict[str, Any]]`.

- [ ] **Step 1: Write failing tests** for locality, maximum cost, provider allow/deny, max hops, and existing unsafe-root behavior.
- [ ] **Step 2: Run tests** and verify failures are constraint-related.
- [ ] **Step 3: Implement** deterministic filtering and bounded BFS without execution side effects.
- [ ] **Step 4: Run focused + existing capability tests** and verify pass.
- [ ] **Step 5: Commit** `feat(mesh): add constrained governed routing`.

### Task 4: Integrated proof fixture and verification

**Files:**
- Create: `examples/capability-mesh-runtime-proof.v1.json`
- Test: `tests/test_capability_mesh_runtime.py`
- Modify: `docs/CAPABILITY_MESH_RUNTIME.md`

**Interfaces:**
- Consumes: sanitized inventory, templates, compiler, resolver.
- Produces: a deterministic public fixture proving `character-spec -> browser-playback-evidence` while rejecting an unavailable or constraint-incompatible path.

- [ ] **Step 1: Write failing end-to-end test** for compile + route.
- [ ] **Step 2: Run it** and verify failure until the proof fixture/integration exists.
- [ ] **Step 3: Add** the sanitized proof fixture and documentation.
- [ ] **Step 4: Run all capability tests, Ruff check, and Ruff format check.**
- [ ] **Step 5: Commit** `test(mesh): add capability mesh runtime proof`.

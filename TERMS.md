# Terms

## Runtime isomorphism

Preservation of the declared contract, governance order, lawful transitions, and receipt schema
across different implemented model substrates.

## Heterogeneous family

A family whose tiers use distinct upstream providers and architecture families. Here: Qwen2,
Mistral, and Kimi Linear.

## Constraint-first execution

Validation that occurs before a model backend is constructed or invoked.

## Agent role binding

An explicit mapping from a named interaction role to a tier and system prompt. A role binding is
not an autonomous worker, permission grant, or external actuation authority.

## ISO-Mesh

The governed coordination surface. Version 0.3.0 implements role routing and sequential local
family conformance, not distributed multi-node inference.

## CollectiveOS bridge

A sealed JSON request/response boundary that resolves declared roles and links the response to a
tier receipt.

## Conformance artifact

A structured, hash-sealed record of an execution and its evidence.

## Proof Vault

An external storage/authority concept for signed and immutable lineage. Local hash seals prepare
records for a Proof Vault but do not claim that WORM anchoring occurred.

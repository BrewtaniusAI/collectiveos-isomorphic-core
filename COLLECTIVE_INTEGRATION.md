# CollectiveOS Integration Contract

## Purpose

The bridge gives CollectiveOS a stable local contract for selecting an OIMS role, executing its
bound model tier, and receiving evidence linked to that execution.

## Request

Schema: `schemas/collective-request.schema.json`

```json
{
  "request_id": "optional-caller-id",
  "agent": "Giles",
  "prompt": "Create a bounded implementation strategy.",
  "max_tokens": 512
}
```

`agent` may be a profile id, display name, or declared alias. If omitted, `rabbit-ops` is used.

## Binding

The bridge resolves the request through `AGENT_MANIFEST.json`. The binding selects:

- the exact model tier;
- the role-specific system prompt;
- the declared role purpose.

The binding cannot grant filesystem, network, shell, device, or external-service authority. This
repository performs inference only.

## Response

Schema: `schemas/collective-response.schema.json`

The sealed response includes:

- request id and canonical request hash;
- `role_binding_only` activation semantics;
- `autonomous_worker_claim: false`;
- the `QC -> GATA -> GATA_PRIME` governance route;
- the resolved agent profile without duplicating its manifest system-prompt text;
- the linked tier receipt and its record hash;
- an outer canonical record seal.

Verify:

```bash
python -m oims verify --path artifacts/collective-<request-hash>.jsonld
```

## Invocation

Direct:

```bash
python -m oims collective \
  --agent Cypher \
  --prompt "Check this evidence for contradictions."
```

File envelope:

```bash
python -m oims collective --request-file examples/collective-request.json
```

PowerShell:

```powershell
.\scripts\run_collective_agent.ps1 `
  -Agent Rabbit `
  -Prompt "Turn this objective into a reversible checklist."
```

## Failure semantics

- invalid envelope: no model executes;
- unknown agent: no model executes;
- input contract failure: receipt records the governed collapse/idle state;
- missing or altered weights: backend fails closed;
- unsupported runtime version: backend fails closed;
- model failure: receipt says `BACKEND_UNAVAILABLE`;
- seal or hash-link mismatch: `oims verify` exits nonzero.

In this implementation, QC is preflight validation, GATA is post-inference/output validation, and
GATA PRIME is receipt sealing and verification. External governance services are not implied.

## Loopback service

Version 0.3.1 adds an authenticated local service:

```powershell
$env:OIMS_SERVICE_TOKEN = "<random 32-byte-or-longer secret>"
oims-service --host 127.0.0.1 --port 9319
```

`POST /v1/collective` accepts the same request object and returns the same sealed response.
Inference is serialized so multiple callers do not load competing weight tiers simultaneously.
`GET /health` distinguishes physical weight readiness from fixture or source completeness.

## Deployment boundary

The service refuses non-loopback binding. Authentication is deployment-owned and separate from
Quest device credentials. Process isolation, forced inference cancellation, external actuation,
and canonical Proof Vault/WORM authority remain outside OIMS and must be supplied by the owning
deployment.

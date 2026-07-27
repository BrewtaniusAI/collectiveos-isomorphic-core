# Collective Quest OIMS service

The Quest integration uses a loopback-only HTTP wrapper around the real `run_collective_request` runtime.

```powershell
.\scripts\start_quest_oims.ps1
```

The launcher performs a full SHA-256 verification of all pinned weights before starting `127.0.0.1:8310`.

- `GET /health` reports family and local weight readiness.
- `POST /v1/chat` accepts `prompt` or the Giles-compatible `message` field.
- GPU work is serialized so simultaneous headset requests cannot load competing model tiers.
- Fixture backends are not exposed through the service.
- A backend-unavailable or unlawful result is returned as HTTP 503.
- The server refuses non-loopback bind addresses.

Configure Giles with:

```powershell
$env:COLLECTIVE_OIMS_URL = "http://127.0.0.1:8310"
```

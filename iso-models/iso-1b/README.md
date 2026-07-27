# ISO-1B — Intake/Edge

- binding: Qwen2.5-1.5B-Instruct
- architecture family: Qwen2
- provider: Qwen
- quantization: Q4_K_M
- exact download: 1,117,320,736 bytes
- default offload: all layers
- roles: SYN Edge and fast intake

Run:

```bash
python -m oims run --tier ISO-1B --prompt "bounded intake probe"
python -m oims collective --agent Syn --prompt "classify this request"
```

Exact revision, size, and SHA-256 are in `MODEL_MANIFEST.json`.

# ISO-30B — Strategist

ISO-30B is the large OIMS capacity tier. Its heterogeneous binding is Kimi Linear
48B total / 3B active.

- architecture family: Kimi Linear/KDA
- provider: Moonshot AI
- GGUF conversion: bartowski imatrix
- quantization: Q3_K_M
- exact download: 22,680,802,720 bytes
- default context: 4,096 tokens
- default offload: 20 of 27 layers
- roles: Giles Strategist, Cypher Analyst, and Lock Security

```bash
python -m oims run --tier ISO-30B --prompt "bounded strategy probe"
python -m oims collective --agent Giles --prompt "synthesize a strategy"
```

The partial-offload default preserves VRAM headroom on a 24 GB RTX 4090 and uses system RAM for
remaining layers. Reduce `--n-gpu-layers` if allocation fails.

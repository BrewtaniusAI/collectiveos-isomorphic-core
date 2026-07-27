# ISO-7B — Operator

- binding: Mistral-7B-Instruct-v0.3
- architecture family: Mistral
- provider: Mistral AI
- GGUF conversion: bartowski
- quantization: Q4_K_M
- exact download: 4,372,812,000 bytes
- default offload: all layers
- roles: Rabbit Ops, Max Device, and Muse Creative

Mistral v0.3's GGUF chat template accepts user/assistant roles but not a system role. The runtime
therefore prepends the governed role prompt to the user turn instead of sending an invalid system
message.

```bash
python -m oims run --tier ISO-7B --prompt "bounded operator probe"
python -m oims collective --agent Rabbit --prompt "turn this into a checklist"
```

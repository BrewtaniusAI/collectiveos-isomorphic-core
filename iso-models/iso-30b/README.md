# ISO-30B

ISO-30B is the large OIMS capacity tier. Its current reference binding is the 32B-class
Qwen2.5-32B-Instruct GGUF model.

- quantization: Q4_K_M
- local download: approximately 19.9 GB across five files
- default context: 2,048 tokens
- status: runtime binding implemented
- execution: `python -m oims run --tier ISO-30B --prompt "..."`;

On a 24 GB GPU, reduce `--n-gpu-layers` if complete GPU offload exceeds available memory.

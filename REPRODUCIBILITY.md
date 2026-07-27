# Reproducibility

Reproduction is anchored by:

- immutable Hugging Face repository revisions;
- exact GGUF filenames;
- local SHA-256 weight locks;
- one shared contract hash;
- deterministic decoding settings;
- source commit capture;
- sealed tier and family records.

```bash
python -m pip install -e ".[weights]"
python -m oims weights pull --tier all
python -m oims weights check --tier all --full-hash
python -m oims family --prompt "family conformance probe"
```

Generated text can still vary across llama.cpp versions, hardware kernels, and floating-point
execution. OIMS reproducibility therefore distinguishes governance-transition reproducibility from
byte-identical model-output reproducibility.

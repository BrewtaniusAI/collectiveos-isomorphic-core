# Quickstart

## Install

```bash
python -m venv .venv
python -m pip install -e ".[weights]"
```

Install a CUDA-enabled build of `llama-cpp-python` as described in `WEIGHTS.md`.

## Download all pinned weights

```bash
python -m oims weights pull --tier all
python -m oims weights check --tier all
```

## Run the family

```bash
python -m oims family --prompt "family conformance probe"
```

Inspect:

- `artifacts/iso-1b-conformance.jsonld`
- `artifacts/iso-7b-conformance.jsonld`
- `artifacts/iso-30b-conformance.jsonld`
- `artifacts/conformance_report.jsonld`

For a no-weight governance smoke test:

```bash
python -m oims family --backend fixture --prompt "fixture probe"
```

Fixture reports are explicitly labeled `TEST_OR_INCOMPLETE`.

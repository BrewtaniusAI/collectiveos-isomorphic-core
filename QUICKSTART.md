# Quickstart

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[weights]"

$env:CMAKE_ARGS = "-DGGML_CUDA=on"
$env:FORCE_CMAKE = "1"
python -m pip install --upgrade --force-reinstall --no-cache-dir "llama-cpp-python>=0.3.34,<0.4"

.\scripts\download_weights.ps1 -Tier all
python -m oims doctor
.\scripts\run_all_weights.ps1 -Prompt "heterogeneous family probe"
```

Run a CollectiveOS role:

```powershell
python -m oims collective `
  --agent Giles `
  --prompt "Develop a verified implementation strategy."
```

Fixture-only smoke test:

```bash
python -m oims --artifacts-dir artifacts-smoke mesh \
  --backend fixture \
  --prompt "fixture probe"
python -m oims verify --path artifacts-smoke/conformance_report.jsonld
```

Fixture output is always `TEST_OR_INCOMPLETE`.

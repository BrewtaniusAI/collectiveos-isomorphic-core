param(
    [string]$Prompt = "heterogeneous family acceptance probe",
    [string]$WeightsDir = "weights",
    [string]$ArtifactsDir = "artifacts",
    [int]$MaxTokens = 256
)

$ErrorActionPreference = "Stop"

python -m oims --weights-dir $WeightsDir doctor
if ($LASTEXITCODE -ne 0) {
    throw "OIMS doctor did not approve this machine"
}

python -m oims --weights-dir $WeightsDir weights check --tier all --full-hash
if ($LASTEXITCODE -ne 0) {
    throw "Pinned heterogeneous weights failed full SHA-256 verification"
}

python -m oims `
    --weights-dir $WeightsDir `
    --artifacts-dir $ArtifactsDir `
    mesh `
    --prompt $Prompt `
    --max-tokens $MaxTokens
if ($LASTEXITCODE -ne 0) {
    throw "Heterogeneous family execution failed"
}

python -m oims verify `
    --path (Join-Path $ArtifactsDir "conformance_report.jsonld") `
    --require-weight-backed
if ($LASTEXITCODE -ne 0) {
    throw "Family receipt failed WEIGHT_BACKED acceptance"
}

Write-Host "OIMS heterogeneous family accepted." -ForegroundColor Green

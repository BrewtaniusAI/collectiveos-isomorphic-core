param(
    [Parameter(Mandatory = $true)]
    [string]$Prompt,
    [string]$WeightsDir = "weights",
    [string]$ArtifactsDir = "artifacts",
    [int]$MaxTokens = 256
)

$ErrorActionPreference = "Stop"

python -m oims `
    --weights-dir $WeightsDir `
    --artifacts-dir $ArtifactsDir `
    mesh `
    --prompt $Prompt `
    --max-tokens $MaxTokens

if ($LASTEXITCODE -ne 0) {
    throw "OIMS family execution failed with exit code $LASTEXITCODE"
}

python -m oims verify `
    --path (Join-Path $ArtifactsDir "conformance_report.jsonld") `
    --require-weight-backed

if ($LASTEXITCODE -ne 0) {
    throw "OIMS family evidence verification failed with exit code $LASTEXITCODE"
}

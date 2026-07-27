param(
    [Parameter(Mandatory = $true)]
    [string]$Agent,
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
    collective `
    --agent $Agent `
    --prompt $Prompt `
    --max-tokens $MaxTokens

if ($LASTEXITCODE -ne 0) {
    throw "CollectiveOS OIMS role execution failed with exit code $LASTEXITCODE"
}

[CmdletBinding()]
param(
    [Parameter()]
    [int]$Port = 8310,

    [Parameter()]
    [string]$WeightsDir = ".\weights",

    [Parameter()]
    [string]$ArtifactsDir = ".\artifacts"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "OIMS virtual environment not found. Complete the README installation first."
}

Push-Location $root
try {
    & $python -m oims weights check --tier all --full-hash
    if ($LASTEXITCODE -ne 0) {
        throw "OIMS weights failed full-hash verification. The service was not started."
    }
    & $python -m oims.server `
        --host 127.0.0.1 `
        --port $Port `
        --weights-dir $WeightsDir `
        --artifacts-dir $ArtifactsDir
}
finally {
    Pop-Location
}

param(
    [ValidateSet("all", "ISO-1B", "ISO-7B", "ISO-30B")]
    [string]$Tier = "all",
    [string]$WeightsDir = "weights"
)

$ErrorActionPreference = "Stop"

python -m oims --weights-dir $WeightsDir weights pull --tier $Tier
if ($LASTEXITCODE -ne 0) {
    throw "OIMS weight download failed with exit code $LASTEXITCODE"
}

python -m oims --weights-dir $WeightsDir weights check --tier $Tier
if ($LASTEXITCODE -ne 0) {
    throw "OIMS weight verification failed with exit code $LASTEXITCODE"
}

[CmdletBinding()]
param(
    [ValidateSet('Validate', 'Simulate', 'Probe')]
    [string]$Mode = 'Simulate',

    [Parameter(Mandatory = $true)]
    [string]$Plan,

    [Parameter(Mandatory = $true)]
    [string]$BaseImage,

    [Parameter(Mandatory = $true)]
    [string]$BaseModelDir,

    [Parameter(Mandatory = $true)]
    [string]$DatasetDir,

    [Parameter(Mandatory = $true)]
    [string]$OutputDir,

    [string]$AcceptPlanHash,
    [string]$SourceCommit,
    [int]$GpuDeviceId = 0,
    [string]$MemoryLimit = '120g'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Docker Desktop / docker CLI is required.'
}

if ($BaseImage -notmatch '@sha256:[0-9a-f]{64}$') {
    throw 'BaseImage must be pinned as image@sha256:<64 lowercase hex characters>.'
}

$PlanPath = (Resolve-Path -LiteralPath $Plan).Path
$RepositoryRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw 'Git is required to prove the Model Forge build context is a clean commit.'
}
if (-not (Get-Command tar -ErrorAction SilentlyContinue)) {
    throw 'tar is required to export the exact Model Forge commit as the Docker build context.'
}
$HeadCommit = (& git -C $RepositoryRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "Could not resolve the Model Forge source commit (exit $LASTEXITCODE)."
}
if ($SourceCommit -and $SourceCommit -ne $HeadCommit) {
    throw 'SourceCommit does not match the repository HEAD selected for the build context.'
}
$SourceCommit = $HeadCommit
if ($SourceCommit -notmatch '^[0-9a-f]{40}$') {
    throw 'SourceCommit must be an exact 40-character lowercase Git commit.'
}
$DirtyState = @(& git -C $RepositoryRoot status --porcelain=v1 --untracked-files=all)
if ($LASTEXITCODE -ne 0) {
    throw "Could not verify the Model Forge build context (exit $LASTEXITCODE)."
}
if ($DirtyState.Count -ne 0) {
    throw 'Model Forge refuses a dirty build context; commit or remove every tracked/untracked change.'
}

foreach ($Directory in @($BaseModelDir, $DatasetDir, $OutputDir)) {
    if (-not (Test-Path -LiteralPath $Directory -PathType Container)) {
        if ($Mode -eq 'Simulate') {
            New-Item -ItemType Directory -Path $Directory -Force | Out-Null
        }
        else {
            throw "Required directory does not exist: $Directory"
        }
    }
}

$ComposePath = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\forge\compose.yaml')).Path
$EnvironmentNames = @(
    'FORGE_BASE_IMAGE',
    'FORGE_BUILD_CONTEXT',
    'FORGE_SOURCE_COMMIT',
    'FORGE_PLAN',
    'FORGE_BASE_MODEL_DIR',
    'FORGE_DATASET_DIR',
    'FORGE_OUTPUT',
    'FORGE_GPU_DEVICE_ID',
    'FORGE_MEMORY_LIMIT',
    'FORGE_ACCEPT_PLAN_HASH'
)
$OriginalEnvironment = @{}
foreach ($Name in $EnvironmentNames) {
    $OriginalEnvironment[$Name] = [Environment]::GetEnvironmentVariable($Name, 'Process')
}

$BuildContext = $null
$ArchivePath = $null
try {
    $BuildContext = Join-Path `
        ([System.IO.Path]::GetTempPath()) `
        ("collective-model-forge-" + [guid]::NewGuid().ToString('N'))
    $ArchivePath = "$BuildContext.tar"
    New-Item -ItemType Directory -Path $BuildContext | Out-Null
    & git -C $RepositoryRoot archive --format=tar "--output=$ArchivePath" $SourceCommit
    if ($LASTEXITCODE -ne 0) {
        throw "Could not export the Model Forge source commit (exit $LASTEXITCODE)."
    }
    & tar -xf $ArchivePath -C $BuildContext
    if ($LASTEXITCODE -ne 0) {
        throw "Could not extract the Model Forge build context (exit $LASTEXITCODE)."
    }
    Remove-Item -LiteralPath $ArchivePath -Force
    $ArchivePath = $null

    $env:FORGE_BASE_IMAGE = $BaseImage
    $env:FORGE_BUILD_CONTEXT = $BuildContext
    $env:FORGE_SOURCE_COMMIT = $SourceCommit
    $env:FORGE_PLAN = $PlanPath
    $env:FORGE_BASE_MODEL_DIR = (Resolve-Path -LiteralPath $BaseModelDir).Path
    $env:FORGE_DATASET_DIR = (Resolve-Path -LiteralPath $DatasetDir).Path
    $env:FORGE_OUTPUT = (Resolve-Path -LiteralPath $OutputDir).Path
    $env:FORGE_GPU_DEVICE_ID = [string]$GpuDeviceId
    $env:FORGE_MEMORY_LIMIT = $MemoryLimit

    & docker compose -f $ComposePath config --quiet
    if ($LASTEXITCODE -ne 0) {
        throw "Model Forge Compose validation failed with exit code $LASTEXITCODE."
    }

    switch ($Mode) {
        'Validate' {
            & docker compose -f $ComposePath run --rm --build simulate `
                forge validate --plan /forge/plan.json
        }
        'Simulate' {
            & docker compose -f $ComposePath run --rm --build simulate
        }
        'Probe' {
            if ($AcceptPlanHash -notmatch '^sha256:[0-9a-f]{64}$') {
                throw 'Probe requires the exact validated plan hash in -AcceptPlanHash.'
            }
            $env:FORGE_ACCEPT_PLAN_HASH = $AcceptPlanHash
            & docker compose -f $ComposePath --profile probe run --rm --build probe
        }
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Model Forge $Mode failed with exit code $LASTEXITCODE."
    }
}
finally {
    foreach ($Name in $EnvironmentNames) {
        [Environment]::SetEnvironmentVariable($Name, $OriginalEnvironment[$Name], 'Process')
    }
    if ($ArchivePath -and (Test-Path -LiteralPath $ArchivePath -PathType Leaf)) {
        Remove-Item -LiteralPath $ArchivePath -Force
    }
    if ($BuildContext -and (Test-Path -LiteralPath $BuildContext -PathType Container)) {
        Remove-Item -LiteralPath $BuildContext -Recurse -Force
    }
}

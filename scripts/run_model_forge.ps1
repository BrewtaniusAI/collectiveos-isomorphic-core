[CmdletBinding()]
param(
    [ValidateSet('Validate', 'Simulate', 'Verify', 'Probe')]
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
    [string]$Receipt,
    [string]$SourceCommit,
    [int]$GpuDeviceId = 0,
    [string]$MemoryLimit = '124g'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if ($PSVersionTable.PSVersion.Major -lt 7) {
    throw 'Model Forge requires PowerShell 7 or later.'
}

function Test-ContainedRelativePath {
    param([Parameter(Mandatory = $true)][string]$RelativePath)

    $ParentPrefix = '..' + [System.IO.Path]::DirectorySeparatorChar
    return (
        -not [System.IO.Path]::IsPathRooted($RelativePath) -and
        $RelativePath -ne '..' -and
        -not $RelativePath.StartsWith($ParentPrefix)
    )
}

function Test-PathsOverlap {
    param(
        [Parameter(Mandatory = $true)][string]$Left,
        [Parameter(Mandatory = $true)][string]$Right
    )

    $LeftToRight = [System.IO.Path]::GetRelativePath($Left, $Right)
    $RightToLeft = [System.IO.Path]::GetRelativePath($Right, $Left)
    return (
        (Test-ContainedRelativePath -RelativePath $LeftToRight) -or
        (Test-ContainedRelativePath -RelativePath $RightToLeft)
    )
}

function Invoke-ForgeImageBuild {
    param(
        [Parameter(Mandatory = $true)][string]$RepositoryRoot,
        [Parameter(Mandatory = $true)][string]$SourceCommit,
        [Parameter(Mandatory = $true)][string]$SourceTree,
        [Parameter(Mandatory = $true)][string]$BaseImage,
        [Parameter(Mandatory = $true)][string]$ForgeImage
    )

    $Attestation = "commit=$SourceCommit`ntree=$SourceTree`n"
    $DockerStartInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $DockerStartInfo.FileName = 'docker'
    $DockerStartInfo.UseShellExecute = $false
    $DockerStartInfo.RedirectStandardInput = $true
    foreach ($Argument in @(
        'build',
        '--file',
        'forge/Containerfile',
        '--build-arg',
        "FORGE_BASE_IMAGE=$BaseImage",
        '--build-arg',
        "FORGE_SOURCE_COMMIT=$SourceCommit",
        '--build-arg',
        "FORGE_SOURCE_TREE=$SourceTree",
        '--tag',
        $ForgeImage,
        '-'
    )) {
        $DockerStartInfo.ArgumentList.Add($Argument)
    }

    $GitStartInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $GitStartInfo.FileName = 'git'
    $GitStartInfo.UseShellExecute = $false
    $GitStartInfo.RedirectStandardOutput = $true
    foreach ($Argument in @(
        '-C',
        $RepositoryRoot,
        'archive',
        '--format=tar',
        "--add-virtual-file=.oims-forge-source.attestation:$Attestation",
        $SourceCommit
    )) {
        $GitStartInfo.ArgumentList.Add($Argument)
    }

    $DockerProcess = [System.Diagnostics.Process]::Start($DockerStartInfo)
    if ($null -eq $DockerProcess) {
        throw 'Could not start the immutable Model Forge image build.'
    }
    $GitProcess = $null
    $CopyFailure = $null
    try {
        $GitProcess = [System.Diagnostics.Process]::Start($GitStartInfo)
        if ($null -eq $GitProcess) {
            throw 'Could not start the exact-commit archive stream.'
        }
        try {
            $GitProcess.StandardOutput.BaseStream.CopyTo(
                $DockerProcess.StandardInput.BaseStream
            )
        }
        catch {
            $CopyFailure = $_
        }
        finally {
            $DockerProcess.StandardInput.Close()
        }
        $GitProcess.WaitForExit()
        $DockerProcess.WaitForExit()
        if ($null -ne $CopyFailure) {
            throw "Could not stream the exact-commit archive to Docker: $CopyFailure"
        }
        if ($GitProcess.ExitCode -ne 0) {
            throw "Could not export the Model Forge source commit (exit $($GitProcess.ExitCode))."
        }
        if ($DockerProcess.ExitCode -ne 0) {
            throw "Could not build the immutable Model Forge image (exit $($DockerProcess.ExitCode))."
        }
    }
    finally {
        if (-not $DockerProcess.HasExited) {
            $DockerProcess.StandardInput.Close()
            $DockerProcess.Kill($true)
            $DockerProcess.WaitForExit()
        }
        if ($null -ne $GitProcess -and -not $GitProcess.HasExited) {
            $GitProcess.Kill($true)
            $GitProcess.WaitForExit()
        }
        if ($null -ne $GitProcess) {
            $GitProcess.Dispose()
        }
        $DockerProcess.Dispose()
    }
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Docker Desktop / docker CLI is required.'
}

if ($BaseImage -notmatch '^[a-z0-9][a-z0-9._:/-]*@sha256:[0-9a-f]{64}$') {
    throw 'BaseImage must be pinned as image@sha256:<64 lowercase hex characters>.'
}

$PlanPath = (Resolve-Path -LiteralPath $Plan).Path
$RepositoryRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw 'Git is required to prove the Model Forge build context is a clean commit.'
}
$RepositoryAffectingGitEnvironment = @(
    'GIT_ALTERNATE_OBJECT_DIRECTORIES',
    'GIT_CEILING_DIRECTORIES',
    'GIT_COMMON_DIR',
    'GIT_DIR',
    'GIT_DISCOVERY_ACROSS_FILESYSTEM',
    'GIT_INDEX_FILE',
    'GIT_NAMESPACE',
    'GIT_OBJECT_DIRECTORY',
    'GIT_PREFIX',
    'GIT_WORK_TREE'
)
$ActiveGitOverrides = @(
    Get-ChildItem Env: | Where-Object {
        $RepositoryAffectingGitEnvironment -contains $_.Name -or $_.Name -like 'GIT_CONFIG_*'
    }
)
if ($ActiveGitOverrides.Count -ne 0) {
    throw 'Model Forge refuses repository-affecting Git environment overrides.'
}
$ResolvedWorkTree = (& git -C $RepositoryRoot rev-parse --show-toplevel).Trim()
if ($LASTEXITCODE -ne 0 -or -not $ResolvedWorkTree) {
    throw 'Could not resolve the Model Forge Git worktree.'
}
$ResolvedWorkTree = (Resolve-Path -LiteralPath $ResolvedWorkTree).Path
if ($ResolvedWorkTree -ne $RepositoryRoot) {
    throw 'Git did not resolve the expected Model Forge worktree.'
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
$SourceTree = (& git -C $RepositoryRoot rev-parse "${SourceCommit}^{tree}").Trim()
if ($LASTEXITCODE -ne 0 -or $SourceTree -notmatch '^[0-9a-f]{40}$') {
    throw 'Could not resolve the exact Model Forge source tree.'
}
$IndexFlags = @(& git -C $RepositoryRoot ls-files -v)
if ($LASTEXITCODE -ne 0) {
    throw "Could not inspect Model Forge index flags (exit $LASTEXITCODE)."
}
$HiddenIndexEntries = @($IndexFlags | Where-Object { $_ -notmatch '^H ' })
if ($HiddenIndexEntries.Count -ne 0) {
    throw 'Model Forge refuses assume-unchanged, skip-worktree, or other hidden index entries.'
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
$BaseModelPath = (Resolve-Path -LiteralPath $BaseModelDir).Path
$DatasetPath = (Resolve-Path -LiteralPath $DatasetDir).Path
$OutputPath = (Resolve-Path -LiteralPath $OutputDir).Path
foreach ($ProtectedSource in @($PlanPath, $BaseModelPath, $DatasetPath)) {
    if (Test-PathsOverlap -Left $OutputPath -Right $ProtectedSource) {
        throw 'OutputDir must not equal, contain, or be contained by Plan, BaseModelDir, or DatasetDir.'
    }
}

$ContainerReceipt = $null
if ($Mode -eq 'Verify') {
    if (-not $Receipt) {
        throw 'Verify requires -Receipt pointing to a receipt beneath OutputDir.'
    }
    $ReceiptPath = (Resolve-Path -LiteralPath $Receipt).Path
    if (-not (Test-Path -LiteralPath $ReceiptPath -PathType Leaf)) {
        throw "Forge receipt does not exist: $ReceiptPath"
    }
    $OutputRoot = $OutputPath
    $RelativeReceipt = [System.IO.Path]::GetRelativePath($OutputRoot, $ReceiptPath)
    $ParentPrefix = '..' + [System.IO.Path]::DirectorySeparatorChar
    if (
        [System.IO.Path]::IsPathRooted($RelativeReceipt) -or
        $RelativeReceipt -eq '..' -or
        $RelativeReceipt.StartsWith($ParentPrefix)
    ) {
        throw 'Verify requires Receipt to remain beneath OutputDir.'
    }
    $ContainerReceipt = '/forge/output/' + $RelativeReceipt.Replace('\', '/')
}

$ComposePath = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\forge\compose.yaml')).Path
$EnvironmentNames = @(
    'FORGE_BASE_IMAGE',
    'FORGE_IMAGE_TAG',
    'FORGE_SOURCE_COMMIT',
    'FORGE_SOURCE_TREE',
    'FORGE_PLAN',
    'FORGE_BASE_MODEL_DIR',
    'FORGE_DATASET_DIR',
    'FORGE_OUTPUT',
    'FORGE_RECEIPT',
    'FORGE_GPU_DEVICE_ID',
    'FORGE_MEMORY_LIMIT',
    'FORGE_ACCEPT_PLAN_HASH'
)
$OriginalEnvironment = @{}
foreach ($Name in $EnvironmentNames) {
    $OriginalEnvironment[$Name] = [Environment]::GetEnvironmentVariable($Name, 'Process')
}

try {
    $TagHasher = [System.Security.Cryptography.SHA256]::Create()
    try {
        $TagMaterial = [System.Text.Encoding]::UTF8.GetBytes("$SourceCommit`n$BaseImage")
        $ImageTag = -join (
            $TagHasher.ComputeHash($TagMaterial) | ForEach-Object { $_.ToString('x2') }
        )
    }
    finally {
        $TagHasher.Dispose()
    }
    $ForgeImage = "collective-model-forge:$ImageTag"

    $env:FORGE_BASE_IMAGE = $BaseImage
    $env:FORGE_IMAGE_TAG = $ImageTag
    $env:FORGE_SOURCE_COMMIT = $SourceCommit
    $env:FORGE_SOURCE_TREE = $SourceTree
    $env:FORGE_PLAN = $PlanPath
    $env:FORGE_BASE_MODEL_DIR = $BaseModelPath
    $env:FORGE_DATASET_DIR = $DatasetPath
    $env:FORGE_OUTPUT = $OutputPath
    [Environment]::SetEnvironmentVariable('FORGE_RECEIPT', $null, 'Process')
    [Environment]::SetEnvironmentVariable('FORGE_ACCEPT_PLAN_HASH', $null, 'Process')
    if ($ContainerReceipt) {
        $env:FORGE_RECEIPT = $ContainerReceipt
    }
    $env:FORGE_GPU_DEVICE_ID = [string]$GpuDeviceId
    $env:FORGE_MEMORY_LIMIT = $MemoryLimit
    if ($Mode -eq 'Probe') {
        if ($AcceptPlanHash -notmatch '^sha256:[0-9a-f]{64}$') {
            throw 'Probe requires the exact validated plan hash in -AcceptPlanHash.'
        }
        $env:FORGE_ACCEPT_PLAN_HASH = $AcceptPlanHash
    }

    $ComposeOutput = @(
        & docker compose -f $ComposePath --profile probe config --format json
    )
    if ($LASTEXITCODE -ne 0 -or $ComposeOutput.Count -eq 0) {
        throw "Model Forge Compose validation failed with exit code $LASTEXITCODE."
    }
    $ResolvedCompose = ($ComposeOutput -join [Environment]::NewLine) | ConvertFrom-Json
    $ExpectedServices = @('simulate', 'verify', 'probe')
    $ObservedServices = @($ResolvedCompose.services.PSObject.Properties.Name)
    if (@(Compare-Object $ExpectedServices $ObservedServices).Count -ne 0) {
        throw 'Model Forge Compose policy contains an unexpected service.'
    }
    $ExpectedEntrypoint = @(
        'python',
        '-I',
        '-S',
        '/usr/local/libexec/oims-forge-entrypoint.py'
    )
    $ExpectedReceipt = '/forge/output/receipt.json'
    if ($ContainerReceipt) {
        $ExpectedReceipt = $ContainerReceipt
    }
    $ExpectedAcceptPlanHash = 'unset'
    if ($Mode -eq 'Probe') {
        $ExpectedAcceptPlanHash = $AcceptPlanHash
    }
    $ExpectedCommands = @{
        'simulate' = @('forge', 'simulate', '--plan', '/forge/plan.json', '--output', '/forge/output')
        'verify' = @('forge', 'verify', '--receipt', $ExpectedReceipt)
        'probe' = @(
            'forge',
            'probe',
            '--plan',
            '/forge/plan.json',
            '--output',
            '/forge/output',
            '--accept-plan-hash',
            $ExpectedAcceptPlanHash
        )
    }
    $ExpectedMounts = @{
        '/forge/plan.json' = @{
            Source = $PlanPath
            ReadOnly = $true
        }
        '/forge/output' = @{
            Source = $OutputPath
            ReadOnly = $false
        }
        '/forge/inputs/base' = @{
            Source = $BaseModelPath
            ReadOnly = $true
        }
        '/forge/inputs/dataset' = @{
            Source = $DatasetPath
            ReadOnly = $true
        }
    }
    foreach ($ServiceName in $ExpectedServices) {
        $Service = $ResolvedCompose.services.$ServiceName
        $BuildProperty = $Service.PSObject.Properties['build']
        if (
            $null -ne $BuildProperty -or
            [string]$Service.image -ne $ForgeImage -or
            [string]$Service.pull_policy -ne 'never' -or
            [string]$Service.user -ne '65532:65532' -or
            [string]$Service.network_mode -ne 'none' -or
            -not [bool]$Service.read_only -or
            (@($Service.cap_drop) -join ',') -ne 'ALL' -or
            @($Service.security_opt) -notcontains 'no-new-privileges:true'
        ) {
            throw "Model Forge Compose service $ServiceName violates the pre-start sandbox policy."
        }
        if ((@($Service.entrypoint) -join "`0") -ne ($ExpectedEntrypoint -join "`0")) {
            throw "Model Forge Compose service $ServiceName has an unexpected entrypoint."
        }
        if ((@($Service.command) -join "`0") -ne (@($ExpectedCommands[$ServiceName]) -join "`0")) {
            throw "Model Forge Compose service $ServiceName has an unexpected command."
        }
        $ExpectedEnvironment = @{
            'HF_HUB_OFFLINE' = '1'
            'TRANSFORMERS_OFFLINE' = '1'
            'HF_DATASETS_OFFLINE' = '1'
            'OIMS_FORGE_CONTAINER' = '1'
            'OIMS_FORGE_BASE_IMAGE' = $BaseImage
            'OIMS_FORGE_SOURCE_COMMIT' = $SourceCommit
            'OIMS_FORGE_SOURCE_TREE' = $SourceTree
        }
        if ($ServiceName -eq 'probe') {
            $ExpectedEnvironment['OIMS_FORGE_ENABLE_PROBE'] = '1'
        }
        $ObservedEnvironmentNames = @($Service.environment.PSObject.Properties.Name)
        if (@(Compare-Object @($ExpectedEnvironment.Keys) $ObservedEnvironmentNames).Count -ne 0) {
            throw "Model Forge Compose service $ServiceName has an unexpected environment variable."
        }
        foreach ($Name in $ExpectedEnvironment.Keys) {
            if ([string]$Service.environment.$Name -ne [string]$ExpectedEnvironment[$Name]) {
                throw "Model Forge Compose service $ServiceName has an unexpected environment value."
            }
        }
        $ObservedMounts = @($Service.volumes)
        if ($ObservedMounts.Count -ne $ExpectedMounts.Count) {
            throw "Model Forge Compose service $ServiceName has an unexpected mount count."
        }
        $SeenTargets = @{}
        foreach ($Volume in $ObservedMounts) {
            $Target = [string]$Volume.target
            if (
                [string]$Volume.type -ne 'bind' -or
                -not $ExpectedMounts.ContainsKey($Target) -or
                $SeenTargets.ContainsKey($Target)
            ) {
                throw "Model Forge Compose service $ServiceName has an unexpected bind mount target."
            }
            $SeenTargets[$Target] = $true
            $ExpectedMount = $ExpectedMounts[$Target]
            $ObservedReadOnly = $false
            $ReadOnlyProperty = $Volume.PSObject.Properties['read_only']
            if ($null -ne $ReadOnlyProperty) {
                $ObservedReadOnly = [bool]$ReadOnlyProperty.Value
            }
            if (
                [string]$Volume.source -ne [string]$ExpectedMount.Source -or
                $ObservedReadOnly -ne [bool]$ExpectedMount.ReadOnly
            ) {
                throw "Model Forge Compose service $ServiceName has an unexpected bind mount source or mode."
            }
        }
    }

    Invoke-ForgeImageBuild `
        -RepositoryRoot $RepositoryRoot `
        -SourceCommit $SourceCommit `
        -SourceTree $SourceTree `
        -BaseImage $BaseImage `
        -ForgeImage $ForgeImage

    switch ($Mode) {
        'Validate' {
            $ComposeOutput | & docker compose -f - run --rm simulate `
                forge validate --plan /forge/plan.json
        }
        'Simulate' {
            $ComposeOutput | & docker compose -f - run --rm simulate
        }
        'Verify' {
            $ComposeOutput | & docker compose -f - run --rm verify
        }
        'Probe' {
            $ComposeOutput | & docker compose -f - --profile probe run --rm probe
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
}

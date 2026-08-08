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

function Test-BackingTreeSetsOverlap {
    param(
        [Parameter(Mandatory = $true)][string[]]$Left,
        [Parameter(Mandatory = $true)][string[]]$Right
    )

    foreach ($LeftPath in $Left) {
        foreach ($RightPath in $Right) {
            if (Test-PathsOverlap -Left $LeftPath -Right $RightPath) {
                return $true
            }
        }
    }
    return $false
}

function Get-ForgePathSnapshot {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not ('OimsForgePathIdentity' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Globalization;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using Microsoft.Win32.SafeHandles;

public sealed class OimsForgePathSnapshot : IDisposable
{
    public string Identity { get; private set; }
    public string BackingIdentity { get; private set; }
    public string BackingTreePath { get; private set; }
    public string[] BackingTreePaths { get; private set; }
    public string CanonicalPath { get; private set; }
    public string BoundPath { get; private set; }
    private SafeFileHandle WindowsHandle;
    private int LinuxDescriptor = -1;

    internal OimsForgePathSnapshot(
        string identity,
        string backingIdentity,
        string backingTreePath,
        string[] backingTreePaths,
        string canonicalPath,
        string boundPath,
        SafeFileHandle windowsHandle)
    {
        Identity = identity;
        BackingIdentity = backingIdentity;
        BackingTreePath = backingTreePath;
        BackingTreePaths = backingTreePaths;
        CanonicalPath = canonicalPath;
        BoundPath = boundPath;
        WindowsHandle = windowsHandle;
    }

    internal OimsForgePathSnapshot(
        string identity,
        string backingIdentity,
        string backingTreePath,
        string[] backingTreePaths,
        string canonicalPath,
        string boundPath,
        int linuxDescriptor)
    {
        Identity = identity;
        BackingIdentity = backingIdentity;
        BackingTreePath = backingTreePath;
        BackingTreePaths = backingTreePaths;
        CanonicalPath = canonicalPath;
        BoundPath = boundPath;
        LinuxDescriptor = linuxDescriptor;
    }

    [DllImport("libc", EntryPoint = "close", SetLastError = true)]
    private static extern int LinuxClose(int fileDescriptor);

    public void Dispose()
    {
        if (WindowsHandle != null)
        {
            WindowsHandle.Dispose();
            WindowsHandle = null;
        }
        if (LinuxDescriptor >= 0)
        {
            int descriptor = LinuxDescriptor;
            LinuxDescriptor = -1;
            if (LinuxClose(descriptor) != 0)
                throw new Win32Exception(Marshal.GetLastWin32Error());
        }
    }
}

public static class OimsForgePathIdentity
{
    private const uint FileShareRead = 0x00000001;
    private const uint FileShareWrite = 0x00000002;
    private const uint OpenExisting = 3;
    private const uint FileFlagBackupSemantics = 0x02000000;
    private const int LinuxOpenPath = 0x00200000;
    private const int LinuxOpenCloseOnExec = 0x00080000;
    private const int AtEmptyPath = 0x00001000;
    private const uint StatxMode = 0x00000002;
    private const uint StatxIno = 0x00000100;
    private const uint StatxMountId = 0x00001000;
    private const int MaximumMountInfoLines = 65536;
    private const int MaximumMountInfoLineLength = 1048576;
    private const int MaximumBackingTreePaths = 1024;
    private const int MaximumMountParentTraversals = 131072;

    [StructLayout(LayoutKind.Sequential)]
    private struct ByHandleFileInformation
    {
        public uint FileAttributes;
        public System.Runtime.InteropServices.ComTypes.FILETIME CreationTime;
        public System.Runtime.InteropServices.ComTypes.FILETIME LastAccessTime;
        public System.Runtime.InteropServices.ComTypes.FILETIME LastWriteTime;
        public uint VolumeSerialNumber;
        public uint FileSizeHigh;
        public uint FileSizeLow;
        public uint NumberOfLinks;
        public uint FileIndexHigh;
        public uint FileIndexLow;
    }

    [StructLayout(LayoutKind.Explicit, Size = 256)]
    private struct StatxBuffer
    {
        [FieldOffset(0)] public uint Mask;
        [FieldOffset(28)] public ushort Mode;
        [FieldOffset(32)] public ulong Inode;
        [FieldOffset(136)] public uint DeviceMajor;
        [FieldOffset(140)] public uint DeviceMinor;
        [FieldOffset(144)] public ulong MountId;
    }

    private sealed class LinuxMountRecord
    {
        public ulong MountId;
        public ulong ParentId;
        public uint DeviceMajor;
        public uint DeviceMinor;
        public string Root;
        public string MountPoint;
    }

    private sealed class LinuxBackingTree
    {
        public string DirectPath;
        public string[] Paths;
    }

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern SafeFileHandle CreateFile(
        string fileName,
        uint desiredAccess,
        uint shareMode,
        IntPtr securityAttributes,
        uint creationDisposition,
        uint flagsAndAttributes,
        IntPtr templateFile
    );

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetFileInformationByHandle(
        SafeFileHandle handle,
        out ByHandleFileInformation information
    );

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern uint GetFinalPathNameByHandle(
        SafeFileHandle handle,
        StringBuilder path,
        uint pathLength,
        uint flags
    );

    [DllImport("libc", EntryPoint = "open", SetLastError = true)]
    private static extern int LinuxOpen(string path, int flags);

    [DllImport("libc", EntryPoint = "readlink", SetLastError = true)]
    private static extern IntPtr LinuxReadLink(string path, byte[] buffer, UIntPtr bufferSize);

    [DllImport("libc", EntryPoint = "statx", SetLastError = true)]
    private static extern int Statx(
        int directoryFileDescriptor,
        string path,
        int flags,
        uint mask,
        out StatxBuffer buffer
    );

    private static string DecodeMountInfoPath(string value)
    {
        return value
            .Replace("\\040", " ")
            .Replace("\\011", "\t")
            .Replace("\\012", "\n")
            .Replace("\\134", "\\");
    }

    private static bool IsContainedPath(string root, string candidate, bool strict)
    {
        string relative = Path.GetRelativePath(root, candidate);
        if (
            Path.IsPathRooted(relative) ||
            relative == ".." ||
            relative.StartsWith("../", StringComparison.Ordinal)
        )
            return false;
        return !strict || relative != ".";
    }

    private static string LinuxBackingCoordinate(
        uint deviceMajor,
        uint deviceMinor,
        string backingPath
    )
    {
        string deviceRoot = String.Format(
            CultureInfo.InvariantCulture,
            "/oims-forge-backing/linux-{0:x8}-{1:x8}",
            deviceMajor,
            deviceMinor
        );
        string normalized = Path.GetFullPath(backingPath);
        return normalized == "/" ? deviceRoot : deviceRoot + normalized;
    }

    private static bool IsMountDescendant(
        LinuxMountRecord candidate,
        ulong ancestorId,
        Dictionary<ulong, LinuxMountRecord> records,
        Dictionary<ulong, bool> ancestryCache,
        ref int remainingTraversals
    )
    {
        HashSet<ulong> observed = new HashSet<ulong>();
        List<ulong> traversed = new List<ulong>();
        LinuxMountRecord current = candidate;
        bool result;
        while (true)
        {
            if (ancestryCache.TryGetValue(current.MountId, out result))
                break;
            if (!observed.Add(current.MountId))
                throw new InvalidOperationException("Host mount topology contains a parent cycle.");
            remainingTraversals -= 1;
            if (remainingTraversals < 0)
                throw new InvalidOperationException(
                    "Host mount parent traversal exceeds the supported bound."
                );
            traversed.Add(current.MountId);
            if (current.ParentId == ancestorId)
            {
                result = true;
                break;
            }
            if (!records.TryGetValue(current.ParentId, out current))
            {
                result = false;
                break;
            }
        }
        foreach (ulong mountId in traversed)
            ancestryCache[mountId] = result;
        return result;
    }

    private static LinuxBackingTree LinuxBackingTreePaths(
        StatxBuffer buffer,
        string canonicalPath
    )
    {
        List<LinuxMountRecord> orderedRecords = new List<LinuxMountRecord>();
        Dictionary<ulong, LinuxMountRecord> records =
            new Dictionary<ulong, LinuxMountRecord>();
        int lineCount = 0;
        foreach (string line in File.ReadLines(
            "/proc/self/mountinfo",
            new UTF8Encoding(false, true)
        ))
        {
            lineCount += 1;
            if (lineCount > MaximumMountInfoLines || line.Length > MaximumMountInfoLineLength)
                throw new InvalidOperationException("Host mount topology exceeds the supported bound.");
            int separator = line.IndexOf(" - ", StringComparison.Ordinal);
            string[] fields = (separator < 0 ? line : line.Substring(0, separator)).Split(
                new[] { ' ' },
                StringSplitOptions.RemoveEmptyEntries
            );
            ulong mountId;
            ulong parentId;
            string[] device = fields.Length >= 3 ? fields[2].Split(':') : new string[0];
            uint deviceMajor;
            uint deviceMinor;
            if (
                separator < 0 ||
                fields.Length < 6 ||
                !UInt64.TryParse(
                    fields[0],
                    NumberStyles.None,
                    CultureInfo.InvariantCulture,
                    out mountId
                ) ||
                !UInt64.TryParse(
                    fields[1],
                    NumberStyles.None,
                    CultureInfo.InvariantCulture,
                    out parentId
                ) ||
                device.Length != 2 ||
                !UInt32.TryParse(
                    device[0],
                    NumberStyles.None,
                    CultureInfo.InvariantCulture,
                    out deviceMajor
                ) ||
                !UInt32.TryParse(
                    device[1],
                    NumberStyles.None,
                    CultureInfo.InvariantCulture,
                    out deviceMinor
                )
            )
                throw new InvalidOperationException("Host mount topology is malformed.");
            LinuxMountRecord record = new LinuxMountRecord
            {
                MountId = mountId,
                ParentId = parentId,
                DeviceMajor = deviceMajor,
                DeviceMinor = deviceMinor,
                Root = DecodeMountInfoPath(fields[3]),
                MountPoint = DecodeMountInfoPath(fields[4]),
            };
            if (
                !Path.IsPathRooted(record.Root) ||
                !Path.IsPathRooted(record.MountPoint) ||
                records.ContainsKey(record.MountId)
            )
                throw new InvalidOperationException("Host mount identity is ambiguous.");
            records.Add(record.MountId, record);
            orderedRecords.Add(record);
        }
        LinuxMountRecord directRecord;
        if (
            !records.TryGetValue(buffer.MountId, out directRecord) ||
            directRecord.DeviceMajor != buffer.DeviceMajor ||
            directRecord.DeviceMinor != buffer.DeviceMinor
        )
            throw new InvalidOperationException("Host mount backing root cannot be verified.");
        if (!IsContainedPath(directRecord.MountPoint, canonicalPath, false))
            throw new InvalidOperationException("Host path is outside its authenticated mountpoint.");
        string relative = Path.GetRelativePath(directRecord.MountPoint, canonicalPath);
        string backingPath = Path.GetFullPath(
            relative == "." ? directRecord.Root : Path.Combine(directRecord.Root, relative)
        );
        string directPath = LinuxBackingCoordinate(
            buffer.DeviceMajor,
            buffer.DeviceMinor,
            backingPath
        );
        HashSet<string> paths = new HashSet<string>(StringComparer.Ordinal) { directPath };
        Dictionary<ulong, bool> ancestryCache = new Dictionary<ulong, bool>();
        int remainingTraversals = MaximumMountParentTraversals;
        foreach (LinuxMountRecord record in orderedRecords)
        {
            if (
                record.MountId == directRecord.MountId ||
                !IsContainedPath(canonicalPath, record.MountPoint, true) ||
                !IsMountDescendant(
                    record,
                    directRecord.MountId,
                    records,
                    ancestryCache,
                    ref remainingTraversals
                )
            )
                continue;
            paths.Add(LinuxBackingCoordinate(record.DeviceMajor, record.DeviceMinor, record.Root));
            if (paths.Count > MaximumBackingTreePaths)
                throw new InvalidOperationException(
                    "Host recursive mount topology exceeds the supported bound."
                );
        }
        string[] visiblePaths = new string[paths.Count];
        paths.CopyTo(visiblePaths);
        Array.Sort(visiblePaths, StringComparer.Ordinal);
        return new LinuxBackingTree { DirectPath = directPath, Paths = visiblePaths };
    }

    public static OimsForgePathSnapshot Capture(string path)
    {
        if (RuntimeInformation.IsOSPlatform(OSPlatform.Windows))
        {
            SafeFileHandle handle = CreateFile(
                path,
                0,
                FileShareRead | FileShareWrite,
                IntPtr.Zero,
                OpenExisting,
                FileFlagBackupSemantics,
                IntPtr.Zero);
            if (handle.IsInvalid)
            {
                handle.Dispose();
                throw new Win32Exception(Marshal.GetLastWin32Error());
            }
            try
            {
                ByHandleFileInformation information;
                if (!GetFileInformationByHandle(handle, out information))
                    throw new Win32Exception(Marshal.GetLastWin32Error());
                ulong index = ((ulong)information.FileIndexHigh << 32) | information.FileIndexLow;
                StringBuilder canonicalPath = new StringBuilder(32768);
                uint canonicalLength = GetFinalPathNameByHandle(
                    handle,
                    canonicalPath,
                    (uint)canonicalPath.Capacity,
                    0
                );
                if (canonicalLength == 0 || canonicalLength >= (uint)canonicalPath.Capacity)
                    throw new Win32Exception(Marshal.GetLastWin32Error());
                string identity = String.Format(
                    "windows:{0:x8}:{1:x16}",
                    information.VolumeSerialNumber,
                    index
                );
                return new OimsForgePathSnapshot(
                    identity,
                    identity,
                    canonicalPath.ToString(),
                    new[] { canonicalPath.ToString() },
                    canonicalPath.ToString(),
                    path,
                    handle
                );
            }
            catch
            {
                handle.Dispose();
                throw;
            }
        }
        if (RuntimeInformation.IsOSPlatform(OSPlatform.Linux))
        {
            int fileDescriptor = LinuxOpen(path, LinuxOpenPath | LinuxOpenCloseOnExec);
            if (fileDescriptor < 0)
                throw new Win32Exception(Marshal.GetLastWin32Error());
            try
            {
                StatxBuffer buffer;
                uint requested = StatxMode | StatxIno | StatxMountId;
                int result = Statx(fileDescriptor, "", AtEmptyPath, requested, out buffer);
                if (result != 0)
                    throw new Win32Exception(Marshal.GetLastWin32Error());
                if ((buffer.Mask & requested) != requested)
                    throw new InvalidOperationException(
                        "statx did not return mode, inode, and mount identities."
                    );
                byte[] canonicalBuffer = new byte[32768];
                IntPtr readLength = LinuxReadLink(
                    "/proc/self/fd/" + fileDescriptor,
                    canonicalBuffer,
                    (UIntPtr)(uint)canonicalBuffer.Length
                );
                long canonicalLength = readLength.ToInt64();
                if (canonicalLength <= 0 || canonicalLength >= canonicalBuffer.Length)
                    throw new Win32Exception(Marshal.GetLastWin32Error());
                string canonicalPath = Encoding.UTF8.GetString(
                    canonicalBuffer,
                    0,
                    (int)canonicalLength
                );
                if (canonicalPath.EndsWith(" (deleted)", StringComparison.Ordinal))
                    throw new InvalidOperationException("Host mount object was unlinked.");
                string identity = String.Format(
                    "linux:{0:x4}:{1:x8}:{2:x8}:{3:x16}:{4:x16}",
                    buffer.Mode,
                    buffer.DeviceMajor,
                    buffer.DeviceMinor,
                    buffer.Inode,
                    buffer.MountId
                );
                string backingIdentity = String.Format(
                    "linux:{0:x4}:{1:x8}:{2:x8}:{3:x16}",
                    buffer.Mode,
                    buffer.DeviceMajor,
                    buffer.DeviceMinor,
                    buffer.Inode
                );
                string boundPath = String.Format(
                    "/proc/{0}/fd/{1}",
                    Environment.ProcessId,
                    fileDescriptor
                );
                LinuxBackingTree backingTree = LinuxBackingTreePaths(buffer, canonicalPath);
                return new OimsForgePathSnapshot(
                    identity,
                    backingIdentity,
                    backingTree.DirectPath,
                    backingTree.Paths,
                    canonicalPath,
                    boundPath,
                    fileDescriptor
                );
            }
            catch
            {
                new OimsForgePathSnapshot(
                    "", "", "", new string[0], "", "", fileDescriptor
                ).Dispose();
                throw;
            }
        }
        throw new PlatformNotSupportedException("Model Forge host identity requires Windows or Linux.");
    }
}
'@ | Out-Null
    }
    return [OimsForgePathIdentity]::Capture($Path)
}

function Assert-ForgeHostMountIdentity {
    param(
        [Parameter(Mandatory = $true)][hashtable]$ExpectedPaths,
        [Parameter(Mandatory = $true)][hashtable]$ExpectedSnapshots
    )

    $CurrentCanonicalPaths = @{}
    $CurrentBackingTreePaths = @{}
    $BoundPaths = @{}
    foreach ($Name in $ExpectedPaths.Keys) {
        $ExpectedPath = [string]$ExpectedPaths[$Name]
        $ExpectedSnapshot = $ExpectedSnapshots[$Name]
        $CurrentPath = (Resolve-Path -LiteralPath $ExpectedPath).Path
        $CurrentSnapshot = $null
        try {
            $CurrentSnapshot = Get-ForgePathSnapshot $CurrentPath
            $BackingTreeDifference = @(
                Compare-Object `
                    -ReferenceObject @($ExpectedSnapshot.BackingTreePaths) `
                    -DifferenceObject @($CurrentSnapshot.BackingTreePaths) `
                    -CaseSensitive
            )
            if (
                $CurrentPath -cne $ExpectedPath -or
                [string]$CurrentSnapshot.Identity -cne [string]$ExpectedSnapshot.Identity -or
                [string]$CurrentSnapshot.BackingTreePath -cne `
                    [string]$ExpectedSnapshot.BackingTreePath -or
                $BackingTreeDifference.Count -ne 0 -or
                [string]$CurrentSnapshot.CanonicalPath -cne [string]$ExpectedSnapshot.CanonicalPath
            ) {
                throw "Model Forge host mount identity changed before container launch: $Name"
            }
            $CurrentCanonicalPaths[$Name] = [string]$CurrentSnapshot.CanonicalPath
            $CurrentBackingTreePaths[$Name] = @($CurrentSnapshot.BackingTreePaths)
            $BoundPaths[$Name] = [string]$ExpectedSnapshot.BoundPath
        }
        finally {
            if ($null -ne $CurrentSnapshot) {
                $CurrentSnapshot.Dispose()
            }
        }
    }
    foreach ($ProtectedName in @('Plan', 'BaseModel', 'Dataset')) {
        if (
            [string]$ExpectedSnapshots['Output'].BackingIdentity -ceq
            [string]$ExpectedSnapshots[$ProtectedName].BackingIdentity
        ) {
            throw 'OutputDir must not share a backing filesystem object with a protected input.'
        }
        if (
            Test-BackingTreeSetsOverlap `
                -Left @($CurrentBackingTreePaths['Output']) `
                -Right @($CurrentBackingTreePaths[$ProtectedName])
        ) {
            throw 'OutputDir backing tree must remain disjoint from protected inputs.'
        }
        if (
            Test-PathsOverlap `
                -Left $CurrentCanonicalPaths['Output'] `
                -Right $CurrentCanonicalPaths[$ProtectedName]
        ) {
            throw 'OutputDir must remain disjoint from Plan, BaseModelDir, and DatasetDir.'
        }
    }
    return $BoundPaths
}

function ConvertTo-ForgeByteCount {
    param([AllowNull()][object]$Value)

    if ($null -eq $Value) {
        return $null
    }
    $Text = ([string]$Value).ToLowerInvariant()
    if ($Text -notmatch '^(?<Amount>[0-9]+)(?<Unit>b|k|kb|kib|m|mb|mib|g|gb|gib|t|tb|tib)?$') {
        return $null
    }
    $Multipliers = @{
        '' = [System.Numerics.BigInteger]1
        'b' = [System.Numerics.BigInteger]1
        'k' = [System.Numerics.BigInteger]1024
        'kb' = [System.Numerics.BigInteger]1024
        'kib' = [System.Numerics.BigInteger]1024
        'm' = [System.Numerics.BigInteger]1048576
        'mb' = [System.Numerics.BigInteger]1048576
        'mib' = [System.Numerics.BigInteger]1048576
        'g' = [System.Numerics.BigInteger]1073741824
        'gb' = [System.Numerics.BigInteger]1073741824
        'gib' = [System.Numerics.BigInteger]1073741824
        't' = [System.Numerics.BigInteger]1099511627776
        'tb' = [System.Numerics.BigInteger]1099511627776
        'tib' = [System.Numerics.BigInteger]1099511627776
    }
    $Unit = [string]$Matches.Unit
    $Amount = [System.Numerics.BigInteger]::Parse(
        [string]$Matches.Amount,
        [System.Globalization.CultureInfo]::InvariantCulture
    )
    return ($Amount * $Multipliers[$Unit]).ToString(
        [System.Globalization.CultureInfo]::InvariantCulture
    )
}

function Test-ForgeTmpfsPolicy {
    param([AllowNull()][object]$Value)

    $Entries = @($Value)
    if ($Entries.Count -ne 1) {
        return $false
    }
    $Parts = ([string]$Entries[0]).Split(':', 2)
    if ($Parts.Count -ne 2 -or $Parts[0] -cne '/tmp') {
        return $false
    }
    $Options = @{}
    foreach ($Option in $Parts[1].Split(',')) {
        $Assignment = $Option.Split('=', 2)
        if (
            $Assignment.Count -ne 2 -or
            $Options.ContainsKey($Assignment[0])
        ) {
            return $false
        }
        $Options[$Assignment[0]] = $Assignment[1]
    }
    return (
        $Options.Count -eq 2 -and
        (@(Compare-Object @('mode', 'size') @($Options.Keys) -CaseSensitive)).Count -eq 0 -and
        (ConvertTo-ForgeByteCount $Options['size']) -eq '1073741824' -and
        [string]$Options['mode'] -ceq '1777'
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
    $DockerStartInfo.RedirectStandardOutput = $true
    foreach ($Argument in @(
        'build',
        '--quiet',
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
            try {
                $GitProcess.Kill($true)
            }
            catch [System.InvalidOperationException] {
                # Git exited between the stream failure and termination request.
            }
        }
        finally {
            $DockerProcess.StandardInput.Close()
        }
        $GitProcess.WaitForExit()
        $ImageId = $DockerProcess.StandardOutput.ReadToEnd().Trim()
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
        if ($ImageId -notmatch '^sha256:[0-9a-f]{64}$') {
            throw 'Docker did not return an immutable Model Forge image ID.'
        }
        return $ImageId
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

function Invoke-ForgeDockerRun {
    param(
        [Parameter(Mandatory = $true)][object]$Service,
        [Parameter(Mandatory = $true)][string[]]$Command,
        [Parameter(Mandatory = $true)][string]$ModeName,
        [switch]$EnableGpu
    )

    $DockerArguments = [System.Collections.Generic.List[string]]::new()
    $DockerArguments.Add('run')
    foreach ($Argument in @('--rm', '--pull', [string]$Service.pull_policy)) {
        $DockerArguments.Add($Argument)
    }
    if ([bool]$Service.read_only) {
        $DockerArguments.Add('--read-only')
    }
    $DockerArguments.Add('--user')
    $DockerArguments.Add([string]$Service.user)
    $DockerArguments.Add('--network')
    $DockerArguments.Add([string]$Service.network_mode)
    $DockerArguments.Add('--pids-limit')
    $DockerArguments.Add([string]$Service.pids_limit)
    $DockerArguments.Add('--memory')
    $DockerArguments.Add([string]$Service.mem_limit)
    $DockerArguments.Add('--memory-swap')
    $DockerArguments.Add([string]$Service.memswap_limit)
    $DockerArguments.Add('--shm-size')
    $DockerArguments.Add([string]$Service.shm_size)
    foreach ($Capability in @($Service.cap_drop)) {
        $DockerArguments.Add('--cap-drop')
        $DockerArguments.Add([string]$Capability)
    }
    foreach ($SecurityOption in @($Service.security_opt)) {
        $DockerArguments.Add('--security-opt')
        $DockerArguments.Add([string]$SecurityOption)
    }
    foreach ($Tmpfs in @($Service.tmpfs)) {
        $DockerArguments.Add('--tmpfs')
        $DockerArguments.Add([string]$Tmpfs)
    }
    foreach ($EnvironmentProperty in @(
        $Service.environment.PSObject.Properties | Sort-Object Name
    )) {
        $DockerArguments.Add('--env')
        $DockerArguments.Add(
            "{0}={1}" -f $EnvironmentProperty.Name, [string]$EnvironmentProperty.Value
        )
    }
    foreach ($Volume in @($Service.volumes)) {
        $Source = [string]$Volume.source
        if (
            $Source.Contains(',') -or
            $Source.Contains('"') -or
            $Source.Contains("`r") -or
            $Source.Contains("`n") -or
            $Source.Contains([char]0)
        ) {
            throw 'Model Forge bind source cannot be represented as an exact Docker --mount argument.'
        }
        $Mount = "type=bind,src=$Source,dst=$([string]$Volume.target),bind-recursive=disabled"
        $ReadOnlyProperty = $Volume.PSObject.Properties['read_only']
        if ($null -ne $ReadOnlyProperty -and [bool]$ReadOnlyProperty.Value) {
            $Mount += ',readonly'
        }
        $DockerArguments.Add('--mount')
        $DockerArguments.Add($Mount)
    }
    if ($EnableGpu) {
        $Reservations = @($Service.deploy.resources.reservations.devices)
        $Driver = [string]$Reservations[0].driver
        $DeviceIds = @($Reservations[0].device_ids)
        $DockerArguments.Add('--gpus')
        $DockerArguments.Add("driver=$Driver,device=$($DeviceIds -join ',')")
    }
    $Entrypoint = @($Service.entrypoint)
    $DockerArguments.Add('--entrypoint')
    $DockerArguments.Add([string]$Entrypoint[0])
    $DockerArguments.Add([string]$Service.image)
    for ($Index = 1; $Index -lt $Entrypoint.Count; $Index += 1) {
        $DockerArguments.Add([string]$Entrypoint[$Index])
    }
    foreach ($Argument in $Command) {
        $DockerArguments.Add($Argument)
    }

    & docker @DockerArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Model Forge $ModeName failed with exit code $LASTEXITCODE."
    }
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Docker Desktop / docker CLI is required.'
}

if ($BaseImage -notmatch '^[a-z0-9][a-z0-9._:/-]*@sha256:[0-9a-f]{64}$') {
    throw 'BaseImage must be pinned as image@sha256:<64 lowercase hex characters>.'
}
$ExpectedMemoryBytes = ConvertTo-ForgeByteCount $MemoryLimit
if ($null -eq $ExpectedMemoryBytes -or $ExpectedMemoryBytes -eq '0') {
    throw 'MemoryLimit must be a positive integral Docker byte size.'
}
$ExpectedSharedMemoryBytes = ConvertTo-ForgeByteCount '8gb'

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
if ($ResolvedWorkTree -cne $RepositoryRoot) {
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
$ExpectedHostPaths = @{
    'Plan' = $PlanPath
    'BaseModel' = $BaseModelPath
    'Dataset' = $DatasetPath
    'Output' = $OutputPath
}
$ExpectedHostSnapshots = @{}
foreach ($Name in $ExpectedHostPaths.Keys) {
    $ExpectedHostSnapshots[$Name] = Get-ForgePathSnapshot $ExpectedHostPaths[$Name]
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
    if (@(Compare-Object $ExpectedServices $ObservedServices -CaseSensitive).Count -ne 0) {
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
    $ExpectedMountTargets = @($ExpectedMounts.Keys)
    foreach ($ServiceName in $ExpectedServices) {
        $Service = $ResolvedCompose.services.$ServiceName
        $ExpectedServiceProperties = @(
            'cap_drop',
            'command',
            'entrypoint',
            'environment',
            'image',
            'mem_limit',
            'memswap_limit',
            'network_mode',
            'pids_limit',
            'pull_policy',
            'read_only',
            'security_opt',
            'shm_size',
            'tmpfs',
            'user',
            'volumes'
        )
        if ($ServiceName -eq 'probe') {
            $ExpectedServiceProperties += @('deploy', 'profiles')
        }
        $ObservedServiceProperties = @($Service.PSObject.Properties.Name)
        if (@(Compare-Object $ExpectedServiceProperties $ObservedServiceProperties -CaseSensitive).Count -ne 0) {
            throw "Model Forge Compose service $ServiceName has an unexpected policy field."
        }
        $BuildProperty = $Service.PSObject.Properties['build']
        if (
            $null -ne $BuildProperty -or
            [string]$Service.image -cne $ForgeImage -or
            [string]$Service.pull_policy -cne 'never' -or
            [string]$Service.user -cne '65532:65532' -or
            [string]$Service.network_mode -cne 'none' -or
            -not [bool]$Service.read_only -or
            (@($Service.cap_drop) -join ',') -cne 'ALL' -or
            (@($Service.security_opt) -join ',') -cne 'no-new-privileges:true' -or
            [int64]$Service.pids_limit -ne 512 -or
            (ConvertTo-ForgeByteCount $Service.mem_limit) -ne $ExpectedMemoryBytes -or
            (ConvertTo-ForgeByteCount $Service.memswap_limit) -ne $ExpectedMemoryBytes -or
            (ConvertTo-ForgeByteCount $Service.shm_size) -ne $ExpectedSharedMemoryBytes -or
            -not (Test-ForgeTmpfsPolicy $Service.tmpfs)
        ) {
            throw "Model Forge Compose service $ServiceName violates the pre-start sandbox policy."
        }
        if ($ServiceName -eq 'probe') {
            if ((@($Service.profiles) -join ',') -cne 'probe') {
                throw 'Model Forge Compose probe has an unexpected profile.'
            }
            if (
                (@(Compare-Object @('resources') @($Service.deploy.PSObject.Properties.Name) -CaseSensitive)).Count -ne 0 -or
                (@(Compare-Object @('reservations') @($Service.deploy.resources.PSObject.Properties.Name) -CaseSensitive)).Count -ne 0 -or
                (@(Compare-Object @('devices') @($Service.deploy.resources.reservations.PSObject.Properties.Name) -CaseSensitive)).Count -ne 0
            ) {
                throw 'Model Forge Compose probe has an unexpected resource reservation.'
            }
            $DeviceReservations = @($Service.deploy.resources.reservations.devices)
            if ($DeviceReservations.Count -ne 1) {
                throw 'Model Forge Compose probe must expose exactly one GPU reservation.'
            }
            $Device = $DeviceReservations[0]
            if (
                (@(Compare-Object @('capabilities', 'device_ids', 'driver') @($Device.PSObject.Properties.Name) -CaseSensitive)).Count -ne 0 -or
                [string]$Device.driver -cne 'nvidia' -or
                (@($Device.device_ids) -join ',') -cne [string]$GpuDeviceId -or
                (@($Device.capabilities) -join ',') -cne 'gpu'
            ) {
                throw 'Model Forge Compose probe has an unexpected GPU reservation.'
            }
        }
        if ((@($Service.entrypoint) -join "`0") -cne ($ExpectedEntrypoint -join "`0")) {
            throw "Model Forge Compose service $ServiceName has an unexpected entrypoint."
        }
        if ((@($Service.command) -join "`0") -cne (@($ExpectedCommands[$ServiceName]) -join "`0")) {
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
        if (@(Compare-Object @($ExpectedEnvironment.Keys) $ObservedEnvironmentNames -CaseSensitive).Count -ne 0) {
            throw "Model Forge Compose service $ServiceName has an unexpected environment variable."
        }
        foreach ($Name in $ExpectedEnvironment.Keys) {
            if ([string]$Service.environment.$Name -cne [string]$ExpectedEnvironment[$Name]) {
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
                [string]$Volume.type -cne 'bind' -or
                -not ($ExpectedMountTargets -ccontains $Target) -or
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
                [string]$Volume.source -cne [string]$ExpectedMount.Source -or
                $ObservedReadOnly -ne [bool]$ExpectedMount.ReadOnly
            ) {
                throw "Model Forge Compose service $ServiceName has an unexpected bind mount source or mode."
            }
        }
    }

    $ForgeImageId = Invoke-ForgeImageBuild `
        -RepositoryRoot $RepositoryRoot `
        -SourceCommit $SourceCommit `
        -SourceTree $SourceTree `
        -BaseImage $BaseImage `
        -ForgeImage $ForgeImage
    foreach ($ServiceName in $ExpectedServices) {
        $ResolvedCompose.services.$ServiceName.image = $ForgeImageId
    }
    $BoundHostPaths = Assert-ForgeHostMountIdentity `
        -ExpectedPaths $ExpectedHostPaths `
        -ExpectedSnapshots $ExpectedHostSnapshots
    $BoundMountSources = @{
        '/forge/plan.json' = $BoundHostPaths['Plan']
        '/forge/output' = $BoundHostPaths['Output']
        '/forge/inputs/base' = $BoundHostPaths['BaseModel']
        '/forge/inputs/dataset' = $BoundHostPaths['Dataset']
    }
    foreach ($ServiceName in $ExpectedServices) {
        foreach ($Volume in @($ResolvedCompose.services.$ServiceName.volumes)) {
            $Volume.source = $BoundMountSources[[string]$Volume.target]
        }
    }
    $SelectedServiceName = $Mode.ToLowerInvariant()
    if ($Mode -eq 'Validate') {
        $SelectedServiceName = 'simulate'
    }
    $SelectedService = $ResolvedCompose.services.$SelectedServiceName
    $SelectedCommand = @($SelectedService.command)
    switch ($Mode) {
        'Validate' {
            $SelectedCommand = @('forge', 'validate', '--plan', '/forge/plan.json')
        }
    }
    Invoke-ForgeDockerRun `
        -Service $SelectedService `
        -Command $SelectedCommand `
        -ModeName $Mode `
        -EnableGpu:($Mode -eq 'Probe')
}
finally {
    foreach ($Name in $EnvironmentNames) {
        [Environment]::SetEnvironmentVariable($Name, $OriginalEnvironment[$Name], 'Process')
    }
    foreach ($Snapshot in $ExpectedHostSnapshots.Values) {
        $Snapshot.Dispose()
    }
}

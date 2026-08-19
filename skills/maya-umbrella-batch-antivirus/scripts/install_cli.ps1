#requires -Version 5.1

[CmdletBinding(PositionalBinding = $false)]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$')]
    [string]$Version
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Assert-SafeDirectory {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }

    $item = Get-Item -LiteralPath $Path -Force
    if (-not $item.PSIsContainer) {
        throw "Expected a directory but found another filesystem object: $Path"
    }
    if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Refusing an install path that is a symlink, junction, or reparse point: $Path"
    }
}

function Assert-InstallTargetAbsent {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (Test-Path -LiteralPath $Path) {
        throw "Installation already exists; refusing to overwrite it: $Path"
    }
}

function Assert-SafeZipEntries {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ArchivePath,

        [Parameter(Mandatory = $true)]
        [string]$DestinationPath
    )

    Add-Type -AssemblyName System.IO.Compression.FileSystem | Out-Null
    $destinationRoot = [System.IO.Path]::GetFullPath($DestinationPath).TrimEnd(
        [System.IO.Path]::DirectorySeparatorChar,
        [System.IO.Path]::AltDirectorySeparatorChar
    ) + [System.IO.Path]::DirectorySeparatorChar
    $seenEntries = [System.Collections.Generic.HashSet[string]]::new(
        [System.StringComparer]::OrdinalIgnoreCase
    )
    $archive = [System.IO.Compression.ZipFile]::OpenRead($ArchivePath)
    try {
        if ($archive.Entries.Count -eq 0) {
            throw "Release archive is empty."
        }

        foreach ($entry in $archive.Entries) {
            if ([string]::IsNullOrWhiteSpace($entry.FullName)) {
                throw "Release archive contains an unnamed entry."
            }

            $entryPath = $entry.FullName.Replace(
                [char]'/',
                [System.IO.Path]::DirectorySeparatorChar
            ).Replace(
                [char]'\',
                [System.IO.Path]::DirectorySeparatorChar
            )
            if ([System.IO.Path]::IsPathRooted($entryPath) -or $entryPath.Contains(':')) {
                throw "Release archive contains an absolute or device path: $($entry.FullName)"
            }

            $candidate = [System.IO.Path]::GetFullPath(
                [System.IO.Path]::Combine($destinationRoot, $entryPath)
            )
            if (-not $candidate.StartsWith($destinationRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
                throw "Release archive entry escapes the staging directory: $($entry.FullName)"
            }
            if (-not $seenEntries.Add($candidate)) {
                throw "Release archive contains duplicate paths: $($entry.FullName)"
            }
        }
    }
    finally {
        $archive.Dispose()
    }
}

function Invoke-ValidatedProcess {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,

        [Parameter(Mandatory = $true)]
        [string]$Arguments,

        [int]$TimeoutMilliseconds = 30000
    )

    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $FilePath
    $startInfo.Arguments = $Arguments
    $startInfo.WorkingDirectory = [System.IO.Path]::GetDirectoryName($FilePath)
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true

    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    try {
        if (-not $process.Start()) {
            throw "Unable to start executable validation: $FilePath"
        }
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit($TimeoutMilliseconds)) {
            try {
                $process.Kill()
            }
            catch {
                # Preserve the timeout as the primary failure.
            }
            throw "Executable validation timed out after $TimeoutMilliseconds ms: $Arguments"
        }

        [pscustomobject]@{
            ExitCode = $process.ExitCode
            StdOut = $stdoutTask.GetAwaiter().GetResult()
            StdErr = $stderrTask.GetAwaiter().GetResult()
        }
    }
    finally {
        $process.Dispose()
    }
}

$temporaryRoot = $null
try {
    if ($env:OS -ne "Windows_NT") {
        throw "This installer supports Windows only."
    }
    $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [System.Security.Principal.WindowsPrincipal]::new($identity)
    if ($principal.IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "Run this per-user installer without elevation."
    }
    if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
        throw "LOCALAPPDATA is required."
    }

    $localAppData = [System.IO.Path]::GetFullPath($env:LOCALAPPDATA)
    if (-not [System.IO.Path]::IsPathRooted($localAppData)) {
        throw "LOCALAPPDATA must resolve to an absolute path."
    }

    $productRoot = Join-Path $localAppData "maya_umbrella_scanner"
    $versionsRoot = Join-Path $productRoot "versions"
    $installDirectory = Join-Path $versionsRoot $Version

    Assert-SafeDirectory -Path $localAppData
    Assert-SafeDirectory -Path $productRoot
    Assert-SafeDirectory -Path $versionsRoot
    Assert-InstallTargetAbsent -Path $installDirectory

    [void][System.IO.Directory]::CreateDirectory($productRoot)
    [void][System.IO.Directory]::CreateDirectory($versionsRoot)
    Assert-SafeDirectory -Path $productRoot
    Assert-SafeDirectory -Path $versionsRoot

    $temporaryRoot = Join-Path $productRoot (".install-" + [System.Guid]::NewGuid().ToString("N"))
    if (Test-Path -LiteralPath $temporaryRoot) {
        throw "Unique staging directory unexpectedly already exists: $temporaryRoot"
    }
    [void][System.IO.Directory]::CreateDirectory($temporaryRoot)
    Assert-SafeDirectory -Path $temporaryRoot

    $archiveName = "maya_umbrella_scanner-$Version.zip"
    $checksumName = "SHA256SUMS"
    $releaseBase = "https://github.com/loonghao/maya_umbrella_scanner/releases/download/v$Version"
    $archiveUrl = "$releaseBase/$archiveName"
    $checksumUrl = "$releaseBase/$checksumName"
    $archivePath = Join-Path $temporaryRoot $archiveName
    $checksumPath = Join-Path $temporaryRoot $checksumName
    $stagingDirectory = Join-Path $temporaryRoot "payload"

    # GitHub requires TLS 1.2; Windows PowerShell 5.1 can otherwise inherit an older default.
    [System.Net.ServicePointManager]::SecurityProtocol =
        [System.Net.ServicePointManager]::SecurityProtocol -bor
        [System.Net.SecurityProtocolType]::Tls12

    Invoke-WebRequest -UseBasicParsing -Uri $checksumUrl -OutFile $checksumPath | Out-Null
    Invoke-WebRequest -UseBasicParsing -Uri $archiveUrl -OutFile $archivePath | Out-Null

    if ((Get-Item -LiteralPath $checksumPath).Length -le 0) {
        throw "Downloaded SHA256SUMS is empty."
    }
    if ((Get-Item -LiteralPath $archivePath).Length -le 0) {
        throw "Downloaded release archive is empty."
    }

    $checksumPattern = '^(?<hash>[0-9A-Fa-f]{64})[ \t]+\*?(?<name>' +
        [System.Text.RegularExpressions.Regex]::Escape($archiveName) + ')$'
    $checksumMatches = @()
    foreach ($line in [System.IO.File]::ReadAllLines($checksumPath)) {
        $match = [System.Text.RegularExpressions.Regex]::Match(
            $line,
            $checksumPattern,
            [System.Text.RegularExpressions.RegexOptions]::CultureInvariant
        )
        if ($match.Success) {
            $checksumMatches += $match
        }
    }
    if ($checksumMatches.Count -ne 1) {
        throw "SHA256SUMS must contain exactly one strict entry for $archiveName."
    }

    $expectedHash = $checksumMatches[0].Groups['hash'].Value
    $actualHash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash
    if (-not [string]::Equals($actualHash, $expectedHash, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Release archive SHA-256 does not match SHA256SUMS."
    }

    [void][System.IO.Directory]::CreateDirectory($stagingDirectory)
    Assert-SafeZipEntries -ArchivePath $archivePath -DestinationPath $stagingDirectory
    Expand-Archive -LiteralPath $archivePath -DestinationPath $stagingDirectory

    $extractedEntries = @(Get-ChildItem -LiteralPath $stagingDirectory -Force -Recurse)
    $reparseEntries = @(
        $extractedEntries | Where-Object {
            ($_.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0
        }
    )
    if ($reparseEntries.Count -ne 0) {
        throw "Release archive extracted a symlink, junction, or reparse point."
    }

    $executables = @(
        Get-ChildItem -LiteralPath $stagingDirectory -Filter "maya_umbrella.exe" -File -Force -Recurse
    )
    if ($executables.Count -ne 1) {
        throw "Release archive must contain exactly one maya_umbrella.exe; found $($executables.Count)."
    }
    $executable = $executables[0]

    $versionResult = Invoke-ValidatedProcess -FilePath $executable.FullName -Arguments "--version"
    if ($versionResult.ExitCode -ne 0 -or -not [string]::IsNullOrWhiteSpace($versionResult.StdErr)) {
        throw "maya_umbrella.exe --version failed validation."
    }
    $expectedVersionOutput = "maya-umbrella-scanner $Version"
    if (-not [string]::Equals(
        $versionResult.StdOut.Trim(),
        $expectedVersionOutput,
        [System.StringComparison]::Ordinal
    )) {
        throw "maya_umbrella.exe reported an unexpected version."
    }

    $helpResult = Invoke-ValidatedProcess -FilePath $executable.FullName -Arguments "scan --help"
    if ($helpResult.ExitCode -ne 0 -or -not [string]::IsNullOrWhiteSpace($helpResult.StdErr)) {
        throw "maya_umbrella.exe scan --help failed validation."
    }
    if (
        $helpResult.StdOut -notmatch '(?im)^usage:' -or
        $helpResult.StdOut.IndexOf('--path', [System.StringComparison]::Ordinal) -lt 0 -or
        $helpResult.StdOut.IndexOf('--report', [System.StringComparison]::Ordinal) -lt 0
    ) {
        throw "maya_umbrella.exe does not expose the required scan command contract."
    }

    $cleanHelpResult = Invoke-ValidatedProcess -FilePath $executable.FullName -Arguments "clean --help"
    if ($cleanHelpResult.ExitCode -ne 0 -or -not [string]::IsNullOrWhiteSpace($cleanHelpResult.StdErr)) {
        throw "maya_umbrella.exe clean --help failed validation."
    }
    $requiredCleanArguments = @(
        '--path',
        '--maya-version',
        '--approved-scan-report',
        '--approved-scan-report-sha256',
        '--confirm-clean'
    )
    foreach ($requiredArgument in $requiredCleanArguments) {
        if ($cleanHelpResult.StdOut.IndexOf($requiredArgument, [System.StringComparison]::Ordinal) -lt 0) {
            throw "maya_umbrella.exe does not expose the required clean command contract."
        }
    }

    $stagingRoot = [System.IO.Path]::GetFullPath($stagingDirectory).TrimEnd(
        [System.IO.Path]::DirectorySeparatorChar,
        [System.IO.Path]::AltDirectorySeparatorChar
    ) + [System.IO.Path]::DirectorySeparatorChar
    $executablePath = [System.IO.Path]::GetFullPath($executable.FullName)
    if (-not $executablePath.StartsWith($stagingRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Validated executable escaped the staging directory."
    }
    $relativeExecutable = $executablePath.Substring($stagingRoot.Length)
    $installedExecutable = Join-Path $installDirectory $relativeExecutable

    $resultJson = [ordered]@{
        schema_version = 1
        status = "installed"
        version = $Version
        install_directory = $installDirectory
        executable = $installedExecutable
        source_repository = "loonghao/maya_umbrella_scanner"
        release_tag = "v$Version"
        archive = $archiveName
        sha256 = $actualHash.ToLowerInvariant()
    } | ConvertTo-Json -Compress

    # Re-check immediately before the same-volume atomic, no-clobber rename.
    Assert-SafeDirectory -Path $temporaryRoot
    Assert-SafeDirectory -Path $stagingDirectory
    Assert-SafeDirectory -Path $productRoot
    Assert-SafeDirectory -Path $versionsRoot
    Assert-InstallTargetAbsent -Path $installDirectory
    [System.IO.Directory]::Move($stagingDirectory, $installDirectory)

    [Console]::Out.WriteLine($resultJson)
}
catch {
    [Console]::Error.WriteLine("install_cli: $($_.Exception.Message)")
    exit 1
}
finally {
    if ($null -ne $temporaryRoot -and (Test-Path -LiteralPath $temporaryRoot)) {
        Remove-Item -LiteralPath $temporaryRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

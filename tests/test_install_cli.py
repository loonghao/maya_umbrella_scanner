"""Static security-contract tests for the standalone PowerShell installer."""

# Import built-in modules
from pathlib import Path
import re
import shutil
import subprocess

# Import third-party modules
import pytest


REPOSITORY_ROOT = Path(__file__).parents[1]
INSTALLER = REPOSITORY_ROOT / "skills" / "maya-umbrella-batch-antivirus" / "scripts" / "install_cli.ps1"
SCRIPT = INSTALLER.read_text(encoding="utf-8")


def test_installer_requires_a_strict_explicit_version_and_pins_release_source():
    assert "[Parameter(Mandatory = $true)]" in SCRIPT
    assert "[CmdletBinding(PositionalBinding = $false)]" in SCRIPT
    assert "[ValidatePattern('^(0|[1-9][0-9]*)" in SCRIPT
    assert '"maya_umbrella_scanner-$Version.zip"' in SCRIPT
    assert '"SHA256SUMS"' in SCRIPT
    assert '"https://github.com/loonghao/maya_umbrella_scanner/releases/download/v$Version"' in SCRIPT
    assert "SecurityProtocolType]::Tls12" in SCRIPT
    assert "WindowsBuiltInRole]::Administrator" in SCRIPT
    assert "without elevation" in SCRIPT
    assert "api.github.com" not in SCRIPT
    assert "RepoUrl" not in SCRIPT
    assert "BaseUrl" not in SCRIPT


def test_checksum_is_unique_exact_and_verified_before_extraction():
    assert "Regex]::Escape($archiveName)" in SCRIPT
    assert "$checksumMatches.Count -ne 1" in SCRIPT
    assert "exactly one strict entry for $archiveName" in SCRIPT
    assert "Get-FileHash -LiteralPath $archivePath -Algorithm SHA256" in SCRIPT
    assert "StringComparison]::OrdinalIgnoreCase" in SCRIPT
    assert SCRIPT.index("Get-FileHash") < SCRIPT.index("Expand-Archive")


def test_archive_is_staged_safely_and_install_is_no_clobber():
    assert "[System.Guid]::NewGuid()" in SCRIPT
    assert 'Join-Path $productRoot (".install-"' in SCRIPT
    assert "Assert-SafeZipEntries" in SCRIPT
    assert "ZipFile]::OpenRead" in SCRIPT
    assert "entry escapes the staging directory" in SCRIPT
    assert "FileAttributes]::ReparsePoint" in SCRIPT
    assert SCRIPT.count("Assert-SafeDirectory -Path $temporaryRoot") == 2
    assert "Assert-SafeDirectory -Path $stagingDirectory" in SCRIPT
    assert SCRIPT.count("Assert-InstallTargetAbsent -Path $installDirectory") == 2
    assert "[System.IO.Directory]::Move($stagingDirectory, $installDirectory)" in SCRIPT
    assert "Move-Item" not in SCRIPT


def test_executable_identity_and_cli_contract_are_validated_before_install():
    assert "$executables.Count -ne 1" in SCRIPT
    assert 'Arguments "--version"' in SCRIPT
    assert '$expectedVersionOutput = "maya-umbrella-scanner $Version"' in SCRIPT
    assert 'Arguments "scan --help"' in SCRIPT
    assert 'Arguments "clean --help"' in SCRIPT
    assert "IndexOf('--path'" in SCRIPT
    assert "IndexOf('--report'" in SCRIPT
    assert "'--approved-scan-report-sha256'" in SCRIPT
    assert "'--confirm-clean'" in SCRIPT
    assert "WaitForExit($TimeoutMilliseconds)" in SCRIPT
    assert "$startInfo.WorkingDirectory = [System.IO.Path]::GetDirectoryName($FilePath)" in SCRIPT
    assert SCRIPT.index('Arguments "clean --help"') < SCRIPT.index("Directory]::Move")


def test_machine_output_is_json_and_dynamic_or_python_execution_is_absent():
    assert 'Join-Path $localAppData "maya_umbrella_scanner"' in SCRIPT
    assert 'Join-Path $productRoot "versions"' in SCRIPT
    assert "ConvertTo-Json -Compress" in SCRIPT
    assert "[Console]::Out.WriteLine($resultJson)" in SCRIPT
    assert 'status = "installed"' in SCRIPT
    assert 'source_repository = "loonghao/maya_umbrella_scanner"' in SCRIPT
    assert "[Console]::Error.WriteLine" in SCRIPT
    assert "exit 1" in SCRIPT
    assert SCRIPT.count("Invoke-WebRequest") == SCRIPT.count("Invoke-WebRequest -UseBasicParsing")
    assert SCRIPT.count("Invoke-WebRequest") == SCRIPT.count("| Out-Null") - 1
    assert "Invoke-Expression" not in SCRIPT
    assert not re.search(r"(?im)^\s*(?:python|py|pip|uv|uvx)\b", SCRIPT)


def test_installer_parses_in_available_powershell():
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if shell is None:
        pytest.skip("PowerShell is unavailable")

    installer_literal = str(INSTALLER).replace("'", "''")
    command = (
        "$tokens=$null; $errors=$null; "
        "[void][System.Management.Automation.Language.Parser]::ParseFile("
        f"'{installer_literal}', [ref]$tokens, [ref]$errors); "
        "if ($errors.Count) { $errors | ForEach-Object { [Console]::Error.WriteLine($_) }; exit 1 }"
    )
    completed = subprocess.run(
        [shell, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr

#requires -Version 5.1
<#
Installs or updates CNYRUB_TOM Analytics Tool on a Windows PC.

Run in PowerShell:
  Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
  iwr https://raw.githubusercontent.com/Vloods/cnyrub_tom_analytic_tool/main/scripts/install_windows.ps1 -UseBasicParsing | iex

The script:
  - checks for Python 3.11+ and Git;
  - optionally installs them with winget if available;
  - clones/updates the GitHub repository;
  - installs the package in editable mode;
  - verifies cnyrub and cnyrub-gui entry points.
#>

$ErrorActionPreference = "Stop"

$RepoUrl = "https://github.com/Vloods/cnyrub_tom_analytic_tool.git"
$InstallDir = Join-Path $env:USERPROFILE "Documents\cnyrub_tom_analytic_tool"
$ExportDir = "C:\quik_export"

function Write-Step([string]$Message) {
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Command-Exists([string]$Command) {
    $null -ne (Get-Command $Command -ErrorAction SilentlyContinue)
}

function Ensure-WingetPackage([string]$Command, [string]$PackageId, [string]$Name) {
    if (Command-Exists $Command) {
        return
    }
    if (-not (Command-Exists "winget")) {
        throw "$Name is not installed and winget is not available. Install $Name manually, then rerun this script."
    }
    Write-Step "Installing $Name via winget"
    winget install --id $PackageId --exact --accept-package-agreements --accept-source-agreements
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
    if (-not (Command-Exists $Command)) {
        throw "$Name was installed but '$Command' is still not on PATH. Open a new PowerShell window and rerun this script."
    }
}

Write-Step "Checking prerequisites"
Ensure-WingetPackage "git" "Git.Git" "Git"

if (-not (Command-Exists "py") -and -not (Command-Exists "python")) {
    Ensure-WingetPackage "python" "Python.Python.3.11" "Python 3.11+"
}

$script:PythonExe = $null
$script:PythonPrefixArgs = @()
if (Command-Exists "py") {
    & py -3.11 --version | Out-Host
    if ($LASTEXITCODE -eq 0) {
        $script:PythonExe = "py"
        $script:PythonPrefixArgs = @("-3.11")
    } else {
        & py -3 --version | Out-Host
        if ($LASTEXITCODE -eq 0) {
            $script:PythonExe = "py"
            $script:PythonPrefixArgs = @("-3")
        }
    }
}
if (-not $script:PythonExe -and (Command-Exists "python")) {
    & python --version | Out-Host
    if ($LASTEXITCODE -eq 0) {
        $script:PythonExe = "python"
        $script:PythonPrefixArgs = @()
    }
}
if (-not $script:PythonExe) {
    throw "Python 3.11+ is not available on PATH. Install Python 3.11, then rerun this script."
}

function Invoke-Python([string[]]$PythonArgs) {
    $AllArgs = @()
    $AllArgs += $script:PythonPrefixArgs
    $AllArgs += $PythonArgs
    & $script:PythonExe @AllArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Python command failed: $script:PythonExe $($AllArgs -join ' ')"
    }
}

Write-Step "Preparing folders"
New-Item -ItemType Directory -Force -Path (Split-Path $InstallDir) | Out-Null
New-Item -ItemType Directory -Force -Path $ExportDir | Out-Null

if (Test-Path $InstallDir) {
    Write-Step "Updating repository in $InstallDir"
    Push-Location $InstallDir
    git fetch origin
    git checkout main
    git pull --ff-only origin main
    Pop-Location
} else {
    Write-Step "Cloning repository to $InstallDir"
    git clone $RepoUrl $InstallDir
}

Write-Step "Installing package"
Push-Location $InstallDir
Invoke-Python @("-m", "pip", "install", "--upgrade", "pip")
Invoke-Python @("-m", "pip", "install", "-e", ".")

$ScriptsDirOutput = @(Invoke-Python @("-c", "import sysconfig; print(sysconfig.get_path('scripts'))"))
$ScriptsDir = ($ScriptsDirOutput | Where-Object { $_ -and $_.ToString().Trim() } | Select-Object -Last 1)
if ($ScriptsDir) {
    $ScriptsDir = $ScriptsDir.ToString().Trim()
}
if (-not $ScriptsDir -or -not (Test-Path $ScriptsDir)) {
    Write-Host "Python scripts directory detection output:" -ForegroundColor Yellow
    $ScriptsDirOutput | Out-Host
    throw "Could not locate Python Scripts directory after installation."
}

if ($env:Path -notlike "*$ScriptsDir*") {
    $env:Path = "$ScriptsDir;$env:Path"
}
$UserPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
if ($UserPath -notlike "*$ScriptsDir*") {
    [System.Environment]::SetEnvironmentVariable("Path", "$ScriptsDir;$UserPath", "User")
    Write-Host "Added Python Scripts to user PATH: $ScriptsDir"
}

function Get-InstalledCommandPath([string]$CommandName) {
    $Command = Get-Command $CommandName -ErrorAction SilentlyContinue
    if ($Command) {
        return $Command.Source
    }

    $ExePath = Join-Path $ScriptsDir "$CommandName.exe"
    if (Test-Path $ExePath) {
        return $ExePath
    }

    $ScriptPath = Join-Path $ScriptsDir $CommandName
    if (Test-Path $ScriptPath) {
        return $ScriptPath
    }

    throw "Installed command '$CommandName' was not found. Expected it in: $ScriptsDir"
}

$CnyrubCmd = Get-InstalledCommandPath "cnyrub"
$CnyrubGuiCmd = Get-InstalledCommandPath "cnyrub-gui"

Write-Step "Verifying CLI commands"
& $CnyrubCmd --help | Select-String "detect-liquidity-events" | Out-Host
& $CnyrubCmd quote | Out-Host

Write-Step "Installed successfully"
Write-Host "Project directory: $InstallDir"
Write-Host "QUIK export directory: $ExportDir"
Write-Host "Python Scripts directory: $ScriptsDir"
Write-Host "Run GUI with: $CnyrubGuiCmd"
Write-Host "Run CLI with: $CnyrubCmd quote"
Write-Host "If plain 'cnyrub' is not recognized in the current window, open a new PowerShell window and run: cnyrub quote"
Pop-Location

param(
    [string]$Version = "0.1.4"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [string[]]$Arguments = @()
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($Arguments -join ' ')"
    }
}

Write-Host "Building Matokeo RMS desktop bundle..." -ForegroundColor Cyan
$pythonVersion = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ([version]$pythonVersion -ge [version]"3.14") {
    throw "Desktop builds require Python 3.12 or 3.13 because the native WebView shell dependency does not support Python $pythonVersion yet."
}

Invoke-Checked python @("-m", "pip", "install", "--upgrade", "pip")
Invoke-Checked python @("-m", "pip", "install", "-r", "requirements-desktop.txt")

Invoke-Checked python @("manage.py", "check")
Invoke-Checked python @("-m", "PyInstaller", "--noconfirm", "--clean", ".\packaging\windows\MatokeoRMS.spec")

$iscc = Get-Command iscc -ErrorAction SilentlyContinue
if (-not $iscc) {
    $candidates = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles}\Inno Setup 6\ISCC.exe",
        "${env:LOCALAPPDATA}\Programs\Inno Setup 6\ISCC.exe"
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            $iscc = Get-Item $candidate
            break
        }
    }
}

if ($iscc) {
    Write-Host "Building Windows installer with Inno Setup..." -ForegroundColor Cyan
    $isccPath = $iscc.Source
    if (-not $isccPath) {
        $isccPath = $iscc.FullName
    }
    Invoke-Checked $isccPath @("/DMyAppVersion=$Version", ".\packaging\windows\matokeo-rms.iss")
    Write-Host "Installer output: dist\installer" -ForegroundColor Green
} else {
    Write-Host "Inno Setup was not found. Desktop bundle is ready at dist\MatokeoRMS." -ForegroundColor Yellow
    Write-Host "Install Inno Setup 6 and rerun this script to create a setup installer." -ForegroundColor Yellow
}

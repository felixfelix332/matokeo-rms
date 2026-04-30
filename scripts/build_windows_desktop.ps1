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

function Invoke-Python {
    param(
        [string[]]$Arguments = @()
    )

    Invoke-Checked $PythonCommand ($PythonPrefix + $Arguments)
}

Write-Host "Building Matokeo RMS desktop bundle..." -ForegroundColor Cyan
$PythonCommand = "python"
$PythonPrefix = @()
$pythonVersion = & $PythonCommand -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ([version]$pythonVersion -ge [version]"3.14") {
    $foundSupportedPython = $false
    foreach ($candidate in @("3.12", "3.13")) {
        $candidateVersion = ""
        try {
            $candidateVersion = & py "-$candidate" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
        } catch {
            $candidateVersion = ""
        }
        if ($LASTEXITCODE -eq 0 -and [version]$candidateVersion -lt [version]"3.14") {
            $PythonCommand = "py"
            $PythonPrefix = @("-$candidate")
            $pythonVersion = $candidateVersion
            $foundSupportedPython = $true
            break
        }
    }

    if (-not $foundSupportedPython) {
        throw "Desktop builds require Python 3.12 or 3.13 because the native WebView shell dependency does not support Python $pythonVersion yet."
    }
}

Write-Host "Using Python $pythonVersion for desktop build." -ForegroundColor Cyan
Invoke-Python @("-m", "pip", "install", "--upgrade", "pip")
Invoke-Python @("-m", "pip", "install", "-r", "requirements-desktop.txt")

Invoke-Python @("manage.py", "check")
Invoke-Python @("-m", "PyInstaller", "--noconfirm", "--clean", ".\packaging\windows\MatokeoRMS.spec")

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

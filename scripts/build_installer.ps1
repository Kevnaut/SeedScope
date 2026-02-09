param(
    [string]$Version = "0.1.0"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-Step {
    param(
        [string]$Name,
        [scriptblock]$Command
    )
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed with exit code $LASTEXITCODE"
    }
}

$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$pythonExe = Join-Path $projectRoot ".venv\Scripts\python.exe"
$pipExe = Join-Path $projectRoot ".venv\Scripts\pip.exe"
$specFile = Join-Path $projectRoot "SeedScope.spec"
$issFile = Join-Path $projectRoot "installer\SeedScope.iss"

if (-not (Test-Path $pythonExe)) {
    throw "Missing virtual environment python: $pythonExe"
}
if (-not (Test-Path $pipExe)) {
    throw "Missing virtual environment pip: $pipExe"
}
if (-not (Test-Path $specFile)) {
    throw "Missing PyInstaller spec: $specFile"
}
if (-not (Test-Path $issFile)) {
    throw "Missing Inno Setup script: $issFile"
}

Push-Location $projectRoot
try {
    Invoke-Step "Install runtime dependencies" { & $pipExe install -r requirements.txt }
    Invoke-Step "Install build dependencies" { & $pipExe install -r requirements-dev.txt }

    Invoke-Step "Prepare icon" { & $pythonExe scripts/prepare_icon.py }

    Invoke-Step "Build app with PyInstaller" {
        & $pythonExe -m PyInstaller --noconfirm --clean SeedScope.spec
    }

    $isccPath = $null
    $iscc = Get-Command "iscc.exe" -ErrorAction SilentlyContinue
    if ($iscc) {
        $isccPath = $iscc.Source
    }
    if (-not $isccPath) {
        $commonPaths = @(
            "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
            "C:\Program Files\Inno Setup 6\ISCC.exe"
        )
        foreach ($path in $commonPaths) {
            if (Test-Path $path) {
                $isccPath = $path
                break
            }
        }
    }
    if (-not $isccPath) {
        throw "Inno Setup compiler not found. Install Inno Setup 6 and ensure ISCC.exe is available."
    }

    Invoke-Step "Build installer with Inno Setup" { & $isccPath "/DAppVersion=$Version" $issFile }

    Write-Host "Build complete."
    Write-Host "App: dist\SeedScope\SeedScope.exe"
    Write-Host "Installer: dist\installer\SeedScope-Setup-$Version.exe"
}
finally {
    Pop-Location
}

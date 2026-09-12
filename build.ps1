param(
  [string]$EnvironmentName = "game"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$condaCandidates = @(
  $env:CONDA_EXE,
  (Get-Command conda -ErrorAction SilentlyContinue).Source,
  "$env:USERPROFILE\anaconda3\Scripts\conda.exe",
  "$env:USERPROFILE\miniconda3\Scripts\conda.exe",
  "D:\software\Anaconda\Scripts\conda.exe"
)

$condaCommand = $condaCandidates |
  Where-Object { $_ -and (Test-Path -LiteralPath $_) } |
  Select-Object -First 1

if (-not $condaCommand) {
  throw "Conda was not found. Open an Anaconda Prompt or set CONDA_EXE."
}

Write-Host "[1/3] Installing dependencies into Conda environment '$EnvironmentName'..." -ForegroundColor Cyan
& $condaCommand run -n $EnvironmentName python -m pip install -r requirements-build.txt
if ($LASTEXITCODE -ne 0) {
  throw "Dependency installation failed."
}

Write-Host "[2/3] Building Windows EXE..." -ForegroundColor Cyan
& $condaCommand run -n $EnvironmentName python -m PyInstaller `
  --noconfirm `
  --clean `
  PhoneLinkOtpAutofill.spec
if ($LASTEXITCODE -ne 0) {
  throw "PyInstaller build failed."
}

$exeName = (& $condaCommand run -n $EnvironmentName python -c "from release_metadata import EXECUTABLE_NAME; print(EXECUTABLE_NAME)").Trim()

Write-Host "[3/3] Done." -ForegroundColor Green
Write-Host "EXE: $PSScriptRoot\dist\$exeName"

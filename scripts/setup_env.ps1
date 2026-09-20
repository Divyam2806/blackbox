<#
Creates a local virtualenv on Windows and prepares the simulation tools.

Usage (PowerShell, from the project root):
  powershell -ExecutionPolicy Bypass -File scripts\setup_env.ps1

Gazebo and Renode are easiest inside WSL2. For those, open a WSL terminal and
run scripts/setup_env.sh instead.
#>
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Venv = Join-Path $Root ".venv"

Write-Host "== 1/5 Python"
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { $py = Get-Command py -ErrorAction SilentlyContinue }
if (-not $py) { throw "Python not found. Install Python 3.10+ from python.org and tick 'Add to PATH'." }
& $py.Source -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)"
if ($LASTEXITCODE -ne 0) { throw "Python 3.10 or newer is required." }

Write-Host "== 2/5 Virtual environment at $Venv"
if (-not (Test-Path $Venv)) { & $py.Source -m venv $Venv }
$Activate = Join-Path $Venv "Scripts\Activate.ps1"
. $Activate
python -m pip install --upgrade pip wheel | Out-Null

Write-Host "== 3/5 Python packages"
if (Test-Path (Join-Path $Root "pyproject.toml")) {
  pip install -e $Root
  if ($LASTEXITCODE -ne 0) { pip install -r (Join-Path $Root "requirements.txt") }
} else {
  pip install -r (Join-Path $Root "requirements.txt")
}

Write-Host "== 4/5 Host-HAL toolchain (C++ compiler)"
if (-not (Get-Command g++ -ErrorAction SilentlyContinue)) {
  Write-Host "g++ not found. Install MinGW-w64 with:  winget install -e --id MSYS2.MSYS2"
  Write-Host "Then in the MSYS2 shell:  pacman -S mingw-w64-ucrt-x86_64-gcc"
  Write-Host "and add C:\msys64\ucrt64\bin to PATH. Or use WSL2."
}

Write-Host "== 5/5 Config and check"
$envFile = Join-Path $Root ".env"
$example = Join-Path $Root ".env.example"
if (-not (Test-Path $envFile) -and (Test-Path $example)) { Copy-Item $example $envFile; Write-Host "Created .env" }
python (Join-Path $Root "scripts\check_env.py")

Write-Host ""
Write-Host "Done. In a new terminal activate with:  .venv\Scripts\Activate.ps1"
Write-Host "Then run:  fwagent run firmware_samples\cooling_fan_buggy --sim auto"

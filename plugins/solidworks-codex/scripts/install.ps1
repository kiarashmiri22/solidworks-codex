param(
    [switch]$InstallInCodex
)

$ErrorActionPreference = 'Stop'
$pluginRoot = Split-Path -Parent $PSScriptRoot
$repoRoot = Split-Path -Parent (Split-Path -Parent $pluginRoot)
$venvPython = Join-Path $pluginRoot '.venv\Scripts\python.exe'
$requirements = Join-Path $pluginRoot 'requirements.txt'

$launcher = Get-Command py.exe -ErrorAction Stop
& $launcher.Source -3 -c "import sys; assert sys.version_info >= (3, 11), 'Python 3.11 or newer is required'"
if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 or newer is required.' }

if (-not (Test-Path -LiteralPath $venvPython)) {
    & $launcher.Source -3 -m venv (Join-Path $pluginRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the plugin virtual environment.' }
}

& $venvPython -m pip install --disable-pip-version-check -r $requirements
if ($LASTEXITCODE -ne 0) { throw 'Could not install the plugin dependencies.' }

& $venvPython (Join-Path $PSScriptRoot 'doctor.py') --strict
if ($LASTEXITCODE -ne 0) { throw 'The local SolidWorks environment is not ready.' }

if ($InstallInCodex) {
    $codex = Get-Command codex.exe -ErrorAction Stop
    & $codex.Source plugin marketplace add $repoRoot
    if ($LASTEXITCODE -ne 0) { throw 'Could not add the project plugin marketplace to Codex.' }
    & $codex.Source plugin add 'solidworks-codex@solidworks-local'
    if ($LASTEXITCODE -ne 0) { throw 'Could not install the SolidWorks plugin in Codex.' }
}

Write-Host 'SolidWorks Codex setup is ready.'
if (-not $InstallInCodex) {
    Write-Host 'To install it in Codex, rerun this script with -InstallInCodex.'
}

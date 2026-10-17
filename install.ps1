$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    if (Get-Command py -ErrorAction SilentlyContinue) { & py -3 aero.py setup @args }
    else { & python aero.py setup @args }
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally { Pop-Location }

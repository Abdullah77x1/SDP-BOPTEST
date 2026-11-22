param([string]$BoptestPython)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (!$BoptestPython) {
    $BoptestPython = Join-Path $root 'experiments\five_model_hvac16_v1_0_0\.venv\Scripts\python.exe'
}
$py = (Resolve-Path -LiteralPath $BoptestPython).Path
Push-Location -LiteralPath (Join-Path $root 'SDP_BOPTEST_Pilot')
try {
    & $py -B -m unittest final_energy_control.test_rolling final_energy_control.test_digital_twin final_energy_control.test_live_smoke
    if ($LASTEXITCODE -ne 0) { throw 'Core regression checks failed.' }
} finally {
    Pop-Location
}

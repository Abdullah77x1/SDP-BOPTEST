param(
    [string]$AuthorizationFile = 'live_optimizer_twin_authorization.json',
    [int]$Port = 8770,
    [switch]$Describe,
    [switch]$NoBrowser,
    [switch]$Use400W,
    [switch]$Rolling
)

$ErrorActionPreference = 'Stop'
$python = Join-Path $PSScriptRoot 'experiments\five_model_hvac16_v1_0_0\.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Pinned project Python environment is unavailable.' }
if ($Rolling -and !$PSBoundParameters.ContainsKey('AuthorizationFile')) {
    $AuthorizationFile = 'live_rolling_twin_authorization.json'
}

if ($Describe) {
    $arguments = @('--describe')
} else {
    $authorization = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($AuthorizationFile)
    if (!(Test-Path -LiteralPath $authorization -PathType Leaf)) {
        throw "The live session requires its exact authorization JSON. Run this script with -Describe to print the binding."
    }
    $arguments = @('--serve', $authorization, '--port', $Port)
    if (!$NoBrowser) { $arguments += '--open-browser' }
}
if ($Use400W) { $arguments += '--use-400w' }
if ($Rolling) { $arguments += '--rolling' }

Push-Location -LiteralPath (Join-Path $PSScriptRoot 'SDP_BOPTEST_Pilot')
try {
    & $python -B -m final_energy_control.digital_twin @arguments
    if ($LASTEXITCODE -ne 0) { throw "Live digital twin command failed with exit code $LASTEXITCODE." }
} finally {
    Pop-Location
}

# Windows Setup and Execution

Use PowerShell from the checkout root. Install Git for Windows with Git LFS and 64-bit Python 3.12. The tested environment used CPython 3.12.14. Keep the checkout in a reasonably short path for Windows tools.

## 1. Restore bundled assets and install dependencies

```powershell
git lfs install
git lfs pull
py -3.12 -B .\scripts\Initialize-CoreAssets.py
py -3.12 -m venv .\experiments\five_model_hvac16_v1_0_0\.venv
$py = (Resolve-Path .\experiments\five_model_hvac16_v1_0_0\.venv\Scripts\python.exe).Path
& $py -m pip install -r .\experiments\five_model_hvac16_v1_0_0\requirements.txt
```

Git LFS fetches the original O25 checkpoint. Setup verifies the checkpoint and pinned BESTEST Air FMU, then restores the bundled sealed evidence at its original application paths. Rerun setup as needed. The original file hashes must match each time.

## 2. Open the genuine rolling recording

```powershell
$py = (Resolve-Path .\experiments\five_model_hvac16_v1_0_0\.venv\Scripts\python.exe).Path
Set-Location -LiteralPath .\SDP_BOPTEST_Pilot
& $py -B -m final_energy_control.live_dashboard --replay rolling --port 8770
```

Open [rolling replay](http://127.0.0.1:8770/). Play or seek through the 41 recorded advances. The included G218 matched replay uses `--replay g218` in the same command. Ctrl+C stops replay. Neither replay needs Docker.

## 3. Verify inference, control and the read-only live binding

From the checkout root:

```powershell
$py = (Resolve-Path .\experiments\five_model_hvac16_v1_0_0\.venv\Scripts\python.exe).Path
& $py -B .\scripts\Verify-Package-Inference.py
powershell -ExecutionPolicy Bypass -File .\scripts\Run-Regression.ps1 -BoptestPython $py
Set-Location -LiteralPath .\SDP_BOPTEST_Pilot
& $py -B -m final_energy_control.digital_twin --rolling --describe
```

The live entry point and start, pause, resume, and stop implementation are retained. This checkout reproduces the binding of the completed, consumed **LIVE_ROLLING_TWIN_01** campaign. A future genuine-live run requires the separately installed pinned Docker worker stack and an explicitly authorized, separately versioned campaign with an unused ID. The ID is part of the implementation binding, and changing only the authorization filename does not create a new campaign. See [runtime requirements](references/OPTIONAL_EVIDENCE.md#pinned-live-runtime) and [restoring historical evidence](EXCLUDED_FILES_INDEX.md).

After the new campaign is bound and authorized, open a fresh terminal at the checkout root and pass its exact authorization file to the original Windows launcher:

~~~powershell
$authorization = Read-Host 'Absolute path to the authorized unused rolling campaign JSON'
powershell -ExecutionPolicy Bypass -File .\run_live_digital_twin.ps1 -Rolling -AuthorizationFile $authorization
~~~

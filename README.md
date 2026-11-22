# SDP BOPTEST Digital Twin

This Senior Design Project evaluates simulated HVAC control in the pinned BOPTEST BESTEST Air 0.9.0 single-zone benchmark. The application reads simulator measurements, issues observational forecasts, evaluates qualified control choices, applies and verifies a command, and displays the feedback in a loopback dashboard.

- **O25 Random Forest** issues +5, +10, +15, and +30 minute forecasts on supported native trajectories. The original checkpoint is included through Git LFS.
- **HVAC action-response model** uses measured evidence to predict relevant native and warmer control trajectories, including recovery. The partial rolling controller reevaluates every five minutes and commits the next five-minute command.
- **Safety supervision** verifies commands and readbacks, preserves native fallback, and tracks scheduled release and recovery.
- **Evaluation** reports measured cooling-plus-fan electricity, official BOPTEST discomfort, and separate project-band discomfort at 20–26°C. The recorded rolling demo verifies operation on one simulated arm. Measured savings come from matched experiments.

## Windows quick start

Install Git for Windows with Git LFS, 64-bit Python 3.12 with the Windows Python launcher, and a browser. The verified dependency environment used Python 3.12.14. Run in PowerShell:

~~~powershell
git lfs install
git clone --branch feature/complete-boptest-handoff https://github.com/Abdullah77x1/SDP-BOPTEST.git
Set-Location -LiteralPath .\SDP-BOPTEST
git lfs pull
py -3.12 -B .\scripts\Initialize-CoreAssets.py
py -3.12 -m venv .\experiments\five_model_hvac16_v1_0_0\.venv
$py = (Resolve-Path .\experiments\five_model_hvac16_v1_0_0\.venv\Scripts\python.exe).Path
& $py -m pip install -r .\experiments\five_model_hvac16_v1_0_0\requirements.txt
Set-Location -LiteralPath .\SDP_BOPTEST_Pilot
& $py -B -m final_energy_control.live_dashboard --replay rolling --port 8770
~~~

Open [the rolling replay](http://127.0.0.1:8770/). Seek to intervals **8, 9, 10, 18, and 41** for forecast, entry, reevaluation, release, and recovery. Stop with Ctrl+C. Substitute **--replay g218** for the matched 72-hour replay. The two replays work without Docker. [Windows setup, tests, and live dependencies](HOW_TO_RUN.md)

## Repository map

| Path | Contents |
| --- | --- |
| [SDP_BOPTEST_Pilot/final_energy_control](SDP_BOPTEST_Pilot/final_energy_control/) | Active rolling controller, action-response models, optimizer, dashboard, and essential control-loop tests |
| [SDP_BOPTEST_Pilot](SDP_BOPTEST_Pilot/) | BOPTEST client, collector, safety, scoring, pinned case files, and supporting modules |
| [ml_research_v1_0_0](ml_research_v1_0_0/) | Observational inference, feature contract, frozen O25 checkpoint, and retained research references |
| [assets](assets/) | Runtime evidence bundles with an original-path SHA-256 manifest. Setup restores the sealed inputs |
| [scripts](scripts/) | Asset initialization, forecast verification, regression test runner, and optional original archive restoration |
| [experiments](experiments/) | Original experiment registry and pinned Python requirements |
| [report](report/) | Editable technical report, GitHub-readable version, figures, review checklist, and handbook audit |
| [references](references/) | Source index, terminology, model provenance, and evidence locators |

Calibration code reads the same archived G174, G218, and G163 inputs as the verified controller. Run **Verify-Package-Inference.py** to reproduce recorded O25 forecasts and inspect the action-response qualification without model training. **Run-Regression.ps1** runs the 13 essential regressions. [Model provenance](references/MODELS_AND_DATA.md) · [Verification](CORE_PACKAGE_VERIFICATION.md)

## Reports and measured evidence

- [Technical report on GitHub](report/SDP_BOPTEST_TECHNICAL_REPORT.md) · [Editable Word report](report/SDP_BOPTEST_TECHNICAL_REPORT.docx)
- [Source index](references/SOURCE_CODE_INDEX.md) · [Terminology](references/NAME_MAPPING.md) · [Team checklist](report/TEAM_REVIEW_CHECKLIST.md) · [Handbook audit](report/REPORT_COMPLETENESS_AUDIT.md)
- [Experiment evidence](references/EXPERIMENT_EVIDENCE_INDEX.md) · [External histories and restore instructions](EXCLUDED_FILES_INDEX.md) · [GitHub asset and provenance notes](references/GITHUB_HANDOFF.md)

G218 Stage 1 saved **0.074920 kWh (0.504%)** and failed its frozen project-comfort criterion. G163 and the fan/joint strategies retain their original measured outcomes and comfort failures. An archived or technically successful run is insufficient to establish a comfort-compliant energy benefit.

The rolling MPC is partial. Economic early release, delayed starts, re-entry, and fan/joint strategies remain outside the active controller’s qualification. The system has been verified in the simulation benchmark. The full pinned BOPTEST Docker worker stack and a separately versioned, explicitly authorized new campaign are prerequisites for future live runs. [Pinned runtime and license](references/OPTIONAL_EVIDENCE.md#pinned-live-runtime)

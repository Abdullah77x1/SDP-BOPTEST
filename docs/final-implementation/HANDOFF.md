# Final supervised implementation handoff

This handoff covers the Windows offline reproduction of the final supervised dashboard. It preserves the existing application and model bytes. Live operation additionally requires the pinned BOPTEST runtime and an authorized operator. The [setup repository](https://github.com/Abdullah77x1/SDP-BOPTEST-Setup) provides BOPTEST 0.9.0 deployment and installation checks.

## Files and layout

Download the [verified offline handoff](https://github.com/Abdullah77x1/SDP-BOPTEST/releases/download/cosc14-sdp1-offline-v1/COSC14_SDP1_Offline_Handoff.zip) from the [private GitHub release](https://github.com/Abdullah77x1/SDP-BOPTEST/releases/tag/cosc14-sdp1-offline-v1) and unpack it into a new short workspace path. Preserve its three top-level directories. The manifest in the archive records byte counts and SHA-256 hashes. These artifacts are for authorized team and reviewer access.

| Path relative to the archive root | Role |
|---|---|
| `SDP-BOPTEST/SDP_BOPTEST_Pilot/sdp_redesign/native_twin.py`, `native_dashboard.html`, `dashboard_forecast.py`, `dashboard_replay.py` | Final entry point, interface, schema checking, forecast and archived replay. |
| `SDP-BOPTEST/SDP_BOPTEST_Pilot` shared code and `SDP-BOPTEST/ml_research_v1_0_0/dataset.py` | Existing collector, readback, guard, comfort and feature routines. Imported support is also used by older research, which stays distinct from the final operator workflow. |
| `SDP-BOPTEST/experiments/five_model_hvac16_v1_0_0` and sibling `experiments/five_model_hvac16_v1_0_0` | Existing schema and helper modules and pinned package versions. Keep both locations because the original code resolves both. |
| App `runtime_state/forecast-comparison-final-v1/selection` | `selected_model.joblib`, `selected_model.json`, `decision.json`, public held predictions and summary. The model SHA-256 is `a2e2e0e75df700c57dff21c07dd3f1ccaaa36cd9529b44400a7d537afae3b3e5`. |
| App `runtime_state/unified-archive-v1-1` | Binding manifest, ordered schema, final feature dataset and provenance CSVs. |
| App `runtime_state/warmer-extension-v1/STEP3C_D2_G196_WARM45` | Sealed warmer day-196 recording with command and measurement receipts. |
| Sibling `SDP_BOPTEST_Pilot/stage4e_d2_prep02/runtime_state/batches/PUBLIC_D2_D2_G196_20261115_01/D2_G196_N` | Sealed native day-196 recording. |
| `SDP-BOPTEST/report/native-control/verified-command-replay.json`, pinned FMU and license | Regression fixture and official comfort inputs. Retain the [upstream license](https://github.com/ibpsa/project1-boptest/blob/v0.9.0/license.md) with the package. |

## Fresh offline install

Use 64-bit Python 3.12.14 on Windows. Start in the extracted archive directory.

```powershell
py -3.12 --version
py -3.12 -m venv .venv
$py = (Resolve-Path .\.venv\Scripts\python.exe).Path
& $py -m pip install -r .\SDP-BOPTEST\experiments\five_model_hvac16_v1_0_0\requirements.txt
Push-Location .\SDP-BOPTEST\SDP_BOPTEST_Pilot
& $py -B -m sdp_redesign.native_twin --verify-model
& $py -B -m sdp_redesign.dashboard_replay native
& $py -B -m sdp_redesign.dashboard_replay override
& $py -B -m unittest discover -s sdp_redesign/tests -v
Pop-Location
```

The expected native and warmer replays each score 852 complete origins. Native has zero active intervals or releases. Warmer verifies 27 active intervals and three native releases. They compare their reconstructed features, measured outcomes and exact frozen predictions against the original held reference. Their 72-hour electrical totals are 22.34176 and 22.25993 kWh respectively, paired with 1.53095 and 2.66247 K·h official discomfort. Read [the experimental index](../research/EXPERIMENT_INDEX.md) for interpretation.

For a browser replay, use the same Python and working directory with `-B -m sdp_redesign.native_twin --replay override --port 8770`, then open [the local dashboard](http://127.0.0.1:8770/). `--replay native` shows the other recording. Replay reads existing data. Use Ctrl+C to stop.

## Live verification scope

The source host verified one supervised live BOPTEST session on 24 November. The command was applied at 11:05 and native return confirmed at 11:50. The separate setup audit is needed before any new live demonstration. This offline package does not provision Docker images or authorize a simulator advance. [Saved live evidence locations](../research/EVIDENCE_INDEX.md#e15).

The [historical GitHub README](https://github.com/Abdullah77x1/SDP-BOPTEST/blob/2abf4e1846f22149a65a45d35454b4a4b0d8c5f9/README.md) describes the earlier O25 rolling system. The final implementation uses the frozen 27-input checkpoint in the release archive.

## Isolated verification

A fresh Python 3.12.14 environment with the original pinned requirements verified the model, both replay summaries and all 59 regression checks on 24 November. The new replay summaries are identical as data to the archived verification summaries. The review archive has SHA-256 `5581548980707ec01f75062475f471b8032f3312599f1845611714094128843a`. A separate startup check returned HTTP 200 and the expected archived-replay dashboard HTML.

## Review the implementation

The [source entry point](source/native_twin.py), [dashboard HTML](source/native_dashboard.html), [ordered input/output metadata](selected_model.json) and [pinned requirements](requirements.txt) are available for inspection. Use the downloaded archive for execution. The model is the `selected_model.joblib` member under the selection directory listed above.

[Native replay results](verification/native-replay-summary.json) · [Warmer replay results](verification/override-replay-summary.json) · [59 regression tests](verification/offline-regression.txt) · [Live command receipt](verification/command-lifecycle.json) · [Active command screenshot](verification/06-first-command-readback-1105.png) · [Post-release screenshot](verification/09-post-release-feedback-1230.png)

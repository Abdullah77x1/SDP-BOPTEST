# Source Code Index

Current code is the frozen V4 BOPTEST subset. Exact campaign names, public module names, interfaces and receipt IDs keep their original spelling. Source entries describe behavior. The experiment index supplies independent measurements and verdicts.

## Simulator integration

### SRC-001 · BOPTEST HTTP client

Translate structured requests into simulator API calls and return checked response payloads. Inputs are the endpoint, method, payload and instance ID. Outputs and raw receipts feed the ordered client.

Implementation [`SDP_BOPTEST_Pilot/client.py`](../SDP_BOPTEST_Pilot/client.py). Symbols `Client.request`, `Client.deploy`, `Client.discover`.

Relevant checks [test_digital_twin.py](../SDP_BOPTEST_Pilot/final_energy_control/test_digital_twin.py).

### SRC-002 · Ordered BOPTEST requests

Pair API traffic with receipt order and simulator origin. Sequence evidence associates a decision, sent command and readback. This layer does not choose an action.

Implementation [`SDP_BOPTEST_Pilot/stage4e_d0/runner.py`](../SDP_BOPTEST_Pilot/stage4e_d0/runner.py). Symbols `OrderedClient.request`, `Journal`.

Relevant checks [test_digital_twin.py](../SDP_BOPTEST_Pilot/final_energy_control/test_digital_twin.py), [test_live_smoke.py](../SDP_BOPTEST_Pilot/final_energy_control/test_live_smoke.py).

### SRC-003 · Bounded transport and initialization

Apply an authorized run definition, enforce request budgets and use the selected native warmup and 300-second step. Measured history is collected separately at 30-second resolution.

Implementation [`SDP_BOPTEST_Pilot/stage4e_d2i_1/transport.py`](../SDP_BOPTEST_Pilot/stage4e_d2i_1/transport.py). Symbols `BudgetedTransport.request`, `initialize_run`.

Relevant checks [test_digital_twin.py](../SDP_BOPTEST_Pilot/final_energy_control/test_digital_twin.py), [test_g218.py](../SDP_BOPTEST_Pilot/autonomous_hvac_stage1/test_g218.py).

### SRC-004 · BOPTEST Building Simulator physics

Modelica defines fan airflow, ideal coil, room control and defaults. Requested supply temperature is bounded separately from room setpoints. This is the benchmark's plant, not the simplified heat balance or a physical building test.

Implementation [`SDP_BOPTEST_Pilot/deployment/official_v0.9.0/project1-boptest-0.9.0/testcases/bestest_air/models/BESTESTAir/BaseClasses/FanCoilUnit_T.mo`](../SDP_BOPTEST_Pilot/deployment/official_v0.9.0/project1-boptest-0.9.0/testcases/bestest_air/models/BESTESTAir/BaseClasses/FanCoilUnit_T.mo), [`SDP_BOPTEST_Pilot/deployment/official_v0.9.0/project1-boptest-0.9.0/testcases/bestest_air/models/BESTESTAir/BaseClasses/Thermostat_T.mo`](../SDP_BOPTEST_Pilot/deployment/official_v0.9.0/project1-boptest-0.9.0/testcases/bestest_air/models/BESTESTAir/BaseClasses/Thermostat_T.mo). Symbols `FanCoilUnit_T`, `Thermostat_T`.

Relevant checks [test_g218.py](../SDP_BOPTEST_Pilot/autonomous_hvac_stage1/test_g218.py), [test_fan_trial.py](../SDP_BOPTEST_Pilot/final_energy_control/test_fan_trial.py).

## Causal collection and preprocessing

### SRC-005 · Development dataset collector

Convert approved scenario intervals, as-issued forecasts, verified commands and ordered observations into causally aligned raw datasets. Test and development evidence keep their original partitions.

Implementation [`SDP_BOPTEST_Pilot/stage4e_d2i_1_v1_0_1/collector.py`](../SDP_BOPTEST_Pilot/stage4e_d2i_1_v1_0_1/collector.py). Symbols `_collect`.

Relevant checks [test_g218.py](../SDP_BOPTEST_Pilot/autonomous_hvac_stage1/test_g218.py), [test_live_smoke.py](../SDP_BOPTEST_Pilot/final_energy_control/test_live_smoke.py).

### SRC-006 · BOPTEST feature and interval derivation

Build decision-time history, boundary and committed-control fields. Preserve order and express electrical targets as averages over the final five minutes of each lead. The O25 feature and P27 action contracts use different fields.

Implementation [`ml_research_v1_0_0/dataset.py`](../ml_research_v1_0_0/dataset.py). Symbols `state_features`, `interval_history`.

Relevant checks [Verify-Package-Inference.py](../scripts/Verify-Package-Inference.py).

## BOPTEST observational forecasting

### SRC-011 · BOPTEST Forecast Model

Check the artifact SHA-256 and ordered schema, prepare the input contract, return four observational forecast leads and electrical component outputs. Unsupported observations may return unavailable.

Implementation [`ml_research_v1_0_0/inference.py`](../ml_research_v1_0_0/inference.py). Symbols `Predictor.__init__`, `Predictor.forecast_features`, `Predictor.forecast_observations`.

Relevant checks [Verify-Package-Inference.py](../scripts/Verify-Package-Inference.py), [test_live_smoke.py](../SDP_BOPTEST_Pilot/final_energy_control/test_live_smoke.py).

### SRC-012 · Live BOPTEST Forecast Model adapter

Use only the verified prefix at the origin, record forecast availability and match later measured outcomes separately for verification. A persisted forecast record is not the action-response calculation.

Implementation [`SDP_BOPTEST_Pilot/final_energy_control/live_smoke.py`](../SDP_BOPTEST_Pilot/final_energy_control/live_smoke.py). Symbols `record_o25`, `forecast_actual`.

Relevant checks [test_live_smoke.py](../SDP_BOPTEST_Pilot/final_energy_control/test_live_smoke.py), [test_digital_twin.py](../SDP_BOPTEST_Pilot/final_energy_control/test_digital_twin.py).

## Action-response modeling

### SRC-013 · Fixed-hold action-response predecessor

Estimate scoped, fixed hold and recovery paths from qualified matched archives. Used by the original fixed-path optimizer, with its own support limits and measured validation.

Implementation [`SDP_BOPTEST_Pilot/final_energy_control/optimizer_model.py`](../SDP_BOPTEST_Pilot/final_energy_control/optimizer_model.py). Symbols `ResponseModel.predict`, `qualification`.

Relevant checks [test_optimizer.py](../SDP_BOPTEST_Pilot/final_energy_control/test_optimizer.py).

### SRC-014 · HVAC Action-Response Model

Use current temperature, recent power and as-issued boundary conditions, fit the shared regularized phase response to scoped traces, and roll out the supported paths with recovery. Issued weather ends at +30 minutes; later values persist.

Implementation [`SDP_BOPTEST_Pilot/final_energy_control/rolling_model.py`](../SDP_BOPTEST_Pilot/final_energy_control/rolling_model.py). Symbols `observed_state`, `conditions`, `StepModel.rollout`, `calibrated_rolling`.

Relevant checks [test_rolling.py](../SDP_BOPTEST_Pilot/final_energy_control/test_rolling.py), [Verify-Package-Inference.py](../scripts/Verify-Package-Inference.py).

## Optimization algorithm

### SRC-015 · Fixed-hold HVAC Optimizer

Compare native and a qualified fixed warmer trial with energy uncertainty, feasibility and measured support. Candidate forecasts are distinct from measured arm totals.

Implementation [`SDP_BOPTEST_Pilot/final_energy_control/optimizer.py`](../SDP_BOPTEST_Pilot/final_energy_control/optimizer.py). Symbols `PredictiveController._select`.

Relevant checks [test_optimizer.py](../SDP_BOPTEST_Pilot/final_energy_control/test_optimizer.py).

### SRC-016 · Rolling HVAC Optimizer

Compare native and warmer paths at the eligible start, deduct uncertainty and switching cost and check temperature reserve. Recompute qualified continuations using the next observations. Economic early release has no validated counterfactual.

Implementation [`SDP_BOPTEST_Pilot/final_energy_control/rolling_control.py`](../SDP_BOPTEST_Pilot/final_energy_control/rolling_control.py). Symbols `RollingController._prediction`, `RollingController._select`.

Relevant checks [test_rolling.py](../SDP_BOPTEST_Pilot/final_energy_control/test_rolling.py), [test_release_branch.py](../SDP_BOPTEST_Pilot/final_energy_control/test_release_branch.py).

## Rolling control loop

### SRC-017 · Rolling HVAC Controller session owner

Validate runtime and authorization, consume one five-minute command per decision, record forecast and apply the advance, verify effective output, append 30-second history and publish verified feedback. Resume rechecks the endpoint.

Implementation [`SDP_BOPTEST_Pilot/final_energy_control/digital_twin.py`](../SDP_BOPTEST_Pilot/final_energy_control/digital_twin.py). Symbols `collect_session`, `refresh_endpoint`, `create_application`.

Relevant checks [test_digital_twin.py](../SDP_BOPTEST_Pilot/final_energy_control/test_digital_twin.py), [test_rolling.py](../SDP_BOPTEST_Pilot/final_energy_control/test_rolling.py).

## Safety, fallback and recovery

### SRC-018 · HVAC command and fallback supervision

Apply command envelope, validate readbacks and maintain native recovery state. The 25.5°C limit and 120-minute lockout apply to the retained warmer policy. Safety release remains independently available.

Implementation [`SDP_BOPTEST_Pilot/autonomous_hvac_stage1/controller.py`](../SDP_BOPTEST_Pilot/autonomous_hvac_stage1/controller.py). Symbols `EnergyController.decide`, `EnergyController.confirm`.

Relevant checks [tests.py](../SDP_BOPTEST_Pilot/autonomous_hvac_stage1/tests.py), [test_rolling.py](../SDP_BOPTEST_Pilot/final_energy_control/test_rolling.py).

### SRC-019 · Native release and readback

Clear override flags for Native HVAC Control and compare actual flags and effective setpoint against the request and expected schedule. Feedback is required before a command is credited.

Implementation [`SDP_BOPTEST_Pilot/stage4e_d0/plan.py`](../SDP_BOPTEST_Pilot/stage4e_d0/plan.py). Symbols `native_command`, `validate_readback`.

Relevant checks [test_digital_twin.py](../SDP_BOPTEST_Pilot/final_energy_control/test_digital_twin.py), [test_fan_trial.py](../SDP_BOPTEST_Pilot/final_energy_control/test_fan_trial.py).

## Energy evaluation

### SRC-020 · Measured cooling-plus-fan integration

Trapezoidally integrate timed electrical power samples in W into joules, then divide by 3,600,000 for kWh. Reconcile readings with benchmark energy where applicable and keep heating thermal power separate.

Implementation [`SDP_BOPTEST_Pilot/core.py`](../SDP_BOPTEST_Pilot/core.py), [`SDP_BOPTEST_Pilot/stage4e_d0/plan.py`](../SDP_BOPTEST_Pilot/stage4e_d0/plan.py). Symbols `integrate`, `energy_audit`.

Relevant checks [tests.py](../SDP_BOPTEST_Pilot/autonomous_hvac_stage1/tests.py), [test_fan_trial.py](../SDP_BOPTEST_Pilot/final_energy_control/test_fan_trial.py).

## Comfort evaluation

### SRC-021 · Official BOPTEST discomfort

Integrate positive violations of the original time-varying thermal bounds. API value tdis_tot is the archived official result. The official KPI and native thermostat transition schedules are separate resources.

Implementation [`SDP_BOPTEST_Pilot/deployment/official_v0.9.0/project1-boptest-0.9.0/kpis/kpi_calculator.py`](../SDP_BOPTEST_Pilot/deployment/official_v0.9.0/project1-boptest-0.9.0/kpis/kpi_calculator.py). Symbols `KPI_Calculator.get_thermal_discomfort`.

Relevant checks [tests.py](../SDP_BOPTEST_Pilot/autonomous_hvac_stage1/tests.py), [test_joint_fan_trial.py](../SDP_BOPTEST_Pilot/final_energy_control/test_joint_fan_trial.py).

### SRC-022 · Project comfort, paired energy and recovery

Replay original bounds separately from the 20–26°C occupied band and compare matched intervals. Integrate degree-hours, count occupied exceedance minutes, and compare recovery and whole-period energy independently.

Implementation [`SDP_BOPTEST_Pilot/autonomous_hvac_stage1/evaluation.py`](../SDP_BOPTEST_Pilot/autonomous_hvac_stage1/evaluation.py). Symbols `ComfortSchedule.from_fmu`, `score_window`, `evaluate_matched`, `_recovery_mark`.

Relevant checks [tests.py](../SDP_BOPTEST_Pilot/autonomous_hvac_stage1/tests.py), [test_g218.py](../SDP_BOPTEST_Pilot/autonomous_hvac_stage1/test_g218.py).

## Dashboard backend

### SRC-023 · Live Digital Twin Dashboard backend

Serve loopback HTML and verified /state and /command endpoints. SessionControl queues lifecycle requests at safe boundaries. The legacy Controller class in the shared file is a different entry point.

Implementation [`SDP_BOPTEST_Pilot/dashboard.py`](../SDP_BOPTEST_Pilot/dashboard.py), [`SDP_BOPTEST_Pilot/final_energy_control/digital_twin.py`](../SDP_BOPTEST_Pilot/final_energy_control/digital_twin.py). Symbols `make_server`, `SessionControl`, `LiveApplication.snapshot`.

Relevant checks [test_digital_twin.py](../SDP_BOPTEST_Pilot/final_energy_control/test_digital_twin.py).

### SRC-024 · Sealed replay backend

Check the sealed archive, expose measured state and forecasts and change only the playback cursor. The G163 replay provides three matched arms and the frozen acceptance outcome.

Implementation [`SDP_BOPTEST_Pilot/final_energy_control/live_dashboard.py`](../SDP_BOPTEST_Pilot/final_energy_control/live_dashboard.py), [`SDP_BOPTEST_Pilot/final_energy_control/g163_replay.py`](../SDP_BOPTEST_Pilot/final_energy_control/g163_replay.py). Symbols `DashboardState.snapshot`, `G163Replay.frame`.

Relevant checks [tests.py](../SDP_BOPTEST_Pilot/final_energy_control/tests.py), [test_optimizer.py](../SDP_BOPTEST_Pilot/final_energy_control/test_optimizer.py).

## Dashboard frontend

### SRC-025 · Live Digital Twin Dashboard frontend

Render simulator time, measured state, command/readback, forecasts, predictions and comfort. Live lifecycle and replay actions are separate views. Figures 16–19 document historical rendered output.

Implementation [`SDP_BOPTEST_Pilot/final_energy_control/dashboard.html`](../SDP_BOPTEST_Pilot/final_energy_control/dashboard.html), [`SDP_BOPTEST_Pilot/final_energy_control/g163_dashboard.html`](../SDP_BOPTEST_Pilot/final_energy_control/g163_dashboard.html). Symbols `dashboard.html`, `g163_dashboard.html`.

Relevant checks [test_digital_twin.py](../SDP_BOPTEST_Pilot/final_energy_control/test_digital_twin.py), [tests.py](../SDP_BOPTEST_Pilot/final_energy_control/tests.py).

## Experimental verification

### SRC-027 · G174 Warmer Setpoint Control comparison

Compare the warmer trace with a validated archived native reference using original score windows and frozen discomfort limits. Campaign JSON and the seal establish the separate measured outcome.

Implementation [`SDP_BOPTEST_Pilot/energy_savings_g174_v1/comparison.py`](../SDP_BOPTEST_Pilot/energy_savings_g174_v1/comparison.py). Symbols `comfort`.

Relevant checks [tests.py](../SDP_BOPTEST_Pilot/energy_savings_g174_v1/tests.py).

### SRC-028 · Matched G218 and G163 campaigns

Use paired or three-arm run definitions, compare verified forcing and power histories and record energy and comfort acceptance under the original gates.

Implementation [`SDP_BOPTEST_Pilot/autonomous_hvac_stage1/g218.py`](../SDP_BOPTEST_Pilot/autonomous_hvac_stage1/g218.py), [`SDP_BOPTEST_Pilot/final_energy_control/optimizer_campaign.py`](../SDP_BOPTEST_Pilot/final_energy_control/optimizer_campaign.py). Symbols `score_policy_pair`, `score`.

Relevant checks [test_g218.py](../SDP_BOPTEST_Pilot/autonomous_hvac_stage1/test_g218.py), [test_optimizer.py](../SDP_BOPTEST_Pilot/final_energy_control/test_optimizer.py).

### SRC-029 · Fan Control Experiment

Verify bounded 0.60 airflow command, match native state and score intervention plus native recovery. The replication uses a distinct eligible scenario. A provisional project-band pass leaves the official discomfort increase visible.

Implementation [`SDP_BOPTEST_Pilot/final_energy_control/fan_trial.py`](../SDP_BOPTEST_Pilot/final_energy_control/fan_trial.py), [`SDP_BOPTEST_Pilot/final_energy_control/fan_replication.py`](../SDP_BOPTEST_Pilot/final_energy_control/fan_replication.py). Symbols `FanTrialTransport`, `score_pair`, `footprint_audit`.

Relevant checks [test_fan_trial.py](../SDP_BOPTEST_Pilot/final_energy_control/test_fan_trial.py), [test_fan_replication.py](../SDP_BOPTEST_Pilot/final_energy_control/test_fan_replication.py).

### SRC-030 · Joint HVAC Control Experiment

Freeze compensated supply temperature from the verified 14:00 measurements, check both commands and restore native control. The comparison enforces the joint campaign's zero-added official discomfort gate.

Implementation [`SDP_BOPTEST_Pilot/final_energy_control/joint_fan_trial.py`](../SDP_BOPTEST_Pilot/final_energy_control/joint_fan_trial.py). Symbols `definition`, `score_pair`.

Relevant checks [test_joint_fan_trial.py](../SDP_BOPTEST_Pilot/final_energy_control/test_joint_fan_trial.py).

### SRC-031 · Prepared continue-versus-release comparison

Specify equal pre-fork traces and one differing action at 11:15, with the same evaluation horizon and budgets. The package contains preparation and tests with no measured branch result.

Implementation [`SDP_BOPTEST_Pilot/final_energy_control/release_branch.py`](../SDP_BOPTEST_Pilot/final_energy_control/release_branch.py). Symbols `definition`, `binding`.

Relevant checks [test_release_branch.py](../SDP_BOPTEST_Pilot/final_energy_control/test_release_branch.py).

## Testing and reproducibility

### SRC-032 · Regression entry point and inference example

Run the recorded test groups with their separate Python environments and verify the hash-bound frozen inference origin. Controlled fake transport tests are distinct from genuine BOPTEST evidence.

Implementation [`scripts/Run-Regression.ps1`](../scripts/Run-Regression.ps1), [`scripts/Verify-Package-Inference.py`](../scripts/Verify-Package-Inference.py). Symbols `Run-Regression.ps1`, `Verify-Package-Inference.py`.

Relevant checks [test_rolling.py](../SDP_BOPTEST_Pilot/final_energy_control/test_rolling.py).

### SRC-033 · Runtime identity and Windows launcher

Verify the Docker identity independently from live campaign reservation, inspect bindings and preserve limited-live authorization. Replay does not require a running Docker engine.

Implementation [`SDP_BOPTEST_Pilot/stage4e_d1_v2/runtime.py`](../SDP_BOPTEST_Pilot/stage4e_d1_v2/runtime.py), [`run_live_digital_twin.ps1`](../run_live_digital_twin.ps1). Symbols `verify_runtime`, `run_live_digital_twin.ps1`.

Relevant checks [test_digital_twin.py](../SDP_BOPTEST_Pilot/final_energy_control/test_digital_twin.py).

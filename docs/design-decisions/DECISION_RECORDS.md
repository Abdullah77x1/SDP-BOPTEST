# Engineering decision records

These records consolidate dated project evidence and the reasoning already documented in report Chapters 3–6. Reconstructed periods are identified explicitly.

## 01 · Measured office dataset

- **Period.** October, reconstructed.
- **Problem.** Begin with observed indoor conditions and AC measurements.
- **Alternatives.** Synthetic-only start or published office records.
- **Decision.** Use CU-BEMS Floor 6 Zone 4 as a measured-data feasibility study.
- **Basis and evidence.** It offers dated indoor and outdoor conditions and electricity signals. The reading dossier explains observational data bounds. [E04](../research/EVIDENCE_INDEX.md#e04), [E05](../research/EVIDENCE_INDEX.md#e05).
- **Limit and consequence.** Measured correlations cannot verify the effect of a thermostat command. Retain it as a forecasting study.

## 02 · Limits of CU-BEMS

- **Period.** Late October to early November.
- **Problem.** Decide whether CU-BEMS can support occupancy and measured interventions.
- **Alternatives.** Infer occupancy from proxies, mix datasets, or restrict the claim.
- **Decision.** Restrict CU-BEMS to aligned forecasting where signals exist.
- **Basis and evidence.** Labels, interventions and some measurements were missing or unsuitable. The chronological Model B audit keeps the evidence tied to available observations. [E03](../research/EVIDENCE_INDEX.md#e03), [E05](../research/EVIDENCE_INDEX.md#e05).
- **Limit and consequence.** A separate controllable environment is needed.

## 03 · Simulator V2 prototype

- **Period.** Late October.
- **Problem.** Develop a controllable model while studying measured data.
- **Alternatives.** Continue dashboard mockups only or use an RC thermal simulation.
- **Decision.** Build the one-zone Simulator V2 using resistance, capacitance, gains and HVAC equations.
- **Basis and evidence.** An explicit heat balance permits adjustable, repeatable histories and simple sanity checks. Prototype code and literature provide the basis. [E03](../research/EVIDENCE_INDEX.md#e03), [E04](../research/EVIDENCE_INDEX.md#e04).
- **Limit and consequence.** The model’s parameter choices limit claims about a physical room.

## 04 · Prototype limits

- **Period.** 1–2 November evidence.
- **Problem.** Check whether synthetic savings support deployment.
- **Alternatives.** Treat modeled savings as validated or run broader comparisons.
- **Decision.** Keep Simulator V2 for prototyping and compare stronger benchmark options.
- **Basis and evidence.** The seven-day constrained search kept native operation despite one favorable synthetic day. Observer and test requirements became clearer. [E06](../research/EVIDENCE_INDEX.md#e06), [E07](../research/EVIDENCE_INDEX.md#e07).
- **Limit and consequence.** Move to a packaged benchmark with independent command readbacks.

## 05 · EnergyPlus feasibility

- **Period.** 13 November.
- **Problem.** Assess a higher-fidelity simulator and control path.
- **Alternatives.** Implement EnergyPlus callbacks immediately or compare packaged alternatives.
- **Decision.** Verify the installed baseline and API feasibility. Leave the full paired campaign open.
- **Basis and evidence.** Two baseline runs and read-only API discovery provided evidence. Runtime 26.2.0 and cited manual 26.1 are separate. [E08](../research/EVIDENCE_INDEX.md#e08).
- **Limit and consequence.** The benchmark test fixture and integration work still mattered.

## 06 · BOPTEST selection

- **Period.** Mid-November.
- **Problem.** Obtain reproducible baseline/intervention comparisons.
- **Alternatives.** Use Simulator V2, EnergyPlus, or BOPTEST BESTEST Air.
- **Decision.** Use BOPTEST BESTEST Air 0.9.0.
- **Basis and evidence.** Packaged weather, native controller, published points and official KPI/readbacks support repeated comparisons. [E08](../research/EVIDENCE_INDEX.md#e08), [E09](../research/EVIDENCE_INDEX.md#e09), [E10](../research/EVIDENCE_INDEX.md#e10).
- **Limit and consequence.** Findings remain benchmark-specific.

## 07 · Single-zone scope

- **Period.** Mid–late November.
- **Problem.** Choose a scope that can be verified in SDP I.
- **Alternatives.** Build out multi-zone coupling or verify one zone.
- **Decision.** Verify one fixed benchmark zone.
- **Basis and evidence.** A bounded system makes timing, readback, control and units testable. Working requirements record the original scope and delivered subset. [E04](../research/EVIDENCE_INDEX.md#e04), [E10](../research/EVIDENCE_INDEX.md#e10), [E15](../research/EVIDENCE_INDEX.md#e15).
- **Limit and consequence.** Separate multi-zone model and deployment evaluation required in SDP II.

## 08 · Five-minute steps

- **Period.** Mid-November.
- **Problem.** Choose the issue and control interval.
- **Alternatives.** Use the detailed simulator sample directly, or aggregate at coarser intervals.
- **Decision.** Advance and issue forecasts every five minutes. Retain 30-second samples for measured integration and readbacks.
- **Basis and evidence.** Five-minute updates support the demonstrated operator policy. Detailed samples resolve short transitions and interval power. [E08](../research/EVIDENCE_INDEX.md#e08), [E10](../research/EVIDENCE_INDEX.md#e10), [E14](../research/EVIDENCE_INDEX.md#e14).
- **Limit and consequence.** Timing suitability for a physical system remains open.

## 09 · Forecast horizon

- **Period.** Mid-November.
- **Problem.** Provide useful leads with comparable measured targets.
- **Alternatives.** One short horizon or multiple short leads.
- **Decision.** Use +5, +10, +15 and +30 minutes.
- **Basis and evidence.** Multiple leads show immediate and near-term accuracy. Temperature endpoint and final-five-minute power window each preserve their meaning. [E10](../research/EVIDENCE_INDEX.md#e10), [E11](../research/EVIDENCE_INDEX.md#e11).
- **Limit and consequence.** Forecasts do not cover full recovery.

## 10 · Eight to sixteen outputs

- **Period.** 16 November documented.
- **Problem.** Separate HVAC equipment demand and distinguish electricity from heat.
- **Alternatives.** Use combined HVAC power or predict components separately.
- **Decision.** Forecast room temperature, cooling electrical power, fan electrical power and delivered heating at each lead.
- **Basis and evidence.** Component outputs allow separate electrical and heating analysis. The native and paired forecast studies verify actual signal definitions. [E10](../research/EVIDENCE_INDEX.md#e10), [E11](../research/EVIDENCE_INDEX.md#e11).
- **Limit and consequence.** Combined electrical demand is the sum of two predictions. Thermal heat remains separate.

## 11 · Input evolution

- **Period.** 16–24 November.
- **Problem.** Preserve causal, useful features and cover tested conditions.
- **Alternatives.** Keep all fields, use state only, or add known action context.
- **Decision.** Use 23 state/schedule/weather fields and four planned-action or guard fields in the final comparison.
- **Basis and evidence.** Screen constant/duplicate fields and compare state and action variants in weather-group-held-out folds. Audit low-error intervals and leakage. [E10](../research/EVIDENCE_INDEX.md#e10), [E11](../research/EVIDENCE_INDEX.md#e11).
- **Limit and consequence.** Known schedule and restarts are structural signals. Ports and measured effects have separate qualification.

## 12 · Final forecast model

- **Period.** 24 November.
- **Problem.** Choose a dependable ordinary forecaster.
- **Alternatives.** Persistence, OLS, Ridge, Random Forest and XGBoost.
- **Decision.** Use the frozen 27-input Random Forest with a labeled Persistence fallback.
- **Basis and evidence.** Its development +30 min temperature MAE was 0.11545 °C. Consider component accuracy and physical validity as well as MAE. [E11](../research/EVIDENCE_INDEX.md#e11), [E14](../research/EVIDENCE_INDEX.md#e14).
- **Limit and consequence.** XGBoost wins on some error measures. Action effects require matched evaluation.

## 13 · Occupancy information

- **Period.** 23–24 November records.
- **Problem.** Determine whether a predicted probability should replace known occupancy.
- **Alternatives.** Keep the schedule, replace it with XGBoost, or add probability after removing schedule/clock.
- **Decision.** Keep the BOPTEST schedule for SDP I.
- **Basis and evidence.** Replacement worsened combined electrical and arrival errors. The probability was useful when explicit schedule/clock were removed but still used indirectly scheduled signals. [E12](../research/EVIDENCE_INDEX.md#e12).
- **Limit and consequence.** Irregular occupancy and sensor transfer need independent tests.

## 14 · Control strategy research

- **Period.** 18–24 November.
- **Problem.** Find candidate setpoint and airflow policies with a measured energy benefit.
- **Alternatives.** Fixed, rule-based, Ridge predictive, rolling StepModel, fan-only and coordinated fan/supply.
- **Decision.** Compare bounded interventions and recovery against matched native operation.
- **Basis and evidence.** Heat-balance reasoning and control literature motivate separate evaluation. Gate outcomes and recovery varied by trial. [E04](../research/EVIDENCE_INDEX.md#e04), [E13](../research/EVIDENCE_INDEX.md#e13).
- **Limit and consequence.** Only verified comparisons establish measured differences.

## 15 · Automatic optimization disposition

- **Period.** Late November.
- **Problem.** Decide whether selected models can choose a comfort-compliant energy-saving action.
- **Alternatives.** Enable automatic ranking, or keep human-supervised experiments.
- **Decision.** Leave automatic optimization outside the final dashboard.
- **Basis and evidence.** Day-196 electrical effect sign was wrong. Several trials raised discomfort or lacked full recovery. The acceptance gates varied. [E11](../research/EVIDENCE_INDEX.md#e11), [E13](../research/EVIDENCE_INDEX.md#e13).
- **Limit and consequence.** Improve counterfactual accuracy and test constraints before model-directed actuation.

## 16 · Final supervised dashboard

- **Period.** 24 November.
- **Problem.** Deliver one verifiable monitoring, forecast and command workflow.
- **Alternatives.** Replay-only, autonomous controller, or allow a bounded operator request.
- **Decision.** Use replay and live modes with a guarded 24.5 °C, 45-minute request and verified return.
- **Basis and evidence.** Two replays and one live session verify measurements, inference and release. Earlier rolling activities remain historical. [E14](../research/EVIDENCE_INDEX.md#e14), [E15](../research/EVIDENCE_INDEX.md#e15).
- **Limit and consequence.** One case and run establish a demonstration scope. Real deployment and long-term savings remain open.

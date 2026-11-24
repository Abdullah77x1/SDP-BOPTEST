# Research and experimental evidence

This register records source locations as found in the team workspace or on GitHub. Authorized reviewers can use the links where the original artifact has already been uploaded. Unlinked local paths and filenames are retrieval requests for the team, not evidence of publication. Course records, raw datasets and machine-specific logs should stay in approved storage.

[Published research documents and score tables](artifacts/README.md)

### E01
**Scope and handbook.** `Completed_Senior_Design_Project_Proposal-2026 ShaktiSingh.docx`, `SDPI & SDPII Handbook_August 2026.pdf`. Proposal text records the intended multi-zone simulator, control and language interface, and AED 7,500 API/cloud allowance. 26 August is file metadata. The handbook’s final SDP I outline is printed pp. 23–24 and rubrics pp. 27–29.

[Authorized retrieval for larger artifacts](AUTHORIZED_ARTIFACT_RETRIEVAL.md)

### E02
**Planning and dated notes.** The [date evidence](../project-management/GANTT_DATE_EVIDENCE.md) includes August proposal metadata, September reading and design discussions, the Week 7 presentation and early CU-BEMS work. `SDP_Foundation_Team_Work_Plan.pdf` proposes four role areas and a 19–25 October sprint. The [original notes](../meetings/ORIGINAL_MEETING_NOTES.txt) give the 19–20 and 26 October and 2 November evidence. The 9 November line supplies a date alone. The ten-item document mentioned on 19 October was not identified.

### E03
**Simulator V2, neural forecasting, dashboard and faults.** [Initial prototype commit](https://github.com/Abdullah77x1/smart-building-digital-twin/commit/91987bf768ffabfc25dd90b78c4570f78cc94789), [Hamad dashboard branch](https://github.com/Abdullah77x1/smart-building-digital-twin/tree/feature/hamad-dashboard/dashboard), [sensor experiment branch](https://github.com/Abdullah77x1/smart-building-digital-twin/tree/feature/simulator-improvements). Local prototype commits include `ee0388d` Model A, `156d8c0` dashboard integration, `a9fcb38` CU-BEMS audit, `8dce0c5` Model B, `f5d96ad` fault injection and `bf5b90b` end-to-end tests. `smart_building_simulator_v2_package.zip` and `SDP_MultiTask_ML_Model_V1.zip` preserve older files.

### E04
**Research synthesis, requirements and specification.** `SDP_Section_4_1_Complete_Combined_Evidence_Review.pdf` and `SDP_Section_4_1_All_Reading_Consolidated.pdf` record which papers were fully reviewed. `SDP_Section_4_2_Requirements_Elicitation_Working_Package.pdf` and `SDP_Section_4_3_System_Specification_Working_Draft.pdf`, 12 November, preserve requirements and the v0.1 specification. See [requirements and specification status](../requirements/BASELINE.md).

### E05
**Real data.** `real_data_package (1).zip` contains data cards, CU-BEMS records and other building datasets. Local Model B evidence is in `model-b-real-cu-bems` and `model-b-dashboard-integration`. [PLEIA/ROBOD draft archive commit](https://github.com/Abdullah77x1/smart-building-digital-twin/commit/1daa888b9d1b419c16c59d8732e89ae50fda0203) is attributable to account `Abdulla18882`. Original data are obtained from their respective publishers. Review redistribution rights per data card.

### E06
**Presentations and design reassessment.** `SDP_I_Week_7_Presentation.pptx`, `SDP_I_Week_7_Improved_Final.pptx`, `SDP_Four_Phases_Advisor_Presentation_WITH_SPECIFICATIONS.pdf`, `SDP_ADVISOR_MEETING_COMPLETE_GUIDE.pdf`, `SDP_Project_Understanding_and_Week7_Recovery_Guide.docx` and `SDP 1 Report.docx`. The earlier report describes stronger evidence and control requirements following feedback. Its earlier rolling-controller endpoint is superseded as the final design.

### E07
**Prototype optimization.** [Baseline comparison](https://github.com/Abdullah77x1/smart-building-digital-twin/commit/24663d475a604e3255aa1481f8f533c31d62b298), [cooling controller](https://github.com/Abdullah77x1/smart-building-digital-twin/commit/0edd005bcd3a03e9382962c366ae5540daa66211). The local branch `codex/hvac-grid-prototype` at `bdc95d8` and integrated branch at `e109f56` document grid search. The seven-day synthetic +2 °C test added 1,925 out-of-band minutes. The feasible choice under the tested constraints was native.

### E08
**EnergyPlus and selection.** `EnergyPlus_Pilot_Preflight_2026-11-13`, `EnergyPlus_V26_Runtime_2026-11-13/ENERGYPLUS_V26_RUNTIME_REPORT.md`, `EnergyPlus_ABA_Pilot_2026-11-13`, `Primary_Environment_Feasibility_2026-11-13` and `SDP Simulation Comparison.docx`. The installed baseline runtime was 26.2.0-4bd7a1f26f. The academic reference cited in the report is the 26.1 engineering manual. The records verify two baselines and read-only callback discovery. Benchmark selection favored packaged repeatable controls.

### E09
**BOPTEST GitHub handoffs.** [Installer and collector](https://github.com/Abdullah77x1/SDP-BOPTEST-Setup/tree/adc1b1aa96bacdb8df61a7cd3344d3d007bc03ff), [historical rolling handoff PR](https://github.com/Abdullah77x1/SDP-BOPTEST/pull/1), and [O25 asset and exclusions](https://github.com/Abdullah77x1/SDP-BOPTEST/blob/72aefb2a50603b2472e72bfe8dc4f66e89a79689/EXCLUDED_FILES_INDEX.md).

### E10
**BOPTEST archive.** Native/colder `stage4e_d2*` plans, raw readbacks and manifests, `SDP_BOPTEST_Pilot/sdp_redesign/ARCHIVE_DATASET.md`, `WARMER_DATASET_EXTENSION.md` and `runtime_state/unified-archive-v1-1/manifest.json`. The final archive has 31 recordings and 26,412 origins across development, public validation and historical comparison.

### E11
**Data timing and forecasting.** Local three experiment Git repositories in the [inventory](../../REPOSITORY_INDEX.md), `step3-e0-data-timing-gate`, `experiments/hvac_low_*` and the final `sdp_redesign/FINAL_FORECAST_COMPARISON.md`. `runtime_state/forecast-comparison-final-v1` retains group definitions, fit outputs, metrics and frozen model. MAE and RMSE report different aspects of error. Forecast selection and hypothesis testing have different evidential requirements.

### E12
**Occupancy.** `SDP_I_Occupancy_Forecasting_Handoff.pdf`, `occupancy_code_handoff_2026-11-23.zip` and local `occupancy_rf_experiment`, `occupancy_value_experiment`. The [experimental index](EXPERIMENT_INDEX.md) separates the schedule replacement and schedule-free ablation.

### E13
**Control experiments.** Earlier [rolling handoff](https://github.com/Abdullah77x1/SDP-BOPTEST/blob/72aefb2a50603b2472e72bfe8dc4f66e89a79689/RECEDING_HORIZON_OPTIMIZER.md), sealed G174/G218/G163 campaign summaries, `FAN_CONTROL_FEASIBILITY.md`, `FAN_CONTROL_INDEPENDENT_VALIDATION.md`, `sdp_redesign/FINAL_COOLING_REPORT.md` and `FINAL_AIRFLOW_FEASIBILITY.md`. Use paired native/intervention comparison, exact comfort criterion and recovery period for each result.

### E14
**Final implementation and archive reproductions.** Local checkout `SDP_BOPTEST_Pilot/sdp_redesign`, including `native_twin.py`, `dashboard_forecast.py`, `dashboard_replay.py`, `native_dashboard.html`, `DASHBOARD_INTEGRATION.md` and `STEP_4B_HANDOFF.md`. The [handoff](../final-implementation/HANDOFF.md) identifies exact package files.

### E15
**Final live check.** `sdp_redesign/STEP_5_LIVE_VERIFICATION.md` and `runtime_state/step-5-live-20261124T0215335612768Z` contain the original run evidence, live captures and receipts for the command, readback and release. Full local records include machine details. The report uses two verified screenshots and aggregate outcomes.

### E16
**AI-assisted development.** [Saved task record index](../ai-prompts/README.md) and report Appendix F. Prompts record requests. Saved tests or implementation files establish the resulting work, while student review is tracked separately.

### E17
**Report and handoff.** Latest supervisor instructions supplied with the brief, final report, [submission workflow](../final-submission/README.md) and [work-package register](../project-management/SDP1_Work_Packages.md). The published team report and administrative route are indexed under final submission.

# SDP I work packages

The [Gantt date register](GANTT_DATE_EVIDENCE.md) explains the dates and uncertainty. The [schedule](GANTT.md) displays the original 19–25 October sprint separately from the reconstructed work. The 26 October note assigns Abdullah Alhashmi to the simulator, Hamad Saleh to the dashboard, Alhoor Alhosani to prediction and Abdulla Alrashdi to optimization. The [team contribution summaries](../../CONTRIBUTIONS.md) describe the assigned roles, documented individual work and shared deliverables.

The AED 7,500 in the proposal is an allowance for cloud services and APIs. No actual expenditure or complete original effort plan was verified.

## WP1 · Initiation and planning

- **Timing and status.** 2026-09-14, 2026-09-28, 2026-10-19 to 2026-10-26. Reconstructed. Complete.
- **Dependencies.** Original proposal and course guidance.
- **Work and deliverables.** Read the proposal and handbook, define outcomes, agree how to divide work and report progress. Proposal and initial plan. Recovered proposal, dated meeting notes and planning sprint.
- **Responsibility.** Team planning. The dated September records establish activity, with named responsibilities recorded on 26 October.
- **Evidence and limits.** D01–D05, D09–D10. These records establish planning activity; the precise kickoff date and individual effort hours are not documented.

## WP2 · Literature and patent research

- **Timing and status.** 2026-09-22 to 2026-09-28, 2026-10-19 to 2026-11-24. Reconstructed. Complete.
- **Dependencies.** WP1.
- **Work and deliverables.** Review digital twins, datasets, thermal physics, forecasting and control. Check related patents. Literature comparison and references. Recovered Section 4.1 dossier and bounded two-grant search.
- **Responsibility.** Shared team literature and patent research.
- **Evidence and limits.** D04–D05, D09, D14. A 27 September participant message reports reading the three articles. Full-paper use is tied to the later saved dossier.

## WP3 · Requirements and specification

- **Timing and status.** 2026-09-28, 2026-10-04 to 2026-10-12, 2026-10-20 to 2026-11-12. Reconstructed. Partial.
- **Dependencies.** WP1, WP2.
- **Work and deliverables.** Specify dashboard behavior, model signals and test limits. Review functional and non-functional needs. Requirements and testable baseline. Recovered Section 4.2 and v0.1 Section 4.3 draft.
- **Responsibility.** Shared team requirements and specification development.
- **Evidence and limits.** D05–D08, D14. Early slides document proposed scope and tests. The available Section 4.3 record is a working specification; formal approval is not documented.

## WP4 · Real-building data and forecasting

- **Timing and status.** 2026-10-05 to 2026-11-08. Reconstructed. Complete.
- **Dependencies.** WP2, WP3.
- **Work and deliverables.** Audit CU-BEMS Zone 4, compare measured forecasting and investigate other datasets. Data suitability and real-data benchmark. Recovered CU-BEMS audit, Model B and data cards.
- **Responsibility.** Abdullah Alhashmi’s documented CU-BEMS audit and Model B commits; the broader dataset investigations are recorded as team research.
- **Evidence and limits.** D06–D08, D12–D13. Dated CUBEMS design, header analysis and notebook precede the local Model B work.

## WP5 · Simulator V2 and synthetic data

- **Timing and status.** 2026-10-23 to 2026-11-02. Reconstructed. Complete.
- **Dependencies.** WP3, WP4.
- **Work and deliverables.** Use a one-zone resistance-capacitance model and generate weather-, occupancy- and schedule-driven data. Runnable simulator, equations and synthetic baseline. Initial upload and integrated demo recovered.
- **Responsibility.** Abdullah Alhashmi assigned simulator on 26 October. Git shows prototype imports, documentation and integration.
- **Evidence and limits.** D11–D12. The 23 October Simulator V2 archive precedes the Git upload.

## WP6 · Initial ML and sensor robustness

- **Timing and status.** 2026-10-26 to 2026-11-02. Reconstructed. Complete.
- **Dependencies.** WP4, WP5.
- **Work and deliverables.** Train synthetic Model A, evaluate chronological generalization, test noise, missing values and stuck sensors. Prototype neural forecasting and robustness checks. Recovered model package and local diagnostic commits.
- **Responsibility.** Alhoor Alhosani was assigned machine learning and prediction. Abdullah Alhashmi has documented local Model A and fault-test commits. The prototype forecasting deliverables are recorded as team work.
- **Evidence and limits.** E02, E03. Fault work remained in the prototype. Final BOPTEST fallback covers insufficient history and validation failures.

## WP7 · Initial cooling optimization

- **Timing and status.** 2026-10-26 to 2026-11-02. Reconstructed. Complete.
- **Dependencies.** WP5.
- **Work and deliverables.** Compare baseline and adjusted setpoints, apply a comfort constraint and inspect trade-offs. Prototype controller and comparison. Synthetic one-day and seven-day results recovered.
- **Responsibility.** Abdulla Alrashdi was assigned optimization. Controller and comparison commits are recorded under the account `Abdulla18882`; Abdullah Alhashmi has documented local grid-search commits. The individual contribution record preserves the basis of the account attribution.
- **Evidence and limits.** E02, E03, E07. Short favorable simulation failed to generalize into a comfort-compliant seven-day alternative.

## WP8 · Prototype dashboard and reviews

- **Timing and status.** 2026-10-20 to 2026-11-02. Reconstructed. Complete.
- **Dependencies.** WP4, WP5, WP6.
- **Work and deliverables.** Design the interface and show synthetic history, forecast and what-if comparisons. Prepare advisor demonstrations. Prototype dashboard and presentations. Recovered dashboard branch and local demo commits.
- **Responsibility.** Hamad Saleh assigned dashboard. Earlier dashboard branch commits by P00l7, with matching provenance. Abdullah Alhashmi’s local integration commits.
- **Evidence and limits.** E02, E03, E06. The feedback source records a date and topics, with reviewer identity unconfirmed for some notes.

## WP9 · Simulator evaluation and BOPTEST choice

- **Timing and status.** 2026-11-08 to 2026-11-14. Reconstructed. Complete.
- **Dependencies.** WP4, WP5, WP7, WP8.
- **Work and deliverables.** Review EnergyPlus, run interface and baseline suitability checks, compare with BOPTEST. Simulator decision and bounded baseline evidence. BOPTEST selected for reproducible command/readback workflow.
- **Responsibility.** Shared team simulator evaluation and design decision, documented in the EnergyPlus study files and selection records.
- **Evidence and limits.** E06, E08. EnergyPlus baselines ran, but a completed paired controller workflow was unavailable.

## WP10 · BOPTEST setup and data collection

- **Timing and status.** 2026-11-14 to 2026-11-24. Reconstructed. Complete.
- **Dependencies.** WP9.
- **Work and deliverables.** Pin BESTEST Air 0.9.0, collect native and colder pairs, then add warmer-control cases. Setup tooling and 31-recording archive. Recovered manifests and command receipts.
- **Responsibility.** BOPTEST setup publication by `Abdullah77x1`; data collection and review are documented as shared team deliverables.
- **Evidence and limits.** E09, E10, E11. The setup repo packages installation and collection. The final archive and raw replays have separate delivery requirements.

## WP11 · Feature selection and model evaluation

- **Timing and status.** 2026-11-16 to 2026-11-24. Reconstructed. Complete.
- **Dependencies.** WP10.
- **Work and deliverables.** Expand 8 to 16 targets, screen inputs, audit unusually small errors, use grouped comparisons and freeze 27-input forest. Input/output manifest, frozen model and score tables. Development +30 min temperature MAE 0.11545 °C.
- **Responsibility.** Abdullah Alhashmi’s three documented local offline experiment repositories; later model evaluation is recorded as team work in the machine learning responsibility area.
- **Evidence and limits.** E10, E11. Repeated weather and known schedules limit claims. The reserved public groups were previously examined.

## WP12 · Occupancy forecasting

- **Timing and status.** 2026-11-23 to 2026-11-24. Reconstructed. Complete.
- **Dependencies.** WP4, WP10, WP11.
- **Work and deliverables.** Compare UCI classifiers and failed transfer, then test replacing schedule and adding probability without schedule or clock. Two controlled HVAC comparisons. Final system retains known scheduled occupancy.
- **Responsibility.** Team occupancy research, documented through the teammate handoff and local A/B Random Forest experiment artifacts.
- **Evidence and limits.** E12. Fixed lighting and thermostat cues limit claims for irregular occupancy. Historical pre-cooling code is separate.

## WP13 · Advanced HVAC optimization

- **Timing and status.** 2026-11-18 to 2026-11-24. Reconstructed. Complete.
- **Dependencies.** WP7, WP10.
- **Work and deliverables.** Test fixed, rule-based, action forest, Ridge, StepModel, fan-only and coordinated approaches. Matched control evidence, acceptance criteria and negative findings. Autonomous optimization declined.
- **Responsibility.** Team control research in the optimization responsibility area, supported by earlier controller commits and the historical rolling handoff.
- **Evidence and limits.** E07, E13. Some small savings came with discomfort. Wrong-sign electrical response and incomplete recoveries limited decisions.

## WP14 · Final supervised integration

- **Timing and status.** 2026-11-23 to 2026-11-24. Reconstructed. Complete.
- **Dependencies.** WP10, WP11, WP13.
- **Work and deliverables.** Combine observation, 27-input frozen inference, operator request validation, readback and native release. Supervised dashboard and native/warmer offline modes. Local checkout proof.
- **Responsibility.** Shared integration of simulation, forecasting, visualization and control research. The final source and verification records document the integrated team system.
- **Evidence and limits.** E11, E14. Historical O25 and rolling controller remain separate. The final source and assets are available through the [private release handoff](../final-implementation/HANDOFF.md); access requires repository permission.

## WP15 · Testing and live verification

- **Timing and status.** 2026-10-07 to 2026-10-12, 2026-10-31 to 2026-11-02, 2026-11-24. Mixed evidence. Complete.
- **Dependencies.** WP4, WP5, WP6, WP8, WP14.
- **Work and deliverables.** Reproduce model and both day-196 replays, exercise safety/feedback units and verify one controlled live session. 852 scored origins per replay, 59 regression checks and one verified live lifecycle.
- **Responsibility.** Team testing and verification, documented in the live and offline test artifacts.
- **Evidence and limits.** D07–D08, D12, D17. Early data checks, prototype testing and final offline/live verification are separate periods.

## WP16 · Reporting and private handoff

- **Timing and status.** 2026-10-04 to 2026-10-12, 2026-11-22 to 2026-11-24. Reconstructed. Report and private handoff published.
- **Dependencies.** WP1–WP15.
- **Work and deliverables.** Compile report, semester progress, source index, individual evidence and reproducible handoff. The Word and PDF report, semester documentation, contribution records and software handoff are published in the private main repository. Official forms and course submission are handled separately.
- **Responsibility.** Shared team reporting and publication, with four role-based individual contribution summaries.
- **Evidence and limits.** D06, D08, D17–D18. Early review material and final preparation occupy separate periods. Week 14 deadline announcement pending.

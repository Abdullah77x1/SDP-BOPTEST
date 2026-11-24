# LLM-Enabled Intelligent Digital Twin for Smart Building Energy Management

**Khalifa University · COSC 497 · COSC14 · Fall 2026**

**Team** · Abdullah Alhashmi, Hamad Saleh, Alhoor Alhosani and Abdulla Alrashdi

We investigated how a digital twin can forecast HVAC behavior and evaluate changes in building operation. The original proposal included multi-zone simulation, natural-language interaction and automatic energy management. The verified SDP I system is a single-zone simulated twin. It compares forecasts with measurements and allows one supervised cooling action.

## Project record

- [Semester progress](PROJECT_PROGRESS.md), [editable schedule and work packages](docs/project-management/GANTT.md), and [meeting and feedback records](docs/meetings/README.md).
- [Repository inventory](REPOSITORY_INDEX.md), [published research records](docs/research/artifacts/README.md), [experiment results](docs/research/EXPERIMENT_INDEX.md), and [engineering decisions](docs/design-decisions/DECISION_RECORDS.md).
- [Requirements and specification](docs/requirements/BASELINE.md), [individual contributions](CONTRIBUTIONS.md), [AI-assisted development](docs/ai-prompts/README.md), and [final submission](docs/final-submission/README.md).

## Final report

[Word](docs/final-submission/COSC14%20SDP1%20Final%20report.docx) · [PDF](docs/final-submission/COSC14%20SDP1%20Final%20report.pdf)

## Run or verify the final dashboard

Download the [final implementation ZIP](https://github.com/Abdullah77x1/SDP-BOPTEST/releases/download/cosc14-sdp1-offline-v1/COSC14_SDP1_Offline_Handoff.zip) from the private release and unpack it. The [handoff guide](docs/final-implementation/HANDOFF.md) lists the model location, Python 3.12.14 setup, replay commands and optional live BOPTEST connection. Review the [dashboard source](docs/final-implementation/source/native_twin.py), [ordered model schema](docs/final-implementation/selected_model.json) and [saved regression results](docs/final-implementation/verification/offline-regression.txt).

The final entry point is `sdp_redesign.native_twin`. It uses BOPTEST BESTEST Air 0.9.0 and a frozen 27-input, 16-output Random Forest. Forecast leads are +5, +10, +15 and +30 minutes. The browser shows room and outdoor conditions, HVAC power, predictions, matched measurements, energy and comfort. A human can request 24.5 °C for 45 simulated minutes in the supported live window. The dashboard verifies the effective setting and native release.

## Repositories and design history

| Repository | Role |
|---|---|
| [SDP-BOPTEST](https://github.com/Abdullah77x1/SDP-BOPTEST) | Main project index. Its existing tracked handoff and [PR 1](https://github.com/Abdullah77x1/SDP-BOPTEST/pull/1) are the earlier O25 and rolling-controller research. [Earlier instructions](https://github.com/Abdullah77x1/SDP-BOPTEST/blob/2abf4e1846f22149a65a45d35454b4a4b0d8c5f9/HOW_TO_RUN.md) retain that context. |
| [SDP-BOPTEST-Setup](https://github.com/Abdullah77x1/SDP-BOPTEST-Setup) | Official pinned simulator deployment, Windows setup, Docker configuration and research collector. Needed for a live simulator install. |
| [smart-building-digital-twin](https://github.com/Abdullah77x1/smart-building-digital-twin) | Simulator V2, initial neural forecasting, fault experiments, synthetic baseline comparisons and Hamad’s prototype dashboard. |

We began with CU-BEMS and other measured office datasets, built Simulator V2 for controlled prototype tests, and examined EnergyPlus before choosing BOPTEST. We used BOPTEST to compare forecasting methods and HVAC controls with verified command readback. Several tested automatic or airflow policies gave small savings, increased discomfort, or had incomplete recovery evidence. The frozen model forecasts ordinary operation. The final software delegates actuation decisions to the operator. Multi-zone operation, the LLM interface and validated automatic optimization remain future work.

The three team repositories are private and require authorized GitHub access. The [IBPSA BOPTEST v0.9.0 repository](https://github.com/ibpsa/project1-boptest/tree/v0.9.0) is the external upstream. [Submission information](docs/final-submission/README.md)

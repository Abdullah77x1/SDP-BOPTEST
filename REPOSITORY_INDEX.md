# Project repository index

COSC14 · Fall 2026. This read-only inventory records GitHub and local evidence examined on 24 November 2026. [Full audit and findings](AUDIT_FINAL_SUBMISSION.md) · [Semester progress](PROJECT_PROGRESS.md) · [Handoff](docs/final-implementation/HANDOFF.md)

## Three private GitHub repositories

| Repository | Role and period supported by records | Verified GitHub branches and evidence | Relationship to final reproduction |
|---|---|---|---|
| [SDP-BOPTEST](https://github.com/Abdullah77x1/SDP-BOPTEST) | Main project documentation home. GitHub commits 22–23 Nov. Final release and semester archive dated 24 Nov. | Earlier `main` snapshot [2abf4e1](https://github.com/Abdullah77x1/SDP-BOPTEST/commit/2abf4e1846f22149a65a45d35454b4a4b0d8c5f9), `feature/complete-boptest-handoff` [72aefb2](https://github.com/Abdullah77x1/SDP-BOPTEST/commit/72aefb2a50603b2472e72bfe8dc4f66e89a79689). [PR 1](https://github.com/Abdullah77x1/SDP-BOPTEST/pull/1) merged via [4f4b742](https://github.com/Abdullah77x1/SDP-BOPTEST/commit/4f4b742eeafad318a1ccc229e3ce4d7f8492e3de). Rolling handoff by account `Abdullah77x1`. Main ZIP upload by `Abdulla18882`; its downloaded archive was verified as the earlier rolling handoff. | Houses shared runtime modules and historical O25 checkpoint, retrieved through Git LFS in a fresh authenticated clone. The earlier snapshot predates the final supervised entry point and model. The [private release handoff](docs/final-implementation/HANDOFF.md) supplies the final dashboard, frozen 27-input model and replay dependencies. Expected tracked paths for the historical snapshot are listed in the pre-publication audit. |
| [SDP-BOPTEST-Setup](https://github.com/Abdullah77x1/SDP-BOPTEST-Setup) | Official pinned simulator setup and research collector, 18 Nov. | Earlier `main` snapshot [adc1b1a](https://github.com/Abdullah77x1/SDP-BOPTEST-Setup/commit/adc1b1aa96bacdb8df61a7cd3344d3d007bc03ff); setup import [7af2404](https://github.com/Abdullah77x1/SDP-BOPTEST-Setup/commit/7af24047cc82348deb50f26120ceed0e347fb5a5), account `Abdullah77x1`. Readme, `Setup.ps1`, `compose.team.yml`, `SHA256SUMS.json`, `research/`. No PR found in the accessible results. | Install guide and external dependency for a live benchmark setup. Offline replay uses existing recordings and does not require a running Docker service. |
| [smart-building-digital-twin](https://github.com/Abdullah77x1/smart-building-digital-twin) | Early Simulator V2, Multi-Task ML V1, dashboard, synthetic optimization and dataset research. GitHub history 26 Oct–15 Nov. | Earlier `main` snapshot [7f1380e](https://github.com/Abdullah77x1/smart-building-digital-twin/commit/7f1380e8b7a867c54e21855de1504d1a0d3797d2), `feature/hamad-dashboard` [a1f5d69](https://github.com/Abdullah77x1/smart-building-digital-twin/commit/a1f5d690740ef75475e8752928f5186ca79af7ec), `feature/simulator-improvements` [8f5eed0](https://github.com/Abdullah77x1/smart-building-digital-twin/commit/8f5eed0fe87fefbda09e5cbfc6244285faa0e9cf). Accounts `Abdullah77x1`, `P00l7`, and `Abdulla18882` have relevant evidence. No PR surfaced in the connected search. An earlier report mentions a dashboard PR without a verifiable number or URL. | Historical context, early contributor evidence and prototype reproduction. The final BOPTEST dashboard does not import this repository. |

## External dependency

[IBPSA project1-boptest](https://github.com/ibpsa/project1-boptest/tree/v0.9.0) is the public upstream for the pinned simulator and BESTEST Air case.

## Local experiments and worktrees

| Local repository or linked worktree | Period, head and author evidence | Important files and role | Publication relationship |
|---|---|---|---|
| `experiments/hvac_16_outputs_v2_0_0` | 16 Nov · `sdp/hvac-16-outputs-v2.0.0`, `3180d2c` and `74cf947`, Abdullah Alhashmi | Offline 16-output reconstruction, target contract, baseline and byte-preserving checkout. | Standalone local Git repository with no remote configured. Use historical evidence reference. |
| `experiments/five_model_hvac16_v1_0_0` | 17 Nov · `sdp/five-model-hvac16-v1.0.0`, `7aa2866`, Abdullah Alhashmi | Five-model scores and diagnoses. Final app imports the sibling `config.py`, `estimators.py`, `io_utils.py`. | Standalone local Git repository with no remote configured. Distribute required helper bytes in reviewed final package. |
| `experiments/native_only_five_model_hvac16_v1_0_0` | 17 Nov · `sdp/native-only-five-model-hvac16-v1.0.0`, `0c44d7f`, `79f5273`, Abdullah Alhashmi | Native-only model comparison and archive audit. | Standalone local Git repository with no remote configured. Earlier research evidence. |
| `cu-bems-zone4-audit` | 2 Nov · `codex/cu-bems-zone4-audit`, `a9fcb38` | CU-BEMS Zone 4 audit and readiness plan. | Linked to the prototype Git database. |
| `model-b-real-cu-bems` | 2 Nov · `codex/model-b-real-cu-bems`, `8dce0c5` | Real-data benchmark and frozen Model B. | Linked prototype worktree. |
| `model-b-dashboard-integration` | 2 Nov · `codex/model-b-dashboard-integration`, `2123ee0` | Real-data display and inference integration. | Linked prototype worktree. |
| `ornl-optimization-feasibility` | Local branch at `2123ee0` | Separate task workspace for ORNL feasibility. The common head alone cannot confirm all working files. | Linked prototype worktree. |
| `ornl-policy-comparison` | 2 Nov · `codex/ornl-policy-comparison`, `5b36304` | Recorded ORNL policy and weather comparisons. | Linked prototype worktree. |
| `sensor-fault-integration` | 2 Nov · `codex/sensor-fault-integration`, `f5d96ad` | Sensor noise/fault injection and causal handling. | Linked prototype worktree. |
| `final-integrated-demo` | 2 Nov · `codex/final-integrated-demo`, `bf5b90b` | Advisor prototype demo spanning six capabilities. | Linked prototype worktree. Earlier Simulator V2 demo. |

Additional local-only prototype refs include grid search `bdc95d8`, dashboard grid integration `e109f56`, Model A/dashboard `156d8c0`, local simulator improvements `ee0388d` and end-to-end demo `65152f5`. The accessible owned and collaborator repository listings, local remote configs and archive inventories did not identify an additional independent team GitHub repository. Recovered EnergyPlus and occupancy materials are folders or ZIP handoffs. Upstream BOPTEST and EnergyPlus are third-party projects.

Link all three project repositories from the central README. Link historical commits only where the object is confirmed on GitHub. The local commit IDs above identify the corresponding workspace evidence. GitHub links identify remotely accessible objects.

## Final release and semester archive

[Software, model and reproduction](docs/final-implementation/HANDOFF.md) · [Research assets](docs/research/artifacts/README.md) · [Progress](PROJECT_PROGRESS.md) · [Final report](docs/final-submission/README.md)

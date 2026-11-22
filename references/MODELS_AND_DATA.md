# Models and Data Evidence

<a id="model-001"></a>

## MODEL-001 — O25 Random Forest

The original observational Random Forest issues the +5, +10, +15 and +30-minute forecasts. Git LFS fetches the exact [33,142,394-byte joblib checkpoint](../ml_research_v1_0_0/models/observational_RandomForest.joblib). [Windows setup](../HOW_TO_RUN.md) verifies its frozen SHA-256.

- Runtime path <code>ml_research_v1_0_0/models/observational_RandomForest.joblib</code>
- SHA-256 <code>57159e038df9f27f303246426ae55375441440c3352b3bea396c3e4f069bcce3</code>

## Active action-response models

The [rolling model](../SDP_BOPTEST_Pilot/final_energy_control/rolling_model.py) and [earlier fixed-response model](../SDP_BOPTEST_Pilot/final_energy_control/optimizer_model.py) use the bundled G218 seal and original G174 and G163 calibration inputs. They load no second serialized estimator. O25 forecasts remain observational.

Historical training and benchmarking use the optional sources below. [Experiment evidence index](EXPERIMENT_EVIDENCE_INDEX.md)

<a id="data-002"></a>

## DATA-002 — Development feature overlay

External · <code>ml_research_v1_0_0/development_overlay.npz</code> · SHA-256 <code>86e7b530974b4a8953a5a34fedaa80742fadc686dd821e2b5f02b25afe467632</code>

<a id="data-003"></a>

## DATA-003 — Dataset provenance and partition assignment

External · <code>ml_research_v1_0_0/DATASET_PROVENANCE.json</code> · SHA-256 <code>caa4403a1d3e36737036b00b5466d1c20b39b5bd6c0effba468e7e7337e99ee6</code>

<a id="data-004"></a>

## DATA-004 — Frozen model comparison results

External · <code>ml_research_v1_0_0/MODEL_COMPARISON_RESULTS.csv</code> · SHA-256 <code>cf8c63cfbce457336d0dd1ff995531fe55c8be7ed5ce7b82b4d5d1e69dc70c2c</code>

<a id="data-005"></a>

## DATA-005 — Frozen feature ablation results

External · <code>ml_research_v1_0_0/MULTI_MODEL_ABLATION_RESULTS.csv</code> · SHA-256 <code>e551d5ce99cc08c7b0d53b981dc21fb4fa62dbdb5c7b1b33cd53f217eb2480e5</code>

<a id="data-006"></a>

## DATA-006 — V3.1 dataset manifest

External · <code>archive/SDP_BOPTEST_FINAL_TEAM_PACKAGE_v3_1/datasets/DATASET_MANIFEST.json</code> · SHA-256 <code>75ce85ed7235676bfc1e44163d30dda29053698b2030791b1c84c28ed737f4fd</code>

# Excluded Files Index

The original **SDP_BOPTEST_TEAM_PACKAGE.zip** remains intact and contains the omitted members in its original folder layout. Its SHA-256 is `106589797dc7f98f80466abd64006a02213c387c2777e38e65d9f60cd04817db`. Use the [complete excluded file inventory](references/EXCLUDED_FILES.tsv) for exact member paths, prior sizes and SHA-256 hashes. The older V4 archive and project workspace retain still earlier source material.

| Work | Core contents | Original external evidence |
| --- | --- | --- |
| Current rolling demo and G218 matched replay | Complete sealed batch members. G218 runtime histories are restored by core setup | Earlier screening, exploratory analyses, and related development records |
| G174 and G163 | Original comparison scores, selected exact G174 warm/native and G163 native/fixed calibration input files | Full campaign and receipt replay, including G163 predictive arm history and full original batch seals. G174 original native-equivalence and full saved-history checks |
| G258 and G218 fan-only and G258 joint | Original comparison, frozen configuration, cleanup and command outcome summaries | Complete per-step histories and raw API records for independent reintegration |
| Original fixed live and prior smoke review | Original fixed-live summary and retained narrative references | Detailed old live browser records and original per-step evidence |
| ML training, ablation and older benchmarks | Active O25 checkpoint and inference contract, action-response implementation, report’s published comparison tables | Full training/validation stores, grouped scores, held samples, development overlay and earlier artifacts |

The [experiment index](references/EXPERIMENT_EVIDENCE_INDEX.md) labels local and external evidence per campaign. The original ledgers, acceptance results, frozen readbacks, and evidence contents remain unchanged in the original package or repository. Prepared experiments still have no measured outcome. [Campaign-specific historical locators](references/HISTORICAL_LOCATORS.md#evidence-3976b0c80731)

## Workspace-only publication exclusions

Two original JSON files contain workstation paths. They are available through the original evidence archive and are listed with their original SHA-256 hashes in the [excluded inventory](references/EXCLUDED_FILES.tsv).

| Original relative path | Role |
| --- | --- |
| ml_research_v1_0_0/EXPERIMENT_CONFIG.json | Historical ML training configuration |
| SDP_BOPTEST_Pilot/energy_savings_g174_v1/NATIVE_REFERENCE_VERIFICATION.json | Historical G174 native-equivalence record |

The published calibration inputs, summary results, and acceptance decisions retain their original bytes. The earlier 40 MB distribution ZIP and its distribution-only audits are kept in the workspace. Git LFS carries the byte-identical O25 file. Git carries the pinned FMU and runtime evidence bundles without duplicate checkpoint or FMU encodings.

## Restore a specific archive prefix

From the checkout root, give the path to the original ZIP and the exact directory in the inventory. Use a separate review copy as the destination when restoring dependencies for another replay.

```powershell
$archive = Read-Host 'Path to SDP_BOPTEST_TEAM_PACKAGE.zip'
$prefix = 'SDP_BOPTEST_Pilot/final_energy_control/optimizer_runtime_state/batches/OPTIMIZER_G163_NATIVE_FIXED_PREDICTIVE'
py -3.12 -B .\scripts\Restore-Core-Evidence.py $archive $prefix .\review-copy
```

The restore helper verifies the identity of the entire source ZIP and refuses to overwrite differing files. Restore a complete named batch before trying the corresponding full historical replay. The core supports reproduction of its current model qualification and included replay observations. Reproducing other original campaign evaluations requires their complete evidence and appropriate archived dependencies.

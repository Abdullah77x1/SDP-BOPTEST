# GitHub Handoff

## Source and storage

The migration uses the verified BOPTEST core handoff and compares its active entry points with the working BOPTEST project. The rolling controller, action-response model, optimizer, dashboard, safety checks, collectors, and original report figures preserve their verified implementation bytes. Git retains line endings for the hash-bound sources and metadata.

| Required or retained asset | Bytes before Git packing | Storage |
| --- | ---: | --- |
| Frozen O25 Random Forest checkpoint | 33,142,394 | Git LFS. Original joblib, restored directly by the LFS client |
| Pinned BESTEST Air FMU | 16,126,481 | Git. Original FMU |
| G218 sealed evidence used by the action model and matched replay | 4,616,876 | Git. Lossless asset with SHA-256 for every original member |
| Archived G174/G163 calibration and genuine rolling demonstration | 1,977,736 | Git. Lossless asset with SHA-256 for every original member |
| Editable comprehensive report | 1,463,151 | Git. Original Word document |

The O25 file SHA-256 is [recorded in the model guide](MODELS_AND_DATA.md#model-001). The [asset manifest](../assets/ASSETS.json) records the FMU, packed evidence, and original per-file hashes. The [external evidence index](../EXCLUDED_FILES_INDEX.md) identifies historical full batches and training artifacts retained separately.

## Checkout verification

The clean staged checkout passed **13 of 13** essential regressions using the pinned dependency environment. O25 reproduced all four saved forecast leads, the existing rolling qualification passed, and the read-only rolling binding matched the verified core byte for byte. Both genuine recordings served through the existing dashboard. The rolling replay displayed command verification and recovery over 41 recorded advances. The G218 replay displayed 864 advances per arm, 0.074920 kWh measured savings and the original failed comfort acceptance. These checks used the archived results and made no simulator calls. [Windows verification commands](../HOW_TO_RUN.md)

The [core package verification](../CORE_PACKAGE_VERIFICATION.md) records the earlier clean extraction and Chrome rendering check.

Historical experiment authorization records and ledger evidence document already measured runs. Live execution of a future run requires the exact pinned Docker service and a separately versioned unused campaign with explicit authorization.

# CORE Package Verification

This record describes the original BOPTEST core distribution. The [GitHub handoff](references/GITHUB_HANDOFF.md) documents the current checkout, including direct Git LFS delivery of the same checkpoint.

The core runs the current BOPTEST digital twin and replays the sealed rolling session and G218 matched comparison offline. Both modes use the existing application. The live mode requires the pinned external BOPTEST worker and an unused campaign with explicit authorization. [Windows setup](HOW_TO_RUN.md)

| Verification | Check |
| --- | --- |
| Clean extraction | Extracted to a new Windows directory with spaces. Initialized the model, FMU and retained evidence from ZIP contents using the existing pinned Python dependency environment. |
| Active ML checkpoint | Restoration verifies the original SHA-256. O25 reproduced the stored +5, +10, +15 and +30-minute forecasts from the genuine rolling session's 10:55 observation prefix. Persistence inference also loaded. |
| Action-response model and optimizer | Existing qualification passed from local, original archive inputs. Verified maximum supported horizon was 165 minutes. The offline controller and its safety and command-verification tests retained their original restrictions. |
| Rolling dashboard | The existing loopback dashboard rendered the replay navigation and measured temperatures in Chrome. Seeking the original 41 advances exposed O25 forecasts on supported native paths and the model's expected unavailability during warmed overrides. The independent optimizer feedback, 24.5°C readback and native recovery remained available. The single-arm replay showed no measured savings baseline. |
| G218 matched dashboard | Both recorded 864-step arms opened. The displayed 0.074920 kWh reduction and frozen failed acceptance outcome matched the original archive. |
| Essential regression suite | 13 of 13 passed across the rolling, digital twin, and live collector test modules. These automated checks include fabricated transports. The replay check above uses genuine archived measurements. |
| Read-only live configuration | The archived application and clean extraction produced the same rolling binding description. No worker deployment, simulator advance, experiment or training ran. |
| Report | Microsoft Word paginated the DOCX to 45 pages. Original figure bytes, result tables, engineering equations and captions were retained. Report source links resolve against setup-restored paths and the evidence index. The Markdown remains editable beside the Word file. |

The installed Python dependencies were reused to verify the isolated copy. The optional raw histories, training data, and historical experiment receipts remain in the original package. Offline replay and current action-response qualification succeeded with those files absent. The [excluded file index](EXCLUDED_FILES_INDEX.md) identifies the original files needed for older analyses, complete historical replays and campaign re-integration.

The original-archive restore helper recovered an omitted development overlay into a separate review directory. Its SHA-256 matched the external file inventory. The pinned dependency environment also passed its package consistency check.

The rolling controller remains partial receding-horizon control. Economic early release, delayed starts and re-entry remain unqualified. The core leaves the unsuccessful fan-only and joint actions outside the autonomous optimizer. The archive preserves the original energy and comfort decisions.

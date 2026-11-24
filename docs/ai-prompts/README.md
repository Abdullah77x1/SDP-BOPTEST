# AI-assisted development records

Report §1.4 discloses AI assistance. Appendix F records excerpts of genuine project instructions and their deliverables. The table points to original evidence where it survives. This archive was compiled on 24 November. Personal account data and unrelated chats should stay outside the project record.

| Task | Source and instruction excerpt | Evidence for decisions and review |
|---|---|---|
| Forecast data timing | `SDP_PRE_STEP3_READ_ONLY_AUDIT.md`, `step3-e0-data-timing-gate`. Check that inputs were available when each forecast was issued. | Eligibility receipts, grouped folds and schema contracts. Original reviewer names still need confirmation. |
| Model comparison and low errors | `experiments/five_model_hvac16_v1_0_0/USER_REQUEST.md`. Compare five model families and check difficult conditions and unusually low errors. | Saved diagnostics and selected-model report. Record who checked reproduction. |
| Replace scheduled occupancy | `occupancy_rf_experiment/README.md` and supplied experiment brief. Remove two schedule fields, add only the future occupancy probability, use grouped out-of-fold estimates. | Numeric A/B tables and classifier-fit membership. |
| Schedule-free occupancy ablation | `occupancy_value_experiment/README.md` and supplied experiment brief. Give both models identical features except for the added probability. | Matched weather groups, forecast scores and saved arrival evaluation. |
| Final supervised verification | `sdp_redesign/STEP_5_LIVE_VERIFICATION.md` and saved recorded procedure. Verify the active command and return to native control against readbacks. | Saved receipts, actual values and cleanup proof. |
| Final report and semester evidence | Team’s final submission revision briefs and supplied historical notes. Require evidence for dates, claims and contributors. | Final report, original meeting notes and separate student records. |

A prompt describes a request. Source, tests and decisions show what was actually done. Students should add any missing admissible prompt and outcome excerpts and identify their own review before signing the declaration.

Early dated planning records were recovered from private project chats. The [date evidence](../project-management/GANTT_DATE_EVIDENCE.md) identifies their titles, dates, corroborating documents and limits. The archive includes task-relevant excerpts and summaries.

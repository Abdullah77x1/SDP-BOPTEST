# GitHub evidence before final publication

**Historical record — pre-publication audit (24 November 2026).** The findings below describe the repository before the final upload and are retained unchanged as historical evidence. The final implementation and semester records have since been published privately. See the [current README](README.md), [final handoff](docs/final-implementation/HANDOFF.md), [team contributions](CONTRIBUTIONS.md) and [final report](docs/final-submission/README.md) for the current project state.

Read-only source and GitHub checks were performed on 24 November 2026. The authenticated owner inventory returned the three private project repositories below. The collaborator inventory yielded no additional repository. Targeted searches included the owner’s related names, COSC14, the identified dashboard account and the optimization account. The latter account query was unavailable to the connector. No additional project repository or fork was verified in the accessible scope. The local worktrees and experiment repositories remain documented in the [repository index](REPOSITORY_INDEX.md).

| Repository | What was verified |
|---|---|
| [SDP-BOPTEST](https://github.com/Abdullah77x1/SDP-BOPTEST) · private | `main` at `2abf4e1846f22149a65a45d35454b4a4b0d8c5f9` and `feature/complete-boptest-handoff` at `72aefb2a50603b2472e72bfe8dc4f66e89a79689`. Merged [PR #1](https://github.com/Abdullah77x1/SDP-BOPTEST/pull/1) from `Abdullah77x1`. Tracked README and archive contain the earlier O25 and rolling controller. |
| [SDP-BOPTEST-Setup](https://github.com/Abdullah77x1/SDP-BOPTEST-Setup) · private | `main` at `adc1b1aa96bacdb8df61a7cd3344d3d007bc03ff`. Setup scripts, Compose configuration, checksums and research collector. No PR in the accessible search. |
| [smart-building-digital-twin](https://github.com/Abdullah77x1/smart-building-digital-twin) · private | `main` at `7f1380e8b7a867c54e21855de1504d1a0d3797d2`; `feature/hamad-dashboard` at `a1f5d690740ef75475e8752928f5186ca79af7ec`; `feature/simulator-improvements` at `8f5eed0fe87fefbda09e5cbfc6244285faa0e9cf`. Earlier prototype, machine learning and controls. Verified account contributions include `Abdullah77x1`, `P00l7` and `Abdulla18882`. Dashboard-source provenance and unresolved account mapping are in the two individual records. No matching public or accessible PR number was found for the reported dashboard PR. |
| [IBPSA project1-boptest](https://github.com/ibpsa/project1-boptest/tree/v0.9.0) · public upstream | The team uses the tagged 0.9.0 implementation and the BESTEST Air case. The external upstream is separate from project-owned repositories. |

## Fresh private clone and historical LFS

An authenticated isolated clone of SDP-BOPTEST main verified the earlier checkpoint. Git LFS 3.8.1 retrieved the complete 33,142,394-byte object. The SHA-256 matched the remote pointer, `57159e038df9f27f303246426ae55375441440c3352b3bea396c3e4f069bcce3`. The fetched tracked ZIP `SDP-BOPTEST-main.zip` passed its member integrity check. Its 488 entries include the earlier O25 and rolling controller. It has no `sdp_redesign/native_twin.py`, final selection metadata, or final model. ZIP SHA-256 `ae4efcf7b6a0643f74b5074dae6fc64c1e80d124b2b53f64761f3988ac2ab22c`. The direct remote paths for the final entry point and model metadata also returned missing-path responses on both main and the earlier handoff branch.

## Final implementation and publication status

The local, staged package is `COSC14_SDP1_Offline_Handoff.zip`. It supplies the final dashboard, checkpoint, schemas, two sealed replays, pinned dependencies, tests and selected original live receipts. Every one of its 8,545 declared payload files verified against the archive manifest. The archive contains its 8,546th member, the manifest itself. Credential-pattern and excluded-directory checks were applied to the payload. No third-party real-building data, team environment file, Git metadata or virtual environment is part of this package. The pinned BOPTEST license is retained with the FMU. Check attribution and rights for any later supplement, including CU-BEMS and weather data mixed into prior archives.

The draft report contains course roster identifiers. Limit its final private distribution to the approved course route. Signatures, individual logbooks and raw data belong in authorized storage or the approved submission. The final replay package and semester documentation are prepared for private upload. The staged primary tree contains 33 files. The review check found no credential-pattern matches in staged text. GitHub-based reproduction and an independent live installation are outstanding checks. No repository was pushed, merged, deleted or made public in this review.

[Final handoff](docs/final-implementation/HANDOFF.md) · [Submission workflow](docs/final-submission/README.md)

This records the repository state before the final publishing step. See the [current project entry point](README.md) and [final implementation handoff](docs/final-implementation/HANDOFF.md) for the published destinations.

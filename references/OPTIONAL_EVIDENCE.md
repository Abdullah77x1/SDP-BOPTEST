# Evidence Location and Pinned Runtime

The original BOPTEST-only evidence ZIP preserves older traces and research materials omitted from this repository. [Original archive and retrieval](../EXCLUDED_FILES_INDEX.md)

## Pinned live runtime

The package includes the [exact BESTEST Air FMU](../SDP_BOPTEST_Pilot/deployment/official_v0.9.0/project1-boptest-0.9.0/testcases/bestest_air/models/wrapped.fmu), the [BOPTEST license](../SDP_BOPTEST_Pilot/deployment/official_v0.9.0/project1-boptest-0.9.0/license.md), original case sources, and original runtime identities. The full worker stack and images are external. Use the original BOPTEST v0.9.0 release source and verified worker image set from the custodian. The preserved source ZIP `SDP_BOPTEST_Pilot/deployment/project1-boptest-0.9.0.zip` in the project workspace has SHA-256 `173a3edb67d904e114e5e88ec3e6b4a6de3b325fe68676311d84e6d500a90608`.

Install Docker Desktop with the Linux engine and Docker CLI on PATH. Provision the exact identities in [the runtime identity file](../SDP_BOPTEST_Pilot/stage4e_d0/RUNTIME_REFERENCE_IDENTITIES.json), using the [loopback override](../SDP_BOPTEST_Pilot/deployment/compose.localhost.override.yml). Run the read-only binding inspection documented in [Windows setup](../HOW_TO_RUN.md). Genuine operation also requires a new unused campaign binding and explicit authorization. Archive playback uses neither the Docker engine nor a campaign authorization.

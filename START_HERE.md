# Start Here

The BOPTEST Building Simulator is a repeatable physical model of one zone. O25 forecasts what the room may do next given available observations. A separate action-response model estimates how supported control choices affect temperature and cooling-plus-fan electricity. The rolling controller applies one five-minute action, verifies its readback, and measures what happens before deciding again.

1. Follow [Windows setup](HOW_TO_RUN.md) to fetch the O25 Git LFS checkpoint, restore the hash-verified evidence and install Python dependencies.
2. Open the rolling replay and seek to frames **8, 9, 10, 18 and 41**. Look for the transition from native observations to candidate predictions, verified warmer command, native release, and recovery.
3. Read the [editable report](report/SDP_BOPTEST_TECHNICAL_REPORT.docx) or [Markdown](report/SDP_BOPTEST_TECHNICAL_REPORT.md). Trace results in the [experiment index](references/EXPERIMENT_EVIDENCE_INDEX.md) and code in the [source index](references/SOURCE_CODE_INDEX.md).

The genuine rolling demonstration records operation of one simulated arm. Use the matched campaign results to discuss savings and their original comfort failures. See the [terminology guide](references/NAME_MAPPING.md) for original component identifiers.

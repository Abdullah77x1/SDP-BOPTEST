# Requirements and specification baseline

[Research source register](../research/EVIDENCE_INDEX.md#e04) · [Engineering decisions](../design-decisions/DECISION_RECORDS.md) · [Final handoff](../final-implementation/HANDOFF.md)

The [original proposal](Original%20project%20proposal.docx) describes a multi-zone twin, language interaction, and automatic energy management. The [requirements elicitation package](Requirements%20elicitation%20working%20package.pdf) and [working specification](System%20specification%20working%20draft%20v0.1.pdf) translate that scope into requirements and measures. The v0.1 working specification is dated 12 November. The team still needs the supervisor-approved original for the official appendix.

| Category | Demonstrated baseline |
|---|---|
| Functional | Read BOPTEST, prepare causal features, issue four quantities at four horizons, match measurements to targets, support a guarded operator-requested hold and verify readback and release. |
| Functional | Display simulator time, current measures, forecasts, measured results, energy, comfort and command state. Replay two saved recordings without Docker. |
| Non-functional | Use pinned dependencies, frozen model and ordered schema. Keep the dashboard on loopback. Guard missing data and commands and show the status clearly. |
| Non-functional | Verify the two archived replays, model integrity, acquisition chronology and operating limits. Any physical connection requires independent risk review and commissioning. |

The final report's Chapter 2 table records dimensions, exact timing, units, limits and verification. Appendix H traces the original goals to the delivered scope.

# Experiment index

Use this index with the [original evidence register](EVIDENCE_INDEX.md) and the numbered source entries in the final report. The results below are measured in their named dataset or benchmark and do not establish physical building performance.

| Investigation | Source and verified outcome |
|---|---|
| CU-BEMS and other building measurements | [E05](EVIDENCE_INDEX.md#e05), report §4.2. Usable forecasts on selected real readings. Missing matched controls and occupancy labels restricted the claims. |
| Simulator V2 neural forecasts and cooling grid search | [E03](EVIDENCE_INDEX.md#e03), [E07](EVIDENCE_INDEX.md#e07). Synthetic scenarios supported prototyping, and a seven-day comfort constraint eliminated the most energy-saving setpoint candidate. |
| EnergyPlus and BOPTEST selection | [E08](EVIDENCE_INDEX.md#e08), [E10](EVIDENCE_INDEX.md#e10). EnergyPlus two baselines verified. BOPTEST chosen for packaged control/readback experiments. |
| Frozen final model and feature audit | [E11](EVIDENCE_INDEX.md#e11), report §4.4 and Appendix A. Final development +30 min temperature MAE 0.11545 °C versus 0.27627 °C Persistence. XGBoost did better on some electrical and RMSE metrics. |
| Occupancy 1, replace schedule | [E12](EVIDENCE_INDEX.md#e12). Public +30 min temperature MAE 0.09278 → 0.08863 °C, combined electrical MAE 0.007502 → 0.007877 kW. Arrival errors increased. |
| Occupancy 2, add probability after removing schedule and time fields | [E12](EVIDENCE_INDEX.md#e12). Public +30 min combined MAE 0.01711 → 0.00970 kW and arrival temperature MAE 1.94459 → 1.32697 °C. Overall temperature MAE increased. Thermostat conditions still reveal the fixed schedule. |
| Fixed warmer and rule-based holds | [E13](EVIDENCE_INDEX.md#e13). Day 174 saving 0.07847 kWh with increased official discomfort. Day 218 saving 0.07492 kWh, failing the predefined project discomfort criterion. |
| Forest what-if and predictive tests | [E13](EVIDENCE_INDEX.md#e13). Day-196 +30 min measured electrical effect −0.08044 kW, predicted +0.00050 kW. Ridge-based fixed hold and StepModel rolling paths had limited support and comfort or qualification gaps. |
| Fan and supply variants | [E13](EVIDENCE_INDEX.md#e13). Fan-only passed the particular project-band checks with increased official discomfort. Fixed joint case failed the stricter official no-increase gate. Later coordinated cases crossed the temperature gate after release and lacked full comparable recovery. |
| Final replay and live proof | [E14](EVIDENCE_INDEX.md#e14), [E15](EVIDENCE_INDEX.md#e15). 852 scored origins in each offline replay. Live mode verified one hold, readback, release and cleanup. Measured 2.01165 kWh and 0.41288 K·h over 150 simulated minutes. |

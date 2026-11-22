# Terminology and Original Identifiers

| Name used in the report | Original identifier | Meaning |
| --- | --- | --- |
| BOPTEST Building Simulator | BESTEST Air 0.9.0 | Single-zone physics, weather, native thermostat and comfort schedules |
| BOPTEST Forecast Model | O25 Random Forest | Observational forecasts at +5/+10/+15/+30 minutes |
| HVAC Action-Response Model | StepModel / calibrated_rolling | Qualified candidate-specific path predictions with recovery |
| HVAC Optimizer | PredictiveController or RollingController._select | Eligible action selection. G163 used a fixed-hold predecessor |
| Rolling HVAC Controller | RollingController / partial receding-horizon controller | One verified action per five-minute interval |
| Live Digital Twin Dashboard | final_energy_control dashboard | Verified state, forecasts, decisions, readbacks and playback |
| Native HVAC Control | A0 / native | Original thermostat and equipment schedules |
| Warmer Setpoint Control | 24.5°C override / A3 fixed hold | Qualified cooling override with native heating |
| Fan Control Experiment | G218_FAN060_1400_01 and G258_FAN060_1400_01 | Fan 0.60 with native supply control |
| Joint HVAC Control Experiment | G258_JOINT060_1400_01 | Fan 0.60 and frozen colder supply target |
| Archived comfort-rule controller | Stage 4D | Earlier BOPTEST design retained where shared or needed for provenance |

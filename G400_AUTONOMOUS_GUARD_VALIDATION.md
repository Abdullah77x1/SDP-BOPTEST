# G400 autonomous guard validation

**G299 matched experiment — NOT EXECUTED.** The policy, collector and acceptance checks are ready. The pinned BOPTEST 0.9.0 runtime and local BESTEST Air FMU passed read-only verification. The only remaining execution requirement is explicit authorization for this exact G400 campaign. Neither slot has been reserved.

## Implementation and offline verification

`SDP_AUTONOMOUS_HVAC_G400_1.0.0` computes trapezoidal mean cooling electrical power from the **61 verified 30-second samples from 10:25 through 10:55**. At 11:00 a mean **≥400 W**, or missing, stale, invalid or unverified morning history, vetoes the warmer start for the day. Below 400 W the original Stage 1 checks decide. Each entry decision records the mean, sample window and receipt, the guard reason, and whether Stage 1 would otherwise start. A risk veto is logged separately from a Stage 1 safety veto. [Versioned controller](SDP_BOPTEST_Pilot/autonomous_hvac_stage1/guard400.py)

The existing ordered collector and matched scorer are shared with G218. The Stage 1 control logic, **11:00–11:45** window, 45-minute hold cap, 25.5°C safety margin, 120-minute recovery lockout, and command/readback safeguards remain intact. The shared adapter refactor changes the current source fingerprint. The original G218 execution binding remains recorded in its sealed evidence. [Collector](SDP_BOPTEST_Pilot/autonomous_hvac_stage1/g218.py) · [Frozen G218 results](G218_AUTONOMOUS_VALIDATION_RESULTS.md)

**30 offline tests passed**. They covered the inclusive threshold, trapezoidal mean, unavailable and late inputs, original safety checks, ignored post-window samples, native qualification and stop, verified hold/release and recovery, bad readback, authorization rejection, and the original comfort scorer. The mixed-demand pair used a fabricated transport. The G174 and measured G218 dashboard replays also loaded their historical final verdicts.

## Frozen campaign

**G299** uses benchmark day offset **299**, with a seven-day native warmup from **25,228,800 s**, scoring from **25,833,600 to 26,092,800 s**. The full footprint has a minimum **86,400 s** separation from the existing and planned windows checked, including protected slots and all three partition-plan variants. The project embargo is **3,600 s**. The configuration check read archived timing metadata and pinned exogenous weather only. The first two days have daytime outdoor peaks of **17.8°C and 14.4°C** and solar peaks of **635 and 612 W/m²**. That makes cooling plausible. Whether the 400 W screen will have both a high-demand and a lower-demand morning remains to be measured. [Footprint plan](SDP_BOPTEST_Pilot/stage4e_d2p/COLLECTION_AND_PARTITION_PLAN.json) · [Campaign definition](SDP_BOPTEST_Pilot/autonomous_hvac_stage1/g400.py)

Run A native first, then B guarded only if A has an occupied, cooling-active morning on **each side of 400 W**. Cooling activity requires at least 10 W cooling and positive fan power at 10:50 and 10:55. The qualification gate reads only native morning chunks and the 10:55 issued boundary. It returns **NONQUALIFYING SCENARIO** before reserving B if either regime is absent. There is one selection and initialization per arm, a maximum of **864 five-minute advances per arm / 1,728 total**, 30-second measurements and zero retries. The matched scorer verifies identical settings, warmup, pre-action state and as-issued forcing.

## Acceptance and delivery

| Measure | Frozen acceptance | G299 status |
| --- | --- | --- |
| Energy | At least **0.0225 kWh** net savings both over 72 hours and across holds plus recovery. Report cooling, fan, holds and recovery separately. | Unevaluated |
| Comfort | Original BOPTEST discomfort reported separately. Require zero added whole-period project discomfort beyond **10⁻⁷ K·h**, zero added violation minutes, and zero project-band violations during holds and recovery. Hold temperature ≤25.5°C. | Unevaluated |
| Delivery and recovery | Require a high-demand veto of an otherwise eligible start, at least one verified 24.5°C hold, verified native release and recovery within 120 minutes. The scorer records daily demand, original Stage 1 eligibility, actual starts/releases, maximum temperatures, vetoes and recovery. | Unobserved |

The measured G174 and G218 dashboard replays remain available. The G400 replay depends on a completed and verified pair. This two-arm design evaluates the guarded policy against native operation. Superiority to Stage 1 would require a matched Stage 1 comparator. [Existing demo instructions](EXCLUDED_FILES_INDEX.md)

From `SDP_BOPTEST_Pilot`, print the frozen binding and use it in the explicit authorization record. The record needs the displayed `binding` fields, `status` set to `EXPLICITLY_AUTHORIZED_G400_G299_PAIR`, and affirmative user `approval_text` for this one launch. Campaign SHA-256 is `21385e630363945a2904a4eda0da983dc5936cf1fe38d7a4062d57e38c658ee3`. Implementation SHA-256 is `a59dc613584957736cb476a5a5fd568552fc59cc65e5e96a7f8c70847e80c13e`.

```powershell
$py = '..\experiments\five_model_hvac16_v1_0_0\.venv\Scripts\python.exe'
& $py -B -m autonomous_hvac_stage1.g400 --describe
& $py -B -m autonomous_hvac_stage1.g400 --execute .\g400_execution_authorization.json
```

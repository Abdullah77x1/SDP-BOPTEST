"""Offline, side-effect-free forecast API for the frozen BESTEST Air contracts."""
from pathlib import Path

import joblib
import numpy as np
from threadpoolctl import threadpool_limits

from dataset import (ACTION, CONTRACTS, HORIZONS, OUT, TARGETS, FLAG, FLAGS, SET, TEMP, REFERENCE, check,
                     commit_features, interval_history, plan_encode, read, sha, state_features)

VERSION = "SDP_ML_RESEARCH_1.0.0"
UNITS = {"indoor_temperature":"degC","cooling":"kW electric","fan":"kW electric",
         "combined":"kW electric","heating":"kW thermal"}
RESEARCH_SCHEDULE = {(32400,1800,296.90),(39600,1800,296.65),
                     (50400,1800,296.90),(39600,900,296.90),(39600,2700,296.90)}

def values(values_by_name, fields):
    missing=[field for field in fields if field not in values_by_name]
    check(not missing,"Missing inputs: "+", ".join(missing))
    x=np.array([float(values_by_name[field]) for field in fields])
    check(np.isfinite(x).all(),"Nonfinite required inputs")
    return x

def invalid(reason):
    return dict(version=VERSION,status="invalid",valid=False,reason=str(reason),horizons_min=HORIZONS,
                units=UNITS,predictions=None)

class Predictor:
    """Use only the local bundle listed in the generated research model manifest."""
    def __init__(self,name="observational",directory=OUT):
        directory=Path(directory)
        manifest=read(directory/"MODEL_PROVENANCE.json")
        check(manifest["version"]==VERSION,"Model version mismatch")
        self.info=manifest["interfaces"][name]
        self.name=name
        self.reg=None
        if name!="persistence":
            path=directory/self.info["artifact"]
            check(sha(path)==self.info["artifact_sha256"],"Model artifact hash mismatch")
            bundle=joblib.load(path)
            self.reg=bundle["model"]
            check(bundle["targets"]==TARGETS and tuple(bundle["features"])==CONTRACTS[self.info["contract"]],
                  "Model contract mismatch")

    def forecast_features(self,origin,known,proposed_action=None,prior_latch=None,experimental=False):
        """Consume predecision features for P27 and postdecision features for O25."""
        try:
            check(type(origin) is int and origin>=0 and origin%300==0,"Invalid 300 s origin")
            if self.name=="experimental_action":
                check(experimental,"Proposed-action inference requires explicit research-only opt-in")
                check(type(prior_latch) is int and prior_latch in (0,1),"Missing known prior latch")
                check(not any(f in known for f in ACTION),"Supply nominal proposal separately from observed state")
                check("cooling_override_committed" not in known and "cooling_setpoint_change_committed_k" not in known,
                      "Predecision request includes a current committed command")
                if proposed_action is None:
                    act=plan_encode(origin,latch=prior_latch)
                else:
                    check(set(proposed_action)=={"activate_s","release_s","target_k"},
                          "One cooling block with activate_s, release_s and target_k required")
                    a,b,k=(proposed_action[f] for f in ("activate_s","release_s","target_k"))
                    check(type(a) is int and type(b) is int and type(k) in (int,float),"Invalid action timestamps or target")
                    check((a%86400,b-a,round(k,9)) in RESEARCH_SCHEDULE,
                          "Unsupported clock, duration or temperature. Use an observed nominal policy.")
                    act=plan_encode(origin,a,b,k,prior_latch)
                check(list(act) in self.info["observed_action_tuples"],"Proposed plan/latch tuple absent from training")
                known={**known,**dict(zip(ACTION,act))}
            else:
                check(proposed_action is None,"This interface forecasts observations only. Proposal unsupported.")
            if self.name=="persistence":
                fields=self.info["features"]
                result=np.repeat(values(known,fields),4)
                outside=[]
            else:
                fields=self.info["features"]
                v=values(known,fields)
                outside=[f for f,c,lo,hi in zip(fields,v,self.info["minimum"],self.info["maximum"])
                         if not lo-1e-7<=c<=hi+1e-7]
                with threadpool_limits(limits=1):
                    if isinstance(self.reg,list):
                        result=np.array([float(r.predict(v[None,:])[0]) for r in self.reg])
                    else:
                        result=self.reg.predict(v[None,:])[0]
            check(result.shape==(16,) and np.isfinite(result).all(),"Invalid model prediction")
            if np.any(result[4:12]<-1e-6):
                return invalid("Model produced material negative cooling/fan power. Use the observational fallback.")
            predictions=[]
            for i,h in enumerate(HORIZONS):
                predictions.append(dict(horizon_min=h,indoor_temperature=float(result[i]),
                                        cooling=float(result[i+4]),fan=float(result[i+8]),
                                        combined=float(result[i+4]+result[i+8]),heating=float(result[i+12])))
            status=("experimental_only" if self.name=="experimental_action" else
                    "outside_development_range" if outside else "ok")
            return dict(version=VERSION,status=status,valid=not outside,reason=("Outside recorded input ranges"
                        if outside else "Research use only" if self.name=="experimental_action" else ""),
                        optimizer_ready=False,horizons_min=HORIZONS,units=UNITS,
                        outside_development_fields=outside,predictions=predictions)
        except (ValueError,KeyError,TypeError,IndexError,OverflowError) as exc:
            return invalid(exc)

    def forecast_observations(self,origin,endpoints,native,issued_forecast=None,
                              proposed_action=None,prior_latch=None,committed=None,experimental=False):
        """Adapt the raw completed intervals and issued forecast to a supported contract.

        The caller must supply endpoints already received by the cutoff, native 30-second history
        ending at origin, and the validated as-issued forecast record. An observational commit uses
        the already-known current command. A predecision request has no committed command.
        """
        try:
            check(type(origin) is int and origin>=0 and origin%300==0,"Invalid 300 s origin")
            if self.name=="persistence":
                check(committed is None and proposed_action is None,"Persistence requires observed state only")
                check(endpoints[origin]["time"]==origin and native["time"][-1]==origin
                      and native["time"][0]<=origin-300,"Persistence requires origin and one completed interval")
                state=dict(zip(self.info["features"],(endpoints[origin][TEMP]-273.15,
                                                      *interval_history(native)[origin])))
                return self.forecast_features(origin,state)
            check(all(t in endpoints and endpoints[t]["time"]==t for t in (origin,origin-300,origin-1800))
                  and all(t<=origin for t in endpoints),"Missing historical endpoint or future endpoint supplied")
            check(native["time"][-1]==origin and native["time"][0]<=origin-2100,
                  "Need completed native history through t and at least 2,100 seconds of support")
            forecast=issued_forecast["data"]
            check(issued_forecast["issued_at_sim"]==origin
                  and type(issued_forecast["received_order"]) is int and issued_forecast["received_order"]>0
                  and forecast["time"]==list(range(origin,origin+1801,300)),"Wrong forecast vintage/grid")
            x=state_features(origin,endpoints,interval_history(native),forecast)
            if self.name=="observational":
                check(committed is not None and all(committed[k] in (0,1) for k in FLAGS) and
                      not any(committed[k] for k in FLAGS if k!=FLAG),"Current cooling-only commitment required")
                if committed[FLAG]:
                    check(round(committed[SET]-REFERENCE.pair(origin)[1],9) in (-.25,-.5),
                          "Committed cooling level outside observed domain")
                x.update(commit_features(origin,committed))
            else:
                check(committed is None,"Predecision/fallback request must exclude current committed command")
            return self.forecast_features(origin,x,proposed_action,prior_latch,experimental)
        except (ValueError,TypeError,KeyError,IndexError,OverflowError) as exc:
            return invalid(exc)


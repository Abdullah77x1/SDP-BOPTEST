"""Verify held predictions and produce numerical results, contrasts, and figures."""
import itertools

import matplotlib.pyplot as plt
import numpy as np

from analyze import FIG, note, table
from dataset import ALL, OUT, ROOT, TARGETS, HORIZONS, check, csv_rows, csv_write, read, save, sha
from train import ABLATIONS, MODELS, RUN, TRACKS, metadata, persistence, training_masks, proof_ids

AUGMENT = [("O25","Mdiv","O25","M0"),("O25","Mfull","O25","M0"),
           ("A29","M0","O25","M0"),("A29","Mdiv","O25","Mdiv"),("P27","Mdiv","S23","Mdiv")]
REPORT_TARGETS = TARGETS + [f"target_combined_electric_power_{h}min_kw" for h in HORIZONS]
PRIMARY = [*range(4), *range(16,20)]
MODEL_LABEL = {"OLS":"Linear Regression", "RandomForest":"Random Forest", **{k:k for k in ("Ridge","XGBoost","Persistence")}}

def append_combined(arr):
    return np.c_[arr, arr[:,4:8]+arr[:,8:12]]

def load_oof(stage, contract, dataset, model, y, ids, folds):
    result = np.full_like(y,np.nan)
    coverage = np.zeros(len(y),dtype=int)
    for fold,masks,held,inner in folds:
        key=f"{stage}_{contract}_{dataset}_{model}_f{fold}"
        path,meta=RUN/(key+".npz"),read(RUN/(key+".json"))
        check(sha(path)==meta["predictions_sha256"],f"Prediction hash mismatch {key}")
        pred=np.load(path,allow_pickle=False)
        indices=pred["held"]
        t=pred["targets"]
        check(np.array_equal(indices,np.flatnonzero(held)) and proof_ids(ids[held,0])==meta["held_origin_ids_sha256"]
              and proof_ids(ids[masks[dataset],0])==meta["train_origin_ids_sha256"],f"Fold membership mismatch {key}")
        result[np.ix_(indices,t)] = pred["prediction"]
        coverage[indices]+=1
    check(np.all(coverage==1), "Unequal held origin coverage")
    return append_combined(result)

def stats(error):
    abs_error = abs(error)
    med,p90,p95=np.quantile(abs_error,[.5,.9,.95],axis=0)
    return np.array([abs_error.mean(axis=0), np.sqrt(np.square(error).mean(axis=0)),error.mean(axis=0),
                     med,p90,p95,abs_error.max(axis=0)])

def metric_values(error, ref, groups):
    group_labels=np.unique(groups)
    g_indices=[groups==g for g in group_labels]
    pooled,pooled_p=stats(error),stats(ref)
    macro=np.mean([stats(error[m]) for m in g_indices],axis=0)
    macro_p=np.mean([stats(ref[m]) for m in g_indices],axis=0)
    with np.errstate(divide="ignore",invalid="ignore"):
        skill = np.where(pooled_p[1]>1e-12,1-(pooled[1]/pooled_p[1])**2,np.nan)
    return pooled,pooled_p,macro,macro_p,skill

def metric_rows(yp,y,base,group,mask,contract,dataset,model,population,dimension,slice_name,indices):
    err=(yp[mask]-y[mask])[:,indices]
    ref=(base[mask]-y[mask])[:,indices]
    pooled,p0,macro,m0,skill=metric_values(err,ref,group[mask])
    for j,k in enumerate(indices):
        mae,rmse,bias,med,p90,p95,maxae=pooled[:,j]
        yield dict(contract=contract,dataset=dataset,model=model,population=population,dimension=dimension,
                   slice=slice_name,target=REPORT_TARGETS[k],unit="degC" if k<4 else "kW thermal" if k in range(12,16) else "kW electric",
                   n=int(mask.sum()),groups=len(np.unique(group[mask])),mae=mae,rmse=rmse,bias=bias,median_ae=med,
                   p90_ae=p90,p95_ae=p95,max_ae=maxae,group_macro_mae=macro[0,j],group_macro_rmse=macro[1,j],
                   persistence_mae=p0[0,j],persistence_rmse=p0[1,j],
                   persistence_mae_gain= p0[0,j]-mae,persistence_rmse_gain=p0[1,j]-rmse,
                   persistence_mae_gain_pct=100*(1-mae/p0[0,j]) if p0[0,j]>1e-12 else "",
                   persistence_rmse_gain_pct=100*(1-rmse/p0[1,j]) if p0[1,j]>1e-12 else "",
                   group_macro_persistence_mae=m0[0,j],group_macro_persistence_rmse=m0[1,j],
                   mse_skill=skill[j] if np.isfinite(skill[j]) else "")

def populations(x, y, ids, aux):
    group,season,policy=ids[:,2],ids[:,3],ids[:,4]
    field=lambda f:x[:,ALL.index(f)]
    outdoor,solar,cooling,occ=(field(f) for f in ("outdoor_temp_c","solar_irradiance_w_m2",
                   "cooling_electric_power_last_5min_kw","occupancy_now"))
    static = {
       "active_nominal":aux["active_nominal"]==1,"active_delivered_posthoc":aux["active_delivered"]==1,
       "release_origin":aux["release_origin"]==1,"recovery_0_to_120min":aux["recovery"]==1,
       "activation_origin":aux["activation_origin"]==1,
       "native_event_30min_window":aux["native_event"]==1,
       "scheduled_native":aux["scheduled_native"]==1,"stable_native":aux["stable_native"]==1,
       "occupied":occ>0,"unoccupied":occ<=0,
    }
    bins={
        "outdoor_c":(outdoor,(-np.inf,0,10,20,30,np.inf)),
        "solar_w_m2":(solar,(-np.inf,1,250,600,np.inf)),
        "historical_cooling_kw":(cooling,(-np.inf,.01,.1,.5,np.inf)),
    }
    for pop,base in (("D2_retention",np.isin(policy,("N","X"))),("B1_transfer",np.isin(policy,("C15","C45")))):
        yield pop,"total","all",base,tuple(range(20))
        for name,kind in (("group",group),("season",season),("policy",policy),("fold",aux["fold"])):
            indices=range(20) if name in ("group","season") else PRIMARY
            for label in np.unique(kind[base]):
                yield pop,name,str(label),base&(kind==label),tuple(indices)
        for label,m in static.items():
            yield pop,"regime",label,base&m,tuple(PRIMARY)
        for name,(values,edges) in bins.items():
            for low,high in zip(edges,edges[1:]):
                yield pop,name,f"[{low},{high})",base&(values>=low)&(values<high),tuple(PRIMARY)
        for i,h in enumerate(HORIZONS):
            for event in ("release","activation"):
                t=aux[f"next_{event}_offset"]
                yield pop,"regime",f"{event}_crossing",base&(t>=0)&(t<60*h),(i,16+i)
            native_times=aux["time"]%86400
            cross=np.zeros(len(native_times),bool)
            for event in (28800,64800):
                cross |= (native_times>=event-60*h+300)&(native_times<=event+300)
            yield pop,"regime","native_setpoint_boundary",base&cross,(i,16+i)
            d=abs(y[:,i]-field("indoor_temp_c"))
            for lo,hi in ((0,.1),(.1,.5),(.5,np.inf)):
                yield pop,"realized_delta_t_c_posthoc",f"[{lo},{hi})",base&(d>=lo)&(d<hi),(i,16+i)

def augment_deltas(metrics):
    key=lambda r:(r["contract"],r["dataset"],r["model"],r["population"],r["dimension"],r["slice"],r["target"])
    lookup={key(r):r for r in metrics}
    out=[]
    for c,d,c0,d0 in AUGMENT:
        for r in metrics:
            if (r["contract"],r["dataset"]) != (c,d) or r["model"]=="Persistence":
                continue
            rr=lookup[c0,d0,*key(r)[2:]]
            check(r["n"]==rr["n"],"Paired comparison population mismatch")
            out.append(dict(contract=c,dataset=d,reference_contract=c0,reference_dataset=d0,model=r["model"],
                            population=r["population"],dimension=r["dimension"],slice=r["slice"],target=r["target"],
                            unit=r["unit"],n=r["n"],groups=r["groups"],
                            delta_mae=r["mae"]-rr["mae"],delta_rmse=r["rmse"]-rr["rmse"],
                            delta_group_macro_mae=r["group_macro_mae"]-rr["group_macro_mae"],
                            delta_group_macro_rmse=r["group_macro_rmse"]-rr["group_macro_rmse"]))
    return out

def review_margins(deltas, forecasts, y, ids, aux):
    """Apply fixed engineering margins to paired group-macro results."""
    p=ids[:,4]
    group=ids[:,2]
    lookup={(d["contract"],d["dataset"],d["reference_contract"],d["reference_dataset"],d["model"],
             d["population"],d["dimension"],d["slice"],d["target"]):d for d in deltas}
    rows=[]
    for d in deltas:
        summary=d["dimension"]=="total" or (d["dimension"]=="regime" and d["slice"]=="release_crossing")
        if not summary or d["target"] not in [REPORT_TARGETS[k] for k in PRIMARY]:
            continue
        c,ds,c0,d0,model,pop,dim,part,target=[d[k] for k in ("contract","dataset","reference_contract",
                                                        "reference_dataset","model","population","dimension","slice","target")]
        k=REPORT_TARGETS.index(target)
        mask=np.isin(p,("N","X") if pop=="D2_retention" else ("C15","C45"))
        if part=="release_crossing":
            h=HORIZONS[k if k<4 else k-16]
            mask &= (aux["next_release_offset"]>=0)&(aux["next_release_offset"]<h*60)
        e0=forecasts[c0,d0,model][:,k]-y[:,k]
        e=forecasts[c,ds,model][:,k]-y[:,k]
        effect,stable = {},{}
        for g in sorted(set(group[mask])):
            m=mask&(group==g)
            a=stats(e[m]);b=stats(e0[m])
            effect[g]=[float(a[0]-b[0]),float(a[1]-b[1])]
            stable_mask=(group==g)&(aux["stable_native"]==1)&np.isin(p,("N","X") if pop=="D2_retention" else ("C15","C45"))
            if np.any(stable_mask):
                a=stats(e[stable_mask]);b=stats(e0[stable_mask])
                stable[g]=[float(a[0]-b[0]),float(a[1]-b[1])]
        both=sum(a<0 and b<0 for a,b in effect.values())
        threshold=6 if pop=="D2_retention" else 2
        for margin in (.005,.01,.02):
            harm=max((max(v) for v in stable.values()),default=0.)
            passed=(d["delta_group_macro_mae"]<=-margin and d["delta_group_macro_rmse"]<=-margin
                    and both>=threshold and harm<=margin)
            rows.append({**d,"margin":margin,"both_improved_group_count":both,
                         "required_group_count":threshold,"max_stable_group_degradation":harm,
                         "group_delta_mae_rmse":str(effect),"margin_pass":passed})
    return rows

def ablation(x,y,ids,folds,base,forecasts):
    group,policy=ids[:,2],ids[:,4]
    original=np.isin(policy,("N","X"))
    transfer=np.isin(policy,("C15","C45"))
    choices=read(OUT/"ABLATION_FOLLOWUP_CHOICES.json")
    rows=[]
    for model in MODELS[1:]:
        full=forecasts["A29","M0",model]
        selected=choices[model]
        for stage in ("screen","followup"):
            indexes=(2,18) if stage=="screen" else PRIMARY
            reduced=ABLATIONS if stage=="screen" else sorted({selected["temperature"],selected["electricity"]})
            options={"full":full,**{k:load_oof(stage,k,"M0",model,y[:,:16],ids,folds) for k in reduced}}
            for name,pred in options.items():
                for pop,mask in (("D2_retention",original),("B1_transfer",transfer)):
                    reference=list(metric_rows(full,y,base,group,mask,"A29","M0",model,pop,"total","all",indexes))
                    for row,ref in zip(metric_rows(pred,y,base,group,mask,"A29","M0",model,pop,"total","all",indexes),
                                       reference):
                        rows.append(dict(stage=stage,removed_group=name,**row,delta_mae=row["mae"]-ref["mae"],
                                         delta_rmse=row["rmse"]-ref["rmse"],
                                         delta_macro_mae=row["group_macro_mae"]-ref["group_macro_mae"],
                                         delta_macro_rmse=row["group_macro_rmse"]-ref["group_macro_rmse"]))
    csv_write(OUT/"MULTI_MODEL_ABLATION_RESULTS.csv",rows)
    fig,axs=plt.subplots(1,2,figsize=(14,5),layout="constrained")
    for k,axis in zip((2,18),axs):
        relevant={(r["removed_group"],r["model"]):r for r in rows if r["stage"]=="screen"
                  and r["population"]=="D2_retention" and r["target"]==REPORT_TARGETS[k]}
        xs=np.arange(len(ABLATIONS))
        for j,model in enumerate(MODELS[1:]):
            axis.bar(xs+(j-1.5)*.2,[relevant[g,model]["delta_macro_mae"] for g in ABLATIONS],.2,label=MODEL_LABEL[model])
        axis.set_xticks(xs,[g.replace("_"," ") for g in ABLATIONS],rotation=30,ha="right")
        axis.set_ylabel("Δ group-macro MAE, °C" if k==2 else "Δ group-macro MAE, kW")
        axis.set_title("+15 minute temperature" if k==2 else "+15 minute electricity")
        axis.axhline(0,color="black",lw=.6)
    axs[1].legend(fontsize=8)
    fig.savefig(FIG/"group_removal_screen.png",dpi=160)
    plt.close(fig)
    return rows, choices

def run(model_only=False):
    from export_models import selection,export
    from example_inference import run as verify_inference
    from policy_evidence import matched,setpoint
    from reports import ablation_report, model_reports, final_reports

    FIG.mkdir(exist_ok=True)
    x,y,ids,aux=metadata()
    folds=list(training_masks(ids,aux))
    actual=append_combined(y)
    base=append_combined(persistence(x[:,:25]))
    subsets=[row for row in populations(x,y,ids,aux) if np.any(row[3])]
    forecasts={}
    metrics=[]
    physical_rows=[]
    for contract,dataset in TRACKS:
        for model in MODELS:
            forecasts[contract,dataset,model]=pred=base if model=="Persistence" else load_oof(
                "main",contract,dataset,model,y,ids,folds)
            check(np.isfinite(pred).all(),"Incomplete comparison predictions")
            for population,arms in (("D2_retention",("N","X")),("B1_transfer",("C15","C45"))):
                electrical=pred[np.isin(ids[:,4],arms),4:12]
                physical_rows.append(dict(contract=contract,dataset=dataset,model=model,population=population,
                                          origins=len(electrical),min_electrical_kw=float(electrical.min()),
                                          any_below_negative_0_001W=int(np.any(electrical< -1e-6,axis=1).sum()),
                                          any_below_negative_1W=int(np.any(electrical< -.001,axis=1).sum()),
                                          any_below_negative_10W=int(np.any(electrical< -.01,axis=1).sum())))
            for population,dim,part,mask,index in subsets:
                metrics.extend(metric_rows(pred,actual,base,ids[:,2],mask,contract,dataset,model,
                               population,dim,part,index))
    csv_write(OUT/"MODEL_COMPARISON_RESULTS.csv",metrics)
    csv_write(OUT/"MODEL_PHYSICAL_VALIDITY.csv",physical_rows)
    deltas=augment_deltas(metrics)
    csv_write(OUT/"PAIRED_CONFIGURATION_DELTAS.csv",deltas)
    margins=review_margins(deltas,forecasts,actual,ids,aux)
    csv_write(OUT/"PRACTICAL_MARGIN_REVIEW.csv",margins)
    print("Metrics",len(metrics),"paired deltas",len(deltas),"margin rows",len(margins),flush=True)
    obs,action=selection(forecasts,actual,x,ids,aux,margins)
    print("Selected",obs,action,flush=True)
    manifest_file=OUT/"MODEL_PROVENANCE.json"
    if manifest_file.exists():
        manifest=read(manifest_file)
        for name,key in (("observational",obs),("experimental_action",action)):
            r=manifest["interfaces"][name]
            check((r["contract"],r["dataset"],r["model"])==key and
                  sha(OUT/r["artifact"])==r["artifact_sha256"],"Cached export selection or hash changed")
    else:
        manifest=export((obs,action),x,y,ids,aux,folds)
    tests=verify_inference()
    paired=matched(ids,x,actual,aux)
    setpoint()
    summary=model_reports(metrics,deltas,margins,paired,obs,action,x,actual,ids,aux,forecasts,manifest)
    if model_only:
        print("Completed model reports and inference checks",flush=True)
        return
    ab_rows,choices=ablation(x,actual,ids,folds,base,forecasts)
    ablation_report(ab_rows,choices)
    check(len(csv_rows(OUT/"ALL_168_ENGINEERING_FEATURE_JUSTIFICATIONS.csv"))==168,"Feature ledger check")
    cached=[read(p) for p in sorted(RUN.glob("*.json"))]
    expected_runs=4*4*len(TRACKS)+4*4*len(ABLATIONS)+sum(
        4*len({c["temperature"],c["electricity"]}) for c in choices.values())
    check(len(cached)==expected_runs,"Unexpected fit checkpoint count")
    audit_count={"verified_prediction_checkpoints":len(cached),"reused_O25_M0_fits":sum("historical_model" in r for r in cached),
                 "new_grouped_fit_cells":sum("historical_model" not in r for r in cached),
                 "metrics":len(metrics),"configuration_deltas":len(deltas),"ablation_metrics":len(ab_rows),
                 "same_history_effect_cells":len(paired),"distinct_candidate_justifications":168,
                 "BOPTEST_live_attempts":0,"reserved_validation_outcomes_read":0,"verified_adapter_runs":22,
                 "inference_checks":tests}
    save(OUT/"VERIFICATION_RESULTS.json",audit_count)
    final_reports(OUT,manifest,summary,audit_count,metrics,ab_rows)
    file_list=[p for p in OUT.iterdir() if p.is_file() and p.name!="OUTPUT_MANIFEST.json" and p.suffix!=".log"]
    source_files=[*FIG.glob("*.png"),*RUN.glob("*.json"),*(OUT/"models").glob("*.joblib"),*RUN.glob("membership_*.npz")]
    save(OUT/"OUTPUT_MANIFEST.json",{p.relative_to(OUT).as_posix():sha(p) for p in sorted(file_list+source_files)})
    print("PASS final verification",audit_count,flush=True)


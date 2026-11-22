"""Frozen four-fold, development-only policy-diversity and information comparisons."""
import argparse
import os
import time

for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[variable] = "1"

import joblib
import numpy as np
from joblib import Parallel, delayed
from sklearn.ensemble import RandomForestRegressor
from threadpoolctl import threadpool_limits
from xgboost import XGBRegressor

from dataset import (ACTION, ALL, BASE, B3, COMMITTED, CONTRACTS, OUT, PILOT, ROOT, TARGETS,
                     check, csv_rows, read, save, sha)
from config import MODELS, RF_PARAMS, XGB_PARAMS, RIDGE_ALPHAS, SEED, WORKERS
from estimators import linear_model, persistence

RUN = OUT / "fits"
TRACKS = (("O25","M0"), ("O25","Mdiv"), ("O25","Mfull"),
          ("S23","Mdiv"), ("P27","Mdiv"), ("A29","M0"), ("A29","Mdiv"))
RF = "RandomForest"
XGB = "XGBoost"
SCREEN_INDEX = (2, 6, 10)
PRIMARY_COMPONENTS = tuple(range(12))
ABLATIONS = {
    "indoor_history": frozenset(f for f in ALL if f.startswith("indoor_temp")),
    "electric_history": frozenset(f for f in ALL if f.startswith(("cooling_electric_power", "fan_electric_power"))),
    "weather_solar": frozenset(f for f in ALL if f.startswith(("outdoor_temp", "solar_"))),
    "occupancy_calendar": frozenset(f for f in ALL if f.startswith(("occupancy_", "time_of_day_"))),
    "control_and_plan": frozenset(ACTION) | {"cooling_setpoint_current_c", "heating_setpoint_current_c",
                                             "cooling_override_current"},
    "committed_command": frozenset(COMMITTED),
}

def metadata():
    archive = np.load(OUT / "development_overlay.npz", allow_pickle=False)
    provenance = read(OUT / "DATASET_PROVENANCE.json")
    check(sha(OUT / "development_overlay.npz") == provenance["overlay_sha256"], "Overlay hash mismatch")
    x, y, ids, aux = (archive[k] for k in ("X","Y","ids","aux"))
    check(list(archive["features"]) == list(ALL) and list(archive["targets"]) == TARGETS, "Schema drift")
    columns = dict(zip(archive["aux_columns"], aux.T))
    return x, y, ids, columns

def training_masks(ids, columns):
    folder = BASE / "run_01"
    folds = read(folder / "outer_folds.json")
    inner_path = folder / "ridge_inner_splits.json"
    hashes = read(BASE / "OUTPUT_CHECKSUMS_SHA256.json")
    for key in ("run_01/outer_folds.json", "run_01/ridge_inner_splits.json",
                "run_01/development_oof_predictions.npz", "run_01/origin_folds.csv"):
        check(sha(BASE / key) == hashes[key], f"Historical output hash drift: {key}")
    inner = read(inner_path)
    plan = PILOT / "hvac_control_expansion_v1/MATCHED_SIZE_TIMESTAMP_PLAN.json"
    check(sha(plan) == read(B3 / "AUDIT_RESULTS.json")["Mdiv_timestamp_plan_sha256"], "Mdiv map drift")
    saved = read(plan)
    check(all(row["seed"] == 20261118 for row in saved), "Mdiv seed drift")
    wanted = {(row["group_id"], row["time_s"]):row["policy_pair"] == "C15_C45" for row in saved}
    group, policy = ids[:,2], ids[:,4]
    orig = np.isin(policy, ("N","X"))
    alt = np.isin(policy, ("C15","C45"))
    matched = np.array([(alt[i] if wanted.get((g,int(t)), False) else orig[i])
                        for i,(g,t) in enumerate(zip(group, columns["time"]))])
    for row in folds:
        fold = row["fold"]
        in_train = np.isin(group, row["train_groups"])
        in_test = np.isin(group, row["held_groups"])
        check(not np.any(in_train & in_test) and np.array_equal(in_test, columns["fold"] == fold),
              "Fold population mismatch")
        masks = {"M0":orig & in_train, "Mdiv":matched & in_train, "Mfull":(orig|alt) & in_train}
        check([int(m.sum()) for m in masks.values()] == [10224,10224,11928 if fold in (1,4) else 13632],
              "Train sizes differ from frozen design")
        check(np.sum(orig & in_test) == 3408 and np.sum(alt & in_test) == (1704 if fold in (1,4) else 0),
              "Held sizes differ from frozen design")
        for g in np.unique(group[masks["M0"]]):
            at = group == g
            check(np.array_equal(np.sort(columns["time"][at & masks["M0"]]),
                                 np.sort(columns["time"][at & masks["Mdiv"]])), "Mdiv clock marginals changed")
        yield fold, masks, in_test, [s for s in inner if s["outer_fold"] == fold]

def ridge_fit(x, y, groups, inner):
    actuals, errors, memberships = {}, {}, {}
    for split in inner:
        train = np.isin(groups, split["train_groups"])
        held = np.isin(groups, split["held_groups"])
        check(not np.any(train & held) and np.all(train | held), "Inner group split mismatch")
        for alpha in RIDGE_ALPHAS:
            model = linear_model("Ridge", alpha).fit(x[train], y[train])
            np.testing.assert_allclose(model.named_steps["scale"].mean_, x[train].mean(axis=0), atol=1e-12)
            err = model.predict(x[held]) - y[held]
            for g in split["held_groups"]:
                mask = groups[held] == g
                errors[alpha,g] = (np.sqrt(np.mean(err[mask]**2, axis=0)), np.mean(abs(err[mask]), axis=0))
        memberships[split["inner_fold"]] = split["held_groups"]
    all_groups = sorted(set(groups))
    for alpha in RIDGE_ALPHAS:
        rmse, mae = np.mean([errors[alpha,g] for g in all_groups], axis=0)
        actuals[alpha] = list(zip(rmse.tolist(), mae.tolist()))
    chosen = np.array([min((*actuals[a][j], a) for a in RIDGE_ALPHAS)[2] for j in range(y.shape[1])])
    return linear_model("Ridge", chosen).fit(x, y), {
        "chosen":chosen.tolist(), "inner_scores_rmse_mae":actuals, "inner_held_groups":memberships}

def fit(model, fold, x, y, groups, inner, indices):
    if model == "Ridge":
        return ridge_fit(x, y, groups, inner)
    if model == "OLS":
        return linear_model(model).fit(x, y), {}
    def fit_one(j, target_index):
        seed = SEED + 1000*fold + target_index
        reg = (RandomForestRegressor(**RF_PARAMS, random_state=seed) if model == RF
               else XGBRegressor(**XGB_PARAMS, random_state=seed))
        return reg.fit(x, y[:,j])
    return Parallel(n_jobs=WORKERS, prefer="threads")(
        delayed(fit_one)(j,i) for j,i in enumerate(indices)), {}

def predict(model, x):
    if isinstance(model, list):
        return np.column_stack([reg.predict(x) for reg in model])
    return model.predict(x)

def proof_ids(ids):
    import hashlib
    return hashlib.sha256(("\n".join(ids)+"\n").encode("utf-8")).hexdigest()

def fit_save(fold, model, config, dataset, stage, x, y, ids, train, held, inner,
             features, target_idx, keep_model=False):
    key = f"{stage}_{config}_{dataset}_{model}_f{fold}"
    fpath = RUN / (key+".npz")
    meta_path = RUN / (key+".json")
    model_path = RUN / (key+".joblib")
    if fpath.exists() and meta_path.exists() and (not keep_model or model_path.exists()):
        return
    columns = [ALL.index(f) for f in features]
    xtrain = x[train][:,columns]
    xtest = x[held][:,columns]
    ytrain = y[train][:,target_idx]
    started = time.perf_counter()
    reg, info = fit(model, fold, xtrain, ytrain, ids[train,2], inner, target_idx)
    elapsed = time.perf_counter()-started
    fitted_preprocessing = None
    if model in ("OLS","Ridge"):
        scaler = reg.named_steps["scale"]
        np.testing.assert_allclose(scaler.mean_, xtrain.mean(axis=0), atol=1e-12)
        fitted_preprocessing = {"mean":scaler.mean_.tolist(), "scale":scaler.scale_.tolist()}
    pred = predict(reg, xtest)
    check(pred.shape == (held.sum(),len(target_idx)) and np.isfinite(pred).all(), "Prediction failure")
    if keep_model:
        joblib.dump({"model":reg, "model_family":model, "contract":config, "data":dataset,
                     "features":features, "targets":[TARGETS[i] for i in target_idx],
                     "fold":fold, "status":"DEVELOPMENT_FOLD_RESEARCH"},
                    model_path, compress=2)
        np.testing.assert_allclose(predict(joblib.load(model_path)["model"], xtest[:3]),
                                   pred[:3], rtol=1e-9, atol=1e-10)
    np.savez_compressed(fpath, prediction=pred, held=np.flatnonzero(held), targets=target_idx)
    save(meta_path, {"fit":key, "model":model, "fold":fold, "config":config, "dataset":dataset,
                     "stage":stage, "train_count":int(train.sum()), "held_count":int(held.sum()),
                     "train_origin_ids_sha256":proof_ids(ids[train,0]),
                     "held_origin_ids_sha256":proof_ids(ids[held,0]),
                     "target_training_value_sha256":__import__("hashlib").sha256(ytrain.tobytes()).hexdigest(),
                     "features":list(features), "target_names":[TARGETS[i] for i in target_idx],
                     "fit_seconds":elapsed, "preprocessing":fitted_preprocessing, "ridge":info,
                     "predictions_sha256":sha(fpath), "model_sha256":sha(model_path) if keep_model else None})
    print(f"{key}: {elapsed:.2f}s", flush=True)

def reuse_original(fold, model, x, y, ids, train, held):
    key = f"main_O25_M0_{model}_f{fold}"
    out = RUN/(key+".npz")
    detail = RUN/(key+".json")
    if out.exists() and detail.exists():
        return
    old = BASE/"run_01"
    hashes = read(BASE / "OUTPUT_CHECKSUMS_SHA256.json")
    archive = np.load(old/"development_oof_predictions.npz", allow_pickle=False)
    origs = csv_rows(old/"origin_folds.csv")
    check([r["row_id"] for r in origs] == ids[:13632,0].tolist(), "Historical OOF rows differ")
    np.testing.assert_array_equal(archive["actual"],y[:13632])
    np.testing.assert_array_equal(archive["fold_id"],[int(r["fold"]) for r in origs])
    model_path = old/"models"/f"{model}_fold_{fold}.joblib"
    check(sha(model_path) == hashes[model_path.relative_to(BASE).as_posix()], "Historical model hash")
    bundle = joblib.load(model_path)
    check(bundle["features"] == list(CONTRACTS["O25"]) and bundle["targets"] == TARGETS, "Historical model schema")
    indices = np.flatnonzero(held)
    original = indices < 13632
    prediction = np.empty((len(indices),16))
    prediction[original] = archive[model][indices[original]]
    if np.any(~original):
        prediction[~original] = bundle["model"].predict(x[indices[~original],:25])
    np.savez_compressed(out, prediction=prediction, held=indices, targets=np.arange(16))
    save(detail, {"fit":key,"stage":"main","model":model,"fold":fold,"config":"O25","dataset":"M0",
                  "train_count":int(train.sum()),"held_count":int(held.sum()),
                  "train_origin_ids_sha256":proof_ids(ids[train,0]),"held_origin_ids_sha256":proof_ids(ids[held,0]),
                  "historical_model":model_path.relative_to(ROOT).as_posix(),
                  "model_sha256":sha(model_path),"predictions_sha256":sha(out),
                  "historical_oof_sha256":sha(old/"development_oof_predictions.npz")})
    print(f"{key}: reused", flush=True)

def screen_choices(y, ids, columns):
    selections = {}
    original = np.isin(ids[:,4], ("N","X"))
    for model in (RF,XGB,"Ridge","OLS"):
        scores = {}
        for group_name in ABLATIONS:
            observed, predictions, groups = [], [], []
            for fold in range(1,5):
                p = np.load(RUN/f"screen_{group_name}_M0_{model}_f{fold}.npz", allow_pickle=False)
                indices = p["held"]
                m = original[indices]
                eval_idx = indices[m]
                observed.append(y[eval_idx][:,SCREEN_INDEX])
                predictions.append(p["prediction"][m])
                groups.extend(ids[eval_idx,2])
            e = np.vstack(predictions)-np.vstack(observed)
            groups = np.asarray(groups)
            scores[group_name] = np.mean([[
                np.mean(abs(e[groups==g,0])),
                np.mean(abs(e[groups==g,1]+e[groups==g,2]))] for g in np.unique(groups)], axis=0).tolist()
        selections[model] = {"screen_original_group_macro_mae":scores,
                             "temperature":min(scores, key=lambda g:(scores[g][0],g)),
                             "electricity":min(scores, key=lambda g:(scores[g][1],g))}
    return selections

def main(args):
    RUN.mkdir(exist_ok=True)
    x,y,ids,columns = metadata()
    folds = list(training_masks(ids, columns))
    for fold, masks, held, _ in folds:
        np.savez_compressed(RUN/f"membership_f{fold}.npz", **{k:ids[v,0] for k,v in masks.items()},
                            held=ids[held,0])
    save(OUT/"EXPERIMENT_CONFIG.json", {"tracks":TRACKS, "screen_contract":"A29",
         "screen_targets":[TARGETS[i] for i in SCREEN_INDEX],
         "followup_rule":"For each model select one removal per primary quantity by minimum original-group macro MAE at +15 min. Follow-up is exploratory within reused development folds.",
         "followup_targets":[TARGETS[i] for i in PRIMARY_COMPONENTS],
         "ablation_removals":{k:sorted(v) for k,v in ABLATIONS.items()}, "rf":RF_PARAMS,"xgboost":XGB_PARAMS,
         "seed":SEED,"model_seed_rule":"SEED+1000*fold+original_target_index","ridge_alpha_grid":RIDGE_ALPHAS,
         "ridge_inner_split_source":str(BASE/"run_01/ridge_inner_splits.json"), "threads":WORKERS,
         "no_additional_weather_year":True, "B1_NREF":"QA only"})
    with threadpool_limits(limits=1):
        if args.phase in ("all","main"):
            for config,dataset in TRACKS:
                for fold,masks,held,inner in folds:
                    for model in MODELS[1:]:
                        if config == "O25" and dataset == "M0":
                            reuse_original(fold,model,x,y,ids,masks[dataset],held)
                        else:
                            fit_save(fold,model,config,dataset,"main",x,y,ids,masks[dataset],held,inner,
                                     CONTRACTS[config],tuple(range(16)),keep_model=config in ("O25","P27","S23"))
        if args.phase in ("all","ablation"):
            for name, removed in ABLATIONS.items():
                columns_kept = tuple(f for f in ALL if f not in removed)
                for fold,masks,held,inner in folds:
                    for model in MODELS[1:]:
                        fit_save(fold,model,name,"M0","screen",x,y,ids,masks["M0"],held,inner,
                                 columns_kept,SCREEN_INDEX)
            selections = screen_choices(y,ids,columns)
            save(OUT/"ABLATION_FOLLOWUP_CHOICES.json",selections)
            for model, selected in selections.items():
                for name in sorted({selected["temperature"],selected["electricity"]}):
                    columns_kept = tuple(f for f in ALL if f not in ABLATIONS[name])
                    for fold,masks,held,inner in folds:
                        fit_save(fold,model,name,"M0","followup",x,y,ids,masks["M0"],held,inner,
                                 columns_kept,PRIMARY_COMPONENTS)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("all","main","ablation"),default="all")
    main(parser.parse_args())


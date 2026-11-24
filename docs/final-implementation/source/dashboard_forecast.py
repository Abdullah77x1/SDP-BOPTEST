"""Inference and target-time tracking for the frozen dashboard forecast."""

import numpy as np
import sklearn

from stage4e_d0.plan import STEP, TEMP

from . import forecast_comparison as forecast
from .archive_dataset import (DEFAULT_OUTPUT, EXTENDED_VERSION, FEATURES, FORECAST, HORIZONS, STATE, TARGETS,
                              interval_history, predecision_action, require, state_features)

DATASET = DEFAULT_OUTPUT.with_name("unified-archive-v1-1")
SELECTION = DEFAULT_OUTPUT.with_name("forecast-comparison-final-v1") / "selection"
QUANTITIES = ("indoor_temperature", "cooling", "fan", "heating")
TARGET_UNITS = dict(zip(TARGETS, ("degC",)*4 + ("kW electric",)*8 + ("kW thermal",)*4, strict=True))


def forecast_rows(origin, prediction):
    rows = []
    for lead, values in zip(HORIZONS, prediction.reshape(4, len(HORIZONS)).T, strict=True):
        row = dict(zip(QUANTITIES, map(float, values), strict=True))
        rows.append(dict(horizon_min=lead, target=origin + 60*lead, **row,
                         combined=row["cooling"] + row["fan"]))
    return rows


class FrozenForecast:
    def __init__(self, selection=SELECTION, dataset=DATASET):
        self.metadata = meta = forecast.read_json(selection / "selected_model.json")
        manifest = forecast.read_json(dataset / "manifest.json")
        require(manifest["version"] == EXTENDED_VERSION and tuple(manifest["feature_columns"]) == FEATURES
                and manifest["target_columns"] == TARGETS and manifest["horizons_min"] == HORIZONS
                and manifest["target_units"] == TARGET_UNITS and
                forecast.file_sha(dataset / "manifest.json") == meta["dataset_manifest_sha256"],
                "The selected model is bound to a different dataset contract")
        require(meta["name"] == "forest_action" and tuple(meta["features"]) == FEATURES
                and meta["targets"] == TARGETS and meta["horizons_min"] == HORIZONS
                and meta["meant_for_ordinary_forecasting"] and meta["what_if_qualified"] is False,
                "The selected model schema or qualification differs")
        require(meta["environment"]["scikit_learn"] == sklearn.__version__,
                f"Use scikit-learn {meta['environment']['scikit_learn']} to load the frozen forest")
        self.model = forecast.load_model(selection / "selected_model.joblib", meta["name"], meta["sha256"])
        require(len(self.model) == len(TARGETS) and all(est.n_features_in_ == len(FEATURES) for est in self.model),
                "Frozen forest has the wrong input or output width")

    def at(self, origin, endpoints, intervals, issued, block, prior_veto, actual=None):
        reason = "Waiting for 35 minutes of verified measurement history"
        if issued is None:
            reason = "No valid issued forecast at this origin"
        # The builders receive only the specific completed origins and intervals they need.
        try:
            window = {t: endpoints[t] for t in (origin, origin-STEP, origin-1800)}
            power = {t: intervals[t] for t in window}
        except KeyError:
            window = None
        if window is not None and issued is not None:
            try:
                raw = issued["data"]
                require(issued["issued_at_sim"] == origin and raw["time"][:7] == list(range(origin, origin+1801, STEP))
                        and all(len(raw[k]) >= 7 and np.isfinite(raw[k][:7]).all() for k in FORECAST),
                        "Missing, nonfinite or misaligned issued forecast")
                state = state_features(origin, window, power, raw)
                action = predecision_action(origin, block, prior_veto)
                x = np.asarray([*(state[k] for k in STATE), *action], dtype=float)
                require(x.shape == (27,) and np.isfinite(x).all(), "Missing or nonfinite predecision inputs")
                prediction = forecast.predict(self.model, self.metadata["name"], x[None, :])[0]
                require((prediction[4:] >= forecast.NEGATIVE_POWER).all(), "Invalid equipment power forecast")
                return {"source": "Random Forest", "origin": origin, "values": forecast_rows(origin, prediction),
                        "reason": "", "features": x.tolist()}
            except (KeyError, ValueError, TypeError) as error:
                reason = str(error)
        if actual is not None:
            values = (endpoints[origin][TEMP]-273.15, *(actual[key] for key in QUANTITIES[1:]))
            if np.isfinite(values).all():
                x = np.full((1, len(FEATURES)), np.nan)
                x[0, [FEATURES.index(key) for key in forecast.PERSISTENCE_INPUTS]] = values
                return {"source": "Persistence fallback", "origin": origin,
                        "values": forecast_rows(origin, forecast.persistence(x)[0]), "reason": reason}
        return {"source": "Unavailable", "origin": origin, "values": [], "reason": reason}


def completed_power(chunk, end):
    """Use the training grid for lag inputs, with no partial or future samples."""
    if chunk["time"] != list(range(end-STEP, end+1, 30)):
        # A live solver can expose extra event samples. A sparse gap or ambiguous
        # event interval is left unavailable to the forest.
        return None
    try:
        return interval_history(chunk)[end]
    except ValueError:
        return None

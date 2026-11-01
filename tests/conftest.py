"""Explicit learned artifact fixtures; never used outside tests."""
import hashlib
import json

import sklearn
import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

from mini_flood.ai_settings import FEATURE_NAMES, load_ai_config


def make_bundle(path, config=None, constant=None):
    cfg = config or load_ai_config()
    path.mkdir(parents=True, exist_ok=True)
    X = pd.DataFrame(np.random.default_rng(17).uniform(0, 20, (100, len(FEATURE_NAMES))), columns=FEATURE_NAMES)
    artifacts = {}
    for h in cfg.horizons_seconds:
        y = (X.water_level_cm + X.water_delta_window_cm * h / cfg.data.rise_window_seconds
             if constant is None else np.full(len(X), constant))
        model = Ridge(alpha=0).fit(X, y)
        filename = f"model_{h}.joblib"
        joblib.dump(model, path / filename)
        artifacts[str(h)] = {"file": filename, "algorithm": "ridge",
                             "sha256": hashlib.sha256((path / filename).read_bytes()).hexdigest()}
    metadata = {"model_version": "test-learned", "features": list(FEATURE_NAMES),
                "feature_signature": cfg.feature_signature, "horizons_seconds": list(cfg.horizons_seconds),
                "library_versions": {"scikit_learn": sklearn.__version__}, "data_source": "real", "promoted": True, "artifacts": artifacts}
    (path / "mini_flood_metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    return metadata

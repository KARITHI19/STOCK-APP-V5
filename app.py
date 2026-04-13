# app.py

import os
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")

import streamlit as st
import pandas as pd
import numpy as np
import tensorflow as tf
from sklearn.preprocessing import MinMaxScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import hashlib
import re
from io import BytesIO
import joblib
from supabase import create_client, Client

# ----------------------------------------
# Supabase Configuration
# ----------------------------------------
DEFAULT_SUPABASE_URL = "https://bqumqfdisvihzknhaaej.supabase.co"
MODEL_SUITES_DIR = os.path.join("models", "saved_suites")
MODEL_SUITE_VERSION = "v7"
SEQUENCE_LENGTH = 60


def get_secret_value(key, default=""):
    env_value = os.getenv(key)
    if env_value not in (None, ""):
        return env_value

    try:
        secret_value = st.secrets.get(key, default)
        if secret_value not in (None, ""):
            return secret_value
    except Exception:
        pass

    return default


SUPABASE_URL = get_secret_value("SUPABASE_URL", DEFAULT_SUPABASE_URL)
SUPABASE_KEY = get_secret_value("SUPABASE_KEY", "")
SUPABASE_SERVICE_ROLE_KEY = get_secret_value("SUPABASE_SERVICE_ROLE_KEY", "") or get_secret_value("SUPABASE_SECRET_KEY", "")
MODEL_STORAGE_BUCKET = get_secret_value("SUPABASE_MODEL_BUCKET", "model-suites")
MODEL_STORAGE_PREFIX = get_secret_value("MODEL_STORAGE_PREFIX", "saved_suites")
MAIN_APP_URL = get_secret_value("MAIN_APP_URL", "http://localhost:8501/")
RESET_APP_URL = get_secret_value("RESET_APP_URL", "https://stock-app-v5-igwqkscqgidq6buhuxksar.streamlit.app/")
ADMIN_PANEL_URL = get_secret_value("ADMIN_PANEL_URL", "https://stock-app-v5-ekjlrgbrp3zelhxcuxgrzv.streamlit.app/")


@st.cache_resource(show_spinner=False)
def get_supabase_client():
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None

    try:
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception:
        return None


@st.cache_resource(show_spinner=False)
def get_supabase_admin_client():
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        return None

    try:
        return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    except Exception:
        return None


def get_upload_signature(file_name, file_bytes):
    payload = file_name.encode("utf-8") + file_bytes
    return hashlib.md5(payload).hexdigest()


@st.cache_data(show_spinner=False)
def load_uploaded_dataframe(file_bytes: bytes):
    df = pd.read_csv(BytesIO(file_bytes))
    return clean_uploaded_dataframe(df)


def get_nested_value(value, key, default=None):
    if value is None:
        return default
    if isinstance(value, dict):
        return value.get(key, default)
    if hasattr(value, key):
        return getattr(value, key)
    if hasattr(value, "model_dump"):
        try:
            dumped = value.model_dump()
            if isinstance(dumped, dict):
                return dumped.get(key, default)
        except Exception:
            return default
    return default


def is_user_disabled(user) -> bool:
    app_metadata = get_nested_value(user, "app_metadata", {}) or {}
    return bool(app_metadata.get("disabled", False))


def is_admin_user(user) -> bool:
    app_metadata = get_nested_value(user, "app_metadata", {}) or {}
    return str(app_metadata.get("role", "")).strip().lower() == "admin"


def normalize_users(response):
    if response is None:
        return []
    if isinstance(response, list):
        return response
    users = get_nested_value(response, "users")
    if isinstance(users, list):
        return users
    try:
        return list(response)
    except TypeError:
        return []


def list_auth_users():
    admin_client = get_supabase_admin_client()
    if admin_client is None:
        return []

    try:
        return normalize_users(admin_client.auth.admin.list_users())
    except TypeError:
        return normalize_users(admin_client.auth.admin.list_users(page=1, per_page=200))
    except Exception:
        return []


def email_exists_in_auth(email: str) -> bool:
    target = email.strip().lower()
    if not target:
        return False
    for user in list_auth_users():
        current_email = str(get_nested_value(user, "email", "") or "").strip().lower()
        if current_email == target:
            return True
    return False


def validate_password_strength(password: str) -> str | None:
    if len(password) < 8:
        return "Password must be at least 8 characters."
    if not re.search(r"[A-Z]", password):
        return "Password must include at least one uppercase letter."
    if not re.search(r"[a-z]", password):
        return "Password must include at least one lowercase letter."
    if not re.search(r"\d", password):
        return "Password must include at least one number."
    if not re.search(r"[^A-Za-z0-9]", password):
        return "Password must include at least one special character."
    return None


def supports_prediction_metadata_columns() -> bool:
    cache_key = "supports_prediction_metadata_columns"
    if cache_key in st.session_state:
        return bool(st.session_state[cache_key])

    supported = False
    if supabase is not None:
        try:
            supabase.table("predictions").select("prediction_direction, model_used").limit(1).execute()
            supported = True
        except Exception:
            supported = False

    st.session_state[cache_key] = supported
    return supported


def clean_uploaded_dataframe(df: pd.DataFrame):
    cleaned_df = df.copy()
    cleaned_df.columns = [str(col).strip() for col in cleaned_df.columns]
    cleaned_df = cleaned_df.replace(["None", "none", "nan", "NaN", ""], np.nan)

    parsed_date_column = None

    if "Date" in cleaned_df.columns:
        parsed_dates = pd.to_datetime(cleaned_df["Date"], errors="coerce")
        if parsed_dates.notna().sum() >= 3:
            parsed_date_column = "Date"
            cleaned_df["Date"] = parsed_dates

    if parsed_date_column is None:
        for column in cleaned_df.columns:
            parsed_dates = pd.to_datetime(cleaned_df[column], errors="coerce")
            if parsed_dates.notna().sum() >= 3:
                parsed_date_column = column
                if column != "Date":
                    cleaned_df = cleaned_df.rename(columns={column: "Date"})
                cleaned_df["Date"] = pd.to_datetime(cleaned_df["Date"], errors="coerce")
                break

    for column in cleaned_df.columns:
        if column == "Date":
            continue
        cleaned_df[column] = pd.to_numeric(cleaned_df[column], errors="coerce")

    numeric_cols = cleaned_df.select_dtypes(include=[np.number]).columns.tolist()

    if parsed_date_column is not None:
        cleaned_df = cleaned_df[cleaned_df["Date"].notna()]
        if numeric_cols:
            cleaned_df = cleaned_df.dropna(subset=numeric_cols, how="all")
        cleaned_df = cleaned_df.sort_values("Date")

    cleaned_df = cleaned_df.reset_index(drop=True)
    return cleaned_df


def build_technical_indicator_features(
    df: pd.DataFrame,
    target_column: str,
    include_ma10: bool,
    include_ma20: bool,
    include_ma50: bool,
    include_ema10: bool,
    include_ema20: bool,
    include_rsi: bool,
    include_macd: bool,
):
    featured_df = df.copy()
    feature_columns = [target_column]
    selected_indicator_labels = []
    selected_indicator_keys = []

    if include_ma10:
        featured_df["MA_10"] = featured_df[target_column].rolling(window=10, min_periods=10).mean()
        feature_columns.append("MA_10")
        selected_indicator_labels.append("MA10")
        selected_indicator_keys.append("ma10")

    if include_ma20:
        featured_df["MA_20"] = featured_df[target_column].rolling(window=20, min_periods=20).mean()
        feature_columns.append("MA_20")
        selected_indicator_labels.append("MA20")
        selected_indicator_keys.append("ma20")

    if include_ma50:
        featured_df["MA_50"] = featured_df[target_column].rolling(window=50, min_periods=50).mean()
        feature_columns.append("MA_50")
        selected_indicator_labels.append("MA50")
        selected_indicator_keys.append("ma50")

    if include_ema10:
        featured_df["EMA_10"] = featured_df[target_column].ewm(span=10, adjust=False).mean()
        feature_columns.append("EMA_10")
        selected_indicator_labels.append("EMA10")
        selected_indicator_keys.append("ema10")

    if include_ema20:
        featured_df["EMA_20"] = featured_df[target_column].ewm(span=20, adjust=False).mean()
        feature_columns.append("EMA_20")
        selected_indicator_labels.append("EMA20")
        selected_indicator_keys.append("ema20")

    if include_rsi:
        delta = featured_df[target_column].diff()
        gains = delta.clip(lower=0)
        losses = -delta.clip(upper=0)
        avg_gain = gains.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
        avg_loss = losses.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        featured_df["RSI_14"] = (100 - (100 / (1 + rs))).fillna(50.0)
        feature_columns.append("RSI_14")
        selected_indicator_labels.append("RSI")
        selected_indicator_keys.append("rsi14")

    if include_macd:
        ema_fast = featured_df[target_column].ewm(span=12, adjust=False).mean()
        ema_slow = featured_df[target_column].ewm(span=26, adjust=False).mean()
        featured_df["MACD_12_26"] = ema_fast - ema_slow
        feature_columns.append("MACD_12_26")
        selected_indicator_labels.append("MACD")
        selected_indicator_keys.append("macd12_26")

    return featured_df, feature_columns, selected_indicator_labels, selected_indicator_keys


def build_dataset_signature(df: pd.DataFrame, feature_names, target_column):
    signature_columns = list(feature_names)
    if "Date" in df.columns:
        signature_columns = ["Date", *signature_columns]

    signature_df = df[signature_columns].copy()

    if "Date" in signature_df.columns:
        signature_df["Date"] = pd.to_datetime(signature_df["Date"], errors="coerce").astype("int64")

    hash_values = pd.util.hash_pandas_object(signature_df, index=True).values
    payload = hash_values.tobytes() + "|".join(feature_names).encode("utf-8") + f"|{target_column}".encode("utf-8")
    return hashlib.md5(payload).hexdigest()


def build_sequences(feature_data, target_data, sequence_length):
    X, y = [], []

    for i in range(sequence_length, len(feature_data)):
        X.append(feature_data[i-sequence_length:i])
        y.append(target_data[i])

    return np.array(X), np.array(y)


def inverse_target_values(scaled_values, target_scaler):
    values = np.asarray(scaled_values).reshape(-1, 1)
    return target_scaler.inverse_transform(values).reshape(-1)


def compute_direction_metrics(actual_values, predicted_values, reference_start):
    actual_values = np.asarray(actual_values).reshape(-1)
    predicted_values = np.asarray(predicted_values).reshape(-1)
    if len(actual_values) == 0 or len(predicted_values) == 0 or len(actual_values) != len(predicted_values):
        return {"Direction Accuracy": np.nan, "Up Precision": np.nan, "Down Precision": np.nan}

    prev_actual = np.concatenate([[reference_start], actual_values[:-1]])
    actual_up = actual_values >= prev_actual
    pred_up = predicted_values >= prev_actual

    direction_accuracy = float(np.mean(actual_up == pred_up))

    up_mask = pred_up
    down_mask = ~pred_up
    up_precision = float(np.mean(actual_up[up_mask])) if np.any(up_mask) else np.nan
    down_precision = float(np.mean((~actual_up)[down_mask])) if np.any(down_mask) else np.nan

    return {
        "Direction Accuracy": direction_accuracy,
        "Up Precision": up_precision,
        "Down Precision": down_precision,
    }


def slugify_name(value):
    slug = re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower())
    return slug.strip("_") or "model"


def get_suite_dir(suite_key):
    suite_hash = hashlib.md5(suite_key.encode("utf-8")).hexdigest()
    return os.path.join(MODEL_SUITES_DIR, suite_hash)


def get_suite_meta_path(suite_key):
    return os.path.join(get_suite_dir(suite_key), "suite_meta.joblib")


def get_suite_storage_prefix(suite_key):
    suite_hash = hashlib.md5(suite_key.encode("utf-8")).hexdigest()
    return f"{MODEL_STORAGE_PREFIX}/{suite_hash}"


def ensure_model_storage_bucket():
    admin_client = get_supabase_admin_client()
    if admin_client is None:
        return False

    try:
        admin_client.storage.get_bucket(MODEL_STORAGE_BUCKET)
        return True
    except Exception:
        try:
            admin_client.storage.create_bucket(
                MODEL_STORAGE_BUCKET,
                options={"public": False},
            )
            return True
        except Exception:
            return False


def sync_suite_to_storage(suite_key):
    admin_client = get_supabase_admin_client()
    if admin_client is None or not ensure_model_storage_bucket():
        return False

    suite_dir = get_suite_dir(suite_key)
    if not os.path.isdir(suite_dir):
        return False

    bucket = admin_client.storage.from_(MODEL_STORAGE_BUCKET)
    remote_prefix = get_suite_storage_prefix(suite_key)

    try:
        for entry in os.listdir(suite_dir):
            local_path = os.path.join(suite_dir, entry)
            if not os.path.isfile(local_path):
                continue

            bucket.upload(
                f"{remote_prefix}/{entry}",
                local_path,
                {"content-type": "application/octet-stream", "upsert": "true"},
            )
        return True
    except Exception:
        return False


def restore_suite_from_storage(suite_key):
    admin_client = get_supabase_admin_client()
    if admin_client is None or not ensure_model_storage_bucket():
        return False

    remote_prefix = get_suite_storage_prefix(suite_key)
    bucket = admin_client.storage.from_(MODEL_STORAGE_BUCKET)

    try:
        objects = bucket.list(remote_prefix)
    except Exception:
        return False

    if not objects:
        return False

    suite_dir = get_suite_dir(suite_key)
    os.makedirs(suite_dir, exist_ok=True)

    restored_any = False
    for item in objects:
        file_name = item.get("name")
        if not file_name:
            continue

        remote_path = f"{remote_prefix}/{file_name}"
        local_path = os.path.join(suite_dir, file_name)

        try:
            payload = bucket.download(remote_path)
            with open(local_path, "wb") as output_file:
                output_file.write(payload)
            restored_any = True
        except Exception:
            continue

    return restored_any


def save_candidate_artifact(candidate, suite_dir):
    model_name = candidate["name"]
    kind = candidate["kind"]
    model_slug = slugify_name(model_name)
    artifact_path = None

    if kind == "sequence" and candidate.get("model") is not None:
        artifact_path = os.path.join(suite_dir, f"{model_slug}.keras")
        candidate["model"].save(artifact_path)
    elif kind in {"tabular", "stat"} and candidate.get("model") is not None:
        artifact_path = os.path.join(suite_dir, f"{model_slug}.joblib")
        joblib.dump(candidate["model"], artifact_path)

    return artifact_path


def load_candidate_artifact(record):
    kind = record.get("kind")
    artifact_path = record.get("artifact_path")

    if not artifact_path:
        return None

    if not os.path.exists(artifact_path):
        raise FileNotFoundError(f"Missing saved artifact: {artifact_path}")

    if kind == "sequence":
        return tf.keras.models.load_model(artifact_path)

    return joblib.load(artifact_path)


def save_model_suite(
    suite_key,
    leaderboard_df,
    best_model_name,
    candidate_models,
    feature_columns,
    target_column,
    feature_scaler,
    target_scaler,
):
    suite_dir = get_suite_dir(suite_key)
    os.makedirs(suite_dir, exist_ok=True)

    saved_models = {}
    for model_name, candidate in candidate_models.items():
        artifact_path = save_candidate_artifact(candidate, suite_dir)
        saved_models[model_name] = {
            "name": candidate["name"],
            "kind": candidate["kind"],
            "artifact_path": artifact_path,
            "predictions_actual": np.asarray(candidate["predictions_actual"]).reshape(-1).tolist(),
            "note": candidate.get("note", ""),
        }

    payload = {
        "key": suite_key,
        "best_model_name": best_model_name,
        "leaderboard": leaderboard_df.to_dict(orient="records"),
        "models": saved_models,
        "feature_columns": list(feature_columns),
        "target_column": target_column,
        "feature_scaler": feature_scaler,
        "target_scaler": target_scaler,
    }
    joblib.dump(payload, get_suite_meta_path(suite_key))
    sync_suite_to_storage(suite_key)


def load_model_suite(suite_key):
    meta_path = get_suite_meta_path(suite_key)
    suite_source = "saved"
    if not os.path.exists(meta_path):
        restored = restore_suite_from_storage(suite_key)
        if restored:
            suite_source = "cloud"
        if not os.path.exists(meta_path):
            return None

    if not os.path.exists(meta_path):
        return None

    try:
        payload = joblib.load(meta_path)
        if payload.get("key") != suite_key:
            return None

        models = {}
        loaded_any_runtime_model = False
        for model_name, record in payload.get("models", {}).items():
            loaded_model = None
            load_error = ""

            if record.get("artifact_path"):
                try:
                    loaded_model = load_candidate_artifact(record)
                    loaded_any_runtime_model = True
                except Exception as exc:
                    load_error = str(exc)

            models[model_name] = {
                "name": record["name"],
                "kind": record["kind"],
                "model": loaded_model,
                "predictions_actual": np.asarray(record.get("predictions_actual", []), dtype=float),
                "note": record.get("note", ""),
                "load_error": load_error,
            }

        if not models:
            return None

        # Baseline has no artifact, so this keeps saved suites usable even if some optional artifacts fail.
        if not loaded_any_runtime_model and "Naive Baseline" not in models:
            return None

        return {
            "key": payload["key"],
            "best_model_name": payload["best_model_name"],
            "leaderboard": pd.DataFrame(payload.get("leaderboard", [])),
            "models": models,
            "source": suite_source,
            "feature_columns": payload.get("feature_columns", []),
            "target_column": payload.get("target_column"),
            "feature_scaler": payload.get("feature_scaler"),
            "target_scaler": payload.get("target_scaler"),
        }
    except Exception:
        return None


def evaluate_predictions(actual, predicted):
    return {
        "MAE": float(mean_absolute_error(actual, predicted)),
        "RMSE": float(np.sqrt(mean_squared_error(actual, predicted))),
        "R2": float(r2_score(actual, predicted)),
    }


def rank_trained_models(leaderboard_df):
    trained_df = leaderboard_df[leaderboard_df["Status"] == "trained"].copy()
    if trained_df.empty:
        return trained_df

    return trained_df.sort_values(["R2", "RMSE", "MAE"], ascending=[False, True, True])


def get_best_model_name(leaderboard_df):
    ranked_df = rank_trained_models(leaderboard_df)
    if ranked_df.empty:
        return None
    return ranked_df.iloc[0]["Model"]


def get_available_model_names(ranked_df, model_suite):
    available_names = []
    models = model_suite.get("models", {})

    for model_name in ranked_df["Model"].tolist():
        candidate = models.get(model_name)
        if not candidate:
            continue

        if candidate["kind"] == "baseline" or candidate.get("model") is not None:
            available_names.append(model_name)

    return available_names


def get_validation_data(X_train, y_train):
    if len(X_train) < 12:
        return X_train, y_train, None, None

    val_size = max(1, int(len(X_train) * 0.1))
    if len(X_train) - val_size < 1:
        return X_train, y_train, None, None

    return X_train[:-val_size], y_train[:-val_size], X_train[-val_size:], y_train[-val_size:]


def build_lstm_model(input_shape):
    model = tf.keras.Sequential([
        tf.keras.layers.Input(shape=input_shape),
        tf.keras.layers.LSTM(96, return_sequences=True),
        tf.keras.layers.Dropout(0.2),
        tf.keras.layers.LSTM(48),
        tf.keras.layers.Dense(24, activation="relu"),
        tf.keras.layers.Dense(1),
    ])
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=0.001),
        loss=tf.keras.losses.Huber(),
    )
    return model


def build_gru_model(input_shape):
    model = tf.keras.Sequential([
        tf.keras.layers.Input(shape=input_shape),
        tf.keras.layers.GRU(96, return_sequences=True),
        tf.keras.layers.Dropout(0.15),
        tf.keras.layers.GRU(48),
        tf.keras.layers.Dense(24, activation="relu"),
        tf.keras.layers.Dense(1),
    ])
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=0.001),
        loss=tf.keras.losses.Huber(),
    )
    return model


def build_bilstm_model(input_shape):
    model = tf.keras.Sequential([
        tf.keras.layers.Input(shape=input_shape),
        tf.keras.layers.Bidirectional(tf.keras.layers.LSTM(64, return_sequences=True)),
        tf.keras.layers.Dropout(0.15),
        tf.keras.layers.Bidirectional(tf.keras.layers.LSTM(32)),
        tf.keras.layers.Dense(24, activation="relu"),
        tf.keras.layers.Dense(1),
    ])
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=0.001),
        loss=tf.keras.losses.Huber(),
    )
    return model


def train_sequence_model(name, builder, X_train, y_train, X_test, note):
    tf.keras.backend.clear_session()
    tf.keras.utils.set_random_seed(42)

    X_fit, y_fit, X_val, y_val = get_validation_data(X_train, y_train)
    model = builder((X_train.shape[1], X_train.shape[2]))

    fit_kwargs = {
        "x": X_fit,
        "y": y_fit,
        "epochs": 40,
        "batch_size": 32,
        "verbose": 0,
        "shuffle": False,
    }

    if X_val is not None and y_val is not None:
        fit_kwargs["validation_data"] = (X_val, y_val)
        fit_kwargs["callbacks"] = [
            tf.keras.callbacks.EarlyStopping(
                monitor="val_loss",
                patience=6,
                restore_best_weights=True,
            ),
            tf.keras.callbacks.ReduceLROnPlateau(
                monitor="val_loss",
                factor=0.5,
                patience=3,
                min_lr=1e-5,
            ),
        ]

    history = model.fit(**fit_kwargs)
    epochs_used = len(history.history.get("loss", []))
    val_loss = history.history.get("val_loss", [])
    training_note = f"{note} Early stopping with dropout regularization; epochs used: {epochs_used}."
    if val_loss:
        training_note += f" Best validation loss: {min(val_loss):.4f}."

    predictions = model.predict(X_test, verbose=0).reshape(-1)
    return {
        "name": name,
        "kind": "sequence",
        "model": model,
        "predictions": predictions,
        "note": training_note,
    }


def train_tuned_tabular_model(name, configs, X_train_flat, y_train, X_test_flat):
    X_fit, y_fit, X_val, y_val = get_validation_data(X_train_flat, y_train)
    best_config = None
    best_rmse = None

    for config_note, builder in configs:
        estimator = builder()
        estimator.fit(X_fit, y_fit)

        if X_val is not None and y_val is not None:
            val_predictions = np.asarray(estimator.predict(X_val)).reshape(-1)
            val_rmse = float(np.sqrt(mean_squared_error(y_val, val_predictions)))
        else:
            val_predictions = np.asarray(estimator.predict(X_fit)).reshape(-1)
            val_rmse = float(np.sqrt(mean_squared_error(y_fit, val_predictions)))

        if best_rmse is None or val_rmse < best_rmse:
            best_rmse = val_rmse
            best_config = (config_note, builder)

    if best_config is None:
        raise ValueError(f"No valid configuration succeeded for {name}.")

    selected_note, selected_builder = best_config
    final_model = selected_builder()
    final_model.fit(X_train_flat, y_train)
    predictions = np.asarray(final_model.predict(X_test_flat)).reshape(-1)

    return {
        "name": name,
        "kind": "tabular",
        "model": final_model,
        "predictions": predictions,
        "note": f"{selected_note} Selected with validation RMSE {best_rmse:.4f}.",
    }


def recursive_forecast(
    candidate,
    scaled_feature_data,
    feature_columns,
    target_column,
    target_scaler,
    days_ahead,
    recent_target_values=None,
):
    if candidate["kind"] == "baseline":
        last_value = float(recent_target_values[-1])
        return np.repeat(last_value, days_ahead)

    if candidate["kind"] == "stat":
        return np.asarray(candidate["model"].forecast(steps=days_ahead)).reshape(-1)

    target_index = feature_columns.index(target_column)
    seq = scaled_feature_data[-SEQUENCE_LENGTH:].copy()
    preds_scaled = []

    for _ in range(days_ahead):
        if candidate["kind"] == "sequence":
            pred = candidate["model"].predict(seq.reshape(1, SEQUENCE_LENGTH, seq.shape[1]), verbose=0)
            pred_value = float(pred[0][0])
        else:
            pred_value = float(candidate["model"].predict(seq.reshape(1, -1))[0])

        preds_scaled.append(pred_value)
        new_row = seq[-1].copy()
        new_row[target_index] = pred_value
        seq = np.vstack([seq[1:], new_row])

    return inverse_target_values(preds_scaled, target_scaler)


def inject_custom_styles():
    st.markdown(
        """
        <style>
        :root {
            --bg-soft: #07111a;
            --panel: #0f1b2b;
            --panel-strong: #13263a;
            --ink: #e5eef8;
            --muted: #9fb0c3;
            --accent: #1d9bf0;
            --accent-2: #10b981;
            --border: rgba(159, 176, 195, 0.18);
        }

        .stApp {
            background:
                radial-gradient(circle at top right, rgba(29, 155, 240, 0.2), transparent 28%),
                radial-gradient(circle at left center, rgba(16, 185, 129, 0.16), transparent 24%),
                linear-gradient(180deg, #040b12 0%, #091521 100%);
            color: var(--ink);
        }

        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #08111d 0%, #0b1725 100%);
        }

        [data-testid="stSidebar"] * {
            color: #f8fafc !important;
        }

        .auth-card {
            background: linear-gradient(180deg, rgba(15,27,43,0.98), rgba(11,23,37,0.98));
            border: 1px solid var(--border);
            border-radius: 18px;
            padding: 18px 20px;
            box-shadow: 0 18px 50px rgba(2, 6, 23, 0.36);
            margin-bottom: 14px;
        }

        .auth-title {
            font-size: 1.05rem;
            font-weight: 700;
            margin-bottom: 0.35rem;
            color: var(--ink);
        }

        .auth-subtitle {
            font-size: 0.92rem;
            color: var(--muted);
            margin-bottom: 0;
        }

        .hero-card {
            background: linear-gradient(135deg, rgba(13,27,42,0.98), rgba(17,50,79,0.96) 52%, rgba(10,87,110,0.92));
            color: white;
            border-radius: 24px;
            padding: 24px 26px;
            margin-bottom: 18px;
            border: 1px solid rgba(148, 163, 184, 0.16);
            box-shadow: 0 24px 60px rgba(2, 6, 23, 0.42);
        }

        .hero-card h1, .hero-card p {
            color: white !important;
        }

        .stButton > button,
        .stFormSubmitButton > button {
            border-radius: 999px;
            border: none;
            background: linear-gradient(90deg, var(--accent), #38bdf8);
            color: white;
            font-weight: 700;
            padding: 0.6rem 1rem;
        }

        .stTabs [data-baseweb="tab-list"] {
            gap: 0.4rem;
        }

        .stTabs [data-baseweb="tab"] {
            background: rgba(19, 38, 58, 0.9);
            color: var(--ink);
            border-radius: 999px;
            padding: 0.35rem 0.9rem;
        }

        .stAlert {
            background: rgba(15, 27, 43, 0.9);
            border: 1px solid var(--border);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_data_inspection(df: pd.DataFrame):
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    total_missing = int(df.isna().sum().sum())

    st.subheader("Data Inspection")
    metric_cols = st.columns(4)
    metric_cols[0].metric("Rows", f"{len(df):,}")
    metric_cols[1].metric("Columns", len(df.columns))
    metric_cols[2].metric("Numeric Columns", len(numeric_cols))
    metric_cols[3].metric("Missing Cells", f"{total_missing:,}")

    if "Date" in df.columns and df["Date"].notna().any():
        start_date = df["Date"].min()
        end_date = df["Date"].max()
        if pd.notna(start_date) and pd.notna(end_date):
            st.caption(f"Date range: {start_date.date()} to {end_date.date()}")

    inspection_df = pd.DataFrame(
        {
            "Column": df.columns,
            "Data Type": [str(df[column].dtype) for column in df.columns],
            "Missing": [int(df[column].isna().sum()) for column in df.columns],
            "Missing %": [
                round((df[column].isna().sum() / len(df)) * 100, 2) if len(df) else 0.0
                for column in df.columns
            ],
            "Unique Values": [int(df[column].nunique(dropna=True)) for column in df.columns],
        }
    )

    st.dataframe(inspection_df, use_container_width=True)

    if numeric_cols:
        st.caption("Numeric summary")
        st.dataframe(df[numeric_cols].describe().transpose(), use_container_width=True)

        st.caption("Closing Price Movement Over Years")
        if "Close" in df.columns and "Date" in df.columns and df["Date"].notna().any():
            trend_df = (
                df[["Date", "Close"]]
                .dropna()
                .sort_values("Date")
            )
            fig, ax = plt.subplots(figsize=(10, 4))
            ax.plot(trend_df["Date"], trend_df["Close"], color="#1d9bf0", linewidth=2)
            ax.set_title("Closing Price Movement Over Years")
            ax.set_xlabel("Years")
            ax.set_ylabel("Prices")
            ax.xaxis.set_major_locator(mdates.YearLocator())
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
            fig.autofmt_xdate()
            st.pyplot(fig)
            plt.close(fig)
        else:
            st.info("Close and Date columns are required to display the closing price movement chart with years on the x-axis.")
    else:
        st.info("No numeric columns available for summary statistics.")


# ----------------------------------------
# Session State Initialization
# ----------------------------------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if "user" not in st.session_state:
    st.session_state.user = None

if "upload_count" not in st.session_state:
    st.session_state.upload_count = 0

if "seen_upload_signatures" not in st.session_state:
    st.session_state.seen_upload_signatures = []

if "active_upload_signature" not in st.session_state:
    st.session_state.active_upload_signature = None


# ----------------------------------------
# Page Config (MUST BE FIRST)
# ----------------------------------------
st.set_page_config(page_title="Stock Predictor", layout="wide")
inject_custom_styles()
supabase = get_supabase_client()


# ----------------------------------------
# AUTH SECTION (NOT LOGGED IN)
# ----------------------------------------
if not st.session_state.logged_in:
    st.sidebar.markdown(
        """
        <div class="auth-card">
            <div class="auth-title">Welcome Back</div>
            <p class="auth-subtitle">Sign in or create an account to unlock full access.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if supabase is None:
        st.sidebar.info("Authentication is disabled until Supabase secrets are configured in Streamlit Cloud.")

    login_tab, register_tab, reset_tab = st.sidebar.tabs(["Login", "Register", "Reset Password"])

    with login_tab:
        if supabase is None:
            st.caption("Set `SUPABASE_URL` and `SUPABASE_KEY` in Streamlit Cloud secrets to enable login.")
        else:
            with st.form("login_form", clear_on_submit=True):
                login_email = st.text_input("Email", key="login_email")
                login_password = st.text_input("Password", type="password", key="login_password")
                login_btn = st.form_submit_button("Login")

            if login_btn:
                try:
                    response = supabase.auth.sign_in_with_password({
                        "email": login_email,
                        "password": login_password
                    })

                    if response.user:
                        if is_user_disabled(response.user):
                            try:
                                supabase.auth.sign_out()
                            except Exception:
                                pass
                            st.sidebar.error("This account has been disabled. Contact admin.")
                        else:
                            st.session_state.logged_in = True
                            st.session_state.user = response.user
                            st.sidebar.success("Login successful ✅")
                            st.rerun()
                    else:
                        st.sidebar.error("Login failed ❌")
                except Exception:
                    st.sidebar.error("Invalid credentials ❌")

    with register_tab:
        if supabase is None:
            st.caption("Registration is disabled until Supabase secrets are configured.")
        else:
            with st.form("register_form", clear_on_submit=True):
                first_name = st.text_input("First Name", key="register_first_name")
                last_name = st.text_input("Last Name", key="register_last_name")
                email = st.text_input("Email", key="register_email")
                confirm_email = st.text_input("Confirm Email", key="register_confirm_email")
                password = st.text_input("Password", type="password", key="register_password")
                confirm_password = st.text_input("Confirm Password", type="password", key="register_confirm_password")
                register_btn = st.form_submit_button("Create Account")

            if register_btn:
                first_name = first_name.strip()
                last_name = last_name.strip()
                email = email.strip().lower()
                confirm_email = confirm_email.strip().lower()
                password_error = validate_password_strength(password)

                if not first_name or not last_name:
                    st.sidebar.error("Enter your first and last name.")
                elif email != confirm_email:
                    st.sidebar.error("Emails do not match ❌")
                elif password_error:
                    st.sidebar.error(password_error)
                elif password != confirm_password:
                    st.sidebar.error("Passwords do not match ❌")
                elif email_exists_in_auth(email):
                    st.sidebar.error("This email is already registered. Please login.")
                else:
                    try:
                        res = supabase.auth.sign_up({
                            "email": email,
                            "password": password,
                            "options": {
                                "data": {
                                    "first_name": first_name,
                                    "last_name": last_name,
                                    "full_name": f"{first_name} {last_name}".strip(),
                                }
                            },
                        })
                        response = supabase.functions.invoke(
                        "hyper-task",
                        invoke_options={"body": {"name": "Functions"}}
                    )
                        if res.user and not res.session:
                            st.sidebar.success("Confirm your email and login.")
                        elif res.user and res.session:
                            st.sidebar.success("Account created successfully.")
                        else:
                            st.sidebar.error("Registration failed. Please try again.")
                    except Exception as e:
                        error_text = str(e).lower()
                        if "already registered" in error_text or "already exists" in error_text:
                            st.sidebar.error("This email is already registered. Please login.")
                        else:
                            st.sidebar.error(f"Error: {e}")

    with reset_tab:
        st.caption("Open the secure password reset page to reset your password with an email OTP.")
        st.link_button("Open Password Reset Page", RESET_APP_URL, use_container_width=True)
        st.markdown(f"[Or open it manually]({RESET_APP_URL})")


# ----------------------------------------
# USER PANEL (LOGGED IN)
# ----------------------------------------
else:
    user = st.session_state.user

    if supabase is None:
        st.session_state.logged_in = False
        st.session_state.user = None
        st.warning("Supabase secrets are not configured, so authenticated features are unavailable.")
        st.rerun()

    if is_user_disabled(user):
        st.session_state.logged_in = False
        st.session_state.user = None
        st.error("This account has been disabled. Contact admin.")
        st.stop()

    st.sidebar.markdown(
        """
        <div class="auth-card">
            <div class="auth-title">Account</div>
            <p class="auth-subtitle">Manage your session and review your recent activity.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.sidebar.success(f"Welcome Back:\n{user.email}")

    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.session_state.user = None
        st.rerun()

    if is_admin_user(user):
        st.sidebar.markdown("---")
        st.sidebar.subheader("Admin Access")
        st.sidebar.link_button("Open Admin Panel", ADMIN_PANEL_URL, use_container_width=True)

    st.sidebar.markdown("---")
    st.sidebar.subheader("📜 Prediction History")

    try:
        if supports_prediction_metadata_columns():
            res = supabase.table("predictions") \
                .select("file_name, target_column, prediction_date, predicted_value, prediction_direction, model_used, created_at") \
                .eq("user_id", user.id) \
                .order("created_at", desc=True) \
                .limit(5) \
                .execute()
        else:
            res = supabase.table("predictions") \
                .select("file_name, target_column, prediction_date, predicted_value, created_at") \
                .eq("user_id", user.id) \
                .order("created_at", desc=True) \
                .limit(5) \
                .execute()

        history = res.data

        if not history:
            st.sidebar.info("No predictions yet.")
        else:
            for item in history:
                price = item.get("predicted_value") or 0

                st.sidebar.markdown(f"""
📁 **File:** {item.get('file_name', 'N/A')}  
🎯 **Target:** {item.get('target_column', 'N/A')}  
📅 **Date:** {item.get('prediction_date', 'N/A')}  
💰 **Price:** {round(price, 2)}  
📈 **Direction:** {item.get('prediction_direction', 'N/A')}  
🧠 **Model:** {item.get('model_used', 'N/A')}  
⏱ **Time(UTC):** {str(item.get('created_at', ''))[:19].replace("T"," ")}

---
""")
    except Exception as e:
        st.sidebar.error(f"Error loading history: {e}")


# ----------------------------------------
# Main App
# ----------------------------------------
st.markdown(
    """
    <div class="hero-card">
        <h1>Stock Price Predictor</h1>
        <p>Upload market data, review model performance, and forecast future prices from a cleaner workspace.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

uploaded_file = st.file_uploader("Upload CSV", type=["csv"])

if not uploaded_file:
    if st.session_state.upload_count >= 2 and not st.session_state.logged_in:
        st.warning("Upload limit reached. Please login.")
    else:
        st.info("Upload a dataset to begin.")
    st.stop()


# ----------------------------------------
# Load Data
# ----------------------------------------
uploaded_bytes = uploaded_file.getvalue()
upload_signature = get_upload_signature(uploaded_file.name, uploaded_bytes)

if upload_signature != st.session_state.active_upload_signature:
    if not st.session_state.logged_in and upload_signature not in st.session_state.seen_upload_signatures:
        st.session_state.seen_upload_signatures.append(upload_signature)
        st.session_state.upload_count = len(st.session_state.seen_upload_signatures)
    st.session_state.active_upload_signature = upload_signature

if st.session_state.upload_count >= 2 and not st.session_state.logged_in and upload_signature not in st.session_state.seen_upload_signatures:
    st.warning("Upload limit reached. Please login.")
    st.stop()

df = load_uploaded_dataframe(uploaded_bytes)
file_name = uploaded_file.name

st.subheader("Preview")
st.write(df.head())
render_data_inspection(df)

# Date handling
if "Date" in df.columns:
    df = df.sort_values("Date")

# Numeric columns
numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
if not numeric_cols:
    st.error("This CSV does not contain numeric columns the stock model can train on. Please upload market data with columns like Date, Open, High, Low, Close, or Volume.")
    st.stop()

target_priority = ["Close", "High", "Open", "Low"]
present_targets = {str(col).strip().lower(): col for col in numeric_cols}
price_targets = [present_targets[name.lower()] for name in target_priority if name.lower() in present_targets]
if not price_targets:
    st.error("Target columns must be one of Open, High, Low, or Close.")
    st.stop()

target_column = st.selectbox("Target Column (OHLC)", price_targets)
if not target_column:
    st.error("No valid OHLC target column is available in this file.")
    st.stop()

# Feature engineering selector
st.markdown("### Feature Engineering")
st.caption("Choose technical indicators to include with the target feature.")
trend_col, momentum_col = st.columns(2)
with trend_col:
    st.markdown("**Trend**")
    use_ma10 = st.checkbox("MA 10", value=False)
    use_ma20 = st.checkbox("MA 20", value=False)
    use_ma50 = st.checkbox("MA 50", value=False)
    use_ema10 = st.checkbox("EMA 10", value=False)
    use_ema20 = st.checkbox("EMA 20", value=False)
with momentum_col:
    st.markdown("**Momentum**")
    use_rsi = st.checkbox("RSI", value=False)
    use_macd = st.checkbox("MACD", value=False)

df, feature_columns, selected_indicator_labels, selected_indicator_keys = build_technical_indicator_features(
    df,
    target_column,
    include_ma10=use_ma10,
    include_ma20=use_ma20,
    include_ma50=use_ma50,
    include_ema10=use_ema10,
    include_ema20=use_ema20,
    include_rsi=use_rsi,
    include_macd=use_macd,
)

if selected_indicator_labels:
    feature_mode_label = f"target + {', '.join(selected_indicator_labels)}"
    feature_mode_key = f"target_plus_{'_'.join(selected_indicator_keys)}"
else:
    feature_mode_label = "target-only"
    feature_mode_key = "target_only"

# Time-aware train/test split
split_index = max(int(len(df) * 0.8), SEQUENCE_LENGTH + 1)
split_index = min(split_index, len(df) - 1)

train_df = df.iloc[:split_index].copy()
test_df = df.iloc[split_index:].copy()

if len(train_df) <= SEQUENCE_LENGTH or len(test_df) == 0:
    st.error(f"This dataset needs enough rows to create training and test data beyond the {SEQUENCE_LENGTH}-row sequence window.")
    st.stop()

columns_to_fill = list(dict.fromkeys(feature_columns + [target_column]))
df[columns_to_fill] = df[columns_to_fill].ffill().bfill()

if df[columns_to_fill].isna().any().any():
    st.error("Feature engineering produced unresolved missing values. Please upload cleaner OHLC data.")
    st.stop()

suite_key = f"{MODEL_SUITE_VERSION}|target={target_column.lower()}|feature={feature_mode_key}|seq={SEQUENCE_LENGTH}"
cached_suite = st.session_state.get("model_suite")

if not cached_suite or cached_suite.get("key") != suite_key:
    cached_suite = load_model_suite(suite_key)
    if cached_suite:
        st.session_state.model_suite = cached_suite
        if cached_suite.get("source") == "cloud":
            st.info("Loaded saved model suite from Supabase Storage (reused without retraining).")
        else:
            st.info("Loaded saved model suite from disk (reused without retraining).")

if cached_suite:
    if (
        cached_suite.get("target_column") != target_column
        or list(cached_suite.get("feature_columns", [])) != feature_columns
        or cached_suite.get("feature_scaler") is None
        or cached_suite.get("target_scaler") is None
    ):
        cached_suite = None

if cached_suite:
    feature_scaler = cached_suite["feature_scaler"]
    target_scaler = cached_suite["target_scaler"]
else:
    feature_scaler = MinMaxScaler()
    target_scaler = MinMaxScaler()
    feature_scaler.fit(train_df[feature_columns])
    target_scaler.fit(train_df[[target_column]])

scaled_feature_data = feature_scaler.transform(df[feature_columns])
train_features_scaled = feature_scaler.transform(train_df[feature_columns])
train_target_scaled = target_scaler.transform(train_df[[target_column]]).reshape(-1)

X_train, y_train = build_sequences(train_features_scaled, train_target_scaled, SEQUENCE_LENGTH)

test_window_df = df.iloc[split_index - SEQUENCE_LENGTH:].copy()
test_features_scaled = feature_scaler.transform(test_window_df[feature_columns])
test_target_scaled = target_scaler.transform(test_window_df[[target_column]]).reshape(-1)
X_test, y_test = build_sequences(test_features_scaled, test_target_scaled, SEQUENCE_LENGTH)

if len(X_train) == 0 or len(y_train) == 0:
    st.error(f"This dataset needs more than {SEQUENCE_LENGTH} usable rows in the training split after cleaning.")
    st.stop()

if len(X_test) == 0 or len(y_test) == 0:
    st.error("This dataset needs more held-out rows to evaluate the model on unseen data.")
    st.stop()

actual = test_window_df[target_column].iloc[SEQUENCE_LENGTH:].to_numpy()
target_index = feature_columns.index(target_column)

if "Date" in test_window_df.columns and test_window_df["Date"].notna().any():
    prediction_dates = test_window_df["Date"].iloc[SEQUENCE_LENGTH:].reset_index(drop=True)
else:
    prediction_dates = None

st.caption(f"Feature Mode: {feature_mode_label}")

# ----------------------------------------
# Model
# ----------------------------------------
needs_training_for_suite = not cached_suite or cached_suite.get("key") != suite_key
if needs_training_for_suite:
    st.warning(f"No saved models found for this target in {feature_mode_label} mode.")
    train_for_target = st.button("Train And Save Models")
    if not train_for_target:
        st.info("Saved-model mode is active. Select another target with saved models, or click the button to train once.")
        st.stop()

if needs_training_for_suite:
    candidate_rows = []
    candidate_models = {}
    X_train_flat = X_train.reshape(len(X_train), -1)
    X_test_flat = X_test.reshape(len(X_test), -1)
    baseline_predictions = inverse_target_values(X_test[:, -1, target_index], target_scaler)

    with st.spinner("Training and comparing models on held-out data..."):
        baseline_metrics = evaluate_predictions(actual, baseline_predictions)
        candidate_rows.append({
            "Model": "Naive Baseline",
            "Status": "trained",
            "Notes": "Repeats the last observed target value.",
            **baseline_metrics,
        })
        candidate_models["Naive Baseline"] = {
            "name": "Naive Baseline",
            "kind": "baseline",
            "model": None,
            "predictions_actual": baseline_predictions,
            "note": "Repeats the last observed target value.",
        }

        tabular_candidates = [
            (
                "Linear Regression",
                [
                    (
                        "Flattened sequence regression with no regularization; useful as a low-variance benchmark.",
                        lambda: LinearRegression(),
                    ),
                ],
            ),
            (
                "Random Forest",
                [
                    (
                        "Shallow ensemble tuned to reduce overfitting with capped depth and larger leaf size.",
                        lambda: RandomForestRegressor(
                            n_estimators=250,
                            max_depth=10,
                            min_samples_leaf=4,
                            random_state=42,
                            n_jobs=-1,
                        ),
                    ),
                    (
                        "Slightly deeper ensemble balanced for bias and variance on flattened windows.",
                        lambda: RandomForestRegressor(
                            n_estimators=350,
                            max_depth=14,
                            min_samples_leaf=2,
                            random_state=42,
                            n_jobs=-1,
                        ),
                    ),
                ],
            ),
        ]

        for model_name, configs in tabular_candidates:
            try:
                trained = train_tuned_tabular_model(model_name, configs, X_train_flat, y_train, X_test_flat)
                predictions_actual = inverse_target_values(trained["predictions"], target_scaler)
                metrics = evaluate_predictions(actual, predictions_actual)
                candidate_rows.append({
                    "Model": model_name,
                    "Status": "trained",
                    "Notes": trained["note"],
                    **metrics,
                })
                trained["predictions_actual"] = predictions_actual
                candidate_models[model_name] = trained
            except Exception as exc:
                candidate_rows.append({
                    "Model": model_name,
                    "Status": "failed",
                    "Notes": f"Training failed: {exc}",
                    "MAE": np.nan,
                    "RMSE": np.nan,
                    "R2": np.nan,
                })

        sequence_candidates = [
            ("LSTM", build_lstm_model, "Stacked LSTM tuned for temporal memory with dropout to curb overfitting."),
            ("GRU", build_gru_model, "GRU sequence model with lighter recurrent capacity for faster generalization."),
            ("BiLSTM", build_bilstm_model, "Bidirectional LSTM for richer context, regularized with dropout and early stopping."),
        ]

        for model_name, builder, note in sequence_candidates:
            try:
                trained = train_sequence_model(model_name, builder, X_train, y_train, X_test, note)
                predictions_actual = inverse_target_values(trained["predictions"], target_scaler)
                metrics = evaluate_predictions(actual, predictions_actual)
                candidate_rows.append({
                    "Model": model_name,
                    "Status": "trained",
                    "Notes": trained["note"],
                    **metrics,
                })
                trained["predictions_actual"] = predictions_actual
                candidate_models[model_name] = trained
            except Exception as exc:
                candidate_rows.append({
                    "Model": model_name,
                    "Status": "failed",
                    "Notes": f"Training failed: {exc}",
                    "MAE": np.nan,
                    "RMSE": np.nan,
                    "R2": np.nan,
                })

    leaderboard_df = pd.DataFrame(candidate_rows)
    trained_df = rank_trained_models(leaderboard_df)

    if trained_df.empty:
        st.error("No models were successfully trained on this dataset.")
        st.stop()

    best_model_name = get_best_model_name(leaderboard_df)
    save_model_suite(
        suite_key,
        leaderboard_df,
        best_model_name,
        candidate_models,
        feature_columns,
        target_column,
        feature_scaler,
        target_scaler,
    )
    st.session_state.model_suite = {
        "key": suite_key,
        "leaderboard": leaderboard_df,
        "best_model_name": best_model_name,
        "models": candidate_models,
        "source": "trained",
        "feature_columns": feature_columns,
        "target_column": target_column,
        "feature_scaler": feature_scaler,
        "target_scaler": target_scaler,
    }

model_suite = st.session_state.model_suite
model_suite["feature_columns"] = feature_columns
model_suite["target_column"] = target_column
model_suite["feature_scaler"] = feature_scaler
model_suite["target_scaler"] = target_scaler

# Re-evaluate saved or trained models on the current dataset without retraining.
candidate_rows = []
X_test_flat = X_test.reshape(len(X_test), -1)
baseline_predictions = inverse_target_values(X_test[:, -1, target_index], target_scaler)

for model_name, candidate in model_suite["models"].items():
    try:
        if candidate["kind"] == "baseline":
            predictions_actual = baseline_predictions
            notes = candidate.get("note", "Repeats the last observed target value.")
        elif candidate.get("model") is None:
            raise ValueError(candidate.get("load_error") or "Saved artifact could not be loaded.")
        elif candidate["kind"] == "sequence":
            preds_scaled = np.asarray(candidate["model"].predict(X_test, verbose=0)).reshape(-1)
            predictions_actual = inverse_target_values(preds_scaled, target_scaler)
            notes = candidate.get("note", "")
        else:
            preds_scaled = np.asarray(candidate["model"].predict(X_test_flat)).reshape(-1)
            predictions_actual = inverse_target_values(preds_scaled, target_scaler)
            notes = candidate.get("note", "")

        candidate["predictions_actual"] = predictions_actual
        metrics = evaluate_predictions(actual, predictions_actual)
        candidate_rows.append({
            "Model": model_name,
            "Status": "trained",
            "Notes": notes,
            **metrics,
        })
    except Exception as exc:
        candidate_rows.append({
            "Model": model_name,
            "Status": "failed",
            "Notes": f"Evaluation failed: {exc}",
            "MAE": np.nan,
            "RMSE": np.nan,
            "R2": np.nan,
        })

leaderboard_df = pd.DataFrame(candidate_rows)
trained_df = rank_trained_models(leaderboard_df)
best_model_name = get_best_model_name(leaderboard_df)
model_suite["leaderboard"] = leaderboard_df
model_suite["best_model_name"] = best_model_name

if best_model_name is None:
    st.error("No trained models are available in the saved suite.")
    st.stop()

available_model_names = [name for name in trained_df["Model"].tolist() if name in model_suite["models"]]
default_model_index = available_model_names.index(best_model_name)
selected_model_name = st.selectbox(
    "Prediction Model",
    available_model_names,
    index=default_model_index,
    help="The highest-ranked saved or trained model is preselected automatically.",
)
selected_candidate = model_suite["models"][selected_model_name]
selected_is_best = selected_model_name == best_model_name

if model_suite.get("source") == "saved":
    st.caption("Using saved model artifacts from disk for this target configuration.")
elif model_suite.get("source") == "cloud":
    st.caption("Using saved model artifacts restored from Supabase Storage for this target configuration.")
else:
    st.caption("Using freshly trained model artifacts for this target configuration.")

best_candidate = selected_candidate
best_predictions = np.asarray(best_candidate["predictions_actual"]).reshape(-1)
baseline_predictions = np.asarray(model_suite["models"]["Naive Baseline"]["predictions_actual"]).reshape(-1)

st.subheader("Model Leaderboard")
st.dataframe(leaderboard_df, use_container_width=True)
if selected_is_best:
    st.success(f"Best model selected for future prediction: {selected_model_name}")
else:
    st.warning(f"Using {selected_model_name} manually. Best available model is {best_model_name}.")


# ----------------------------------------
# Prediction
# ----------------------------------------
st.subheader("Prediction Graph")
fig, ax = plt.subplots(figsize=(10, 4.5))

if prediction_dates is not None:
    ax.plot(prediction_dates, actual, label=f"Actual {target_column}", linewidth=2)
    ax.plot(prediction_dates, best_predictions, label=f"{selected_model_name} Prediction", linewidth=2)
    if selected_model_name != "Naive Baseline":
        ax.plot(prediction_dates, baseline_predictions, label="Naive Baseline", linewidth=1.5, linestyle="--")
    ax.set_xlabel("Years")
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.autofmt_xdate()
else:
    ax.plot(actual, label=f"Actual {target_column}", linewidth=2)
    ax.plot(best_predictions, label=f"{selected_model_name} Prediction", linewidth=2)
    if selected_model_name != "Naive Baseline":
        ax.plot(baseline_predictions, label="Naive Baseline", linewidth=1.5, linestyle="--")
    ax.set_xlabel("Observations")

ax.set_ylabel(target_column)
ax.set_title(f"{target_column} Prediction vs Actual on Held-Out Test Data")
ax.legend()
st.pyplot(fig)
plt.close(fig)

st.caption("Top held-out metrics")
st.write(trained_df[["Model", "MAE", "RMSE", "R2"]].head(5).reset_index(drop=True))

direction_reference = float(test_window_df[target_column].iloc[SEQUENCE_LENGTH - 1])
direction_metrics = compute_direction_metrics(actual, best_predictions, direction_reference)
st.subheader("Prediction Direction")
st.write(pd.DataFrame([direction_metrics]))
st.caption("Direction uses the previous actual value as the reference for Up/Down.")


# ----------------------------------------
# Future Prediction
# ----------------------------------------
st.subheader("📅 Future Prediction")

if "Date" not in df.columns or df["Date"].isna().all():
    st.warning("Future prediction requires a usable Date column.")
else:
    last_date = df["Date"].iloc[-1]
    user_date = st.date_input("Select future date")

    if user_date > last_date.date():
        days_ahead = (user_date - last_date.date()).days

        future_values = recursive_forecast(
            best_candidate,
            scaled_feature_data,
            feature_columns,
            target_column,
            target_scaler,
            days_ahead,
            recent_target_values=df[target_column].to_numpy(),
        )
        predicted_price = float(future_values[-1])
        direction_label = "UP" if predicted_price >= float(df[target_column].iloc[-1]) else "DOWN"

        if selected_is_best:
            st.success(f"Best model: {selected_model_name}")
        else:
            st.success(f"Selected model: {selected_model_name}")
            st.info(f"Best available model remains {best_model_name}.")
        st.success(f"Predicted {target_column}: {round(predicted_price, 2)}")
        st.info(f"Predicted Direction: {direction_label}")

        if st.session_state.logged_in and st.session_state.user:
            base_payload = {
                "user_id": st.session_state.user.id,
                "file_name": file_name,
                "target_column": target_column,
                "predicted_value": float(predicted_price),
                "prediction_date": str(user_date),
            }
            if supports_prediction_metadata_columns():
                metadata_payload = {
                    **base_payload,
                    "prediction_direction": direction_label,
                    "model_used": selected_model_name,
                }
                try:
                    supabase.table("predictions").insert(metadata_payload).execute()
                except Exception:
                    st.session_state["supports_prediction_metadata_columns"] = False
                    supabase.table("predictions").insert(base_payload).execute()
            else:
                supabase.table("predictions").insert(base_payload).execute()
    else:
        st.warning("Select a future date.")

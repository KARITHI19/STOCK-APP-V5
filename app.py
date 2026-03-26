# app.py

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import numpy as np
import tensorflow as tf
from sklearn.preprocessing import MinMaxScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
import matplotlib.pyplot as plt
import os
from supabase import create_client, Client

# ----------------------------------------
# Supabase Configuration
# ----------------------------------------
SUPABASE_URL = "https://bqumqfdisvihzknhaaej.supabase.co"
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
MAIN_APP_URL = os.getenv("MAIN_APP_URL", "http://localhost:8501")
RESET_APP_URL = os.getenv("RESET_APP_URL", "http://localhost:8502")


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

# ----------------------------------------
# Session State Initialization
# ----------------------------------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if "user" not in st.session_state:
    st.session_state.user = None

if "upload_count" not in st.session_state:
    st.session_state.upload_count = 0

# ----------------------------------------
# Page Config (MUST BE FIRST)
# ----------------------------------------
st.set_page_config(page_title="Stock Predictor", layout="wide")
inject_custom_styles()

# ----------------------------------------
# 🔐 AUTH SECTION (NOT LOGGED IN)
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

    login_tab, register_tab, reset_tab = st.sidebar.tabs(["Login", "Register", "Reset Password"])

    with login_tab:
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
                    st.session_state.logged_in = True
                    st.session_state.user = response.user
                    st.sidebar.success("Login successful ✅")
                    st.rerun()
                else:
                    st.sidebar.error("Login failed ❌")
            except Exception:
                st.sidebar.error("Invalid credentials ❌")

    with register_tab:
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

            if not first_name or not last_name:
                st.sidebar.error("Enter your first and last name.")
            elif email != confirm_email:
                st.sidebar.error("Emails do not match ❌")
            elif len(password) < 6:
                st.sidebar.error("Password must be at least 6 characters.")
            elif password != confirm_password:
                st.sidebar.error("Passwords do not match ❌")
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
                    if res.user:
                        st.sidebar.success("Registration successful ✅")
                except Exception as e:
                    st.sidebar.error(f"Error: {e}")

    with reset_tab:
        st.caption("Open the secure password reset page to reset your password with an email OTP.")
        st.link_button("Open Password Reset Page", RESET_APP_URL, use_container_width=True)
        st.markdown(f"[Or open it manually]({RESET_APP_URL})")

# ----------------------------------------
# 👤 USER PANEL (LOGGED IN)
# ----------------------------------------
else:
    user = st.session_state.user

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

    st.sidebar.markdown("---")
    st.sidebar.subheader("📜 Prediction History")

    try:
        res = supabase.table("predictions") \
            .select("file_name, prediction_date, predicted_value, created_at") \
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
📅 **Date:** {item.get('prediction_date', 'N/A')}  
💰 **Price:** {round(price, 2)}  
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

MODEL_PATH = "multivariate_lstm.keras"
SEQUENCE_LENGTH = 60

# Upload restriction
if st.session_state.upload_count >= 2 and not st.session_state.logged_in:
    st.warning("Upload limit reached. Please login.")
    st.stop()

uploaded_file = st.file_uploader("Upload CSV", type=["csv"])

if not uploaded_file:
    st.info("Upload a dataset to begin.")
    
    st.stop()

# ----------------------------------------
# Load Data
# ----------------------------------------
st.session_state.upload_count += 1
df = pd.read_csv(uploaded_file)
file_name = uploaded_file.name

st.subheader("Preview")
st.write(df.head())

# Date handling
if "Date" in df.columns:
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date")

# EMA Features
if "Close" in df.columns:
    df["EMA20"] = df["Close"].ewm(span=20).mean()
    df["EMA50"] = df["Close"].ewm(span=50).mean()

# Numeric columns
numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
df[numeric_cols] = df[numeric_cols].fillna(df[numeric_cols].mean())

target_column = st.selectbox("Target Column", numeric_cols)

# Scaling
scaler = MinMaxScaler()
scaled_data = scaler.fit_transform(df[numeric_cols])

# Sequences
X, y = [], []
target_index = numeric_cols.index(target_column)

for i in range(SEQUENCE_LENGTH, len(scaled_data)):
    X.append(scaled_data[i-SEQUENCE_LENGTH:i])
    y.append(scaled_data[i, target_index])

X, y = np.array(X), np.array(y)

# ----------------------------------------
# Model
# ----------------------------------------
retrain = False

if os.path.exists(MODEL_PATH):
    model = tf.keras.models.load_model(MODEL_PATH)

    if model.input_shape[2] != X.shape[2]:
        retrain = True
else:
    retrain = True

if retrain:
    st.warning("Training model...")

    model = tf.keras.Sequential([
        tf.keras.layers.LSTM(64, return_sequences=True, input_shape=(X.shape[1], X.shape[2])),
        tf.keras.layers.Dropout(0.2),
        tf.keras.layers.LSTM(32),
        tf.keras.layers.Dense(1)
    ])

    model.compile(optimizer="adam", loss="mse")
    model.fit(X, y, epochs=10, batch_size=32, verbose=1)
    model.save(MODEL_PATH)

# ----------------------------------------
# Prediction
# ----------------------------------------
predictions = model.predict(X)

temp = np.zeros((len(predictions), len(numeric_cols)))
temp[:, target_index] = predictions.flatten()

predictions_rescaled = scaler.inverse_transform(temp)[:, target_index]
actual = df[target_column].values[SEQUENCE_LENGTH:]

# Plot
st.subheader("Prediction Graph")
fig, ax = plt.subplots()
ax.plot(actual, label="Actual")
ax.plot(predictions_rescaled, label="Predicted")
ax.legend()
st.pyplot(fig)

# Metrics
mae = mean_absolute_error(actual, predictions_rescaled)
rmse = np.sqrt(mean_squared_error(actual, predictions_rescaled))
r2 = r2_score(actual, predictions_rescaled)

st.write({"MAE": mae, "RMSE": rmse, "R2": r2})

# ----------------------------------------
# Future Prediction
# ----------------------------------------
st.subheader("📅 Future Prediction")

last_date = df["Date"].iloc[-1]
user_date = st.date_input("Select future date")

if user_date > last_date.date():
    days_ahead = (user_date - last_date.date()).days

    seq = scaled_data[-SEQUENCE_LENGTH:]
    preds = []

    for _ in range(days_ahead):
        pred = model.predict(seq.reshape(1, SEQUENCE_LENGTH, seq.shape[1]), verbose=0)
        preds.append(pred[0][0])

        new_row = seq[-1].copy()
        new_row[target_index] = pred[0][0]
        seq = np.vstack([seq[1:], new_row])

    temp = np.zeros((len(preds), len(numeric_cols)))
    temp[:, target_index] = preds

    final = scaler.inverse_transform(temp)[:, target_index]
    predicted_price = final[-1]

    st.success(f"Predicted Price: {round(predicted_price, 2)}")

    # Save to DB
if st.session_state.logged_in and st.session_state.user:
    supabase.table("predictions").insert({
        "user_id": st.session_state.user.id,
        "file_name": file_name,
        "target_column": target_column,
        "predicted_value": float(predicted_price),
        "prediction_date": str(user_date)
    }).execute()

else:
    st.warning("Select a future date.")

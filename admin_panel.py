import os
from typing import Any

import pandas as pd
import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError
from supabase import Client, create_client


DEFAULT_SUPABASE_URL = "https://bqumqfdisvihzknhaaej.supabase.co"


def read_secret(name: str, default: str = "") -> str:
    try:
        if name in st.secrets:
            return str(st.secrets[name])
    except StreamlitSecretNotFoundError:
        return default
    return default


SUPABASE_URL = os.getenv("SUPABASE_URL") or read_secret("SUPABASE_URL", DEFAULT_SUPABASE_URL)
SUPABASE_KEY = (
    os.getenv("SUPABASE_KEY")
    or os.getenv("SUPABASE_PUBLISHABLE_KEY")
    or read_secret("SUPABASE_KEY", "")
    or read_secret("SUPABASE_PUBLISHABLE_KEY", "")
)
SUPABASE_SERVICE_ROLE_KEY = (
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    or os.getenv("SUPABASE_SECRET_KEY")
    or read_secret("SUPABASE_SERVICE_ROLE_KEY", "")
    or read_secret("SUPABASE_SECRET_KEY", "")
)
MAIN_APP_URL = os.getenv("MAIN_APP_URL") or read_secret("MAIN_APP_URL", "http://localhost:8501/")

supabase: Client | None = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None
supabase_admin: Client | None = (
    create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY
    else None
)


def init_session_state():
    defaults = {
        "admin_logged_in": False,
        "admin_user": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def inject_styles():
    st.markdown(
        """
        <style>
        :root {
            --bg: #08131d;
            --panel: #0f1e2d;
            --panel-2: #13283a;
            --text: #e2e8f0;
            --muted: #94a3b8;
            --accent: #0ea5e9;
            --success: #22c55e;
            --border: rgba(148, 163, 184, 0.18);
        }

        .stApp {
            background:
                radial-gradient(circle at top right, rgba(14, 165, 233, 0.18), transparent 30%),
                linear-gradient(180deg, #040b12 0%, #091623 100%);
            color: var(--text);
        }

        .panel {
            background: linear-gradient(180deg, rgba(15,30,45,0.96), rgba(11,23,35,0.98));
            border: 1px solid var(--border);
            border-radius: 22px;
            padding: 20px 22px;
            margin-bottom: 18px;
            box-shadow: 0 20px 50px rgba(2, 6, 23, 0.35);
        }

        .panel h1, .panel h2, .panel h3, .panel p {
            color: white !important;
            margin-top: 0;
        }

        .role-badge {
            display: inline-block;
            padding: 0.24rem 0.75rem;
            border-radius: 999px;
            font-size: 0.78rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            background: rgba(34, 197, 94, 0.14);
            color: #bbf7d0;
            border: 1px solid rgba(34, 197, 94, 0.32);
        }

        .stButton > button,
        .stFormSubmitButton > button {
            border-radius: 999px;
            border: none;
            background: linear-gradient(90deg, var(--accent), #38bdf8);
            color: white;
            font-weight: 700;
        }

        .stTabs [data-baseweb="tab"] {
            background: rgba(19, 40, 58, 0.92);
            color: var(--text);
            border-radius: 999px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def get_nested_value(value: Any, key: str, default: Any = None):
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


def get_user_role(user: Any) -> str:
    app_metadata = get_nested_value(user, "app_metadata", {}) or {}
    role = str(app_metadata.get("role", "user")).strip().lower()
    return "admin" if role == "admin" else "user"


def is_user_disabled(user: Any) -> bool:
    app_metadata = get_nested_value(user, "app_metadata", {}) or {}
    return bool(app_metadata.get("disabled", False))


def get_display_name(user: Any) -> str:
    user_metadata = get_nested_value(user, "user_metadata", {}) or {}
    full_name = str(user_metadata.get("full_name", "")).strip()
    if full_name:
        return full_name
    first_name = str(user_metadata.get("first_name", "")).strip()
    last_name = str(user_metadata.get("last_name", "")).strip()
    name = f"{first_name} {last_name}".strip()
    return name or str(get_nested_value(user, "email", "Admin"))


def normalize_users(response: Any) -> list[Any]:
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


def list_auth_users() -> list[Any]:
    if not supabase_admin:
        return []
    try:
        return normalize_users(supabase_admin.auth.admin.list_users())
    except TypeError:
        return normalize_users(supabase_admin.auth.admin.list_users(page=1, per_page=200))


def find_user_by_email(users: list[Any], email: str):
    target = email.strip().lower()
    for user in users:
        current_email = str(get_nested_value(user, "email", "")).strip().lower()
        if current_email == target:
            return user
    return None


def validate_password_strength(password: str) -> str | None:
    if len(password) < 8:
        return "Password must be at least 8 characters."
    if not any(char.isupper() for char in password):
        return "Password must include at least one uppercase letter."
    if not any(char.islower() for char in password):
        return "Password must include at least one lowercase letter."
    if not any(char.isdigit() for char in password):
        return "Password must include at least one number."
    if not any(not char.isalnum() for char in password):
        return "Password must include at least one special character."
    return None


def supports_prediction_metadata_columns() -> bool:
    cache_key = "admin_supports_prediction_metadata_columns"
    if cache_key in st.session_state:
        return bool(st.session_state[cache_key])

    supported = False
    if supabase_admin is not None:
        try:
            supabase_admin.table("predictions").select("prediction_direction, model_used").limit(1).execute()
            supported = True
        except Exception:
            supported = False

    st.session_state[cache_key] = supported
    return supported


def format_time(value: Any) -> str:
    if not value:
        return "N/A"
    return str(value).replace("T", " ")[:19]


def require_clients():
    if supabase is None:
        st.error("Set SUPABASE_KEY for admin panel login.")
        st.stop()
    if supabase_admin is None:
        st.error("Set SUPABASE_SERVICE_ROLE_KEY for admin tools.")
        st.stop()


def login_screen():
    st.markdown(
        """
        <div class="panel">
            <h1>Admin Panel</h1>
            <p>Sign in with an account that already has the <strong>admin</strong> role.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.form("admin_login_form", clear_on_submit=True):
        email = st.text_input("Admin Email")
        password = st.text_input("Password", type="password")
        login_btn = st.form_submit_button("Login")

    col1, col2 = st.columns([1, 1])
    with col1:
        st.link_button("Open Main App", MAIN_APP_URL, use_container_width=True)

    if login_btn:
        email = email.strip().lower()
        if not email or not password:
            st.error("Enter your admin email and password.")
            return
        try:
            response = supabase.auth.sign_in_with_password({"email": email, "password": password})
            if not response.user:
                st.error("Login failed.")
                return
            if is_user_disabled(response.user):
                try:
                    supabase.auth.sign_out()
                except Exception:
                    pass
                st.error("This admin account is disabled.")
                return
            if get_user_role(response.user) != "admin":
                try:
                    supabase.auth.sign_out()
                except Exception:
                    pass
                st.error("This account is not an admin.")
                return
            st.session_state.admin_logged_in = True
            st.session_state.admin_user = response.user
            st.success("Admin login successful.")
            st.rerun()
        except Exception as error:
            st.error(f"Login failed: {error}")


def build_user_frame(users: list[Any]) -> pd.DataFrame:
    rows = []
    for user in users:
        rows.append(
            {
                "email": get_nested_value(user, "email", "N/A"),
                "name": get_display_name(user),
                "role": get_user_role(user),
                "status": "disabled" if is_user_disabled(user) else "active",
                "created_at": format_time(get_nested_value(user, "created_at")),
                "last_sign_in_at": format_time(get_nested_value(user, "last_sign_in_at")),
                "user_id": get_nested_value(user, "id", ""),
            }
        )
    if not rows:
        return pd.DataFrame(columns=["email", "name", "role", "created_at", "last_sign_in_at", "user_id"])
    return pd.DataFrame(rows).sort_values(by=["role", "email"]).reset_index(drop=True)


def create_user(email: str, password: str, first_name: str, last_name: str, role: str):
    metadata = {
        "first_name": first_name.strip(),
        "last_name": last_name.strip(),
        "full_name": f"{first_name.strip()} {last_name.strip()}".strip(),
    }
    supabase_admin.auth.admin.create_user(
        {
            "email": email.strip().lower(),
            "password": password,
            "email_confirm": True,
            "user_metadata": metadata,
            "app_metadata": {"role": role},
        }
    )


def update_user_role(target_user: Any, role: str):
    existing_app_metadata = get_nested_value(target_user, "app_metadata", {}) or {}
    supabase_admin.auth.admin.update_user_by_id(
        get_nested_value(target_user, "id", ""),
        {"app_metadata": {**existing_app_metadata, "role": role}},
    )


def update_user_disabled_state(target_user: Any, disabled: bool):
    existing_app_metadata = get_nested_value(target_user, "app_metadata", {}) or {}
    supabase_admin.auth.admin.update_user_by_id(
        get_nested_value(target_user, "id", ""),
        {"app_metadata": {**existing_app_metadata, "disabled": disabled}},
    )


def load_recent_predictions() -> list[dict[str, Any]]:
    try:
        if supports_prediction_metadata_columns():
            response = (
                supabase_admin.table("predictions")
                .select("user_id, file_name, target_column, prediction_date, predicted_value, prediction_direction, model_used, created_at")
                .order("created_at", desc=True)
                .limit(25)
                .execute()
            )
        else:
            response = (
                supabase_admin.table("predictions")
                .select("user_id, file_name, target_column, prediction_date, predicted_value, created_at")
                .order("created_at", desc=True)
                .limit(25)
                .execute()
            )
        return response.data or []
    except Exception:
        return []


def build_prediction_frame(predictions: list[dict[str, Any]], users: list[Any]) -> pd.DataFrame:
    email_lookup = {
        get_nested_value(user, "id", ""): get_nested_value(user, "email", "Unknown user")
        for user in users
    }
    rows = []
    for item in predictions:
        created_at = pd.to_datetime(item.get("created_at"), errors="coerce", utc=True)
        rows.append(
            {
                "user_id": item.get("user_id", ""),
                "email": email_lookup.get(item.get("user_id"), "Unknown user"),
                "file_name": item.get("file_name", "N/A"),
                "target_column": item.get("target_column", "N/A"),
                "prediction_date": item.get("prediction_date", "N/A"),
                "predicted_value": item.get("predicted_value", 0),
                "prediction_direction": item.get("prediction_direction", "N/A"),
                "model_used": item.get("model_used", "N/A"),
                "created_at": created_at,
            }
        )

    if not rows:
        return pd.DataFrame(
            columns=[
                "user_id",
                "email",
                "file_name",
                "target_column",
                "prediction_date",
                "predicted_value",
                "prediction_direction",
                "model_used",
                "created_at",
            ]
        )

    frame = pd.DataFrame(rows)
    return frame.sort_values(by="created_at", ascending=False).reset_index(drop=True)


def render_user_activity_summary(activity_frame: pd.DataFrame):
    st.subheader("Uploads Summary")
    st.caption("Counts below are based on records in the predictions table.")

    if activity_frame.empty:
        st.info("No upload activity found for the selected user.")
        return

    now = pd.Timestamp.utcnow()
    today_start = now.normalize()
    week_start = today_start - pd.Timedelta(days=now.weekday())
    month_start = today_start.replace(day=1)

    today_count = int((activity_frame["created_at"] >= today_start).sum())
    week_count = int((activity_frame["created_at"] >= week_start).sum())
    month_count = int((activity_frame["created_at"] >= month_start).sum())

    metric_1, metric_2, metric_3 = st.columns(3)
    metric_1.metric("Today", today_count)
    metric_2.metric("This Week", week_count)
    metric_3.metric("This Month", month_count)

    daily = (
        activity_frame.assign(day=activity_frame["created_at"].dt.strftime("%Y-%m-%d"))
        .groupby("day", as_index=False)
        .agg(upload_count=("file_name", "count"), unique_files=("file_name", "nunique"))
        .sort_values(by="day", ascending=False)
    )
    weekly = (
        activity_frame.assign(week=activity_frame["created_at"].dt.to_period("W-MON").astype(str))
        .groupby("week", as_index=False)
        .agg(upload_count=("file_name", "count"), unique_files=("file_name", "nunique"))
        .sort_values(by="week", ascending=False)
    )
    monthly = (
        activity_frame.assign(month=activity_frame["created_at"].dt.strftime("%Y-%m"))
        .groupby("month", as_index=False)
        .agg(upload_count=("file_name", "count"), unique_files=("file_name", "nunique"))
        .sort_values(by="month", ascending=False)
    )

    summary_tab1, summary_tab2, summary_tab3 = st.tabs(["Per Day", "Per Week", "Per Month"])
    with summary_tab1:
        st.dataframe(daily, use_container_width=True, hide_index=True)
    with summary_tab2:
        st.dataframe(weekly, use_container_width=True, hide_index=True)
    with summary_tab3:
        st.dataframe(monthly, use_container_width=True, hide_index=True)


def admin_screen():
    current_user = st.session_state.admin_user
    users = list_auth_users()
    user_frame = build_user_frame(users)
    admin_count = int((user_frame["role"] == "admin").sum()) if not user_frame.empty else 0
    recent_predictions = load_recent_predictions()
    prediction_frame = build_prediction_frame(recent_predictions, users)

    st.markdown(
        f"""
        <div class="panel">
            <h1>Admin Dashboard</h1>
            <p>{get_display_name(current_user)} · {get_nested_value(current_user, "email", "")}</p>
            <div class="role-badge">Admin</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    top_col1, top_col2, top_col3, top_col4 = st.columns(4)
    top_col1.metric("Users", len(user_frame))
    top_col2.metric("Admins", admin_count)
    top_col3.metric("Predictions", len(recent_predictions))
    top_col4.metric("Main App", "Ready")

    action_col1, action_col2 = st.columns([1, 1])
    with action_col1:
        st.link_button("Open Main App", MAIN_APP_URL, use_container_width=True)
    with action_col2:
        if st.button("Logout", use_container_width=True):
            st.session_state.admin_logged_in = False
            st.session_state.admin_user = None
            try:
                supabase.auth.sign_out()
            except Exception:
                pass
            st.rerun()

    users_tab, create_tab, roles_tab, access_tab, activity_tab = st.tabs(
        ["Users", "Create User", "Manage Roles", "User Access", "Prediction Activity"]
    )

    with users_tab:
        st.subheader("All Users")
        st.dataframe(
            user_frame.drop(columns=["user_id"]) if not user_frame.empty else user_frame,
            use_container_width=True,
            hide_index=True,
        )

    with create_tab:
        st.subheader("Create User")
        with st.form("create_user_form", clear_on_submit=True):
            first_name = st.text_input("First Name")
            last_name = st.text_input("Last Name")
            email = st.text_input("Email")
            password = st.text_input("Temporary Password", type="password")
            role = st.selectbox("Role", ["admin", "user"])
            create_btn = st.form_submit_button("Create User")

        if create_btn:
            email = email.strip().lower()
            password_error = validate_password_strength(password)
            if not first_name.strip() or not last_name.strip():
                st.error("Enter first and last name.")
            elif not email:
                st.error("Enter an email.")
            elif password_error:
                st.error(password_error)
            elif find_user_by_email(users, email):
                st.error("A user with that email already exists.")
            else:
                try:
                    create_user(email, password, first_name, last_name, role)
                    st.success(f"Created {role} user successfully.")
                    st.rerun()
                except Exception as error:
                    st.error(f"Could not create user: {error}")

    with roles_tab:
        st.subheader("Promote Or Demote Users")
        options = {
            f"{row.email} ({row.role})": row.user_id
            for row in user_frame.itertuples(index=False)
        }

        if not options:
            st.info("No users available.")
        else:
            with st.form("update_role_form"):
                selected_label = st.selectbox("User", list(options.keys()))
                new_role = st.selectbox("New Role", ["admin", "user"])
                update_btn = st.form_submit_button("Update Role")

            if update_btn:
                target_id = options[selected_label]
                target_user = next((user for user in users if get_nested_value(user, "id", "") == target_id), None)
                if target_user is None:
                    st.error("User not found.")
                elif (
                    new_role == "user"
                    and get_nested_value(target_user, "id", "") == get_nested_value(current_user, "id", "")
                    and admin_count <= 1
                ):
                    st.error("You cannot remove the last remaining admin.")
                else:
                    try:
                        update_user_role(target_user, new_role)
                        st.success("Role updated successfully.")
                        st.caption("The user should sign out and sign back in to refresh access.")
                        st.rerun()
                    except Exception as error:
                        st.error(f"Could not update role: {error}")

    with access_tab:
        st.subheader("Disable Or Enable Users")
        options = {
            f"{row.email} ({row.status}, {row.role})": row.user_id
            for row in user_frame.itertuples(index=False)
        }

        if not options:
            st.info("No users available.")
        else:
            with st.form("update_access_form"):
                selected_label = st.selectbox("User Account", list(options.keys()))
                access_action = st.selectbox("Access Action", ["Disable user", "Enable user"])
                access_btn = st.form_submit_button("Save Access")

            if access_btn:
                target_id = options[selected_label]
                target_user = next((user for user in users if get_nested_value(user, "id", "") == target_id), None)
                disable_user = access_action == "Disable user"

                if target_user is None:
                    st.error("User not found.")
                elif (
                    disable_user
                    and get_nested_value(target_user, "id", "") == get_nested_value(current_user, "id", "")
                    and admin_count <= 1
                ):
                    st.error("You cannot disable the last remaining admin account.")
                else:
                    try:
                        update_user_disabled_state(target_user, disable_user)
                        message = "User disabled successfully." if disable_user else "User enabled successfully."
                        st.success(message)
                        st.caption("Disabled users will be blocked from logging into the app.")
                        st.rerun()
                    except Exception as error:
                        st.error(f"Could not update access: {error}")

    with activity_tab:
        st.subheader("Prediction And Upload Activity")
        if prediction_frame.empty:
            st.info("No prediction activity found.")
        else:
            activity_options = ["All Users"] + [
                f"{row.email} ({row.role}, {row.status})"
                for row in user_frame.itertuples(index=False)
            ]
            selected_activity_user = st.selectbox("Activity View", activity_options)

            if selected_activity_user == "All Users":
                selected_frame = prediction_frame.copy()
            else:
                selected_email = selected_activity_user.split(" (", 1)[0].strip().lower()
                selected_frame = prediction_frame[
                    prediction_frame["email"].astype(str).str.strip().str.lower() == selected_email
                ].copy()

            render_user_activity_summary(selected_frame)

            display_frame = selected_frame.copy()
            if not display_frame.empty:
                display_frame["created_at"] = display_frame["created_at"].dt.strftime("%Y-%m-%d %H:%M:%S")
            st.subheader("Recent Records")
            st.dataframe(display_frame, use_container_width=True, hide_index=True)


st.set_page_config(page_title="Admin Panel", layout="wide")
inject_styles()
init_session_state()
require_clients()

if not st.session_state.admin_logged_in:
    login_screen()
else:
    admin_screen()

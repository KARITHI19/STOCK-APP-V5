import random
import smtplib
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError
from supabase import create_client

st.set_page_config(page_title="Forgot Password", layout="centered")

OTP_EXPIRY_MINUTES = 10
OTP_COOLDOWN_SECONDS = 60

DEFAULT_SUPABASE_URL = "https://bqumqfdisvihzknhaaej.supabase.co"
DEFAULT_SUPABASE_KEY = ""

def read_secret(name: str, default: str = "") -> str:
    try:
        if name in st.secrets:
            return str(st.secrets[name])
    except StreamlitSecretNotFoundError:
        return default
    return default


SUPABASE_URL = read_secret("SUPABASE_URL", DEFAULT_SUPABASE_URL)
SUPABASE_KEY = read_secret("SUPABASE_KEY", DEFAULT_SUPABASE_KEY)
SUPABASE_SERVICE_ROLE_KEY = read_secret("SUPABASE_SERVICE_ROLE_KEY", "")
EMAIL_ADDRESS = read_secret("EMAIL_ADDRESS", "")
EMAIL_APP_PASSWORD = read_secret("EMAIL_APP_PASSWORD", "")
MAIN_APP_URL = read_secret("MAIN_APP_URL", "http://localhost:8501/")

if "reset_step" not in st.session_state:
    st.session_state.reset_step = "request"
if "reset_email" not in st.session_state:
    st.session_state.reset_email = ""
if "reset_verified_email" not in st.session_state:
    st.session_state.reset_verified_email = ""
if "reset_last_otp_time" not in st.session_state:
    st.session_state.reset_last_otp_time = 0.0


def generate_otp():
    return f"{random.randint(100000, 999999)}"


def send_otp_email(sender_email: str, sender_password: str, target_email: str, otp: str):
    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = target_email
    msg["Subject"] = "Your Password Reset OTP"
    msg.attach(
        MIMEText(
            f"""
            <h2>Password Reset OTP</h2>
            <p>Your OTP code is:</p>
            <h3>{otp}</h3>
            <p>This code expires in {OTP_EXPIRY_MINUTES} minutes.</p>
            """,
            "html",
        )
    )

    server = smtplib.SMTP("smtp.gmail.com", 587)
    server.starttls()
    server.login(sender_email, sender_password)
    server.send_message(msg)
    server.quit()


def get_clients():
    if not SUPABASE_URL or not SUPABASE_KEY or not SUPABASE_SERVICE_ROLE_KEY:
        raise ValueError("Missing Supabase setup values.")

    return (
        create_client(SUPABASE_URL, SUPABASE_KEY),
        create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY),
    )


def get_user_by_email(admin_client, email: str):
    for user in admin_client.auth.admin.list_users():
        if user.email and user.email.lower() == email.lower():
            return user
    return None


def create_otp_entry(client, email: str, otp: str):
    expires_at = (datetime.utcnow() + timedelta(minutes=OTP_EXPIRY_MINUTES)).isoformat()
    client.table("password_reset_otps").insert(
        {"email": email, "otp": otp, "expires_at": expires_at, "used": False}
    ).execute()


def verify_otp_entry(client, email: str, otp: str):
    res = (
        client.table("password_reset_otps")
        .select("*")
        .eq("email", email)
        .eq("otp", otp)
        .eq("used", False)
        .limit(1)
        .execute()
    )
    rows = res.data or []

    if not rows:
        return False, "Invalid OTP"

    row = rows[0]
    expires_at = datetime.fromisoformat(str(row["expires_at"]).replace("Z", "+00:00")).replace(tzinfo=None)

    if datetime.utcnow() > expires_at:
        return False, "OTP expired"

    client.table("password_reset_otps").update({"used": True}).eq("id", row["id"]).execute()
    return True, "OTP verified"


st.title("Forgot Password")
st.caption("Enter your email, verify the code we send, then choose a new password.")
st.link_button("Back To Main App", MAIN_APP_URL, use_container_width=True)
server_ready = all(
    [
        SUPABASE_URL,
        SUPABASE_KEY,
        SUPABASE_SERVICE_ROLE_KEY,
        EMAIL_ADDRESS,
        EMAIL_APP_PASSWORD,
    ]
)

if not server_ready:
    st.error("Password reset is temporarily unavailable.")
    st.info("The app owner needs to finish server configuration.")
    st.stop()

if st.session_state.reset_step == "request":
    email = st.text_input("Account Email", value=st.session_state.reset_email)
    if st.button("Send OTP"):
        email = email.strip().lower()
        elapsed = datetime.now().timestamp() - st.session_state.reset_last_otp_time

        if not email:
            st.error("Enter the account email.")
        elif elapsed < OTP_COOLDOWN_SECONDS:
            st.error(f"Wait {int(OTP_COOLDOWN_SECONDS - elapsed)} seconds before sending another OTP.")
        else:
            try:
                client, _ = get_clients()
                otp = generate_otp()
                send_otp_email(
                    EMAIL_ADDRESS,
                    EMAIL_APP_PASSWORD,
                    email,
                    otp,
                )
                create_otp_entry(client, email, otp)
                st.session_state.reset_email = email
                st.session_state.reset_last_otp_time = datetime.now().timestamp()
                st.session_state.reset_step = "verify"
                st.success("OTP sent successfully.")
                st.rerun()
            except Exception as e:
                st.error(f"Could not send OTP: {e}")

elif st.session_state.reset_step == "verify":
    st.write(f"OTP sent to `{st.session_state.reset_email}`")
    otp = st.text_input("Enter OTP")
    col1, col2 = st.columns(2)

    with col1:
        if st.button("Verify OTP"):
            if not otp.strip():
                st.error("Enter the OTP.")
            else:
                try:
                    client, _ = get_clients()
                    valid, message = verify_otp_entry(client, st.session_state.reset_email, otp.strip())
                    if valid:
                        st.session_state.reset_verified_email = st.session_state.reset_email
                        st.session_state.reset_step = "reset"
                        st.success(message)
                        st.rerun()
                    else:
                        st.error(message)
                except Exception as e:
                    st.error(f"Could not verify OTP: {e}")

    with col2:
        elapsed = datetime.now().timestamp() - st.session_state.reset_last_otp_time
        remaining = int(OTP_COOLDOWN_SECONDS - elapsed) if elapsed < OTP_COOLDOWN_SECONDS else 0

        if remaining > 0:
            st.button(f"Resend in {remaining}s", disabled=True)
        elif st.button("Resend OTP"):
            try:
                client, _ = get_clients()
                otp = generate_otp()
                send_otp_email(
                    EMAIL_ADDRESS,
                    EMAIL_APP_PASSWORD,
                    st.session_state.reset_email,
                    otp,
                )
                create_otp_entry(client, st.session_state.reset_email, otp)
                st.session_state.reset_last_otp_time = datetime.now().timestamp()
                st.success("OTP resent successfully.")
                st.rerun()
            except Exception as e:
                st.error(f"Could not resend OTP: {e}")

elif st.session_state.reset_step == "reset":
    st.write(f"Resetting password for `{st.session_state.reset_verified_email}`")
    new_password = st.text_input("New Password", type="password")
    confirm_password = st.text_input("Confirm Password", type="password")

    if st.button("Update Password"):
        if not new_password or not confirm_password:
            st.error("Fill in both password fields.")
        elif len(new_password) < 6:
            st.error("Password must be at least 6 characters.")
        elif new_password != confirm_password:
            st.error("Passwords do not match.")
        else:
            try:
                _, admin_client = get_clients()
                user = get_user_by_email(admin_client, st.session_state.reset_verified_email)
                if not user:
                    st.error("No account found with that email.")
                else:
                    admin_client.auth.admin.update_user_by_id(user.id, {"password": new_password})
                    st.success("Password updated successfully.")
                    st.session_state.reset_step = "request"
                    st.session_state.reset_email = ""
                    st.session_state.reset_verified_email = ""
                    st.session_state.reset_last_otp_time = 0.0
            except Exception as e:
                st.error(f"Could not update password: {e}")

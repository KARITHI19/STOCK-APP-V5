import streamlit as st
import os
from supabase import create_client
from datetime import datetime, timedelta
import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import time

# -------------------
# CONFIG
# -------------------
SUPABASE_URL = "https://bqumqfdisvihzknhaaej.supabase.co"
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS", "")
EMAIL_APP_PASSWORD = os.getenv("EMAIL_APP_PASSWORD", "")
OTP_EXPIRY_MINUTES = 10
OTP_COOLDOWN_SECONDS = 60
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
supabase_admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY) if SUPABASE_SERVICE_ROLE_KEY else None

st.set_page_config(page_title="Login & Password Reset", layout="centered")

# -------------------
# SESSION STATE
# -------------------
if "step" not in st.session_state:
    st.session_state.step = "login"
if "email" not in st.session_state:
    st.session_state.email = ""
if "otp_sent" not in st.session_state:
    st.session_state.otp_sent = False
if "last_otp_time" not in st.session_state:
    st.session_state.last_otp_time = 0
if "verified_user_email" not in st.session_state:
    st.session_state.verified_user_email = None

COOLDOWN = 60  # seconds between OTP requests

# -------------------
# FUNCTIONS
# -------------------
def generate_otp():
    return f"{random.randint(100000, 999999)}"


def get_user_by_email(email):
    if not supabase_admin:
        return None

    for user in supabase_admin.auth.admin.list_users():
        if user.email and user.email.lower() == email.lower():
            return user

    return None

def send_otp_email(email, otp):
    if not EMAIL_ADDRESS or not EMAIL_APP_PASSWORD:
        st.error("Set EMAIL_ADDRESS and EMAIL_APP_PASSWORD in your environment.")
        return False

    msg = MIMEMultipart()
    msg['From'] = EMAIL_ADDRESS
    msg['To'] = email
    msg['Subject'] = "Your Password Reset OTP"

    body = f"""
    <h2>Password Reset OTP</h2>
    <p>Your OTP code is:</p>
    <h3>{otp}</h3>
    <p>This code expires in 10 minutes.</p>
    """
    msg.attach(MIMEText(body, 'html'))

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_APP_PASSWORD)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        st.error(f"Error sending email: {e}")
        return False

def create_otp_entry(email, otp):
    expires_at = (datetime.utcnow() + timedelta(minutes=10)).isoformat()
    supabase.table("password_reset_otps").insert({
        "email": email,
        "otp": otp,
        "expires_at": expires_at,
        "used": False
    }).execute()

def verify_otp(email, otp):
    res = supabase.table("password_reset_otps")\
        .select("*")\
        .eq("email", email)\
        .eq("otp", otp)\
        .eq("used", False)\
        .execute()
    data = res.data
    if not data:
        return False, "Invalid OTP"
    otp_entry = data[0]
    if datetime.utcnow() > datetime.fromisoformat(otp_entry['expires_at']):
        return False, "OTP expired"
    # Mark as used
    supabase.table("password_reset_otps").update({"used": True})\
        .eq("id", otp_entry['id']).execute()
    return True, "OTP verified"

# -------------------
# LOGIN PAGE
# -------------------
if st.session_state.step == "login":
    st.title("🔑 Login")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    col1, col2 = st.columns([2,1])
    with col1:
        if st.button("Login"):
            try:
                user = supabase.auth.sign_in_with_password({
                    "email": email,
                    "password": password
                })
                st.success("Logged in successfully!")
            except Exception as e:
                st.error(f"Login failed: {e}")
    with col2:
        if st.button("Forgot Password?"):
            if not email:
                st.warning("Enter your email to reset password")
            else:
                st.session_state.email = email
                st.session_state.step = "otp"
                # send OTP immediately
                now = time.time()
                otp = generate_otp()
                if send_otp_email(email, otp):
                    create_otp_entry(email, otp)
                    st.session_state.last_otp_time = now
                    st.session_state.otp_sent = True
                    st.success("OTP sent to your email")

# -------------------
# STEP 2: VERIFY OTP
# -------------------
elif st.session_state.step == "otp":
    st.title("📩 Enter OTP")
    otp_input = st.text_input("Enter 6-digit OTP")

    # Countdown timer for resend
    elapsed = time.time() - st.session_state.last_otp_time
    remaining = int(COOLDOWN - elapsed) if elapsed < COOLDOWN else 0

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Verify OTP"):
            if not otp_input:
                st.warning("Enter the OTP")
            else:
                valid, msg = verify_otp(st.session_state.email, otp_input)
                if valid:
                    st.session_state.verified_user_email = st.session_state.email
                    st.session_state.step = "reset"
                    st.success(msg)
                else:
                    st.error(msg)

    with col2:
        if remaining > 0:
            st.button(f"Resend OTP in {remaining}s", disabled=True)
        elif st.button("Resend OTP"):
            otp = generate_otp()
            if send_otp_email(st.session_state.email, otp):
                create_otp_entry(st.session_state.email, otp)
                st.session_state.last_otp_time = time.time()
                st.success("OTP resent successfully")

# -------------------
# STEP 3: RESET PASSWORD
# -------------------
elif st.session_state.step == "reset":
    st.title("🔑 Set New Password")
    new_password = st.text_input("New Password", type="password")
    confirm_password = st.text_input("Confirm Password", type="password")

    if st.button("Update Password"):
        if not st.session_state.verified_user_email:
            st.error("You are not authorized to change password!")
        elif not supabase_admin:
            st.error("Set SUPABASE_SERVICE_ROLE_KEY in your environment.")
        elif not new_password or not confirm_password:
            st.warning("Fill all fields")
        elif new_password != confirm_password:
            st.error("Passwords do not match")
        else:
            try:
                user = get_user_by_email(st.session_state.verified_user_email)
                if not user:
                    st.error("No account found with that email.")
                else:
                    supabase_admin.auth.admin.update_user_by_id(
                        user.id,
                        {"password": new_password}
                    )
                    st.success("Password updated successfully 🎉")
                    # Reset flow
                    st.session_state.step = "login"
                    st.session_state.email = ""
                    st.session_state.otp_sent = False
                    st.session_state.verified_user_email = None
            except Exception as e:
                st.error(f"Error updating password: {e}")

@echo off
setlocal

set "SUPABASE_SERVICE_ROLE_KEY=your_service_role_key"
set "EMAIL_ADDRESS=your_email@gmail.com"
set "EMAIL_APP_PASSWORD=your_16_char_app_password"

streamlit run app1.py

endlocal

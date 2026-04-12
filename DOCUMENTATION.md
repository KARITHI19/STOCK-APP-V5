# Stock App V5 Documentation

## Overview

Stock App V5 is a Streamlit-based stock prediction platform with:

- User authentication (Supabase)
- CSV upload and model training/evaluation
- Future price forecasting
- Prediction history per user
- Admin dashboard for user management and activity monitoring

## Main Components

- `app.py`
  - Main user application
  - Handles login/registration
  - Data upload and preprocessing
  - Feature engineering selection
  - Model training/loading and ranking
  - Future prediction + history storage

- `admin_panel.py`
  - Admin login and dashboard
  - User creation, role updates, enable/disable access
  - Prediction activity reporting

- `admin.py`
  - CLI bootstrap utility to create/promote admin accounts

- `simple_password_reset.py`
  - Password reset helper flow

## Authentication

Authentication uses Supabase Auth.

Registration safeguards:

- Duplicate email check (existing emails are blocked)
- Strong password validation:
  - At least 8 characters
  - One uppercase letter
  - One lowercase letter
  - One number
  - One special character

## Prediction Pipeline

1. Upload CSV file.
2. Select target column from OHLC fields.
3. Manually select feature engineering indicators.
4. Train models or load saved model suite.
5. Evaluate model leaderboard (MAE/RMSE/R2).
6. Select model for prediction.
7. Forecast future date price and direction (UP/DOWN).
8. Save prediction to Supabase.

## Prediction History Fields

Base fields used by app:

- `user_id`
- `file_name`
- `target_column`
- `prediction_date`
- `predicted_value`
- `created_at`

Optional metadata fields:

- `prediction_direction`
- `model_used`

The app has schema fallback logic so older DB schemas continue working.

## Supabase SQL Migration (Recommended)

Run this in Supabase SQL Editor:

```sql
alter table public.predictions
add column if not exists prediction_direction text,
add column if not exists model_used text;

notify pgrst, 'reload schema';
```

## Environment Variables

Required:

- `SUPABASE_URL`
- `SUPABASE_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`

Optional:

- `MAIN_APP_URL`
- `RESET_APP_URL`
- `ADMIN_PANEL_URL`
- `SUPABASE_MODEL_BUCKET`
- `MODEL_STORAGE_PREFIX`

## Running the App

Install dependencies:

```bash
pip install -r requirements.txt
```

Run main app:

```bash
streamlit run app.py
```

Run admin panel:

```bash
streamlit run admin_panel.py
```

Run password reset app:

```bash
streamlit run simple_password_reset.py
```

## Admin Bootstrap

Create/promote admin from CLI:

```bash
python admin.py --email admin@example.com --password "StrongP@ssw0rd" --first-name Admin --last-name User
```

## Troubleshooting

- Missing column errors (`prediction_direction`, `model_used`)
  - Run the migration SQL above
  - Reload schema (`notify pgrst, 'reload schema'`)
  - Restart Streamlit app

- Login or registration issues
  - Verify Supabase keys in environment/secrets
  - Confirm project URL/key values are correct

- Admin access missing
  - Ensure user has `app_metadata.role = admin`


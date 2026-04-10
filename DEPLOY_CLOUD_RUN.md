# Cloud Run Deployment

This repo contains:
- `app.py` - main stock app
- `simple_password_reset.py` - standalone forgot-password app

## Docker

This repo includes one `Dockerfile` that can run either app by setting the `APP_ENTRYPOINT` environment variable.

Build the image:

```bash
gcloud builds submit --tag gcr.io/PROJECT_ID/stock-app-v5
```

Deploy the main app:

```bash
gcloud run deploy stock-app-v5 ^
  --image gcr.io/PROJECT_ID/stock-app-v5 ^
  --platform managed ^
  --region us-central1 ^
  --allow-unauthenticated ^
  --memory 2Gi ^
  --set-env-vars APP_ENTRYPOINT=app.py,RESET_APP_URL=https://YOUR-RESET-SERVICE-URL,SUPABASE_URL=https://YOUR-PROJECT.supabase.co,SUPABASE_KEY=YOUR_ANON_KEY,SUPABASE_SERVICE_ROLE_KEY=YOUR_SERVICE_ROLE_KEY
```

Deploy the password reset app from the same image:

```bash
gcloud run deploy stock-app-v5-reset ^
  --image gcr.io/PROJECT_ID/stock-app-v5 ^
  --platform managed ^
  --region us-central1 ^
  --allow-unauthenticated ^
  --memory 1Gi ^
  --set-env-vars APP_ENTRYPOINT=simple_password_reset.py,MAIN_APP_URL=https://YOUR-MAIN-SERVICE-URL,SUPABASE_URL=https://YOUR-PROJECT.supabase.co,SUPABASE_KEY=YOUR_ANON_KEY,SUPABASE_SERVICE_ROLE_KEY=YOUR_SERVICE_ROLE_KEY,EMAIL_ADDRESS=YOUR_EMAIL,EMAIL_APP_PASSWORD=YOUR_GMAIL_APP_PASSWORD
```

Deploy the admin panel as a separate service:

```bash
gcloud run deploy stock-app-v5-admin ^
  --image gcr.io/PROJECT_ID/stock-app-v5 ^
  --platform managed ^
  --region us-central1 ^
  --allow-unauthenticated ^
  --memory 1Gi ^
  --set-env-vars APP_ENTRYPOINT=admin_panel.py,MAIN_APP_URL=https://YOUR-MAIN-SERVICE-URL,SUPABASE_URL=https://YOUR-PROJECT.supabase.co,SUPABASE_KEY=YOUR_ANON_KEY,SUPABASE_SERVICE_ROLE_KEY=YOUR_SERVICE_ROLE_KEY
```

After both are deployed:
- update the main app service so `RESET_APP_URL` points to the reset service URL
- update the reset app service so `MAIN_APP_URL` points to the main app URL

## Admin Setup

The main app now includes an admin-only panel for:
- creating users and admin users
- promoting or demoting users
- reviewing recent prediction activity

Before you deploy or immediately after deployment, bootstrap the first admin account with the service role key:

```bash
python bootstrap_admin.py ^
  --email admin@example.com ^
  --password YOUR_SECURE_PASSWORD ^
  --first-name Admin ^
  --last-name User ^
  --url https://YOUR-PROJECT.supabase.co ^
  --service-role-key YOUR_SERVICE_ROLE_KEY
```

Notes:
- if the email already exists, the script promotes that account to admin
- role changes take effect after the user signs out and back in
- the admin panel in `app.py` requires `SUPABASE_SERVICE_ROLE_KEY` on the main app service

## Secrets

Do not commit `.streamlit/secrets.toml`.

Use platform environment variables or secrets for:
- `SUPABASE_URL`
- `SUPABASE_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`
- `EMAIL_ADDRESS`
- `EMAIL_APP_PASSWORD`
- `MAIN_APP_URL`
- `RESET_APP_URL`

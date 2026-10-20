# Deploy OceanWatch AI on Streamlit Community Cloud

This guide gets the Streamlit UI live on your Streamlit account
(https://share.streamlit.io / https://streamlit.io/cloud).

## What Cloud can and cannot do

| Works on Cloud | Needs a separate service |
| --- | --- |
| Streamlit multipage UI (`streamlit_app/`) | PostgreSQL (Neon, Supabase, RDS, Railway, …) |
| Secrets via Cloud dashboard | Airflow / dbt / Docker ingestion |
| Read-only dashboards against your DB | Training jobs, large model files |

Community Cloud **does not** run your local Postgres or Docker Compose.
Point the app at a **publicly reachable** Postgres (SSL on).

---

## 1. Push this repo to GitHub

Your Streamlit account deploys from GitHub.

1. Repo must be on GitHub (this project already pushes to `origin`).
2. Streamlit account must have access (public repo, or connect the private repo).

Confirm latest UI + deploy files are on `main`:

```bash
git push origin main
```

---

## 2. Provision a cloud database

Use any hosted Postgres. Examples: [Neon](https://neon.tech), [Supabase](https://supabase.com), AWS RDS.

1. Create a database (e.g. `oceanwatch_db`).
2. Apply your schema / load tables the pages query (same as local `init-db.sql` + transformations).
3. Copy the connection string. Prefer SSL:

```text
postgresql://USER:PASSWORD@HOST:5432/oceanwatch_db?sslmode=require
```

Allow inbound connections from the internet (or Streamlit’s egress if your host supports allowlists).  
Streamlit Cloud does **not** publish a fixed IP on the free tier — use `0.0.0.0/0` + strong password + SSL, or a vendor that supports Streamlit.

Without a populated cloud DB, the site still **boots**, but most pages show empty / connection errors.

---

## 3. Deploy in the Streamlit UI

1. Open **https://share.streamlit.io** and sign in (GitHub).
2. **Create app** / **New app**.
3. Fill in:

| Field | Value |
| --- | --- |
| Repository | `your-user/oceanwatch-ai` (this repo) |
| Branch | `main` |
| Main file path | `streamlit_app/OceanWatch.py` |
| App URL (optional) | e.g. `oceanwatch-ai` → `https://oceanwatch-ai.streamlit.app` |

4. Click **Deploy**.  
   Cloud installs `streamlit_app/requirements.txt` (next to the entrypoint).

---

## 4. Add secrets (database)

1. App → **Settings** → **Secrets**.
2. Paste TOML (same format as `streamlit_app/.streamlit/secrets.toml.example`):

```toml
OCEANWATCH_DB_URI = "postgresql://USER:PASSWORD@HOST:5432/oceanwatch_db?sslmode=require"
```

3. **Save**. The app restarts and picks up the URI via `db_config.get_db_uri()`.

Locally you can copy the example to `.streamlit/secrets.toml` under `streamlit_app/` (gitignored) for parity.

---

## 5. Verify

1. Open `https://<your-app>.streamlit.app`.
2. Home should render the maritime theme.
3. Kenya EEZ / Executive pages should load data if tables exist.
4. If a page errors on SQL, check Secrets URI, SSL, and that tables exist in the cloud DB.

---

## 6. Local smoke-test (optional)

```bash
cd streamlit_app
python -m streamlit run OceanWatch.py
```

With Docker Postgres on `localhost:5433`, no secrets file is required (dev default URI).

---

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| Build fails on `rasterio` / GDAL | Use `streamlit_app/requirements.txt` only (lean). Do not point Cloud at full ML requirements. |
| Build fails on `pyarrow` / `cmake` | Cloud may ignore `runtime.txt` and use Python 3.14 (no pyarrow wheel). Keep pyarrow out of `streamlit_app/requirements.txt`. Optionally set Python 3.12 in Cloud **Settings → Advanced**. |
| `ModuleNotFoundError: ow_theme` | Main file must be `streamlit_app/OceanWatch.py` so that folder is on `sys.path`. |
| DB connection refused / timeout | DB not public, wrong host/port, or firewall. |
| SSL error | Add `?sslmode=require` to the URI. |
| Empty charts | Cloud DB has no rows — run migrations/loads against that instance. |
| App sleeps | Free tier sleeps when idle; first load after sleep is slow. |

---

## Files added for Cloud

| Path | Role |
| --- | --- |
| `streamlit_app/OceanWatch.py` | Entrypoint (custom nav shell) |
| `streamlit_app/requirements.txt` | Lean Python deps for Cloud |
| `streamlit_app/db_config.py` | Secrets → env → local URI |
| `streamlit_app/.streamlit/config.toml` | Theme |
| `streamlit_app/.streamlit/secrets.toml.example` | Secrets template (no real passwords) |
| `docs/DEPLOY_STREAMLIT_CLOUD.md` | This guide |

---

## Security checklist

- [ ] Never commit real `secrets.toml` or `.env`
- [ ] Use a strong DB password and SSL
- [ ] Prefer a read-only DB user for the Streamlit app
- [ ] Rotate credentials if they ever landed in git history

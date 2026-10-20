# Connect OceanWatch to Supabase

**Project:** `yigpktdypxstwnebvlpj`  
**Dashboard:** https://supabase.com/dashboard/project/yigpktdypxstwnebvlpj

The app never hardcodes credentials. It reads `OCEANWATCH_DB_URI` from Streamlit
secrets (Cloud) or env / local `secrets.toml` via `streamlit_app/db_config.py`.

---

## 1. Get the connection string

1. Open the [project dashboard](https://supabase.com/dashboard/project/yigpktdypxstwnebvlpj).
2. **Project Settings** (gear) → **Database**.
3. Under **Connection string**, choose **URI**.
4. Select **Transaction** pooler (port **6543**) for Streamlit Cloud.
5. Reveal / paste your **database password**.
   - Forgot it? **Settings → Database → Reset database password**.
6. Copy the full URI. It looks like:

```text
postgresql://postgres.yigpktdypxstwnebvlpj:[PASSWORD]@aws-0-<region>.pooler.supabase.com:6543/postgres
```

7. Append SSL if missing:

```text
...?sslmode=require
```

**URL-encode** the password if it contains `@ # % / : ? &` etc.

| Use case | Host style | Port |
| --- | --- | --- |
| Streamlit Cloud / many short connections | `*.pooler.supabase.com` (Transaction) | **6543** |
| One-off migrations / `psql` / init scripts | `db.yigpktdypxstwnebvlpj.supabase.co` | **5432** |

---

## 2. Streamlit Community Cloud secret

1. https://share.streamlit.io → your app → **Settings** → **Secrets**.
2. Paste:

```toml
OCEANWATCH_DB_URI = "postgresql://postgres.yigpktdypxstwnebvlpj:YOUR_DB_PASSWORD@aws-0-eu-west-1.pooler.supabase.com:6543/postgres?sslmode=require"
```

3. Replace `YOUR_DB_PASSWORD` with your real password (**URL-encode** `@` → `%40`). Host for this project is **`aws-0-eu-west-1.pooler.supabase.com`**.
4. **Save** — the app restarts and picks up the URI.

---

## 3. Local secret (optional)

```bash
cp streamlit_app/.streamlit/secrets.toml.example streamlit_app/.streamlit/secrets.toml
# edit YOUR_DB_PASSWORD + region host
```

`secrets.toml` is gitignored. Then:

```bash
cd streamlit_app
python -m streamlit run OceanWatch.py
```

Or set an env var (PowerShell):

```powershell
$env:OCEANWATCH_DB_URI = "postgresql://postgres.yigpktdypxstwnebvlpj:PASSWORD@HOST:6543/postgres?sslmode=require"
```

---

## 4. Create schema / load data

Supabase starts with an empty `postgres` database. Point init scripts at the
**direct** URI (port 5432) when possible:

```powershell
$env:OCEANWATCH_DB_URI = "postgresql://postgres.yigpktdypxstwnebvlpj:PASSWORD@db.yigpktdypxstwnebvlpj.supabase.co:5432/postgres?sslmode=require"
```

Then run your usual `ingestion/init_phase*.py` scripts (or SQL in the Supabase
**SQL Editor**).

Free tier ≈ **500 MB** — keep AIS history trimmed for demos.

---

## 5. Verify

| Check | Expected |
| --- | --- |
| Supabase **Table Editor** | Tables appear after init |
| Streamlit app pages | Charts load; no "connection refused" |
| Cloud logs (**Manage app**) | No `password authentication failed` / SSL errors |

---

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `Tenant or user not found` | User must be `postgres.<project_ref>` on the **pooler** host |
| `password authentication failed` | Reset DB password; update secret; URL-encode special chars |
| `connection timed out` | Confirm project is not paused (free tier sleeps); open dashboard to wake |
| SSL error | Add `?sslmode=require` |
| Works locally, fails on Cloud | Cloud must use **pooler :6543**, not only direct :5432 |
| Empty UI | Secret OK but no tables/rows — run init + seed |

---

## Security

- Never commit `secrets.toml` or real URIs with passwords.
- Prefer pooler + strong DB password.
- Rotate the password in Supabase if it was pasted into chat or a ticket.

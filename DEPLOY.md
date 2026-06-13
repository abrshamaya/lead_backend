# Deployment — remedylead.app

## ✅ What YOU need to do (checklist)

Do these once. After that, every `git push` to `main` auto-deploys.

> **Note:** SSH on the VPS listens on port **1212**, not 22 (`ssh -p 1212 user@135.181.99.162`).
> The CI workflows already pass `port: 1212`.

**A. On the VPS (135.181.99.162), one time:**
1. [X] Clone both repos somewhere, e.g. `/srv`:
   ```bash
   cd /srv
   git clone https://github.com/abrshamaya/lead_backend.git
   git clone https://github.com/abrshamaya/amaya_lead.git
   ```
   (Use a token or deploy key — both repos are private. The clone must be able to
   `git fetch` non-interactively, or CI's `git reset --hard` step will fail.)
2. [ ] Make sure the SSH user can run Docker without sudo:
   `sudo usermod -aG docker $USER` then log out/in.
3. [ ] Create the static dir for the backend (uid 5678 = the container user):
   `mkdir -p /srv/lead_backend/AmayaLead/staticfiles && sudo chown 5678 /srv/lead_backend/AmayaLead/staticfiles`
4. [ ] Add the host-nginx vhost for `remedylead.app` + TLS (config in
   [One-time server setup](#one-time-server-setup) below).
5. [ ] Point DNS: `remedylead.app` and `www` A records → `135.181.99.162`.

**B. Generate a deploy SSH key (on your machine):**
6. [ ] `ssh-keygen -t ed25519 -f deploy_key -N ""`
7. [ ] Append the **public** key to the VPS: add `deploy_key.pub` contents to
   `~/.ssh/authorized_keys` for `VPS_USER` on the server.
8. [ ] Keep the **private** `deploy_key` file — it goes into `VPS_SSH_KEY` below.

**C. Add GitHub repository secrets** (Settings → Secrets and variables → Actions):

In **`lead_backend`**:
| Secret | Value |
|--------|-------|
| `VPS_HOST` | `135.181.99.162` |
| `VPS_USER` | your SSH username (e.g. `root`) |
| `VPS_SSH_KEY` | the **private** `deploy_key` (whole file) |
| `VPS_BACKEND_PATH` | `/srv/lead_backend` (wherever you cloned it) |
| `BACKEND_DJANGO_ENV` | paste the **entire** `AmayaLead/.env` file |
| `BACKEND_SCRAPER_ENV` | paste the **entire** `FastAPI/.env` file |

In **`amaya_lead`**:
| Secret | Value |
|--------|-------|
| `VPS_HOST` | `135.181.99.162` |
| `VPS_USER` | same SSH username |
| `VPS_SSH_KEY` | same private `deploy_key` |
| `VPS_FRONTEND_PATH` | `/srv/amaya_lead` (wherever you cloned it) |
| `FRONTEND_ENV` | paste the **entire** frontend `.env` (the `VITE_*` vars) |

> Optional: add a `DJANGO_SECRET_KEY=<random string>` line inside `BACKEND_DJANGO_ENV`.
> Without it, Django falls back to the insecure dev key.

**D. Deploy:**
9. [ ] `git push` each repo (or **Actions → Deploy → Run workflow**). The push
   triggers the pipeline, which builds and starts the containers.
10. [ ] First deploy only — set up the database (Postgres starts empty):
   ```bash
   # on the VPS, in /srv/lead_backend:
   docker compose exec backend python manage.py createsuperuser
   # optional: import existing local sqlite data — see One-time server setup step 6
   ```

That's it. Everything below is reference detail.

---

Two repos, both deployed on the VPS (135.181.99.162) with docker compose:

| Repo | Stack | Ports (host) |
|------|-------|--------------|
| `lead_backend` (this repo) | Postgres, Django (gunicorn), FastAPI scraper, Django-Q cluster | 5432, 8000, 8001 |
| `amaya_lead` (frontend) | Vite build served by nginx container | 8080 |

A host-level nginx terminates HTTPS for `remedylead.app` and routes:
- `/` → frontend container (`127.0.0.1:8080`)
- `/api/` → Django (`127.0.0.1:8000`) — the frontend uses the relative path `/api` in production builds

## One-time server setup

1. Clone both repos on the VPS.
2. Env files are injected automatically by CI from GitHub secrets (see CI/CD below) —
   you do **not** create them on the server by hand. For a purely manual first boot
   before CI is wired up, you can drop them in yourself:
   - `<backend>/AmayaLead/.env` — email creds, ElevenLabs keys, Google Places key
   - `<backend>/FastAPI/.env` — Apify token, OpenRouter key, Google Places key
   - `<frontend>/.env` — `VITE_*` vars (baked into the bundle at **build** time; changing them requires a rebuild, not just a restart)
3. Optionally add `DJANGO_SECRET_KEY=<random string>` to the `BACKEND_DJANGO_ENV` secret (falls back to the dev key otherwise).
4. Host nginx site — the full vhost is committed at
   [`deploy/nginx/remedylead.app.conf`](deploy/nginx/remedylead.app.conf). Install it:

   ```bash
   sudo cp deploy/nginx/remedylead.app.conf /etc/nginx/sites-available/remedylead.app
   sudo ln -s /etc/nginx/sites-available/remedylead.app /etc/nginx/sites-enabled/
   ```

   Issue the TLS cert (cert files don't exist on a fresh box yet):

   ```bash
   sudo certbot --nginx -d remedylead.app -d www.remedylead.app
   ```

   Then `sudo nginx -t && sudo systemctl reload nginx`. The committed file is plain HTTP
   that proxies `/api/`, `/admin/`, `/static/` to Django (`:8000`) and everything else to
   the frontend (`:8080`); `certbot --nginx` adds the 443/TLS blocks and HTTP→HTTPS redirect.

5. Create the static files dir writable by the container user (uid 5678):
   ```
   mkdir -p <backend>/AmayaLead/staticfiles && sudo chown 5678 <backend>/AmayaLead/staticfiles
   ```
6. First boot: `docker compose up -d --build` in the backend repo, then in the frontend repo. Migrations and `collectstatic` run automatically on backend start. Postgres starts **empty** — if you have existing data in a local `db.sqlite3`, migrate it once with:
   ```
   # locally (sqlite is the dev DB):
   python manage.py dumpdata --natural-foreign --natural-primary -e contenttypes -e auth.permission -o data.json
   # on the server:
   docker compose exec backend python manage.py loaddata data.json
   ```
7. Create an admin user: `docker compose exec backend python manage.py createsuperuser`

## Deploying updates

Push to `main` and CI deploys automatically (see below). To deploy by hand on the
server: `git pull && docker compose build && docker compose up -d` in whichever repo
changed.

### CI/CD (GitHub Actions)

Both repos have `.github/workflows/deploy.yml`. On every push to `main` (or a manual
**Actions → Run workflow**) the pipeline:

1. Writes the `.env` file(s) from secrets,
2. `scp`s them to the server,
3. SSHes in, `git reset --hard origin/main` (exact mirror of main),
4. Moves the env files into place and runs `docker compose build && docker compose up -d`.

The env files are injected at deploy time, so you do **not** keep `.env` on the server
manually — you paste their contents into secrets once. Configure these **repository
secrets** (Settings → Secrets and variables → Actions):

**Backend repo (`lead_backend`):**

| Secret | Value |
|--------|-------|
| `VPS_HOST` | `135.181.99.162` |
| `VPS_USER` | SSH user (must be able to run docker) |
| `VPS_SSH_KEY` | Private key with SSH access to the VPS (full PEM contents) |
| `VPS_BACKEND_PATH` | Absolute path of the backend clone on the server |
| `BACKEND_DJANGO_ENV` | Full contents of `AmayaLead/.env` (paste the whole file) |
| `BACKEND_SCRAPER_ENV` | Full contents of `FastAPI/.env` (paste the whole file) |

**Frontend repo (`amaya_lead`):**

| Secret | Value |
|--------|-------|
| `VPS_HOST` | `135.181.99.162` |
| `VPS_USER` | SSH user |
| `VPS_SSH_KEY` | Same private key |
| `VPS_FRONTEND_PATH` | Absolute path of the frontend clone on the server |
| `FRONTEND_ENV` | Full contents of the frontend `.env` (the `VITE_*` vars) |

Generate a dedicated deploy key with `ssh-keygen -t ed25519 -f deploy_key`, append
`deploy_key.pub` to `~/.ssh/authorized_keys` on the VPS, and paste the private
`deploy_key` into `VPS_SSH_KEY`.

You can also trigger a deploy manually from the Actions tab (`workflow_dispatch`).

## Env var notes

- Backend/scraper `.env` changes take effect with `docker compose up -d` (compose injects them via `env_file` — no rebuild needed).
- Frontend `.env` changes **require a rebuild** (`docker compose build`), because Vite inlines `VITE_*` values into the JS bundle — a plain restart won't pick them up.
- `DJANGO_ENV=prod` (set in docker-compose) switches Django to Postgres, `DEBUG=False`, and the `http://scraper:8001` service URL. Local dev without that var keeps sqlite + DEBUG.

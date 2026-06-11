# Deployment — remedylead.app

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
4. Host nginx site (`/etc/nginx/sites-available/remedylead.app`):

   ```nginx
   server {
       server_name remedylead.app www.remedylead.app;

       location /api/ {
           proxy_pass http://127.0.0.1:8000/api/;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
           proxy_read_timeout 300s;
       }

       location /admin/ {
           proxy_pass http://127.0.0.1:8000/admin/;
           proxy_set_header Host $host;
           proxy_set_header X-Forwarded-Proto $scheme;
       }

       location /static/ {
           proxy_pass http://127.0.0.1:8000/static/;
       }

       location / {
           proxy_pass http://127.0.0.1:8080;
           proxy_set_header Host $host;
       }

       listen 443 ssl;  # certbot manages the cert blocks
   }
   ```

   Then `nginx -t && systemctl reload nginx`. Use `certbot --nginx -d remedylead.app -d www.remedylead.app` for TLS.

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
- Frontend `.env` changes **require a rebuild** (`bash deploy.sh`), because Vite inlines `VITE_*` values into the JS bundle.
- `DJANGO_ENV=prod` (set in docker-compose) switches Django to Postgres, `DEBUG=False`, and the `http://scraper:8001` service URL. Local dev without that var keeps sqlite + DEBUG.

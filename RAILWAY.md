# Railway Deployment Guide — CareSync

CareSync deploys as **two Railway services** in one project: the API (FastAPI)
and the Web client (static Vite build).

## Prerequisites

- A [Railway](https://railway.app) account
- The [Railway CLI](https://docs.railway.app/guides/cli): `npm install -g @railway/cli`
- This repo pushed to GitHub

## Setup

### 1. Create the Railway project

```bash
railway login
railway init          # name it "caresync"
```

### 2. Deploy the API service

```bash
# Link to the project
railway link

# Create the API service
railway service create caresync-api
railway link --service caresync-api
```

Set the service root directory and environment variables in the Railway dashboard
(**Settings → Source**):

- **Root Directory:** `backend`
- **Dockerfile Path:** `Dockerfile`

Then set these **environment variables** (Railway dashboard → Variables):

```
CARESYNC_DATABASE_URL=sqlite:////data/caresync.db
CARESYNC_SEED_DEMO_USERS=true
CARESYNC_SESSION_COOKIE_SECURE=true
CARESYNC_CORS_ORIGINS=https://<YOUR_WEB_DOMAIN>,http://localhost:5173
```

> **Important:** Add a **persistent volume** mounted at `/data` so the SQLite
> database survives redeployments. Go to **Settings → Volumes → Add Volume**,
> mount path: `/data`.

### 3. Deploy the Web service

```bash
railway service create caresync-web
railway link --service caresync-web
```

In the Railway dashboard (**Settings → Source**):

- **Root Directory:** `/` (needs the root package.json for the workspace)
- **Dockerfile Path:** `frontend/Dockerfile`

Set this **build argument** (Railway dashboard → Variables):

```
VITE_API_BASE_URL=https://<YOUR_API_DOMAIN>
```

The API domain is the public URL Railway assigns to the `caresync-api` service
(find it under **Settings → Networking → Public Domain**).

### 4. Generate public domains

For each service, go to **Settings → Networking** and click **Generate Domain**.

- API gets something like `caresync-api-production-xxxx.up.railway.app`
- Web gets something like `caresync-web-production-xxxx.up.railway.app`

### 5. Update CORS

Once you know both domains, update the API's `CARESYNC_CORS_ORIGINS` to include
the web domain:

```
CARESYNC_CORS_ORIGINS=https://caresync-web-production-xxxx.up.railway.app
```

### 6. Deploy

Railway auto-deploys on push to `main`. Or trigger manually:

```bash
railway up
```

## Verify

1. Visit `https://<API_DOMAIN>/docs` — FastAPI Swagger UI
2. Visit `https://<WEB_DOMAIN>` — CareSync login page
3. Sign in with `clinical@example.com` / `clinical-password`

## Environment variable reference

| Variable | Required | Default | Notes |
|----------|----------|---------|-------|
| `CARESYNC_DATABASE_URL` | Yes | `sqlite:///./caresync.db` | Use `/data/caresync.db` with a volume |
| `CARESYNC_SEED_DEMO_USERS` | No | `false` | Set `true` for demo |
| `CARESYNC_SESSION_COOKIE_SECURE` | Yes | `false` | Must be `true` over HTTPS |
| `CARESYNC_SESSION_IDLE_SECONDS` | No | `300` | Lock screen timeout |
| `CARESYNC_CORS_ORIGINS` | Yes | localhost only | Comma-separated origins |
| `CARESYNC_STUDY_INSTRUMENTATION_ENABLED` | No | `false` | Study mode |
| `VITE_API_BASE_URL` | Yes (web) | `""` | Build arg: the API's public URL |

# TriageAssist

Clinical decision support for emergency-department triage. The system recommends
an Urgency Level for each Encounter and keeps the Queue ordered from that
recommendation, leaving the final decision with clinical staff.

This ticket establishes the runnable walking skeleton: the HTTP API, the React
client, authentication, and the two Roles. Intake, the Queue board, the
Prioritization Engine, and Reports arrive in later tickets.

Vocabulary follows [`CONTEXT.md`](CONTEXT.md). The data-layer decision is
[ADR 0001](docs/adr/0001-sqlite-local-postgres-production.md): SQLite for local
development and tests, Postgres for the demonstration deployment.

## Stack

| Layer  | Choice                                             |
| ------ | -------------------------------------------------- |
| API    | Python 3.12, FastAPI, SQLAlchemy 2.0 (sync), argon2 |
| Client | React 19, TypeScript, Vite                         |
| Data   | SQLite locally and in tests; Postgres for the demo |

## Prerequisites

- [uv](https://docs.astral.sh/uv/) — installs and pins Python 3.12 itself
- Node.js 20 or newer with npm
- Docker, only if you want to run the Postgres demo path

## Setup (once per checkout)

```powershell
npm install
uv python install 3.12
```

`uv python install` is optional: `uv run` fetches 3.12 automatically because
`backend/.python-version` pins it. `npm install` also installs the `frontend`
workspace.

## Start the stack

```powershell
npm run dev
```

That single command seeds the two demo users and starts:

- API: <http://127.0.0.1:8000> (interactive docs at `/docs`)
- Client: <http://127.0.0.1:5173>

The client proxies `/api` to the API, so the session cookie is same-origin in
the browser.

### Demo users

| Role          | Email                      | Password                 |
| ------------- | -------------------------- | ------------------------ |
| Clinical      | `clinical@example.com`     | `clinical-password`      |
| Administrator | `administrator@example.com` | `administrator-password` |

Seeding is idempotent and does not reset a password that has already been
changed. To seed manually (for example after deleting the database):

```powershell
npm run seed
```

## Run the tests

```powershell
npm test
```

Equivalent to `cd backend; uv run pytest`. The suite runs against a temporary
SQLite database and needs no external service or Docker.

## Postgres demo path

The Compose file provisions Postgres only; the API and client still run as
normal processes. This path is documented but is not exercised by the local
test suite (see ADR 0001).

```powershell
docker compose up -d db
$env:TRIAGEASSIST_DATABASE_URL = "postgresql+psycopg://triageassist:triageassist@127.0.0.1:5432/triageassist"
npm run dev
```

In bash, use `export TRIAGEASSIST_DATABASE_URL=...` instead. To stop Postgres:

```powershell
docker compose down
```

## Environment variables

All variables use the `TRIAGEASSIST_` prefix. A `.env` file in `backend/` is
also read.

| Variable                           | Default                      | Purpose                                      |
| ---------------------------------- | ---------------------------- | -------------------------------------------- |
| `TRIAGEASSIST_DATABASE_URL`        | `sqlite:///./triageassist.db` | SQLAlchemy URL; Postgres URL for the demo    |
| `TRIAGEASSIST_SESSION_TTL_SECONDS` | `28800` (8 hours)            | Session lifetime, enforced on every request  |
| `TRIAGEASSIST_SESSION_COOKIE_NAME` | `triageassist_session`       | Session cookie name                          |
| `TRIAGEASSIST_SESSION_COOKIE_SECURE` | `false`                    | Set `true` when served over HTTPS            |
| `TRIAGEASSIST_SEED_DEMO_USERS`     | `false`                      | Seed demo users during API startup           |

## API surface

| Method | Path                          | Access        |
| ------ | ----------------------------- | ------------- |
| POST   | `/api/auth/login`             | Public        |
| GET    | `/api/auth/me`                | Authenticated |
| POST   | `/api/auth/logout`            | Public        |
| POST   | `/api/auth/password`          | Authenticated |
| GET    | `/api/roles`                  | Public        |
| GET    | `/api/clinical/access`        | Clinical      |
| GET    | `/api/administrator/access`   | Administrator |

The two `/access` routes are the role-gated surfaces for this ticket; they exist
to demonstrate that authorisation is enforced at the API boundary. A wrong Role
receives `403`; an unauthenticated request receives `401`.

## Security behaviour

- Passwords are hashed with argon2id. Plain text is never stored.
- Sessions live in the `sessions` table. The cookie carries an opaque random
  token; only its SHA-256 hash is stored.
- The session cookie is `HttpOnly`, `SameSite=Lax`, and `Secure` when configured.
- Expiry is checked against the stored `expires_at` on every authenticated
  request, not just when the cookie is issued.
- Logout deletes the session row and clears the cookie.
- Changing a password updates the hash; the old password stops working
  immediately. The current session stays signed in.

## Layout

```
backend/
  app/
    main.py            app factory, router wiring, startup seeding
    config.py          Settings (TRIAGEASSIST_* env vars)
    db.py              engine and session factory
    models.py          User, UserSession, Role
    schemas.py         request/response models
    security.py        argon2 hashing, session token hashing
    deps.py            get_current_user, require_role
    seed.py            demo Clinical and Administrator users
    routers/
      auth.py          login, me, logout, change-own-password
      meta.py          the two Roles
      clinical.py      Clinical-gated surface
      administrator.py Administrator-gated surface
  tests/               API-level pytest suite (SQLite)
frontend/
  src/
    App.tsx            session check and screen switch
    LoginScreen.tsx    login form
    Shell.tsx          post-login shell, role badge, password change
    api.ts             typed fetch wrapper
```

There is no migration tool yet. Tables are created at API startup; deleting
`backend/triageassist.db` resets the local database.

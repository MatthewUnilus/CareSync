# TriageAssist

Clinical decision support for emergency-department triage. The system recommends
an Urgency Level for each Encounter and keeps the Queue ordered from that
recommendation, leaving the final decision with clinical staff.

This build covers the walking skeleton: the HTTP API, the React client,
authentication, the two Roles, Patient registration, Encounter intake, the
Triage Assessment record, the live Queue board, the Override action, and the
read-only Administrator dashboard. The Prioritization Engine behind the board
is a documented deterministic stub; the trained classifier, Re-assessment,
Departure, and Reports arrive in later tickets.

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

## Patient matching

Registering a Patient reuses an existing record when the normalised full name
**and** the normalised contact phone number both match:

- name: surrounding whitespace trimmed, internal whitespace collapsed to one
  space, case-folded (`"  Ada   Lovelace "` matches `"ada lovelace"`)
- phone: non-digits dropped, a leading `+` kept (`"0770-090 0123"` matches
  `"07700 900123"`)

Requiring both is deliberate. A name alone collides between different people, so
matching on name only would merge two Patients irreversibly. The cost is that a
returning Patient who gives a new phone number registers a second record; a
duplicate can be resolved later, a bad merge cannot. The API answers
`201 Created` for a new Patient and `200 OK` when an existing record is reused.

The rule is enforced by a unique constraint on the normalised pair, so a
concurrent double submission cannot create two rows either. Re-registration
never overwrites the stored name, age, sex, or contact details.

## Intake

Opening an Encounter requires the intake that a Triage Assessment will later run
on. Every field except notes is required and is validated server-side as well as
in the form:

| Field                      | Range                          |
| -------------------------- | ------------------------------ |
| Presenting complaint       | 1–2000 characters, free text   |
| Pain level                 | 1–10                           |
| Illness duration           | 0–8760 hours                   |
| Temperature                | 30–45 °C                       |
| Heart rate                 | 20–300 bpm                     |
| Blood pressure             | systolic 50–300, diastolic 20–200, systolic above diastolic |
| Oxygen saturation          | 50–100 %                       |
| Notes                      | optional, up to 2000 characters |

`arrived_at` is written when the Encounter is opened and cannot be changed
afterwards; the Encounter itself is never updated, only its intake. Intake is
complete as soon as the Encounter exists, so opening an Encounter also creates
its first Triage Assessment in the same transaction. A later correction attempt
therefore returns `409 Conflict`: the Assessment's snapshot is the durable record
of what the recommendation was made from. See `backend/app/intake.py`.

## Prioritization Engine and the Queue

The engine boundary (Seam B) is `app.prioritisation.recommend`: a pure function
taking a `PrioritisationInputs` and returning exactly one `UrgencyLevel`, with no
session and no database. It is called directly by
`backend/tests/test_prioritisation.py`.

This ticket ships a **documented deterministic stub** at that boundary. In one
paragraph: High if any single severe observation is present — oxygen saturation
below 92%, heart rate outside 50–120, systolic pressure outside 90–179,
temperature outside 35.0–38.9 °C, or pain 8 or more; otherwise Medium if any
moderate observation is present — oxygen saturation below 95%, heart rate above
100, systolic pressure below 100 or 160 and above, temperature 38.0 °C or above
or below 36.0 °C, or pain 5 or more; otherwise Low. It ignores the complaint text,
age, illness duration, and Symptom Groups. Ticket 06 replaces it with the trained
classifier; tickets 05, 07, and 08 add recognition, the safety layer, and the
fallback behind the same boundary.

The Queue is a sort over awaiting Encounters, not a stored sequence: Urgency
Level first (High, Medium, Low), then arrival time, so equally urgent Encounters
are first-in-first-out. The level that governs is the latest Triage Assessment's
Final Decision, which starts equal to the Machine Recommendation and moves only
through an Override. An Encounter is awaiting while `departed_at` is null; ticket
11 adds the Departure action. `waiting_seconds` is derived from `arrived_at` at
read time.

The client polls `GET /api/clinical/queue` every five seconds and on window
focus, so a change to a Final Decision appears without a manual refresh.
`QueueBoard.tsx` renders compact cards — urgency colour, Patient name, short
complaint, time waiting — and expands to the full vitals, pain level, duration,
notes, and the Override form.

## Override

A Clinical user may disagree with a Machine Recommendation and set a different
Final Decision on the governing Triage Assessment of an awaiting Encounter:

```http
POST /api/clinical/encounters/{id}/override
{
  "assessment_id": 12,
  "final_decision": "High",
  "reason": "patient deteriorating",
  "free_text": null
}
```

The Override is refused (`409`) when the Encounter has departed, when the named
Assessment is not the governing one, or when the Final Decision would equal the
Machine Recommendation. A reason is mandatory (`422` when absent), and it must
come from the fixed set — *vitals inconsistent with recommendation, symptom not
captured, clinical gestalt, patient deteriorating, duplicate entry, other*.
Free text is accepted only for `other`; supplying it with any other reason is
refused. The acting user is recorded from the session.

The fixed list lives once, in `backend/app/override_reasons.py`, and is exposed
to the client at `GET /api/clinical/override-reasons`. Each Override appends an
`overrides` row linked to the Assessment, the actor, the reason, and any free
text. The Machine Recommendation itself is never written by this path: a
`before_update` guard freezes it, and the request model refuses unknown fields.
Both values survive, so accuracy can still be measured.

A card shows an **Override** flag whenever the Final Decision differs from the
Machine Recommendation (`override_flag` on each queue entry). That flag is its
own state, separate from the unclassified flag ticket 08 will add. The
Administrator's dense table shows the same fact as "Differs" and needs no change,
because it already compares the two stored values. The Queue reorders on the
next poll, since it sorts on Final Decision.

## Administrator dashboard

The same client serves both Roles from one codebase and one build. Signing in
sends a Clinical user to `/clinical` and an Administrator to `/administrator`;
any other path is replaced with the Role's own landing route.

The Administrator dashboard is the dense-tabular view over the same awaiting
Queue. Each row shows Urgency Level, Patient name, the short complaint, time
waiting, and whether the Final Decision differs from the Machine Recommendation
(a neutral "Same" until Override exists). It polls
`GET /api/administrator/queue` every five seconds and on window focus through
the same `usePolling` hook as the Clinical board, so an Override or a Departure
appears without a manual refresh.

There are no clinical actions anywhere in the Administrator surface — no
registration, intake, Override, Re-assessment, or Departure. That is enforced by
the API, not by hiding buttons: every `/api/clinical/*` route refuses an
Administrator with `403`, and the Administrator queue route refuses a Clinical
user in the same way. The dashboard ends with a Reports section that tickets 13
and 14 fill; it is read-only and currently explains what will mount there.

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

| Method | Path                                    | Access        |
| ------ | --------------------------------------- | ------------- |
| POST   | `/api/auth/login`                       | Public        |
| GET    | `/api/auth/me`                          | Authenticated |
| POST   | `/api/auth/logout`                      | Public        |
| POST   | `/api/auth/password`                    | Authenticated |
| GET    | `/api/roles`                            | Public        |
| GET    | `/api/clinical/access`                  | Clinical      |
| POST   | `/api/clinical/patients`                | Clinical      |
| POST   | `/api/clinical/encounters`              | Clinical      |
| GET    | `/api/clinical/encounters`              | Clinical      |
| GET    | `/api/clinical/queue`                   | Clinical      |
| GET    | `/api/clinical/encounters/{id}`         | Clinical      |
| PUT    | `/api/clinical/encounters/{id}/intake`  | Clinical      |
| GET    | `/api/clinical/override-reasons`        | Clinical      |
| POST   | `/api/clinical/encounters/{id}/override` | Clinical     |
| GET    | `/api/administrator/access`             | Administrator |
| GET    | `/api/administrator/queue`              | Administrator |

The `/access` routes are the role-gated surfaces from ticket 01; they exist to
demonstrate that authorisation is enforced at the API boundary. A wrong Role
receives `403`; an unauthenticated request receives `401`.

`GET /api/clinical/encounters` is a recency list for reviewing a saved intake —
newest arrival first, `?limit=` up to 100. It is not the Queue: it is not
ordered by Urgency Level and does not filter awaiting versus departed.

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
    models.py          User, UserSession, Role, Patient, Encounter,
                       TriageAssessment, Override, Sex
    schemas.py         request/response models
    patients.py        Patient matching rule and find-or-create
    intake.py          whether an Encounter's intake may still be corrected
    prioritisation.py  Seam B: the pure Prioritization Engine (stub in ticket 03)
    assessments.py     captures inputs, runs the engine, appends the Assessment
    override_reasons.py  the fixed Override Reason set (one source of truth)
    overrides.py       performing an Override and its guards
    queue.py           the Queue as a sort over awaiting Encounters
    security.py        argon2 hashing, session token hashing
    deps.py            get_current_user, require_role
    seed.py            demo Clinical and Administrator users
    routers/
      auth.py          login, me, logout, change-own-password
      meta.py          the two Roles
      clinical.py      Patient registration, intake, Assessments, Queue
      administrator.py Administrator queue read model and access surface
  tests/               API-level pytest suite (SQLite) and Seam B unit tests
frontend/
  src/
    App.tsx            session check, Role landing route, surface switch
    LoginScreen.tsx    login form
    routing.ts         Role landing paths and path routing
    ClinicalWorkspace.tsx  Queue / Intake switch for the Clinical role
    QueueBoard.tsx     live Queue cards, expansion, Override form, polling
    AdministratorDashboard.tsx  dense Queue table, Reports mount point
    usePolling.ts      shared poll-on-interval and poll-on-focus hook
    queueDisplay.ts    shared waiting-time and urgency formatting
    IntakeScreen.tsx   Clinical intake and recent Encounters
    Shell.tsx          post-login shell, role badge, password change
    api.ts             typed fetch wrapper
```

There is no migration tool yet. Tables are created at API startup; deleting
`backend/triageassist.db` resets the local database.

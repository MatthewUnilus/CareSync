# TriageAssist

Clinical decision support for emergency-department triage. The system recommends
an Urgency Level for each Encounter and keeps the Queue ordered from that
recommendation, leaving the final decision with clinical staff.

This build covers the walking skeleton: the HTTP API, the React client,
authentication, the two Roles, Patient registration, Encounter intake, the
Triage Assessment record, the live Queue board, and the read-only Administrator
dashboard. The Prioritization Engine behind the board is a documented
deterministic stub; the trained classifier, Override, Re-assessment, Departure,
and Reports arrive in later tickets.

Vocabulary follows [`CONTEXT.md`](CONTEXT.md). The data-layer decision is
[ADR 0001](docs/adr/0001-sqlite-local-postgres-production.md): SQLite for local
development and tests, Postgres for the demonstration deployment.

## Stack

| Layer  | Choice                                             |
| ------ | -------------------------------------------------- |
| API    | Python 3.12, FastAPI, SQLAlchemy 2.0 (sync), argon2 |
| Client | React 19, TypeScript, Vite                         |
| Mobile | Capacitor 8 shell over the same Vite build         |
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
Final Decision, which currently equals the Machine Recommendation because no
Override exists yet. An Encounter is awaiting while `departed_at` is null; ticket
11 adds the Departure action. `waiting_seconds` is derived from `arrived_at` at
read time.

The client polls `GET /api/clinical/queue` every five seconds and on window
focus, so a change to a Final Decision appears without a manual refresh.
`QueueBoard.tsx` renders compact cards — urgency colour, Patient name, short
complaint, time waiting — and expands to the full vitals, pain level, duration,
notes, and the actions that exist (none for the Queue yet).

## Mobile client

The bedside client is the same React application in a Capacitor native shell.
`capacitor.config.ts` points `webDir` at `frontend/dist`, the output of
`npm run build:web`; there is no second UI, no forked screen and no bundled mock
data. The app calls the same backend API as the dashboard.

### Prerequisites

- Android: a JDK and the Android SDK (Android Studio is the easiest route).
  `npx cap doctor` reports what is missing.
- iOS: macOS with Xcode. The generated iOS project uses Swift Package Manager,
  not CocoaPods.

### Build and run (Android)

```powershell
npm install
npm run mobile:sync        # build:web, then copy the bundle into android/ and ios/
npm run mobile:run:android # sync, build and install on a running emulator/device
```

`npm run mobile:open:android` opens the project in Android Studio instead, from
which you can run the emulator or use **Build > Build APK(s)**. From the
command line, a debug APK is produced by:

```powershell
cd android
.\gradlew.bat assembleDebug
```

The APK lands in `android/app/build/outputs/apk/debug/`.

### Pointing the app at the dev API

A WebView has its own origin (the packaged bundle), so a relative `/api` request
would resolve to the bundle, not to the API. The native build therefore uses an
absolute base URL:

1. `VITE_API_BASE_URL` at build time, for example
   `$env:VITE_API_BASE_URL = "http://localhost:8000"; npm run mobile:sync`; or
2. the **Server** field on the native login screen, saved in the device's local
   storage. It takes precedence and needs no rebuild.

The native default is `http://localhost:8000`. On an emulator or a USB-attached
device, forward the host port so that address reaches the machine running the
API:

```powershell
adb reverse tcp:8000 tcp:8000
```

`adb reverse` also keeps the app and the API on the same site (`http://localhost`
on different ports). That matters for authentication: the session cookie is
`SameSite=Lax`, and a browser does not attach it to a cross-site fetch. Pointing
the app at `http://10.0.2.2:8000` reaches the API at the network level but makes
it a different site, so login would appear to succeed and the next request would
be refused with `401`. For a deployed HTTPS API, set the base URL to that HTTPS
address; the WebView origin is then `https://localhost`, which the backend must
allow in `TRIAGEASSIST_CORS_ORIGINS`.

The API grants credentialed CORS only to the origins listed in
`TRIAGEASSIST_CORS_ORIGINS` (localhost by default). The browser never needs it
because the Vite dev server proxies `/api`; the native shell is genuinely
cross-origin.

For this plain-HTTP development path, the Android manifest permits cleartext
traffic and the iOS `Info.plist` allows local networking. Remove both
allowances when the API is served over HTTPS. The iOS project is generated by
the same config, but building it needs macOS and Xcode.

### Primary screen and session expiry

A Clinical user lands on Intake in the native app; the web dashboard still lands
on the Queue, and the existing view switch exposes both screens in both forms.
Session expiry is not reimplemented for mobile: the app shares `api.ts`, so an
expired session produces the same `401 Not authenticated` response and the same
on-screen error as the browser, with no separate mobile session state. Signing in
again resumes work.

### Generated projects

The `android/` and `ios/` platform projects are committed so a clone can be
built without regenerating them. Their own `.gitignore` files exclude copied web
assets (`*/assets/public`), Gradle/Xcode build output, `local.properties`, Pods,
derived data and keystores. `npm run mobile:sync` repopulates the ignored assets
after every client change.

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

Runs the API suite (`uv run --directory backend pytest`) and then the client
suite (`node --test` over `frontend/src/*.test.ts`, covering API base URL
resolution and platform detection). Use `npm run test:api` or
`npm run test:web` to run either half alone.

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
| `TRIAGEASSIST_CORS_ORIGINS`        | localhost origins             | Comma-separated origins granted credentialed CORS (the native shell) |
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
capacitor.config.ts    native shell config; webDir is frontend/dist
android/               Capacitor Android project (committed; build output ignored)
ios/                   Capacitor iOS project (committed; build output ignored)
backend/
  app/
    main.py            app factory, router wiring, startup seeding, CORS
    config.py          Settings (TRIAGEASSIST_* env vars)
    db.py              engine and session factory
    models.py          User, UserSession, Role, Patient, Encounter,
                       TriageAssessment, Sex
    schemas.py         request/response models
    patients.py        Patient matching rule and find-or-create
    intake.py          whether an Encounter's intake may still be corrected
    prioritisation.py  Seam B: the pure Prioritization Engine (stub in ticket 03)
    assessments.py     captures inputs, runs the engine, appends the Assessment
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
    LoginScreen.tsx    login form; native Server setting
    routing.ts         Role landing paths and path routing
    ClinicalWorkspace.tsx  Queue / Intake switch for the Clinical role
    QueueBoard.tsx     live Queue cards, expansion, five-second polling
    AdministratorDashboard.tsx  dense Queue table, Reports mount point
    usePolling.ts      shared poll-on-interval and poll-on-focus hook
    queueDisplay.ts    shared waiting-time and urgency formatting
    IntakeScreen.tsx   Clinical intake and recent Encounters
    Shell.tsx          post-login shell, role badge, password change
    api.ts             typed fetch wrapper; absolute URL in the native shell
    platform.ts        Capacitor platform mapping, default clinical view
    runtime.ts         Capacitor platform detection
    runtimeConfig.ts   API base URL resolution and device override
    *.test.ts          node:test suites for the two modules above
```

There is no migration tool yet. Tables are created at API startup; deleting
`backend/triageassist.db` resets the local database.

# CareSync

CareSync is a nursing workflow management system for a private hospital ward. It
is presented through one responsive client codebase — a ward surface for
clinical staff and a read-only operations dashboard for administrators — with a
Capacitor shell so the same build runs on a shared tablet.

It answers the three problems a ward nurse names — documentation, access to
information away from the ward, and tracking outstanding work across several
patients — by keeping one clinical record and deriving the worklists from it. A
Patient is registered and, when they are an inpatient, admitted to a ward. Staff
chart Observations, write Nursing Notes from Note Templates, record the doctor's
Medication Orders and the administrations that follow, track Investigations to a
reviewed result, and carry Tasks raised from a ward round or by hand. A Ward
Board shows the open Admissions ordered by outstanding work counted from the
record.

It does not diagnose, recommend treatment, calculate a dose, check an
interaction or allergy, interpret a result value, or decide who is treated
first. Every figure is derived on read and stored nowhere, so a displayed number
can never drift from the rows behind it.

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

A Patient may carry an optional **hospital number**. When a number is involved
it decides identity, and the name-and-phone rule is the fallback used only when
neither side has one:

- **Same number reuses the record.** A registration whose normalised hospital
  number equals an existing Patient's number is that Patient, whatever name or
  phone was entered alongside it.
- **Different numbers stay separate.** Two Patients whose numbers differ are
  different people, even when the name **and** the phone both match. This is the
  case that matters on a ward, where a family phone number is shared and
  surnames repeat.
- **Neither number: name and phone.** With no number on either side, a record
  is reused only when the normalised full name **and** the normalised contact
  phone both match:

  - name: surrounding whitespace trimmed, internal whitespace collapsed to one
    space, case-folded (`"  Ada   Lovelace "` matches `"ada lovelace"`)
  - phone: non-digits dropped, a leading `+` kept (`"0770-090 0123"` matches
    `"07700 900123"`)

The hospital number is optional, so a walk-in with no number is still
registrable. It is stored as entered and compared in normalised form, the way
name and phone are.

Requiring name and phone together is deliberate. A name alone collides between
different people, so matching on name only would merge two Patients
irreversibly. The cost is that a returning Patient who gives a new phone number
registers a second record; a duplicate can be resolved later, a bad merge
cannot. The API answers `201 Created` for a new Patient and `200 OK` when an
existing record is reused.

Adding a number later **attaches it to the selected existing Patient**. It does
not merge that record with an unrelated Patient who shares its name, and a
registration that carries a number attaches to the Patient already holding that
number rather than auto-merging an unnumbered record that happens to share the
name. Patient search matches on the hospital number as well as name and phone,
so a number can find someone whose name cannot be spelled. The rule is enforced
at the data layer, so a concurrent double submission cannot create two rows
either, and re-registration never overwrites the stored name, age, sex, or
contact details.

## Ward features

The ward surface is reached from the **Ward board** tab, with **Intake**,
**Patient history** and **Study timing** beside it.

### Admissions and the Ward Board

An **Admission** is a period of inpatient care: a Patient, a ward, and a bed or
location. It is separate from an **Encounter** (a visit with a reason and an
end), and an Admission may link the Encounter it came from so the visit and the
stay read as one history
([ADR 0008](docs/adr/0008-admission-separate-from-encounter.md)). A location
move keeps the board honest about where a patient is; a discharge closes the
stay, removes it from the board, and keeps its history.

The **Ward Board** (`GET /api/ward/board`) lists every open Admission ordered by
outstanding work counted from the record: overdue medication doses, then doses
due now, then results awaiting review, then open Tasks, with bed order breaking
ties. The order and the counts are recomputed on every read and stored nowhere.
The board does not score or rank patients clinically.

### Observation chart

Every set of vital signs is an **Observation**: one row per set, charted against
an Encounter or an Admission, never both and never neither. A Patient's chart is
their single time series for vitals, each set stamped with the time and the
Clinical user who took it, and unchangeable once saved. A reading outside its
published adult reference range is marked for display and nothing more — the
system never alters a value, reorders anything on the strength of one, or raises
an alert ([ADR 0010](docs/adr/0010-observation-range-marked-for-display.md)).
The client renders the abnormal mark from the server's `abnormal_fields`; it
never re-derives the thresholds.

### Nursing notes

A **Nursing Note** is written from a fixed **Note Template** — shift
assessment, ward round entry, intervention record, handover entry, discharge
summary — so it starts from a shape rather than a blank page. Templates live in
one module (`backend/app/notes.py`) and are served by
`GET /api/ward/note-templates`; each note stores one row per field, so a
template change needs no schema change and no client change
([ADR 0013](docs/adr/0013-note-templates-are-code.md)). A new note prefills from
the patient's latest Observation, shown with its source. A correction is a new
note that points at the one it corrects; the corrected note stays in the record.

### Medications

A **Medication Order** transcribes an instruction a doctor already gave: drug,
dose, route, frequency, start time, and who instructed it. The clinical fields
are frozen when the order is written, so a change is a stop and a new order and
both stay in the record
([ADR 0011](docs/adr/0011-medication-order-transcribes-instruction.md)). The
system does not calculate a dose, check a dose against a maximum, or check
interactions or allergies.

**Medication Round Times** — the clock times a frequency maps to — are a
documented convention held in one module and shown to the reader, not clinical
advice. The **due list** is derived at read time from the open orders and the
round times and stored nowhere, so it cannot drift.

A **Medication Administration** records one dose from an order as given,
withheld, refused or unavailable. It is append-only, one row per order and due
time, so a slot cannot be recorded twice. A reason is required when the dose was
not given. It records what a nurse attests to — there is no barcode or wristband
verification. An overdue dose is marked and nothing else happens. The round
times are provisional **UTC** clock times in this build (no ward timezone), and
the due list covers scheduled orders only: continuous infusions, variable doses
and as-required medication are out of scope rather than approximated.

### Investigations

An **Investigation** tracks a requested test through four states — requested,
sample taken, result available, reviewed — with a free-text result note recorded
as the laboratory gave it. Marking a result reviewed records who and when, and
is the accountable act. The system never reads a value, never flags an abnormal
result, and never suggests anything from one
([ADR 0012](docs/adr/0012-investigation-tracks-progress-not-interpretation.md)).
Two worklists fall out of the same record: results awaiting review, and tests
awaiting a result.

### Tasks and the ward round

A **Task** is a unit of work raised against an Admission, by hand from a
patient's page or from a saved Ward Round Entry (several at once, because a
round gives several instructions in one conversation). It carries an optional
due time and an optional assignee, so both an assigned caseload and a shared
ward work. A Clinical user marks it done, recording who and when. An overdue
Task is shown as overdue and nothing else happens — it is not escalated,
reassigned or closed by the system.

### Printable sheets

Three sheets print: a **handover sheet** of the ward's patients with the detail
a handover needs, a **medication round sheet** of the doses due in a chosen
window with space to record each one, and a **ward worklist** of outstanding
Tasks and Investigations grouped by patient. Every sheet carries its generation
time and the line "verify against the system", so a stale sheet is recognisable
as stale rather than authoritative
([ADR 0009](docs/adr/0009-runs-alongside-paper-record.md)). `styles/print.css`
drops navigation and controls and forces a light, high-contrast presentation.

### Administrator dashboard

The Administrator role is read-only oversight; the API refuses it every clinical
action. It mounts:

- **Reports** — Daily Visits and Performance over Encounters (arrival volume,
  end throughput, average waiting).
- **Ward Operations** — the ward census and length of stay, the proportion of
  doses recorded on time, the count of results still awaiting review with the
  oldest wait, and Tasks completed against Tasks raised. Every figure is derived
  at read time from stored rows and never stored.
- **Audit log** — the append-only record of clinical mutations, written in the
  same transaction as the act.

### Study instrumentation

A usability study times a participant on a set task, beside the SUS score. The
**study timing** panel (behind `CARESYNC_STUDY_INSTRUMENTATION_ENABLED`, off by
default) offers explicit begin, end and abandon actions. It records a task
label, the start and end instants, and an anonymised participant identifier — it
records a study identifier, never who the participant is, and never joins to a
Patient. A run can be abandoned and is recorded as abandoned rather than as a
very long one. The instrumented figure supports an observer's stopwatch rather
than replacing it, because an interruption the system does not record would make
the timing wrong.

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
allow in `CARESYNC_CORS_ORIGINS`.

The API grants credentialed CORS only to the origins listed in
`CARESYNC_CORS_ORIGINS` (localhost by default). The browser never needs it
because the Vite dev server proxies `/api`; the native shell is genuinely
cross-origin.

For this plain-HTTP development path, the Android manifest permits cleartext
traffic and the iOS `Info.plist` allows local networking. Remove both
allowances when the API is served over HTTPS. The iOS project is generated by
the same config, but building it needs macOS and Xcode.

### Primary screen and session expiry

A Clinical user lands on the Ward board on every surface, web and native; the
view switch exposes Ward board, Intake, Patient history and Study timing. Session
expiry is not reimplemented for mobile: the app shares `api.ts`, so an expired
session produces the same `401 Not authenticated` response and the same
on-screen error as the browser, with no separate mobile session state. Signing
in again resumes work.

### Generated projects

The `android/` and `ios/` platform projects are committed so a clone can be
built without regenerating them. Their own `.gitignore` files exclude copied web
assets (`*/assets/public`), Gradle/Xcode build output, `local.properties`, Pods,
derived data and keystores. `npm run mobile:sync` repopulates the ignored assets
after every client change.

## Run the tests

```powershell
npm test
```

Runs the API suite (`uv run --directory backend pytest`) and then the client
suite (`node --test` over `frontend/src/*.test.ts`, covering API base URL
resolution, platform detection and default clinical view). Use `npm run test:api`
or `npm run test:web` to run either half alone.

The client has no automated test harness, by a deliberate scope decision; the
screens are verified by hand. [`MANUAL-CHECKLIST.md`](MANUAL-CHECKLIST.md) is the
smoke and manual script for a fresh stack — run it before a demonstration, a
study session or a release.

## Postgres demo path

The Compose file provisions Postgres only; the API and client still run as
normal processes. This path is documented but is not exercised by the local
test suite (see ADR 0001).

```powershell
docker compose up -d db
$env:CARESYNC_DATABASE_URL = "postgresql+psycopg://caresync:caresync@127.0.0.1:5432/caresync"
npm run dev
```

In bash, use `export CARESYNC_DATABASE_URL=...` instead. To stop Postgres:

```powershell
docker compose down
```

## Schema changes and operator notes

This build has **no migration tool**. `Base.metadata.create_all` runs at API
startup and only creates missing tables — it does **not** alter an existing
table or its constraints. Two consequences bite an existing database:

- New tables (from the ward tickets) are created in place.
- The `audit_log` action `CHECK` constraint cannot be widened in place, so a
  database created before a ticket that adds an audit action rejects the new
  writes. The `patients` unique indexes changed with the hospital number, and
  `observations`/`admissions` arrived with the chart.

For an existing local `backend/caresync.db`, **back it up first**, then recreate
and reseed (`npm run seed`, or just `npm run dev`) so the schema is rebuilt from
the current models. For the Postgres demo, migrate by hand or recreate the
database. These are manual operator steps, not an implemented migration.

Audit actions have grown across tickets: `admit_patient`, `move_admission`,
`discharge_patient`, `chart_observation`, `write_nursing_note`,
`correct_nursing_note`, `raise_task`, `complete_task`, `assign_task`,
`record_medication_order`, `stop_medication_order`,
`record_medication_administration`, `record_investigation`,
`record_investigation_sample`, `record_investigation_result`,
`review_investigation`. Each is a value of the `AuditAction` enum in
`backend/app/audit_actions.py`, which is the one source of truth for the set and
its human labels.

## Environment variables

All variables use the `CARESYNC_` prefix. A `.env` file in `backend/` is
also read.

| Variable                                   | Default                   | Purpose                                      |
| ------------------------------------------ | ------------------------- | -------------------------------------------- |
| `CARESYNC_DATABASE_URL`                    | `sqlite:///./caresync.db` | SQLAlchemy URL; Postgres URL for the demo    |
| `CARESYNC_SESSION_TTL_SECONDS`             | `14400` (4 hours)         | Session lifetime, enforced on every request  |
| `CARESYNC_SESSION_IDLE_SECONDS`            | `300` (5 minutes)         | Inactivity lock: a session idle this long is refused until unlocked |
| `CARESYNC_SESSION_HEARTBEAT_SECONDS`       | `60`                      | How often a request refreshes the session's last-seen instant |
| `CARESYNC_SESSION_UNLOCK_MAX_ATTEMPTS`     | `5`                       | Wrong unlock passwords before the session is rate-limited |
| `CARESYNC_SESSION_UNLOCK_LOCKOUT_SECONDS`  | `60`                      | How long a locked session refuses further unlock attempts |
| `CARESYNC_SESSION_COOKIE_NAME`             | `caresync_session`        | Session cookie name                          |
| `CARESYNC_SESSION_COOKIE_SECURE`           | `false`                   | Set `true` when served over HTTPS. See "Security behaviour" |
| `CARESYNC_CORS_ORIGINS`                    | localhost origins         | Comma-separated origins granted credentialed CORS (the native shell) |
| `CARESYNC_SEED_DEMO_USERS`                 | `false`                   | Seed demo users during API startup           |
| `CARESYNC_STUDY_INSTRUMENTATION_ENABLED`   | `false`                   | Surface the study timing panel and its routes; off for normal ward use |

`CARESYNC_SESSION_COOKIE_SECURE` must not be set to `true` without HTTPS:
see "Security behaviour" for why it silently breaks sign-in otherwise.

## API surface

| Method | Path                                    | Access        |
| ------ | --------------------------------------- | ------------- |
| POST   | `/api/auth/login`                       | Public        |
| GET    | `/api/auth/me`                          | Authenticated |
| POST   | `/api/auth/logout`                      | Public        |
| POST   | `/api/auth/lock`                        | Authenticated |
| POST   | `/api/auth/unlock`                      | Public        |
| POST   | `/api/auth/switch-user`                 | Public        |
| POST   | `/api/auth/password`                    | Authenticated |
| GET    | `/api/roles`                            | Public        |
| GET    | `/api/clinical/access`                  | Clinical      |
| POST   | `/api/clinical/patients`                | Clinical      |
| GET    | `/api/clinical/patients`                | Clinical      |
| GET    | `/api/clinical/patients/{id}/encounters` | Clinical     |
| GET    | `/api/clinical/patients/{id}/observations` | Clinical   |
| POST   | `/api/clinical/patients/{id}/hospital-number` | Clinical |
| POST   | `/api/clinical/encounters`              | Clinical      |
| GET    | `/api/clinical/encounters`              | Clinical      |
| GET    | `/api/clinical/encounters/{id}`         | Clinical      |
| PUT    | `/api/clinical/encounters/{id}/intake`  | Clinical      |
| POST   | `/api/clinical/encounters/{id}/end`     | Clinical      |
| POST   | `/api/clinical/encounters/{id}/observations` | Clinical |
| POST   | `/api/clinical/admissions/{id}/observations` | Clinical |
| POST   | `/api/clinical/study-task-runs`         | Clinical      |
| PATCH  | `/api/clinical/study-task-runs/{id}/end` | Clinical     |
| PATCH  | `/api/clinical/study-task-runs/{id}/abandon` | Clinical |
| GET    | `/api/clinical/study-task-runs`         | Clinical      |
| POST   | `/api/ward/admissions`                  | Clinical      |
| GET    | `/api/ward/admissions`                  | Clinical      |
| POST   | `/api/ward/admissions/{id}/move`        | Clinical      |
| POST   | `/api/ward/admissions/{id}/discharge`   | Clinical      |
| GET    | `/api/ward/board`                       | Clinical      |
| GET    | `/api/ward/medications/round-times`     | Clinical      |
| GET    | `/api/ward/medications/due`             | Clinical      |
| GET    | `/api/ward/medication-administration-reasons` | Clinical |
| GET    | `/api/ward/admissions/{id}/medication-orders` | Clinical |
| POST   | `/api/ward/admissions/{id}/medication-orders` | Clinical |
| POST   | `/api/ward/medication-orders/{id}/stop` | Clinical      |
| POST   | `/api/ward/medication-orders/{id}/administrations` | Clinical |
| GET    | `/api/ward/medication-orders/{id}/administration-grid` | Clinical |
| GET    | `/api/ward/admissions/{id}/medication-administrations` | Clinical |
| GET    | `/api/ward/note-templates`              | Clinical      |
| GET    | `/api/ward/admissions/{id}/note-prefill` | Clinical     |
| GET    | `/api/ward/admissions/{id}/notes`       | Clinical      |
| POST   | `/api/ward/admissions/{id}/notes`       | Clinical      |
| GET    | `/api/ward/staff`                       | Clinical      |
| GET    | `/api/ward/tasks`                       | Clinical      |
| GET    | `/api/ward/admissions/{id}/tasks`       | Clinical      |
| POST   | `/api/ward/admissions/{id}/tasks`       | Clinical      |
| POST   | `/api/ward/admissions/{id}/ward-round-tasks` | Clinical |
| POST   | `/api/ward/tasks/{id}/complete`         | Clinical      |
| POST   | `/api/ward/tasks/{id}/assign`           | Clinical      |
| POST   | `/api/ward/admissions/{id}/investigations` | Clinical   |
| GET    | `/api/ward/admissions/{id}/investigations` | Clinical   |
| GET    | `/api/ward/investigations/awaiting-review` | Clinical    |
| GET    | `/api/ward/investigations/awaiting-result` | Clinical    |
| POST   | `/api/ward/investigations/{id}/sample-taken` | Clinical |
| POST   | `/api/ward/investigations/{id}/result`  | Clinical      |
| POST   | `/api/ward/investigations/{id}/review`  | Clinical      |
| GET    | `/api/administrator/access`             | Administrator |
| GET    | `/api/administrator/audit-log`          | Administrator |
| GET    | `/api/administrator/reports/daily-visits` | Administrator |
| GET    | `/api/administrator/reports/performance` | Administrator |
| GET    | `/api/administrator/reports/ward-census` | Administrator |
| GET    | `/api/administrator/reports/length-of-stay` | Administrator |
| GET    | `/api/administrator/reports/medication-timeliness` | Administrator |
| GET    | `/api/administrator/reports/investigation-review` | Administrator |
| GET    | `/api/administrator/reports/task-completion` | Administrator |

The `/access` routes are role-gated demonstration surfaces; authorisation is
enforced at the API boundary. A wrong Role receives `403`; an unauthenticated
request receives `401`. The study-task-run routes additionally require
`CARESYNC_STUDY_INSTRUMENTATION_ENABLED` and return `403` when it is off.

`GET /api/clinical/encounters` is a recency list for reviewing saved work —
newest arrival first, `?limit=` up to 100.

`GET /api/clinical/patients` searches Patients by name, contact number or
hospital number, `?q=` plus `?limit=` up to 100. A blank or whitespace-only
query returns nothing, so the view cannot be used to list every Patient. Search
is a discovery aid and is deliberately looser than the identity rule
`find_or_create_patient` applies: a name is enough to *find* a Patient, never to
*match* one.

`GET /api/administrator/audit-log` is the append-only record of clinical
mutations, each naming its actor; `?encounter_id=` narrows it to one Encounter.
See [ADR 0007](docs/adr/0007-audit-log.md).

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

### Shared-device session lock

A ward tablet is picked up by whoever is nearest, so a session has to stop
showing patient data when the last person walks away. That is the inactivity
lock, and it is enforced on the server, not only in the client.

- After `CARESYNC_SESSION_IDLE_SECONDS` with no request (5 minutes by
  default), the session is locked. The next request, including a background
  poll, is refused with **423 Locked**, distinct from 401, so the client shows
  the lock screen rather than the sign-in screen.
- Locking does **not** end the session. The `sessions` row and the cookie
  survive, and unlocking is a password check on that same session
  (`POST /api/auth/unlock`), not a fresh sign-in. The token is unchanged.
- A locked session is refused by every authenticated route, not just
  `/api/auth/me`. The client's lock screen hides patient data, but the refusal
  is the server's; a hidden screen on its own would not survive a request made
  with a tool.
- `POST /api/auth/lock` locks deliberately, for a handover that should not
  wait for the timer. `POST /api/auth/switch-user` signs out and returns to
  sign-in, for handing the tablet to a different person.
- Unlock attempts are rate-limited on the session row: after
  `CARESYNC_SESSION_UNLOCK_MAX_ATTEMPTS` wrong passwords (5 by default),
  further attempts are refused with **429 Too Many Attempts** for
  `CARESYNC_SESSION_UNLOCK_LOCKOUT_SECONDS` (60 by default). This stops a
  locked tablet being used as an unattended guessing surface.
- The session lifetime (`CARESYNC_SESSION_TTL_SECONDS`, 4 hours by
  default) is the outer bound on a token, a backstop behind the lock rather
  than the day's working hours. A token that escapes the lock (a restored tab,
  a copied cookie) dies within half a shift.

The lock is evaluated when a request arrives. There is no scheduled job and no
background task, consistent with the rule that the system never acts on a
timer.

### The secure cookie needs HTTPS

`CARESYNC_SESSION_COOKIE_SECURE` defaults to `false` because local
development and the test suite run over plain HTTP. It must be set to `true`
for the deployment, and the deployment must serve the API over **HTTPS**
through a reverse proxy.

A `Secure` cookie is sent only over an encrypted connection, so the browser
withholds it over plain HTTP. If this flag is turned on against a plain-HTTP
deployment, the cookie is never sent back and sign-in appears to do nothing:
the request succeeds, the session row is written, and every following request
looks unauthenticated. That failure is silent and easy to misread as a login
bug. Enable HTTPS and the reverse proxy first, then set the flag. HTTPS is a
go-live prerequisite, not something this code provides.

## Layout

```
capacitor.config.ts    native shell config; webDir is frontend/dist
android/               Capacitor Android project (committed; build output ignored)
ios/                   Capacitor iOS project (committed; build output ignored)
backend/
  app/
    main.py            app factory, router wiring, startup seeding, CORS
    config.py          Settings (CARESYNC_* env vars)
    db.py              engine and session factory
    models.py          User, UserSession, Role, Patient, Encounter, Admission,
                       Observation, NursingNote/Field, MedicationOrder,
                       MedicationAdministration, Task, Investigation,
                       AuditEntry, StudyTaskRun
    schemas.py         request/response models
    patients.py        Patient matching rule and find-or-create
    intake.py          whether an Encounter's reason may be corrected
    admissions.py      Admission open/discharge status
    departures.py      end-of-visit and awaiting-Encounter guard
    observations.py    charting a set and rendering the chart
    notes.py           the Note Template vocabulary and prefill
    medications.py     the round-time convention and the due list
    administrations.py the outcome/reason sets and slot recording
    tasks.py           raising, completing and assigning Tasks
    investigations.py  the four states and the two worklists
    audit_actions.py   the fixed Audit action set and labels (one source of truth)
    audit.py           appending audit entries and reading the log
    reports.py         read-only Reports derived on demand from stored records
    security.py        argon2 hashing, session token hashing
    session_lock.py    inactivity lock and unlock rate limiting (session row)
    timeutils.py       UTC helpers
    deps.py            get_current_session, get_current_user, require_role
    seed.py            demo Clinical and Administrator users
    routers/
      auth.py          login, me, lock, unlock, switch-user, logout,
                       change-own-password
      meta.py          the two Roles
      clinical.py      Patient registration, encounters, Observations, study runs
      ward.py          Admissions, board, medications, notes, tasks, investigations
      administrator.py Audit log, access surface and Reports
  tests/               API-level pytest suite (SQLite)
frontend/
  src/
    App.tsx            session check, Role landing route, surface switch
    LoginScreen.tsx    login form; native Server setting
    LockScreen.tsx     the inactivity lock screen; unlock or switch user
    routing.ts         Role landing paths and path routing
    ClinicalWorkspace.tsx  Ward board / Intake / Patient history / Study timing switch
    WardBoard.tsx      live ward board, admissions, and per-patient disclosures
    ObservationChart.tsx  one Patient's Observation time series and chart form
    NursingNotes.tsx   note writer from a template, with prefill and corrections
    MedicationOrders.tsx  order writer, due list and administration grid
    Investigations.tsx investigations writer and the two chase lists
    TaskList.tsx       cross-patient Tasks and per-patient task writer
    PrintSheets.tsx    the three printable sheets and their launcher
    StudyInstrumentation.tsx  study timing panel (begin/end/abandon)
    PatientHistoryScreen.tsx  Patient search and one Patient's Encounters over time
    AdministratorDashboard.tsx  Reports, Ward Operations and the Audit Log
    AdministratorReports.tsx    Daily Visits and Performance
    WardOperationsDashboard.tsx census, length of stay, timeliness, review, tasks
    IntakeScreen.tsx   Clinical intake and recent Encounters
    IntakeFields.tsx   the shared Observation field set
    Shell.tsx          post-login shell, role badge, password change
    api.ts             typed fetch wrapper; absolute URL in the native shell
    design.ts          shared BoardUI class vocabulary for this client
    brand.tsx          logo mark
    queueDisplay.ts    shared formatting; sex labels; vital-reading rows
    usePolling.ts      shared poll-on-interval and poll-on-focus hook
    platform.ts        Capacitor platform mapping, default clinical view
    runtime.ts         Capacitor platform detection
    runtimeConfig.ts   API base URL resolution and device override
    *.test.ts          node:test suites for the modules above
  styles/
    globals.css        Tailwind entry, dark-mode strategy, base reset
    theme.css          semantic colour tokens (light and dark)
    typography.css     the composite type utilities
    brand.css          the teal brand re-tint
    print.css          @media print rules for the printable sheets
docs/
  adr/                 decision records 0001–0014
  archive/             removed-subsystem documents (triage era) behind a header
  agents/              issue-tracker and domain-doc consumer rules
MANUAL-CHECKLIST.md    the smoke and manual test script for a fresh stack
```

There is no migration tool. Tables are created at API startup; deleting
`backend/caresync.db` resets the local database.

# CareSync

CareSync is a nursing workflow management system for a private hospital ward. It
is presented through one responsive client codebase — a ward surface for clinical
staff and a read-only operations dashboard for administrators — with a Capacitor
shell so the same build runs on a shared tablet.

This build covers the walking skeleton: the HTTP API, the React client,
authentication and its shared-device session lock, the two Roles, Patient
registration and matching, a visit record that carries a reason for the visit
only, the append-only Audit Log, and the read-only Administrator Reports. It does
not score urgency, recommend a level or order a queue. The ward features —
Admissions and the Ward Board, the Observation chart, Nursing Notes, Medication
Orders and administrations, Investigations, Tasks, handover printing and the
operations dashboard — are not built yet (tickets 29–40).

Vocabulary follows [`CONTEXT.md`](CONTEXT.md). The data-layer decision is
[ADR 0001](docs/adr/0001-sqlite-local-postgres-production.md): SQLite for local
development and tests, Postgres for the demonstration deployment.

> **Obsolete sections — triage era.** The sections marked **Obsolete** below
> (**Intake**, **Symptom Groups**, **Prioritization Engine and the Queue**,
> **Override**, **Departure**, **Re-assessment**, **Administrator dashboard**,
> **Reports**, **API surface** and **Layout**) describe the triage system that
> tickets 25 and 26 removed — the Prioritization Engine, the Queue, Override,
> Re-assessment, Symptom Groups and the Accuracy Evaluation. Their endpoints,
> fields and settings (including the `CARESYNC_FALLBACK_PROVIDER_*` variables)
> no longer exist, so they are history rather than instructions for the current
> build. A full documentation pass (ticket 41) will rewrite them; the setup,
> environment, security and mobile sections remain current.

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

> **Operator note — ticket 29.** Ticket 29 adds a `hospital_number` column to
> the `Patients` table and changes its unique indexes. There is no migration
> tool, and `create_all` only creates missing tables — it never alters an
> existing one — so a `backend/caresync.db` created before ticket 29 still
> carries the old schema and the API will not run against it. Preserve that file
> first: back it up (copy it aside), then let a freshly seeded database be
> created with `npm run seed`. Do not run on the old schema, and do not remove
> an existing `caresync.db` without taking that backup first.

> **Operator note — ticket 30.** Ticket 30 adds the ward tables — `Observations`
> and `Admissions` — and its chart API writes to them. An existing
> `backend/caresync.db` has neither table, and, more seriously, its `audit_log`
> carries a `CHECK` constraint on `action` whose allowed set excludes
> `chart_observation`. `create_all` only creates missing tables; it never alters
> an existing table or its constraints, so it will not upgrade that `CHECK`, and
> any chart write will fail against the old `audit_log`. Preserve and back up the
> current file, then reseed a fresh database with `npm run seed` before running
> the new chart API. The Postgres schema has the same problem — the same
> constraints are baked in — so it likewise needs a recreate or an explicit
> migration before the chart API will run.

## Intake

> **Obsolete — triage era.** The intake fields and the frozen-Assessment
> behaviour below were removed by ticket 26. A visit now carries a reason for the
> visit only, corrected with `PUT /api/clinical/encounters/{id}/intake`. Kept as
> history pending ticket 41.

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
| Respiratory rate           | 0–80 breaths/min               |
| Blood pressure             | systolic 50–300, diastolic 20–200, systolic above diastolic |
| Oxygen saturation          | 50–100 %                       |
| Notes                      | optional, up to 2000 characters |

`arrived_at` is written when the Encounter is opened and cannot be changed
afterwards; the Encounter itself is never updated, only its intake. Intake is
complete as soon as the Encounter exists, so opening an Encounter also creates
its first Triage Assessment in the same transaction. A later correction attempt
therefore returns `409 Conflict`: the Assessment's snapshot is the durable record
of what the recommendation was made from. To capture a changed condition, use a
Re-assessment (below), which appends a new Assessment instead of rewriting an
old one. See `backend/app/intake.py`.

## Symptom Groups

> **Obsolete — triage era.** Symptom Group recognition fed the classifier and
> was removed with it (ticket 26); the vocabulary file and its module no longer
> exist. Kept as history pending ticket 41.

The free-text presenting complaint is mapped onto the finite Symptom Group
vocabulary in `backend/app/symptom_groups.json`, versioned there as
`1.0.0`. Each entry records whether it was anchored on an ESI v4 red flag or
added as a common presentation. The list is data, not code: recognition is
spaCy entity extraction with the vocabulary installed as an `EntityRuler` over
`en_core_web_sm` (`backend/app/symptom_groups.py`), so a group is recognised
only when its exact canonical phrase occurs in the complaint.

There is no synonym table, no lemmatisation, no stemming and no inference.
"Heart attack" is not *chest pain*; "no chest pain" is still *chest pain*; and
the longer phrase wins an overlap, so "vomiting blood" does not also report
"vomiting". Negation is not interpreted. The recognised groups are shown on the
expanded card precisely so a misreading of the text is visible to the Clinical
user; the card says "None recognised" when the complaint matched nothing.

Recognition runs once, inside `create_triage_assessment`, and the result is
frozen into the Assessment with the rest of its inputs. No groups is stored as
an empty string, which is distinguishable from having recognised one. The
recognised groups are dimensions of the classifier's feature vector, so
recognition feeds the recommendation; the shipped interim artefact gives them a
zero coefficient only because its training source records no complaints, which
the artefact declares under `training.constant_features`.

The first `uv sync` downloads spaCy and the `en_core_web_sm` wheel from GitHub
releases, so it needs network access.

## Prioritization Engine and the Queue

> **Obsolete — triage era.** This whole section, and its "Reading the Queue
> board", "Red-flag safety layer" and "Cached fallback" subsections, describe the
> Prioritization Engine and the Queue that ticket 26 removed. No urgency level is
> computed and no queue is ordered, and none of the settings named here (the
> `CARESYNC_FALLBACK_PROVIDER_*` variables in particular) exist. Kept as history
> pending ticket 41.

The engine boundary (Seam B) is `app.prioritisation.recommend`: a pure function
taking a `PrioritisationInputs` and returning exactly one `UrgencyLevel`, with no
session and no database. It is called directly by
`backend/tests/test_prioritisation.py`.

Measured against the Emergency Severity Index it is scored on, the engine
implements three of ESI's four decision points — A (life-saving need) and B
(high-risk presentation) through the safety layer and the classifier's features,
and D (danger-zone vitals) through the cited red flags — and substitutes the
trained classifier for **C (projected resource categories)**, which it does not
collect. That substitution is why the middle tier is the hardest to get right;
the reasoning is in [`docs/archive/prioritisation-in-context.md`](docs/archive/prioritisation-in-context.md).

Since ticket 06 the boundary is backed by a **trained supervised classifier**, a
multinomial logistic regression over a structured feature vector. The vector is
built by `app.features.build_feature_vector` from recognised Symptom Groups,
pain level, illness duration, age and the five vitals; the free-text complaint
is never a feature. One definition of the vector serves both training and
inference, so a model can never be trained on a different vector from the one it
is asked to score.

The artefact is `backend/models/urgency-classifier-v1.1.0.json` — standardisation
constants, one coefficient row per Urgency Level, the dataset identity, the
vocabulary version and the cross-validated scores, all in one small, readable
file. Inference is a softmax over the non-zero coefficients per class: the
training source records no pain level, illness duration, complaint or respiratory
rate, so only age and four of the vitals carry weight — deterministic,
microseconds, no I/O after the first call (the loader is cached), so the
three-second budget is met many times over.

Training data is the CC0 Harvard Dataverse three-level triage dataset
(DOI 10.7910/DVN/7SOYC7). It is an **interim development artefact**: the source
records no pain level, illness duration, complaint or respiratory rate, so those
dimensions carry a zero coefficient, and 5-fold accuracy (0.42) is below the
majority-class baseline (0.53). The credentialed primary dataset the spec names
supplies exactly those dimensions.
Provenance, licences, the fetch command and the known gaps are in
`backend/evaluation/datasets/README.md`; regenerate the artefact with:

```powershell
cd backend
uv run python -m evaluation.train_classifier
```

Tickets 07 and 08 add the red-flag safety layer and the cached fallback behind
the same boundary. Both are now in place.

### Reading the Queue board

The board orders by Final Decision (urgency) and then arrival time, and says so
in its header: a long-waiting Low legitimately sits below a shorter-waiting
Medium, which otherwise reads as a bug.

The waiting figure is the loudest element on a card once it passes its band —
routine under 4h, long at 4h, breach at 12h, critical at 24h — and past a day it
is expressed in days, because `147h 19m` does not read as six days. Escalation is
carried by size and weight as well as colour, so it survives colour blindness.

**These bands are presentation only.** They never reorder the Queue and never
change a stored Urgency Level; automatic re-triage and time-based escalation are
out of scope. The rationale and the trade-off are in
[ADR 0006](docs/adr/0006-escalate-wait-display-not-decision.md).

### Red-flag safety layer

`app.red_flags` is the deterministic layer that runs **after** the classifier
and can only raise a recommendation to High. It can never lower one, and a
presentation with no firing rule is returned exactly as the classifier produced
it. Twenty red-flag rules cover ESI danger-zone vitals (oxygen saturation, the
age-banded heart-rate thresholds, infant fever), two adult blood-pressure
extremes, and recognised symptoms such as chest pain, stroke signs, altered
mental status, seizure, suicidal ideation, major haemorrhage, anaphylaxis,
overdose, head injury, neck stiffness, vaginal bleeding and syncope.

Each rule carries a clinical citation to ESI v4 and, where it implements the
same criterion, to the independent rubric in
`backend/evaluation/RUBRIC.md`. The full rule table, its citations and the
deliberate limits of the layer are in
[`docs/archive/red-flag-safety-layer.md`](docs/archive/red-flag-safety-layer.md). The limits are
real: it is not a full ESI rule engine, it does not count resources or see
respiratory rate/mental status, and a pain-only presentation can still be
under-triaged because the handbook's severe-pain criterion needs a clinician's
judgement that the engine does not receive.

The layer is pure and deterministic like the classifier, and iterating twenty
predicates is microseconds, so the three-second budget holds. The composed
result is the Machine Recommendation stored on the Assessment and the level the
Queue orders by.

Each rule also names the intake fields it keys on, and the API exposes every
fired rule on the Assessment. So a Queue card can show **why** a presentation
reached High — the rule's finding and its citation — and mark the exact vital
that fired. The flags are re-derived server-side from the Assessment's frozen
snapshot with the same rules the layer ran, so the explanation can never drift
from the recommendation; the client holds no copy of the thresholds.

### Cached fallback for unrecognised complaints

A complaint that recognises no Symptom Group still receives a Machine
Recommendation through a pluggable fallback provider (`app.fallback`). A
matched complaint never takes this path. The provider's answer is cached in the
`fallback_cache` table by a SHA-256 of the complaint text, so identical wording
returns an identical result and a cache hit survives a restart; the safety layer
still runs over the cached answer, because the same words can belong to a
patient with different vitals.

No provider URL is configured by default. That is the unavailable path, not a
crash: a failure or a timeout resolves to the safety layer over **Medium** and
the Assessment is marked `unclassified`. The normal runtime provider is an
HTTP service configured by `CARESYNC_FALLBACK_PROVIDER_URL` (optional
`..._API_KEY`, `..._TIMEOUT_SECONDS`); the build and test suite need no key,
network or paid service. The unclassified state is rendered as its own
violet **Unclassified** badge, separate from the orange **Override** badge.
Details, the timeout policy and the evaluation notes are in
[`docs/archive/cached-fallback.md`](docs/archive/cached-fallback.md).

The Queue is a sort over awaiting Encounters, not a stored sequence: Urgency
Level first (High, Medium, Low), then arrival time, so equally urgent Encounters
are first-in-first-out. The level that governs is the latest Triage Assessment's
Final Decision, which starts equal to the Machine Recommendation and moves only
through an Override or a Re-assessment. An Encounter is awaiting while
`departed_at` is null and departed once its Departure instant is set; those two
are the only conditions in scope. `waiting_seconds` is derived from `arrived_at`
at read time.

The client polls `GET /api/clinical/queue` every five seconds and on window
focus, so a change to a Final Decision or a Departure appears without a manual
refresh. `QueueBoard.tsx` renders compact cards — urgency colour, Patient name,
short complaint, time waiting — and expands to the full vitals, pain level,
duration, the Symptom Groups recognised from the complaint, notes, the
Re-assessment form, the Override form, and the Depart action.

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

A Clinical user lands on Intake on every surface, web and native; the view switch
exposes Intake and Patient history.
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
## Override

> **Obsolete — triage era.** Override was removed with the Prioritization Engine
> (ticket 26); `override_reasons.py`, the `overrides` table and the `/override`
> route no longer exist. Kept as history pending ticket 41.

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
own state, separate from the unclassified flag that ticket 08 added beside it. The
Administrator's dense table shows the same fact as "Differs" and needs no change,
because it already compares the two stored values. The Queue reorders on the
next poll, since it sorts on Final Decision.

## Departure

> **Obsolete — triage era.** Departure was removed by ticket 26 and replaced by
> an end-of-visit action: `POST /api/clinical/encounters/{id}/end`, with
> `ended_at` and a `status` of `open` or `ended` rather than
> `awaiting`/`departed`. Kept as history pending ticket 41.

A Clinical user discharges an awaiting Encounter from the Queue:

```http
POST /api/clinical/encounters/{id}/departure
```

The request carries no body. The departure instant is the server's clock at the
moment of the action and is never accepted from the caller; every departed
Encounter therefore has one. The response is the Encounter with `departed_at`
set and `status` reading `departed`.

Departure is manual only: no timer, background job or cascade departs an
Encounter, and one that arrived days ago is still awaiting until someone acts.
The Queue is a read that filters on `departed_at`, so the Encounter leaves the
awaiting board on the very next poll with no extra refresh mechanism.

`status` (`awaiting` or `departed`) is derived from `departed_at`, not stored in
a second column, so the condition and the instant cannot disagree. A departed
Encounter is still readable in full — Patient, intake, Triage Assessments and
Overrides — through `GET /api/clinical/encounters/{id}`, and it stays in the
recency list. Clinical actions that need an awaiting Encounter are refused with
`409`: both an Override and a Re-assessment say so in their own terms through
the same shared guard. Departing twice is refused with `409` and does not
overwrite the first instant.

## Re-assessment

> **Obsolete — triage era.** Re-assessment and the `TriageAssessment` record
> were removed by ticket 26. Kept as history pending ticket 41.

A Clinical user may ask for a fresh Triage Assessment on an awaiting Encounter:

```http
POST /api/clinical/encounters/{id}/reassessment
{
  "presenting_complaint": "Chest pain, worse on exertion",
  "pain_level": 9,
  ...
}
```

The request carries the intake captured now — the Encounter's condition may have
changed — and the server appends a new Assessment with its own Machine
Recommendation. Re-assessment is manual only: there is no timer, scheduled
re-evaluation, time-based escalation or background job, and reading the Queue
never creates an Assessment.

The new row records `supersedes_assessment_id`, the Assessment that was
governing until it arrived, so the whole sequence is reconstructable from the
rows. Nothing earlier is edited: every previous Assessment keeps its snapshot,
its Machine Recommendation and its Overrides. `GET /api/clinical/encounters/{id}`
returns `assessment` (the governing, most recent one) alongside `assessments`
(the history, oldest first).

The Queue sorts on the **latest** Assessment's Final Decision. So if Assessment A
was Overridden to Low and a Re-assessment then recommends High, the Encounter
sits where that new decision puts it, not where the old Override did. An Override
on a superseded Assessment is refused with `409`, because only the governing
Assessment can move the Encounter.

## Administrator dashboard

> **Obsolete — triage era.** The dense awaiting-Queue table described here was
> removed by ticket 26; the Administrator dashboard now mounts the Reports and
> the Audit Log only. Kept as history pending ticket 41.

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
user in the same way. The dashboard ends with a Reports section, described
below, with the Accuracy Evaluation first and visually featured.

## Reports

> **Obsolete — triage era.** Only two Reports survive — Daily Visits
> (`GET /api/administrator/reports/daily-visits`) and Performance
> (`GET /api/administrator/reports/performance`). The Priority Distribution and
> the Accuracy Evaluation described below were removed by tickets 25 and 26.
> Kept as history pending ticket 41.

The four Reports are read-only. Each is computed inside the request from the
rows that record what happened — arrival and departure instants on the
Encounter, and its Triage Assessment rows — never from a stored snapshot and
never from the live Queue. Nothing is cached, so changing a record changes the
next Report and reverting the record reverts the figure; no Report write creates
a row or performs a clinical action. An Encounter's *governing* Assessment is
its highest-id one, matching the Queue, so a Re-assessment is reflected without
counting the Encounter twice.

A **day** is one UTC calendar day, half-open: `[00:00, next 00:00)`. The Daily
Queue Report takes an optional `?day=YYYY-MM-DD` and otherwise uses the server's
current UTC day.

- **Daily Queue** (`GET /api/administrator/reports/daily-queue`) — *volume* is
  Encounters that arrived on the day; *throughput* is Encounters that departed
  on the day, even if they arrived earlier; *awaiting* is the day's arrivals
  that still have no departure instant.
- **Priority Distribution**
  (`GET /api/administrator/reports/priority-distribution`) — one count per
  Encounter at the Urgency Level of its governing Assessment's Final Decision,
  across every stored Encounter, including departed and re-assessed ones.
- **Performance** (`GET /api/administrator/reports/performance`) — over departed
  Encounters only, because only they have a departure instant. *Waiting time* is
  arrival to departure, the whole Encounter; *processing time* is the governing
  Assessment to departure, the part of the stay after the urgency decision
  existed. The Report returns each departed Encounter's two figures and their
  averages.
- **Accuracy Evaluation**
  (`GET /api/administrator/reports/accuracy-evaluation`) — the flagship view.
  It joins each stored Assessment's immutable Machine Recommendation to an
  independent ground-truth Urgency Level from a labelled evaluation run, and
  reports the 3×3 confusion matrix, per-level precision and recall, separate
  False High-Priority and False Low-Priority rates, the Override rate and
  reason distribution, and fallback coverage as its own statistic. An Override
  can never move a matrix cell. With no labelled run the view shows an explicit
  empty state rather than a flattering zero. Definitions and the run manifest
  contract are in
  [`docs/archive/accuracy-evaluation-report.md`](docs/archive/accuracy-evaluation-report.md).

  To make the Report read stored, immutable Assessments rather than a file,
  materialise the rubric-labelled corpus through the real engine (from
  `backend/`):

  ```powershell
  uv run python -m evaluation.materialise
  ```

  Each evaluation Assessment keeps the rubric label in its own
  `ground_truth_level` column; those rows are excluded from the Queue and from
  the activity and performance Reports, and take precedence when present. The
  offline harness artefact remains the fallback source.

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
$env:CARESYNC_DATABASE_URL = "postgresql+psycopg://caresync:caresync@127.0.0.1:5432/caresync"
npm run dev
```

In bash, use `export CARESYNC_DATABASE_URL=...` instead. To stop Postgres:

```powershell
docker compose down
```

## Schema changes (ticket 31)

After ticket 30, `audit_log` gained a nullable `admission_id` column (with its
foreign key) and a widened allowed-action set covering the ward actions
(`admit_patient`, `move_admission`, `discharge_patient`). This build has **no
migration tool**, and `Base.metadata.create_all` only creates missing tables —
it does **not** alter an existing one. A database created before this change
keeps the old `audit_log` shape and its old action check, and will reject the
new writes.

- **Local SQLite** — back up `caresync.db` first, then recreate it and reseed
  (`npm run seed`, or just `npm run dev`) so the schema is rebuilt.
- **Postgres demo** — the schema is not upgraded in place; migrate `audit_log`
  by hand or recreate the database before running this build.

No migration is implemented; the steps above are the manual operator work.

### Ticket 32 — nursing notes

Ticket 32 adds the `nursing_notes` and `nursing_note_fields` tables plus two more
audit actions (`write_nursing_note`, `correct_nursing_note`). `create_all` builds
the new tables, but it still cannot widen the SQLite `audit_log` action `CHECK`,
so a database created before this change rejects the new writes with the same
failure described above.

- **Local SQLite** — back up `caresync.db`, then recreate and reseed
  (`npm run seed`, or just `npm run dev`), or widen the check with an explicit
  migration.
- **Postgres demo** — `nursing_notes` and `nursing_note_fields` may be created in
  place, but `audit_log` needs the same hand migration or a database rebuild.

### Ticket 33 — tasks

Ticket 33 adds the `tasks` table and three more audit actions (`raise_task`,
`complete_task`, `assign_task`). As before, `create_all` builds the new table but
cannot widen the SQLite `audit_log` action `CHECK`, so a database created before
this change rejects the new writes with the same failure described above.

- **Local SQLite** — back up `caresync.db`, then recreate and reseed
  (`npm run seed`, or just `npm run dev`), or widen the check with an explicit
  migration, before the API uses it.
- **Postgres demo** — `tasks` may be created in place, but `audit_log` needs the
  same hand migration or a database rebuild.

Marking a Task overdue is display-only: a Task past its due time is shown as
overdue and nothing else happens — it is not escalated, reassigned or closed by
the system, so this is not migration work.

### Ticket 34 — medication orders

Ticket 34 adds the `medication_orders` table and two more audit actions
(`record_medication_order`, `stop_medication_order`). As before, `create_all`
builds the new table but cannot widen the SQLite `audit_log` action `CHECK`, so a
database created before this change rejects the new writes.

- **Local SQLite** — back up `caresync.db`, then recreate and reseed
  (`npm run seed`, or just `npm run dev`), or widen the check with an explicit
  migration, before the API uses it.
- **Postgres demo** — `medication_orders` may be created in place, but
  `audit_log` needs the same hand migration or a database rebuild.

Two provisional limits are built in, not migration work: round times are
provisional **UTC** clock times (this build carries no ward timezone), and
as-required (PRN) medication, continuous infusions and variable-dose medication
are out of scope for the due list.

### Ticket 35 — medication administrations

Ticket 35 adds the `medication_administrations` table and one more audit action
(`record_medication_administration`). As before, `create_all` builds the new
table but cannot widen the SQLite `audit_log` action `CHECK`, so a database
created before this change rejects the new writes.

- **Local SQLite** — back up `caresync.db`, then recreate and reseed
  (`npm run seed`, or just `npm run dev`), or widen the check with an explicit
  migration, before the API uses it.
- **Postgres demo** — `medication_administrations` may be created in place, but
  `audit_log` needs the same hand migration or a database rebuild.

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

`CARESYNC_SESSION_COOKIE_SECURE` must not be set to `true` without HTTPS:
see "Security behaviour" for why it silently breaks sign-in otherwise.

## API surface

> **Obsolete — triage era.** This table lists routes the demolition removed
> (Queue, Override, Departure, Re-assessment and the Accuracy Evaluation report)
> and omits the surviving `/encounters/{id}/end` route. Do not treat it as the
> current surface; it is kept as history pending ticket 41.

| Method | Path                                    | Access        |
| ------ | --------------------------------------- | ------------- |
| POST   | `/api/auth/login`                       | Public        |
| GET    | `/api/auth/me`                          | Authenticated |
| POST   | `/api/auth/logout`                      | Public        |
| POST   | `/api/auth/switch-user`                 | Public        |
| POST   | `/api/auth/lock`                        | Authenticated |
| POST   | `/api/auth/unlock`                      | Public        |
| POST   | `/api/auth/password`                    | Authenticated |
| GET    | `/api/roles`                            | Public        |
| GET    | `/api/clinical/access`                  | Clinical      |
| POST   | `/api/clinical/patients`                | Clinical      |
| GET    | `/api/clinical/patients`                | Clinical      |
| GET    | `/api/clinical/patients/{id}/encounters` | Clinical     |
| POST   | `/api/clinical/encounters`              | Clinical      |
| GET    | `/api/clinical/encounters`              | Clinical      |
| GET    | `/api/clinical/queue`                   | Clinical      |
| GET    | `/api/clinical/encounters/{id}`         | Clinical      |
| PUT    | `/api/clinical/encounters/{id}/intake`  | Clinical      |
| GET    | `/api/clinical/override-reasons`        | Clinical      |
| POST   | `/api/clinical/encounters/{id}/override` | Clinical     |
| POST   | `/api/clinical/encounters/{id}/departure` | Clinical    |
| POST   | `/api/clinical/encounters/{id}/reassessment` | Clinical |
| GET    | `/api/administrator/access`             | Administrator |
| GET    | `/api/administrator/queue`              | Administrator |
| GET    | `/api/administrator/audit-log`          | Administrator |
| GET    | `/api/administrator/reports/daily-queue` | Administrator |
| GET    | `/api/administrator/reports/priority-distribution` | Administrator |
| GET    | `/api/administrator/reports/performance` | Administrator |
| GET    | `/api/administrator/reports/accuracy-evaluation` | Administrator |

The `/access` routes are the role-gated surfaces from ticket 01; they exist to
demonstrate that authorisation is enforced at the API boundary. A wrong Role
receives `403`; an unauthenticated request receives `401`.

`GET /api/clinical/encounters` is a recency list for reviewing a saved intake —
newest arrival first, `?limit=` up to 100. It is not the Queue: it is not
ordered by Urgency Level and does not filter awaiting versus departed.

`GET /api/clinical/patients` searches Patients by name or contact number,
`?q=` plus `?limit=` up to 100. A blank or whitespace-only query returns
nothing, so the view cannot be used to list every Patient. Search is a
discovery aid and is deliberately looser than the identity rule
`find_or_create_patient` applies: a name is enough to *find* a Patient, never
to *match* one. `GET /api/clinical/patients/{id}/encounters` returns one
Patient's Encounters over time, excluding evaluation-run rows as the Queue does.

`GET /api/administrator/audit-log` is the append-only record of clinical
mutations — registration, opening an Encounter, intake correction, Override,
Re-assessment and Departure — each naming its actor, `?encounter_id=` narrows
it to one Encounter. See ADR 0007.

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

> **Obsolete — triage era.** This inventory names files the demolition deleted
> (the engine, classifier, Symptom Groups, assessments, queue, overrides, reports
> and accuracy modules, and the Queue/Override frontend). It is kept as history
> pending ticket 41.

```
capacitor.config.ts    native shell config; webDir is frontend/dist
android/               Capacitor Android project (committed; build output ignored)
ios/                   Capacitor iOS project (committed; build output ignored)
backend/
  app/
    main.py            app factory, router wiring, startup seeding, CORS
    config.py          Settings (CARESYNC_* env vars)
    db.py              engine and session factory
    models.py          User, UserSession, Role, Patient, Encounter,
                       TriageAssessment, Override, AuditEntry, Sex
    schemas.py         request/response models
    patients.py        Patient matching rule and find-or-create
    intake.py          whether an Encounter's intake may still be corrected
    prioritisation.py  Seam B: the pure Prioritization Engine
    red_flags.py       the deterministic red-flag safety layer (ticket 07)
    features.py        the structured feature vector training and inference share
    classifier.py      loads the JSON artefact; softmax inference, no database
    symptom_groups.py  the fixed vocabulary and spaCy recognition onto it
    symptom_groups.json  versioned Symptom Group vocabulary (authored list)
    assessments.py     captures inputs, runs the engine, appends the Assessment
    override_reasons.py  the fixed Override Reason set (one source of truth)
    overrides.py       performing an Override and its guards
    audit_actions.py   the fixed Audit action set (one source of truth)
    audit.py           appending audit entries and reading the log
    departures.py      performing a Departure and the awaiting-Encounter guard
    reassessments.py   performing a Re-assessment and recording supersession
    queue.py           the Queue as a sort over awaiting Encounters
    reports.py         read-only Reports derived on demand from stored records
    accuracy.py        the Accuracy Evaluation read model and run manifest loader
    security.py        argon2 hashing, session token hashing
    session_lock.py    inactivity lock and unlock rate limiting (session row)
    deps.py            get_current_session, get_current_user, require_role
    seed.py            demo Clinical and Administrator users
    routers/
      auth.py          login, me, lock, unlock, switch-user, logout,
                       change-own-password
      meta.py          the two Roles
      clinical.py      Patient registration, intake, Assessments, Queue
      administrator.py Administrator queue read model, Reports and access surface
  evaluation/          rubric, labeller, corpus, dataset loaders and training
    datasets/          provenance.json: sources, licences, checksums, rejection
    triage_datasets.py dataset-agnostic loaders into TrainingEncounter rows
    train_classifier.py trains, cross-validates and writes the artefact
  models/              the committed classifier artefact (small JSON)
  tests/               API-level pytest suite (SQLite) and Seam B unit tests
frontend/
  src/
    App.tsx            session check, Role landing route, surface switch
    LoginScreen.tsx    login form; native Server setting
    routing.ts         Role landing paths and path routing
    ClinicalWorkspace.tsx  Queue / Intake / History switch for the Clinical role
    QueueBoard.tsx     live Queue cards, expansion, Override and Depart actions
    PatientHistoryScreen.tsx  Patient search and one Patient's Encounters over time
    AdministratorDashboard.tsx  dense Queue table, Reports mount point
    AdministratorReports.tsx    Accuracy Evaluation, Daily Queue, Distribution, Performance
    usePolling.ts      shared poll-on-interval and poll-on-focus hook
    queueDisplay.ts    shared waiting-time and urgency formatting; the wait-escalation
                       bands, and abnormal-vital marking driven by the server's red flags
    IntakeScreen.tsx   Clinical intake and recent Encounters
    Shell.tsx          post-login shell, role badge, password change
    api.ts             typed fetch wrapper; absolute URL in the native shell
    platform.ts        Capacitor platform mapping, default clinical view
    runtime.ts         Capacitor platform detection
    runtimeConfig.ts   API base URL resolution and device override
    *.test.ts          node:test suites for the two modules above
```

There is no migration tool yet. Tables are created at API startup; deleting
`backend/caresync.db` resets the local database.

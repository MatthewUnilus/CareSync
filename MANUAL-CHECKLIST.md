# CareSync — Manual and Smoke Test Checklist

CareSync has no frontend automated test harness (a deliberate scope decision,
recorded in the spec and [ADR 0001](docs/adr/0001-sqlite-local-postgres-production.md)).
The API is exercised by the pytest suite (`npm run test:api`); the **client is
verified by the smoke and manual checks on this list**. Run it against a fresh
local stack before a demonstration, a study session, or a release.

Every check states the screen, the action, and what a pass looks like. Work
top to bottom; a failed check is a blocking bug, not a note.

## Setup

Start the stack and sign in as each Role:

```powershell
npm install
npm run dev
```

- API at <http://127.0.0.1:8000>, client at <http://127.0.0.1:5173>.
- Clinical: `clinical@example.com` / `clinical-password`.
- Administrator: `administrator@example.com` / `administrator-password`.

To exercise the study checks, set `CARESYNC_STUDY_INSTRUMENTATION_ENABLED=true`
first, then restart the API.

## 1. Authentication and the two Roles

- [ ] Signing in as Clinical lands on the **Ward board**; the view switch shows
      Ward board, Intake, Patient history, Study timing.
- [ ] Signing in as Administrator lands on the Administrator view (Reports, Ward
      Operations, Audit log) and shows **no** clinical action anywhere.
- [ ] A wrong password is refused with a clear message and no session.
- [ ] **Switch user** signs out and returns to sign-in.
- [ ] **Change password** under the account panel succeeds; the old password
      then fails and the new one works.
- [ ] The wrong Role cannot reach the other's view by URL: `/clinical` as an
      Administrator and `/administrator` as Clinical both land on the right page.

## 2. Shared-device session lock

- [ ] Leave the tablet idle past `CARESYNC_SESSION_IDLE_SECONDS` (5 min) and the
      lock screen replaces the workspace; patient data is hidden.
- [ ] Unlocking with the correct password resumes the **same** session (same
      page, no fresh sign-in).
- [ ] Five wrong unlock passwords rate-limit further attempts (a 429-style
      refusal) for the configured lockout.
- [ ] The explicit **Lock** button locks without waiting for the timer, and does
      not sign the user out.
- [ ] A background poll that hits the lock still shows the lock screen (the lock
      is not only enforced on a click).

## 3. Intake, identity and search

- [ ] Register a Patient with a **hospital number**; the record shows it.
- [ ] Register a second Patient with the same name and phone but a **different**
      number; both records stay separate.
- [ ] Register with the **same** number under a different name; the existing
      record is reused, not duplicated.
- [ ] Search by name, contact number and hospital number each find the Patient.
- [ ] A blank search returns nothing (it does not list every Patient).
- [ ] Open a visit from Intake with a reason; it appears in the recent list and
      in the Patient's history.

## 4. Ward board, admission and discharge

- [ ] Admit a Patient to a ward and bed; they appear on the Ward board.
- [ ] Admit with a linked visit; the row shows the linked Encounter.
- [ ] Move the location; the board shows the new ward and bed.
- [ ] Discharge; the row leaves the board, and the stay is still readable in
      Patient history.
- [ ] The board orders by outstanding work (overdue doses, then due now, then
      results to review, then open tasks), with bed order breaking ties.
- [ ] The counts on each row update as work is added and cleared.

## 5. Observation chart

- [ ] **View chart** on a board row charts a new set of vitals.
- [ ] The newest set shows the previous set's readings beside it; the first set
      shows "first reading".
- [ ] A reading outside its reference range is marked, and the mark is display
      only — the value is unchanged.
- [ ] A charted set cannot be edited (there is no edit control).
- [ ] For a child, no reading is marked and the reason is stated.

## 6. Nursing notes

- [ ] Write a note from each of the five templates; the fields match the
      template.
- [ ] A new note is prefilled from the Patient's latest Observation, labelled as
      from the readings, and the values can be amended.
- [ ] Notes read in time order.
- [ ] **Correct this note** appends a new note that names the one it corrects;
      the original stays and is marked corrected.
- [ ] A **Ward Round Entry** note offers "Raise tasks from this entry".

## 7. Tasks and the ward round

- [ ] Raise a Task by hand against a Patient, with an optional due time and an
      optional assignee.
- [ ] Raise several Tasks from one Ward Round Entry; each belongs to that
      Patient and names the entry.
- [ ] The cross-patient task list shows open Tasks across the ward and filters
      to "Assigned to me".
- [ ] A Task past its due time is shown **overdue**; nothing is escalated.
- [ ] Marking a Task done removes it from the open list and keeps it in the
      Patient's record.

## 8. Medications

- [ ] Transcribe a Medication Order (drug, dose, route, frequency, start,
      instructed by); it appears in the record.
- [ ] The round times a frequency maps to are shown as a documented convention.
- [ ] **Stop** an order; it stops producing doses and both the stop and any new
      order stay in the record.
- [ ] The **due list across the ward** shows doses for a chosen UTC day, ordered
      by due time, marking what is overdue.
- [ ] Record a dose as given, withheld, refused and unavailable; a reason is
      required when it was not given.
- [ ] A slot cannot be recorded twice.
- [ ] A dose given after its due time is accepted and marked **late**.
- [ ] The order's week grid shows what was due and what happened.

## 9. Investigations

- [ ] Record a requested test; it reads back as requested.
- [ ] The four states move in order: requested → sample taken → result
      available → reviewed.
- [ ] A result note is stored verbatim and never interpreted, flagged or scored.
- [ ] Marking a result reviewed records who and when.
- [ ] The **results awaiting review** and **tests awaiting a result** lists
      cover several patients and exclude the wrong states.

## 10. Printable sheets (ticket 37)

Print preview each sheet at the paper size the ward uses (A4), from the print
buttons on the Ward board.

- [ ] **Handover sheet** prints the ward's Patients with identity, location, the
      linked visit, latest Observation, medication situation, open Tasks and
      unreviewed results.
- [ ] **Medication round sheet** prints the doses due in the chosen UTC day, in
      due-time order, with a space to record each one and the Patient's identity
      against each dose.
- [ ] **Ward worklist** prints outstanding Tasks and Investigations awaiting a
      result or a review, grouped by Patient.
- [ ] Every sheet carries its **generation time**.
- [ ] Every sheet carries the line **"verify against the system"**.
- [ ] Print preview drops the navigation, the controls and the interactive
      affordances, and uses a legible size — not the screen's type scale.
- [ ] A Patient with a long history prints the **current picture**, not the
      whole record.
- [ ] The sheet prints alone: the app chrome (board, buttons, segmented control)
      does **not** appear on paper.

## 11. Administrator dashboard and Audit log

- [ ] **Reports** shows Daily Visits and Performance figures.
- [ ] **Ward Operations** shows the census, length of stay, medication
      timeliness, results awaiting review (with the oldest wait) and task
      completion.
- [ ] Changing the period (7 / 14 / 30 days) changes the timeliness and task
      figures.
- [ ] Refresh updates the figures; they are derived on read, not cached.
- [ ] The **Audit log** lists clinical mutations, oldest first, with the action's
      human label, actor, time and detail; the Encounter filter narrows it.
- [ ] An Administrator sees no clinical action anywhere and cannot perform one.

## 12. Study instrumentation (ticket 40)

Run this only with `CARESYNC_STUDY_INSTRUMENTATION_ENABLED=true`.

- [ ] With the setting **off**, the Study timing tab states the panel is
      disabled and records nothing.
- [ ] With it **on**, the panel offers Start, End and Abandon.
- [ ] Starting a run records the task label, the anonymised participant id and
      the start instant; the run reads as **running**.
- [ ] Ending a run sets its end instant and reads as **completed**.
- [ ] Abandoning a run reads as **abandoned**, not as a very long run.
- [ ] The recorded runs table carries no nurse identity — only the study id.
- [ ] The export caption states its own limitations (measures the system, not the
      nurse; interruption not accounted for; no participant identity).

## 13. Build and API suite

- [ ] `npm run build:web` completes with no type errors.
- [ ] `npm run test:api` passes (the full pytest suite).
- [ ] A fresh checkout with a deleted `backend/caresync.db` starts, seeds the
      demo users, and serves the login page.

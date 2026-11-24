# Spec — Laboratory dashboard and Investigation results

Status: **ready-for-agent**

## Problem Statement

A nurse can record an Investigation and track that a sample was taken, but laboratory staff have no CareSync worklist. The ward cannot see that the laboratory acknowledged a request, and a nurse must copy the result back into CareSync. This leaves the two teams without a shared record of the handoff.

## Solution

From an Admission, a Clinical user explicitly sends an Investigation to the laboratory. Laboratory staff see it on their dashboard, acknowledge receipt, and publish a free-text result against the same Investigation. The result appears in the ward’s existing Investigation views, where a Clinical user can read it and mark it reviewed. Each handoff records who performed it and when.

## User Stories

1. As a Clinical user, I want to send an Investigation from an Admission, so that the laboratory sees work for the correct Patient.
2. As a Clinical user, I want to choose whether to send an Investigation to the laboratory, so that other investigations can keep their existing workflow.
3. As a Clinical user, I want to record when a sample was taken separately from sending the request, so that the record distinguishes sample collection from the digital handoff.
4. As a Clinical user, I want confirmation after sending succeeds, so that I know the request reached the laboratory worklist.
5. As a Clinical user, I want to see when laboratory staff acknowledged receipt, so that I know someone at the laboratory picked up the request.
6. As a Laboratory user, I want my own dashboard after sign-in, so that I can start with work sent to the laboratory.
7. As a Laboratory user, I want to see incoming requests waiting for acknowledgement, so that I can identify new work.
8. As a Laboratory user, I want to see acknowledged requests awaiting results, so that I can resume pending work.
9. As a Laboratory user, I want to see which results have been published, so that I can verify a completed handoff.
10. As a Laboratory user, I want to see the Patient name, hospital number if available, originating ward, requested test, and sample status, so that I can match the request to the work in front of me.
11. As a Laboratory user, I want to acknowledge receipt explicitly, so that the ward sees who acknowledged the request and when.
12. As a Laboratory user, I want to review the Patient and test details before publishing, so that I can catch a selection error.
13. As a Laboratory user, I want to publish a result note on the original request, so that the ward receives it without re-entry.
14. As a Laboratory user, I want the dashboard to explain a failed or stale submission, so that I can check what was saved before retrying.
15. As a Clinical user, I want published results to appear in the existing results awaiting review worklist for open Admissions, so that I can find them during ward work.
16. As a Clinical user, I want to see a result’s publisher and publication time, so that I know where it came from.
17. As a Clinical user, I want to mark a published result reviewed, so that the ward records who read it and when.
18. As a Clinical user, I want a late result to stay attached to the original Admission, so that discharge does not hide it from that Patient’s history.
19. As a Clinical user, I want a separate way to find late results awaiting review, so that I can follow up after discharge.
20. As an Administrator, I want to see the send, receipt, publication and review in the Audit Log, so that I can trace the handoff.
21. As a Patient, I want laboratory staff to see only information needed for laboratory work, so that unrelated information from my record stays private.

## Implementation Decisions

- Extend the existing Investigation and keep its link to the original Admission. Use an explicit send action with an actor and timestamp. A saved request appears on the laboratory dashboard at the next successful refresh. The dashboard distinguishes an incoming request from one acknowledged by a Laboratory user.
- Preserve the existing Investigation states of requested, sample taken, result available and reviewed. Track laboratory send and receipt as separate milestones. Receipt acknowledges the request in CareSync. Sample collection remains a separate Clinical action. In this first version, a Clinical user sends only after recording sample collection and while the Admission is open. A Laboratory user can publish only after acknowledging receipt.
- Add a Laboratory Role to the shared sign-in and session infrastructure, with a dedicated dashboard and server-side authorization. Laboratory users can read sent Investigations and acknowledge or publish them. Clinical users send and review. Keep the existing Clinical result entry path for Investigations outside the laboratory workflow. For sent Investigations, reserve publication for Laboratory users. Enforce permissions on the API, including direct access by ID. Administrators keep read-only oversight.
- Return a purpose-built projection for laboratory reads. Include request identity, test name, sender and send time, Patient name and hospital number when available, ward context, sample status, and laboratory milestones. Use the original request identifier for all actions. If the Patient has no hospital number, make that absence visible. Keep general Patient search, contact details and other clinical records outside the laboratory response.
- Store the free-text result on the same Investigation, with publisher and server-recorded publication time. Require nonblank text within the existing result note limits. Publication makes the result available for Clinical review. The published note remains read-only in this first version.
- Derive incoming, acknowledged and published views from saved records, ordered by time within each view with a stable tie-breaker. Use the existing client refresh pattern to update the laboratory dashboard and ward Investigation views while open. Show loading, empty, error and retry states. Confirm a send, acknowledgement or publication only after the server saves it.
- Derive the ward’s awaiting-review list for open Admissions from the same result record. Keep already-sent work actionable for the laboratory after Discharge. Show any unreviewed publication on a discharged Admission in a separate ward follow-up list and in the original Admission history. Permit Clinical review there and keep discharged Admissions out of the Ward Board. This is a specific change to the current restriction on moving Investigations after Discharge, limited to receipt, publication and review for already-sent Investigations.
- Use atomic, conditional transitions to prevent duplicate sends, receipts, publications and reviews. Return a conflict for stale or out-of-order actions and let the client refresh the saved state. Write an Audit Entry in the same transaction as each successful action, naming the actor, time, and affected Investigation, Patient and Admission. Keep result text in the Investigation rather than the Audit Log.
- Provide an upgrade path for SQLite and Postgres that preserves existing data and history. Existing Investigations start with no laboratory handoff and keep their current state. Include any changes to stored role and audit action constraints.

## Testing Decisions

- Use the existing HTTP API as the primary test boundary. Assert observable state, permissions and Audit Log entries through API responses. Follow the existing Investigation, role access and audit tests.
- Drive a complete flow across separate signed-in users. Record a request and its sample collection, then send it as Clinical. See and acknowledge it as Laboratory, publish as Laboratory, and see and review the result as Clinical. Verify that the same Investigation and Admission are returned throughout.
- Verify that unsent Investigations stay outside the laboratory dashboard and continue through the existing Clinical workflow. Verify direct access restrictions and check that laboratory responses contain only the permitted data.
- Cover invalid transitions, blank result text, repeat or concurrent submissions, and stale client state. Confirm that rejected actions leave the saved state and Audit Log intact. Include older records, a Patient without a hospital number, Patients with similar names, and publication and review after Discharge.
- Run a manual walkthrough with separate Clinical and Laboratory sessions using simulated data. Check sign-in routing, the dashboard views, refresh across both sessions, visible status, submission feedback and recovery after a failed request.

## Out of Scope

- External laboratory information systems, instrument interfaces and electronic health record integration.
- Specimen accessioning, barcode scanning, chain of custody and verification of physical specimen receipt.
- Result interpretation, reference ranges, abnormal-result flags, clinical prioritization and alerts.
- Structured result panels, attachments, result amendments, request cancellation and rejection workflows.
- Email, SMS and push notifications, offline operation, and live clinical deployment.

## Further Notes

- This extends the two-role decision in the current domain glossary and the ward-only result transcription described in ADR 0012. Update the glossary, ADR and product documentation alongside implementation. Preserve ADR 0012’s boundary around result interpretation and ADR 0009’s paper-record policy.
- The first release assumes one internal laboratory, sample collection before sending, and free-text result publication.

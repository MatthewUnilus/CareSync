# Prioritisation in context — TriageAssist against ESI and queueing theory

This document places the Prioritization Engine against the two bodies of work a
reader is entitled to measure it by: the Emergency Severity Index it is scored
against, and the queueing theory that governs any urgency-ordered waiting line.
It records what the engine implements, what it deliberately does not, and where
its reported numbers come from. It changes no behaviour; every claim about the
engine is traceable to a file in this repository.

## The engine's position against ESI

ESI assigns one of five levels through four decision points, evaluated in order.
TriageAssist implements three of them and replaces the fourth with a classifier.
Being explicit about which is which is the honest way to state what this build
is.

| ESI decision point | What it decides | TriageAssist |
| --- | --- | --- |
| **A** — immediate life-saving intervention | ESI 1 | Implemented in the safety layer and the classifier's risk features |
| **B** — high-risk situation, altered mentation or severe distress | ESI 2 | Implemented as the cited red-flag rules, which raise to High |
| **C** — projected resource categories | ESI 3 / 4 / 5 | **Not implemented in the engine.** The rubric models it; the engine is replaced here by the trained classifier |
| **D** — danger-zone vitals | Escalates ESI 3 to 2 | Implemented as the age-banded vital red flags |

The consequence of the missing **C** is the single most important thing to
understand about the engine's accuracy, and it is developed below.

## The rubric implements C; the engine cannot see it

The scoring rubric already models ESI Decision Point C completely:

- `EsiResource` (`backend/evaluation/rubric.py:71`) — the resource vocabulary,
  following handbook Table 2-3, with a complex procedure counting as two units
  (`resource_units`, `rubric.py:233`).
- `_two_or_more_resources` / `_one_resource` / `_no_resources`
  (`rubric.py:309-318`) — the ≥2 / ==1 / ==0 mapping onto ESI 3 / 4 / 5.

The engine, by contrast, has no resource input. `PrioritisationInputs`
(`backend/app/prioritisation.py`) carries the presenting complaint, pain level,
illness duration, age, the five vitals and the recognised Symptom Groups — and
nothing about expected resources. `build_feature_vector`
(`backend/app/features.py`) builds the classifier's vector from exactly those
fields.

So the engine is **scored against ground truth that uses a decision point it
cannot observe**. That is not a modelling choice made in isolation; it is an
asymmetry that exists inside this repository, and it is the honest explanation
for the numbers in the Accuracy Evaluation.

## Why the middle tier is the weakest — and why that is expected

ESI separates ESI 3 from ESI 4–5 *only* by projected resource need: the vitals
in both bands are stable by definition. Decision Point D exists precisely to
catch the sub-band of ESI 3 that has danger-zone vitals — which is why it can
*escalate to 2* but cannot distinguish 3 from 4.

TriageAssist's Medium is ESI 3 exactly (`CONTEXT.md`, "Urgency Level"):
High = ESI 1–2, Medium = ESI 3, Low = ESI 4–5. Because the engine does not
capture resource need, a stable ESI-3 patient and a stable ESI-4 patient present
it with **identical available information**. The middle class is therefore not
merely poorly learned — it is not separable from the engine's inputs at all.

The primary evaluation run bears this out. On 2,205 encounters, per-class recall
is High 0.389, Medium **0.254**, Low 0.547, and the confusion matrix shows
true-Medium encounters scattering almost evenly (roughly 35% called High, 25%
Medium, 39% Low) — near chance for a three-way decision. The engine's strongest
class is Low, where the corpus is largest; its weakest is Medium, where the
ground truth depends on information the engine does not receive.

This is the correct reading of the headline accuracy figure. The number is low
in part because the engine is asked to reproduce a decision — resource
projection — that its inputs do not contain. Stated plainly: **Medium is
unlearnable from the current feature set, not merely unlearned by the current
model.** Reporting the per-tier figures alongside the headline, as the Accuracy
Evaluation does, is what makes that visible rather than hidden.

## The safety layer protects High, not Medium

`apply_safety_layer` (`backend/app/red_flags.py:374`) has one behaviour: it
returns High when a red flag fires, and otherwise returns the classifier's
answer unchanged. There is no branch that lowers a level, and no branch that
edits a Medium. Consequently a true-Medium encounter the classifier calls **Low**
stays Low unless it also trips a danger-zone vital rule.

The layer is a critical-illness net, and it should be judged as one. Published
triage research locates exactly this kind of blind spot: across a multi-scale
systematic review, sensitivity for immediate mortality was high, but sensitivity
for patients who deteriorated or died shortly after triage fell sharply for
occult presentations — severe sepsis, pulmonary embolism and non-STEMI among
them (below 80%, and in places below 60%), and a meaningful share of
subsequently-hospitalised patients had initially been triaged to the two lowest
acuity tiers. A rule set that only keys on vital thresholds and recognised
symptom groups cannot close that gap, because the gap is defined by patients
whose vitals are not yet deranged.

*(This finding is drawn from a systematic review of five-level triage scales. The
source supplied for this document did not name it in full, so it is described
here by its content rather than given a citation this project cannot verify.
Before it is cited in the dissertation it must be sourced directly.)*

## Static priority and the queueing-theory limitation

The Queue orders by Urgency Level, ties broken by arrival time, and never
changes with how long a patient has waited. ADR 0006 records the visible
consequence: a six-day Low legitimately sits below a freshly arrived Medium. Two
classical results in queueing theory explain why that is a *predictable* cost of
static priority rather than an implementation defect, and they give ADR 0006 its
theoretical backing.

Under a non-preemptive priority discipline with fixed class order, expected
waiting time per class follows Cobham's equation (Cobham, 1954), and the
work-conserving property means that prioritising urgent patients cannot create
capacity — it *redistributes* waiting time onto lower tiers. By the conservation
law (Kleinrock), the utilisation-weighted sum of waiting times is invariant under
any work-conserving discipline, so pulling a critical case forward mathematically
pushes delay onto a less urgent one. The practical corollary is the one that
matters: as utilisation approaches saturation, the lowest class's queue grows
without bound while the higher classes stay bounded. A static-priority board can
therefore show a very long wait for its lowest tier, and correctly so under its
own rule.

The obvious remedy — priority aging, in which a waiting patient accumulates
priority and can eventually overtake a newer arrival — is the Accumulating
Priority Queue (Kleinrock, 1964; full waiting-time distributions in Stanford,
Taylor and Ziedins, 2014). It is worth recording *why TriageAssist does not
adopt it*, because the same literature supplies the reason. Pure accumulating
priority has a known heavy-load failure mode: as utilisation approaches
saturation, **every** class's queue grows unboundedly, because aged lower-acuity
patients eventually overtake new arrivals — including urgent ones. The published
mathematical remedies are hybrids (static priority retained for the top classes,
accumulation only below) or accumulation rates scaled inversely with remaining
slack capacity. Both are considerably more than a board needs, and both trade a
bounded, explainable rule for a parameterised one. For a triage *support* tool
whose value is transparency, a rule a clinician can hold in their head — urgency
first, arrival second — was preferred over one whose behaviour changes with load
in ways the clinician cannot see. That is the trade the project made; it is a
real trade, not a free choice.

## Where bias can enter, and where it cannot

Triage research consistently finds that triage disparities attach to *subjective*
presentations — chest pain, dyspnoea — and largely do not appear for
protocolised, objective triggers such as a stroke pathway. That distinction
maps cleanly onto the two paths in this engine:

- **The objective path** — the red-flag safety layer — keys only on age, the
  five measured vitals and recognised Symptom Groups. It contains no
  demographic field; sex and race/ethnicity do not reach
  `PrioritisationInputs` or the feature vector at all. Disparity cannot enter
  through it.
- **The subjective path** — the free-text presenting complaint, mapped onto
  Symptom Groups, then into the classifier — is where a triage disparity *could*
  in principle enter, because it starts from language rather than measurement.
  `red_flags.py` already records the sharpest limitation of the recognition step
  that feeds it: it sees only the Symptom Groups recognised from the text and
  does not understand negation, so "no chest pain" still registers as chest pain.

*(This finding — that disparity attaches to subjective complaints specifically —
is drawn from a large single-system cohort study described in the source
supplied for this document. It too was not named in full there; source it
directly before citing.)*

## A note on evidence quality

The research this document draws on mixes evidence of materially different
strength, and a reader should not treat the tiers as interchangeable:

- **Use directly**: peer-reviewed cohort studies and systematic reviews (the
  occult-critical-illness sensitivity finding; the subjective-complaint bias
  finding); classical queueing results (Cobham 1954; Kleinrock 1964; Stanford,
  Taylor and Ziedins 2014) and the ESI handbook.
- **Use with care**: simulation studies — genuinely useful for the
  static-versus-dynamic priority trade-off, but models, not observations.
- **Treat as claims, not evidence**: vendor white papers and trade reports
  describing commercial triage products. Where the same intervention class is
  reported both in a peer-reviewed study and in vendor material, the
  peer-reviewed figures are the ones to cite.

This project's own reported accuracy belongs in the first tier in only a limited
sense: it is measured on an interim open dataset (ADR 0005) and is not a
validated clinical result. It should be presented as evidence that the pipeline
is real and its behaviour is measurable, not as evidence that the system is
accurate.

## Summary of the honest position

TriageAssist implements ESI decision points A, B and D with cited thresholds,
and substitutes a trained classifier for decision point C. Its most accurate
class is Low and its least accurate is Medium, because Medium's definition turns
on resource information the engine does not collect. Its safety layer protects
High and, by design, not the middle. Its static priority discipline inherits the
classical starvation limitation of any urgency-ordered queue, documented in ADR
0006 and now given its theoretical basis here. None of these is a defect to be
hidden; each is a boundary of the documented scope, and stating them is what lets
the accuracy evaluation be read for what it actually measures.

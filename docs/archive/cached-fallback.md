> **Archived.** This document describes the cached fallback for unrecognised
> complaints, a layer of the Prioritization Engine, which no longer ships. It was
> removed by [ADR 0014](../adr/0014-remove-triage-engine.md). It is kept because
> the dissertation may cite it, and it does not describe the current design.

# Cached fallback for unrecognised complaints

`backend/app/fallback.py` is layer (3) of the Prioritization Engine described in
`spec.md` ("Prioritization Engine composition"). It is reached only when a
complaint recognises no Symptom Group; a complaint that matches one never takes
this path.

## Why it exists

Recognition is deliberately literal (`app/symptom_groups.py`): a complaint is
mapped only when one of the vocabulary's exact phrases occurs in it. Unusual
wording would otherwise leave the patient with no Machine Recommendation. The
fallback gives the engine a supervised best effort for the long tail while
keeping the deterministic layers authoritative.

## Composition

```
Symptom Groups matched ──► classifier ──► safety layer ──► Machine Recommendation
no Symptom Group        ──► fallback provider (cached, timed) ──► safety layer
                              └── unavailable/timeout ──► safety layer over default ──► unclassified
```

The safety layer always has the last word. A cached answer is the provider's
complaint-only level; the safety layer is applied to it on every resolve, so the
same words used by a patient with different vitals can still be raised to High.
A degraded answer is the safety layer over the documented default, so a red
flag can raise it too.

## The provider seam

`FallbackProvider` is a two-member protocol: a stable `name` and
`classify(complaint) -> UrgencyLevel`. The runtime implementation is
`HttpFallbackProvider`, which posts a minimal, vendor-neutral JSON contract:

```http
POST <TRIAGEASSIST_FALLBACK_PROVIDER_URL>
Content-Type: application/json
Authorization: Bearer <TRIAGEASSIST_FALLBACK_PROVIDER_API_KEY>   # optional

{"complaint": "metallic taste in mouth"}
```

```json
{"urgency_level": "High"}
```

The body may also be one of the three words. Configuration is entirely
environment-driven:

| Setting | Default | Meaning |
| --- | --- | --- |
| `TRIAGEASSIST_FALLBACK_PROVIDER_URL` | unset | No URL means no provider: the degraded path is used. |
| `TRIAGEASSIST_FALLBACK_PROVIDER_API_KEY` | unset | Optional bearer token for the service. |
| `TRIAGEASSIST_FALLBACK_TIMEOUT_SECONDS` | `2.0` | Wall-clock deadline for one provider call. |

The build and the test suite never need an API key, a network or a paid
service. Tests inject a fake provider into `create_app(settings,
fallback_provider=...)`; the provider is app state, so the engine itself stays
pure.

## Cache

`fallback_cache` is a database table keyed by the SHA-256 of the complaint text
exactly as stored. The row carries the complaint, the provider's raw level, the
provider name and the creation instant. The write happens in the same
transaction as the Assessment, so:

- the same complaint submitted twice returns the identical recommendation, with
  the second resolve served from the cache and no provider call;
- a hit survives a process restart because it is in the database, not in
  memory;
- a different patient with the identical complaint receives the identical
  provider answer, but the safety layer still sees that patient's vitals.

A degraded (unclassified) answer is **not** cached. It is already deterministic,
and caching it would keep a transient outage in the record after the provider
recovered.

## Timeout and the default level

`FallbackResolver` runs the provider call on a daemon thread and waits for
`TRIAGEASSIST_FALLBACK_TIMEOUT_SECONDS`. A timeout, an exception or an
unconfigured provider all take the same path: the safety layer runs over
**Medium**, the documented default (`DEFAULT_TIMEOUT_LEVEL`), and the outcome is
marked `unclassified`. Medium is chosen because it neither systematically
under- nor over-triages on its own, and because High would leave the safety
layer nothing to raise. Nothing about the failure is shown as an error or
blocks intake; the card asks for review instead.

## The unclassified flag

`TriageAssessment.unclassified` is frozen with the rest of the Assessment. The
Queue response exposes it as `unclassified_flag`, a field of its own beside
`override_flag`:

- **Override** (orange) means a Clinical user changed the Final Decision away
  from a Machine Recommendation that was classified.
- **Unclassified** (violet) means the fallback provider could not classify the
  complaint, so the recommendation came from the safety layer's default.

Both can be true at once, and neither redefines the other. `QueueBoard.tsx`
renders them as separate badges (`queue-flag-override` and
`queue-flag-unclassified`), and the expanded card adds an explanatory notice.

## Evaluation

The fallback is disabled by passing `fallback=None` to the engine, which is what
`recommend(inputs)` does by default. The fallback-on run passes a
`FallbackResolver` to `assess(inputs, fallback=...)`; `Recommendation` then
carries `fallback_used`, and `Recommendation.unclassified` says whether the
provider degraded. Coverage is therefore countable without a database, either
as `not inputs.recognised_symptom_groups` or, from a stored Assessment, as an
empty `recognised_symptom_groups`. Ticket 15 reports coverage as its own
statistic and must not fold it into the main score; ticket 14 must keep the
fallback-on and fallback-off runs distinguishable when it presents both.

## Tests

`backend/tests/test_fallback.py` proves, at the engine and API seams:

- an unrecognised complaint receives a recommendation rather than an error;
- the same text twice returns an identical result and the second resolve is a
  cache hit;
- provider failure and provider timeout both yield an unclassified result whose
  level is still valid and can be raised by a red flag;
- a matched complaint never calls the provider;
- the cache survives a new application instance over the same database;
- `unclassified_flag` and `override_flag` are independent.

# 35: Medication administrations

**What to build:** A dose is recorded as given, withheld, refused or unavailable, once per slot, with a reason when it was not given. Not giving a dose is as recordable as giving it, which is what makes the medication record honest.

**Blocked by:** 34 (an administration belongs to an order and a due slot).

**Status:** ready-for-agent

- [ ] A new `medication_administrations` table records the order, the due time it answers, the outcome, the reason where the outcome is not given, the actor and the time recorded.
- [ ] The outcome set is fixed: given, withheld, refused, unavailable.
- [ ] A reason is required when the outcome is not given, from a fixed set with free text for the "other" case, following the pattern the deleted Override Reason used. The free text is permitted only for "other".
- [ ] A unique constraint over the order and the due time means a slot cannot be recorded twice. A second attempt is refused, not merged.
- [ ] The table is append-only, enforced by a `before_update` guard in the application layer (ADR 0001).
- [ ] An administered dose removes its slot from the due list, and the record stays readable.
- [ ] An overdue dose stays visible as overdue until it is recorded, and the system does nothing about it: no escalation, no cancellation, no change to the order. This rests on ADR 0010's rule.
- [ ] The administration record for a patient reads as a history: what was due, what happened, when, and by whom.
- [ ] A test asserts a slot cannot be recorded twice, and that a slot with a past due time can still be recorded late and is marked as late rather than refused.
- [ ] Recording an administration writes exactly one Audit Entry in the same transaction as the change.
- [ ] A week of doses for one order can be read as a grid, which is the shape a medication chart takes on paper and is what ticket 37 prints.

## Notes

- Recording a slot late must work. A nurse who gives a dose forty minutes after the round time and finds the system refuses the entry will stop using it, or worse, record it at the wrong time.
- The unique constraint is over the order and the due time, not the order and a wall-clock instant, because the due time is the slot's identity. Two administrations of one order at two round times are two slots; two attempts at one round time are one slot.
- The "other" free-text rule is worth copying deliberately from the deleted `override_reasons.py` shape, which enforced it at the request boundary. It is a small pattern and it kept the reason set reportable.
- There is no barcode verification and this ticket does not add any. The record says what a nurse attests to. State that plainly in the interface and in the ADR, so the limitation is on the record rather than discovered later.
- The outcome vocabulary comes from the nurse's own description of the work. Check it against the hospital's chart when they share it, because the words for refusal and unavailability differ between wards.

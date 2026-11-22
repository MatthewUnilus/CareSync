# 34: Medication orders, round times and the due list

**What to build:** A doctor's medication instruction is transcribed once, and the ward can see what is due and what is overdue across every patient from one list. This is the part of the nurse's third problem that is about medication schedules rather than tasks, and it is the reason they walk back to the ward.

**Blocked by:** 31 (a Medication Order belongs to an Admission).

**Status:** done

- [x] A new `medication_orders` table records the Admission, the drug, the dose, the route, the frequency, the start time, who instructed it, and the order's own state.
- [x] The clinical fields are frozen when the order is written: drug, dose, route, frequency and start time. A `before_update` guard refuses a change, following the pattern the deleted assessment used.
- [x] A dose change is a stop and a new order, so both the stop and the change are visible in the record rather than one overwriting the other.
- [x] An order can be stopped, and a stopped order produces no further due entries.
- [x] A new module holds the frequency-to-clock-times policy: what times of day a frequency maps to.
- [x] The round times a frequency maps to are shown to the user in the interface, so nobody mistakes the convention for clinical advice.
- [x] A due list is derived at read time from the open orders and the round times. It is never stored. A test asserts that reading it adds no rows.
- [x] The due list shows, across the ward, every dose due in a window, with the patient, the drug, the dose, the route and the due time, marking what is overdue.
- [x] The ward board's outstanding medication count starts returning a real figure, replacing the zero that ticket 31 stubbed, and the board's ordering by overdue and due-now doses becomes live.
- [x] A test constructs an order and a clock time and asserts exactly which doses are due and which are overdue.
- [x] Writing an order and stopping one each write exactly one Audit Entry in the same transaction as the change.
- [x] Tests: a stopped order stops producing due entries; a changed dose leaves the first order intact and stopped; the due list marks overdue correctly at a boundary; the derived read writes nothing.

## Notes

- ADR 0011 is the boundary. The system transcribes an instruction and does not calculate a dose, does not check a dose against a maximum, and does not check interactions or allergies. It holds no allergy or interaction data, and generating a prescription is outside the project. Say this in the interface too, where a nurse will read it.
- The frozen-field guard is what makes a dose change legible. Without it, a dose edited in place leaves a record that says the patient was on the new dose all along, which is exactly the failure ADR 0002 guarded against in the deleted engine.
- Deriving the due list rather than storing it follows the reports discipline: a stored due list drifts from the orders that generate it. This is why the derived-read-writes-nothing test matters.
- Round times are a convention and there is no single right set. Choose a documented default, expose it, and expect the hospital to have its own. The times should be one module with a short docstring listing the frequencies and their times, so the hospital's set replaces it in one place.
- Continuous infusions, variable doses and as-required medication are the awkward cases. Decide explicitly whether they are in this ticket or out of it, and record the decision, because a due list that quietly mishandles as-required medication is worse than one that says it does not cover it.
- The due list is a strong candidate for the study's timed tasks, since it is the one screen that replaces a walk down a corridor.

# 29: Hospital number on the Patient

**What to build:** A Patient can be identified by a hospital number, and when two patients share a name and a contact phone they stay separate once both carry numbers. On a ward this is the difference between the right patient and the wrong one, because a family phone number is shared and surnames repeat.

**Blocked by:** 28 (the rename lands before new fields are added, so nothing is added under the old name).

**Status:** ready-for-agent

- [ ] `Patient` gains `hospital_number`, optional, indexed.
- [ ] The registration form captures it, and it is optional: a walk-in with no number is still registrable.
- [ ] The matching rule becomes: equal numbers mean the same Patient; different numbers mean different Patients; with neither number present, the existing rule applies, being the normalised name together with the normalised phone.
- [ ] A patient registered without a number can have one added later, and adding it does not merge them with an unrelated patient who happens to share a name.
- [ ] Patient search matches on the hospital number as well as name and phone, so a number can be used to find someone whose name cannot be spelled.
- [ ] The patient history view shows the number, so a nurse can confirm the record is the right person.
- [ ] The intake screen's registration form shows the number field and its optional status.
- [ ] Tests: two patients sharing both name and phone stay separate once both carry numbers; an equal number reuses the existing record; a patient with no number still matches on name and phone; adding a number to an existing patient does not merge records.

## Notes

- The identity rule lives in `backend/app/patients.py:38-95` and is documented in the `Patient` model's docstring and in the README's "Patient matching" section. All three describe the rule, so all three change together.
- ADR 0014 records that this reverses the rule `proposal-gaps` deliberately froze. That spec said "Any change to the identity-matching rule in `patients.find_or_create_patient`" was out of scope, so the reversal needs to be visible rather than quiet.
- The unique constraint over `name_key` and `contact_key` is what enforces the current rule at the data layer. A hospital number cannot join that constraint directly, because it is nullable and SQL treats nulls as distinct in a unique index. Decide deliberately: a partial unique index on a non-null number is the cleanest, and it needs checking against both SQLite and Postgres since ADR 0001 requires the model layer to stay dialect-neutral.
- Normalisation matters here too. Decide whether the hospital number is stored as entered and normalised for matching, the way name and phone already are, and say so in the module docstring.
- This ticket touches nothing else on the Patient, so it is a narrow slice and it is the only ticket that changes patient identity. Everything after it can rely on the rule being settled.

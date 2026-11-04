# 02: Register a Patient and open an Encounter with intake

**What to build:** A Clinical user registers a Patient and opens an Encounter for them, capturing the intake that a Triage Assessment will later run on. The form works on a phone viewport at the bedside, shows which fields are required, and lets values be corrected until an assessment has run.

**Blocked by:** 01.

**Status:** done

- [ ] A Clinical user registers a Patient with name, age, sex, and contact details.
- [ ] Registering the same Patient again reuses the existing Patient record instead of creating a duplicate, and that Patient's Encounter history stays together.
- [ ] Opening an Encounter records its arrival instant, and the instant is not editable afterwards.
- [ ] Intake captures the presenting complaint as free text, pain level from 1 to 10, illness duration, temperature, heart rate, blood pressure, oxygen saturation, and optional notes.
- [ ] The intake form indicates which fields must be filled before an assessment can run.
- [ ] Intake values can be corrected while no assessment has run for the Encounter.
- [ ] Intake is usable on a phone-width viewport without horizontal scrolling.
- [ ] An Encounter is attributable to exactly one Patient, and a Patient may hold many Encounters over time.

## Comments

Resolved on `integration` (merge `ccff563`). Full suite green: 381 passed, 10 skipped (dataset-dependent, skipped when the published data is not cached).

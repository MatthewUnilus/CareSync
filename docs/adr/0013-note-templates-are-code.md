# 0013 — Note Templates are a fixed code vocabulary with one row per field

**Status:** Accepted (2026-11-22)

## Context

Writing nursing notes, updating patient charts and recording interventions is
the slowest part of the day, and starting from a blank page is most of the cost.
A note wants a starting shape: the fields a shift assessment, a ward round entry,
an intervention record, a handover entry or a discharge summary actually has.

Three things had to be decided, and each has a real alternative:

1. **Where the template lives.** In the database as template rows, or in code as
   a fixed vocabulary served by the API.
2. **How a note stores its fields.** One column per template field, or one row
   per field value.
3. **How fields are typed.** A controlled clinical terminology, or free text.

The hospital has not supplied its real chart, round sheet or observation chart,
so the templates are designed from standard nursing documentation practice and
are expected to be revised once the real forms arrive.

## Decision

Template definitions live in code as a fixed vocabulary, served by the API at
`GET /api/ward/note-templates`. Each field becomes one row per note.

Field values are free text. There is no controlled clinical terminology in scope.

Adding or changing a template field is a code change. It needs no database
change and no client change.

## Consequences

- There is no migration tool, and this decision means none is needed to change a
  template. New columns on existing tables do not appear from a model change, so
  a column-per-field design would have required a migration the repo does not
  have. One row per field sidesteps that entirely.
- The hospital's real forms will change the templates, and the field-per-row
  design absorbs a revision without touching the schema or the client. Expect a
  revision pass once the hospital supplies its chart.
- A template change is deployed like any other code change, which is the trade
  against a database-held template a non-developer could edit. This system has no
  template-editing UI and is not claiming one.
- Free text keeps the field values out of a terminology the project would have to
  author and maintain. The cost is that a field value cannot be queried as a
  coded concept, which is out of scope anyway because the system does not
  interpret clinical content.
- Template definitions are one source of truth, so the client and the server
  cannot disagree about what fields a note has.

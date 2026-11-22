# 28: Rename to CareSync

**What to build:** The system is called CareSync everywhere it names itself. It lands after the demolition so no ticket renames files that a later ticket deletes, and before the ward work so every new file is created under the final name.

**Blocked by:** 27 (renaming files that are about to be deleted is wasted work).

**Status:** ready-for-agent

- [ ] The backend package, the frontend workspace package (`@triageassist/web`), the root package, and any imports between them are renamed.
- [ ] The environment-variable prefix changes from `TRIAGEASSIST_` to `CARESYNC_` in `config.py`, and every documented use moves with it in `README.md`.
- [ ] The default database file is renamed, and so is its `.bak` sibling. Both are gitignored local files, so this is a delete-and-reseed rather than a migration.
- [ ] The session cookie name changes from `triageassist_session`.
- [ ] The Capacitor app id and the Android project name are updated, or explicitly deferred and recorded, so the native shell does not still say TriageAssist.
- [ ] `README.md`, `frontend/PRODUCT.md` and the root `AGENTS.md` say CareSync.
- [ ] `frontend/PRODUCT.md` is repaired beyond the name. It calls the Capacitor mobile shell "planned" when ticket 16 shipped it, and it does not know about the ward, the hospital or the pivot.
- [ ] The FastAPI app title and the OpenAPI metadata say CareSync.
- [ ] `npm test` and `npm run build:web` pass, and the app starts and serves a login page.

## Notes

- The rename is mechanical but wide. Do it in one pass rather than in batches: a half-renamed environment prefix produces a running server reading the wrong settings, which is a confusing failure to debug.
- `TRIAGEASSIST_SEED_DEMO_USERS`, `TRIAGEASSIST_DATABASE_URL`, `TRIAGEASSIST_CORS_ORIGINS` and the session settings are the ones that appear in the README's environment-variable table and in `docker-compose.yml`. Grep for the prefix rather than trusting the table.
- The database file cannot be renamed in place for a running instance. Deleting it and reseeding is the documented practice anyway, since there is no migration tool.
- `frontend/PRODUCT.md` is schema-tagged (`impeccable:product-schema 1`) and is the design-facing contract. Its "Product Purpose", "Positioning" and "Product Principles" sections are mostly triage and need rewriting rather than a name swap. Ticket 41 does the full documentation pass; this ticket only has to stop the file from describing a system that no longer exists.

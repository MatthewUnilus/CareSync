# 28: Rename to CareSync

**What to build:** The system is called CareSync everywhere it names itself. It lands after the demolition so no ticket renames files that a later ticket deletes, and before the ward work so every new file is created under the final name.

**Blocked by:** 27 (renaming files that are about to be deleted is wasted work).

**Status:** done

- [x] The backend package, the frontend workspace package (`@triageassist/web`), the root package, and any imports between them are renamed.
- [x] The environment-variable prefix changes from `TRIAGEASSIST_` to `CARESYNC_` in `config.py`, and every documented use moves with it in `README.md`.
- [x] The default database file is renamed, and so is its `.bak` sibling. Both are gitignored local files, so this is a delete-and-reseed rather than a migration.
- [x] The session cookie name changes from `triageassist_session`.
- [x] The Capacitor app id and the Android project name are updated, or explicitly deferred and recorded, so the native shell does not still say TriageAssist.
- [x] `README.md`, `frontend/PRODUCT.md` and the root `AGENTS.md` say CareSync.
- [x] `frontend/PRODUCT.md` is repaired beyond the name. It calls the Capacitor mobile shell "planned" when ticket 16 shipped it, and it does not know about the ward, the hospital or the pivot.
- [x] The FastAPI app title and the OpenAPI metadata say CareSync.
- [x] `npm test` and `npm run build:web` pass, and the app starts and serves a login page.

## Notes

- The rename is mechanical but wide. Do it in one pass rather than in batches: a half-renamed environment prefix produces a running server reading the wrong settings, which is a confusing failure to debug.
- `TRIAGEASSIST_SEED_DEMO_USERS`, `TRIAGEASSIST_DATABASE_URL`, `TRIAGEASSIST_CORS_ORIGINS` and the session settings are the ones that appear in the README's environment-variable table and in `docker-compose.yml`. Grep for the prefix rather than trusting the table.
- The database file cannot be renamed in place for a running instance. Reseeding is the documented practice, since there is no migration tool.

## Implementation notes

- The two ignored legacy SQLite files were moved to ignored `.before-caresync` backup names rather than destroyed; `npm run seed` created a fresh `backend/caresync.db` with two demo users and no clinical records. A running instance must stop before changing databases. Existing Postgres demo data in the old `triageassist_pgdata` volume is not migrated; the new volume starts fresh.
- Renaming the session cookie signs out existing sessions. The native bundle IDs change, so device builds need reinstalling rather than updating the previous app in place.
- `frontend/src/runtimeConfig.ts` intentionally retains the `triageassist.apiBaseUrl` storage key so existing devices keep their saved server URL; `.gitignore` retains old dissertation-artifact patterns so old files are not exposed. Root `AGENTS.md` contains no old project name, and the concurrent Astryx configuration there is left untouched.
- The browser login heading and shell name, not just API metadata and package names, now read CareSync. The full triage-era README replacement remains ticket 41.
- `frontend/PRODUCT.md` is schema-tagged (`impeccable:product-schema 1`) and is the design-facing contract. Its "Product Purpose", "Positioning" and "Product Principles" sections are mostly triage and need rewriting rather than a name swap. Ticket 41 does the full documentation pass; this ticket only has to stop the file from describing a system that no longer exists.

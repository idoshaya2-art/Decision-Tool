# EMBA TAU Simulation AI Decision OS v1.0 Architecture

```text
Team browser
    │ HTTPS + shared access password
    ▼
Render FastAPI service
    ├── file extraction and review workflow
    ├── deterministic scoring, finance, pricing and simulation engines
    ├── optional OpenAI Decision Agent with read-only tools
    ├── backup / restore validation
    ├── server-only Supabase secret
    └── server-only optional OpenAI API key
            │
            ├── Supabase Data API → PostgreSQL (RLS enabled)
            └── Supabase Storage API → private intopia-files bucket
```

## Decision boundary

- Actuals change only after an import is reviewed and committed.
- Scenarios never modify Actuals.
- The internal score is explicitly an estimate: 50% past performance and 50% future potential.
- Recommendations are produced by deterministic rules and financial calculations. The optional Agent explains, compares and calls read-only analytical tools.
- Q4 planning uses the most recent approved Q1–Q3 actuals when no Q4 actual exists.

## Persistence and security

- No database row or uploaded file relies on Render's local filesystem.
- Every file has bucket, path, MIME, byte size, SHA-256, source metadata and an extraction record.
- The browser receives neither the Supabase Secret nor the OpenAI API key.
- All application tables use RLS with no `anon`/`authenticated` grants; the trusted server uses the service role.
- Delete and failed upload paths remove related metadata consistently in production and in-memory tests.

## Main engines

- `import_service.py` — structured extraction and review payloads.
- `analytics.py` — financial position, scorecard, Q9 forecast, recommendations and scenario portfolio simulation.
- `agent_service.py` — optional OpenAI Responses API orchestration with read-only function tools.
- `backup_service.py` — complete portable ZIP with integrity checks.
- `db.py` / `cloud.py` — repository layer over Supabase Data and Storage APIs.
- `rulebook.py` — Rulebook versioned, deterministic rule checks, report validation and portfolio enforcement.
- `agent_service.py` — Responses API orchestration with server-side tools and auditable AI runs.
- `analytics.py` — financial state, Q9 forecast, scenarios, budget sequencing and economic impacts.

## Tests

- API persistence across new application clients.
- file metadata, checksum, download and delete.
- backup/restore of database and Storage objects.
- Q4 intelligence based on Q1–Q3.
- import review and commit.
- budget-constrained Low/Base/High simulation.
- optional Agent disabled safely without exposing a key.
- opt-in real Supabase persistence test.

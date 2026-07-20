# EMBA TAU Simulation AI Decision OS v1.6 Architecture

```text
Team browser
    │ HTTPS + shared access password
    ▼
Render FastAPI service
    ├── file extraction and review workflow
    ├── deterministic scoring, finance, pricing and simulation engines
    ├── quarterly Digital Twin with immutable Actual baseline
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
- `digital_twin.py` — immutable baseline snapshots and quarter-by-quarter state transitions through Q9.
- `agent_service.py` — optional OpenAI Responses API orchestration with read-only function tools.
- `backup_service.py` — complete portable ZIP with integrity checks.
- `db.py` / `cloud.py` — repository layer over Supabase Data and Storage APIs.
- `rulebook.py` — Rulebook versioned, deterministic rule checks, report validation and portfolio enforcement.
- `agent_service.py` — Responses API orchestration with server-side tools and auditable AI runs.
- `analytics.py` — financial state, Q9 forecast, scenarios, budget sequencing and economic impacts.

## Digital Twin

- `digital_twin_snapshots` stores a locked baseline derived from approved Actuals.
- `digital_twin_runs` stores every Low/Base/High projection and its assumptions.
- `POST /api/simulation/{quarter}` runs and persists the twin alongside the deterministic portfolio result.
- `GET /api/digital-twin/{quarter}` exposes the baseline and recent runs without changing Actuals.
- The Decision Agent reads the same model through `get_digital_twin`; it cannot approve or overwrite data.
- State transitions include area cash transfers, funding, receivables timing, production and sales lag, capacity activation, inventory, technology and sales offices.

## Tests

- API persistence across new application clients.
- file metadata, checksum, download and delete.
- backup/restore of database and Storage objects.
- Q4 intelligence based on Q1–Q3.
- import review and commit.
- budget-constrained Low/Base/High simulation.
- Digital Twin transition timing, Actual immutability and persistence.
- optional Agent disabled safely without exposing a key.
- opt-in real Supabase persistence test.

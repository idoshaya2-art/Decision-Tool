# v0.4 Cloud — Release notes

## Changed

- Replaced SQLite with Supabase PostgreSQL through the server-side Data API.
- Replaced `data/uploads` with a private Supabase Storage bucket.
- Removed all runtime dependencies on Render local filesystem persistence.
- Rebuilt the missing static UI included in the GitHub copy of v0.3.
- Updated integer application IDs to PostgreSQL UUIDs in the fresh cloud schema.

## Added

- Environment validation and a secret-free `.env.example`.
- Shared-link password protection.
- Automatic save indicator and debounced settings/finance saves.
- File metadata, SHA-256 checksum, MIME type, size and audit details.
- Complete ZIP backup and validated Replace/Merge restore.
- Cloud reset that removes Storage objects and company records.
- Supabase SQL schema with RLS and private bucket creation.
- Render Blueprint.
- Unit, API, backup/restore, static persistence and opt-in Supabase integration tests.
- Hebrew deployment checklist and post-deploy verification script.

## Migration note

v0.4 is designed for the empty v0.3 platform. It creates a fresh Supabase schema and does not import a legacy SQLite file automatically. Existing v0.3 data, if any, should be exported to JSON/files and migrated separately before the production system is used.

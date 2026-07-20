begin;

create table if not exists public.decision_sessions (
    id uuid primary key default gen_random_uuid(), quarter text not null, name text not null,
    status text not null default 'draft',
    decision_pack_id uuid references public.decision_packs(id) on delete set null,
    optimization_run_id uuid references public.optimization_runs(id) on delete set null,
    rulebook_version text not null references public.rulebook_versions(version),
    snapshot jsonb not null default '{}'::jsonb, validation jsonb not null default '{}'::jsonb,
    facilitator text not null default '', approved_by jsonb not null default '[]'::jsonb,
    approved_at timestamptz, locked boolean not null default false,
    created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);

create table if not exists public.decision_votes (
    id uuid primary key default gen_random_uuid(),
    session_id uuid not null references public.decision_sessions(id) on delete cascade,
    role text not null, voter_name text not null, vote text not null,
    rationale text not null default '', concerns jsonb not null default '[]'::jsonb,
    created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
    unique (session_id, role)
);

create index if not exists decision_sessions_quarter_idx on public.decision_sessions (quarter, created_at desc);
create index if not exists decision_votes_session_idx on public.decision_votes (session_id, updated_at);

alter table public.decision_sessions enable row level security;
alter table public.decision_votes enable row level security;
revoke all on table public.decision_sessions from anon, authenticated;
revoke all on table public.decision_votes from anon, authenticated;
grant all on table public.decision_sessions to service_role;
grant all on table public.decision_votes to service_role;

commit;

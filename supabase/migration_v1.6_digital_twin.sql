begin;

create table if not exists public.digital_twin_snapshots (
    quarter text not null,
    as_of_quarter text not null default 'none',
    source_type text not null default 'approved_actual',
    state jsonb not null default '{}'::jsonb,
    locked boolean not null default true,
    rulebook_version text not null default '',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (quarter, as_of_quarter, source_type)
);

create table if not exists public.digital_twin_runs (
    id uuid primary key default gen_random_uuid(),
    quarter text not null,
    scenario_name text not null default '',
    baseline_as_of text,
    actions jsonb not null default '[]'::jsonb,
    assumptions jsonb not null default '[]'::jsonb,
    result jsonb not null default '{}'::jsonb,
    feasible boolean not null default false,
    rulebook_version text not null default '',
    created_at timestamptz not null default now()
);

create index if not exists digital_twin_runs_quarter_idx
    on public.digital_twin_runs (quarter, created_at desc);

alter table public.digital_twin_snapshots enable row level security;
alter table public.digital_twin_runs enable row level security;
revoke all on table public.digital_twin_snapshots from anon, authenticated;
revoke all on table public.digital_twin_runs from anon, authenticated;
grant all on table public.digital_twin_snapshots to service_role;
grant all on table public.digital_twin_runs to service_role;

commit;

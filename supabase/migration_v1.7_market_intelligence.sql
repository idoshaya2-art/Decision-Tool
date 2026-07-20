-- INTOPIA DSS v1.7 market-intelligence persistence
create table if not exists public.market_intelligence_runs (
    id uuid primary key default gen_random_uuid(),
    quarter text not null,
    result jsonb not null default '{}'::jsonb,
    input_fingerprint text not null default '',
    created_at timestamptz not null default now()
);
create index if not exists market_intelligence_runs_quarter_idx on public.market_intelligence_runs (quarter, created_at desc);
alter table public.market_intelligence_runs enable row level security;
revoke all on table public.market_intelligence_runs from anon, authenticated;
grant all on table public.market_intelligence_runs to service_role;

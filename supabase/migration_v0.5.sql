-- EMBA TAU Simulation v0.5 migration
-- Safe to rerun. Preserves all v0.4 company rows and Storage objects.

create extension if not exists pgcrypto;

alter table public.settings add column if not exists startup_quarter text not null default 'Q4';
alter table public.settings add column if not exists score_model jsonb not null default '{}'::jsonb;

create table if not exists public.finance_by_area (
    quarter text not null check (quarter ~ '^Q[1-9]$'),
    area text not null,
    currency text not null default '',
    fx_to_sf double precision not null default 1,
    revenue_lc double precision not null default 0,
    gross_profit_lc double precision not null default 0,
    net_profit_lc double precision not null default 0,
    ending_cash_lc double precision not null default 0,
    debt_lc double precision not null default 0,
    ar_lc double precision not null default 0,
    ap_lc double precision not null default 0,
    inventory_value_lc double precision not null default 0,
    current_assets_lc double precision not null default 0,
    current_liabilities_lc double precision not null default 0,
    equity_lc double precision not null default 0,
    total_investment_lc double precision not null default 0,
    operating_cash_flow_lc double precision not null default 0,
    capex_commitments_lc double precision not null default 0,
    source text not null default '',
    confidence text not null default 'Medium',
    notes text not null default '',
    updated_at timestamptz not null default now(),
    primary key (quarter, area)
);

create table if not exists public.report_imports (
    id uuid primary key default gen_random_uuid(),
    upload_id uuid not null references public.uploads(id) on delete cascade,
    quarter text not null,
    parser_type text not null default '',
    status text not null default 'Needs review',
    confidence text not null default 'Low',
    extracted_data jsonb not null default '{}'::jsonb,
    issues jsonb not null default '[]'::jsonb,
    reviewed_by text not null default '',
    reviewed_at timestamptz,
    committed_at timestamptz,
    created_at timestamptz not null default now()
);

create table if not exists public.research_results (
    id uuid primary key default gen_random_uuid(),
    quarter text not null,
    study_id integer references public.market_research_catalog(study_id),
    title text not null,
    area text not null default '',
    product text not null default '',
    key_result text not null default '',
    numeric_data jsonb not null default '{}'::jsonb,
    relevance_domains jsonb not null default '[]'::jsonb,
    source_upload_id uuid references public.uploads(id) on delete set null,
    confidence text not null default 'Medium',
    status text not null default 'Approved',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.strategy_profiles (
    id integer primary key check (id = 1),
    thesis text not null default '',
    priorities jsonb not null default '[]'::jsonb,
    goals jsonb not null default '[]'::jsonb,
    constraints jsonb not null default '[]'::jsonb,
    source_upload_id uuid references public.uploads(id) on delete set null,
    source_excerpt text not null default '',
    updated_at timestamptz not null default now()
);

create table if not exists public.strategic_assessments (
    quarter text primary key check (quarter ~ '^Q[1-9]$'),
    reputation_score double precision,
    ethics_score double precision,
    partnerships_score double precision,
    market_trend_score double precision,
    source text not null default '',
    notes text not null default '',
    updated_at timestamptz not null default now()
);

create table if not exists public.scenario_portfolios (
    id uuid primary key default gen_random_uuid(),
    quarter text not null check (quarter ~ '^Q[1-9]$'),
    name text not null,
    objective text not null default 'Maximize Q9 score',
    budget_sf double precision not null default 0,
    cash_buffer_sf double precision not null default 0,
    actions jsonb not null default '[]'::jsonb,
    result jsonb not null default '{}'::jsonb,
    status text not null default 'Draft',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.quarter_snapshots (
    quarter text primary key check (quarter ~ '^Q[1-9]$'),
    payload jsonb not null default '{}'::jsonb,
    locked boolean not null default false,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.agent_threads (
    id uuid primary key default gen_random_uuid(),
    title text not null default 'New conversation',
    quarter text not null default 'Q4',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.agent_messages (
    id uuid primary key default gen_random_uuid(),
    thread_id uuid not null references public.agent_threads(id) on delete cascade,
    role text not null check (role in ('user', 'assistant')),
    content text not null,
    citations jsonb not null default '[]'::jsonb,
    created_at timestamptz not null default now()
);

create index if not exists finance_area_quarter_idx on public.finance_by_area (quarter);
create index if not exists report_imports_quarter_idx on public.report_imports (quarter, created_at desc);
create index if not exists research_results_quarter_idx on public.research_results (quarter, created_at desc);
create index if not exists scenario_portfolios_quarter_idx on public.scenario_portfolios (quarter, created_at desc);
create index if not exists agent_messages_thread_idx on public.agent_messages (thread_id, created_at);

do $$
declare table_name text;
begin
  foreach table_name in array array[
    'finance_by_area', 'report_imports', 'research_results', 'strategy_profiles', 'strategic_assessments',
    'scenario_portfolios', 'quarter_snapshots', 'agent_threads', 'agent_messages'
  ]
  loop
    execute format('alter table public.%I enable row level security', table_name);
    execute format('revoke all on table public.%I from anon, authenticated', table_name);
    execute format('grant all on table public.%I to service_role', table_name);
  end loop;
end $$;

update public.settings
set selected_quarter = 'Q4', startup_quarter = 'Q4', updated_at = now()
where id = 1
  and selected_quarter = 'Q1'
  and exists (select 1 from public.quarter_finance where quarter = 'Q3');

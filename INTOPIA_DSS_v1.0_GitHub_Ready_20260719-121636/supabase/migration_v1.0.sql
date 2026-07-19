-- EMBA TAU Simulation AI Decision OS v1.0
-- Safe migration: adds versioned rulebook, evidence, forecasts, AI audit and decision packs.

create extension if not exists pgcrypto;

alter table public.report_imports
    add column if not exists rule_validation jsonb not null default '{}'::jsonb;

create table if not exists public.rule_sources (
    source_id text primary key,
    name text not null,
    source_type text not null,
    priority integer not null,
    status text not null,
    version_label text not null default '',
    notes text not null default '',
    updated_at timestamptz not null default now()
);

create table if not exists public.rulebook_versions (
    version text primary key,
    status text not null,
    name text not null,
    source_priority jsonb not null default '[]'::jsonb,
    approved_by text not null default '',
    approved_at timestamptz,
    created_at timestamptz not null default now()
);

create table if not exists public.rules (
    rule_id text not null,
    version text not null references public.rulebook_versions(version),
    name_he text not null,
    name_en text not null,
    knowledge_type text not null,
    domain text not null,
    areas jsonb not null default '[]'::jsonb,
    products jsonb not null default '[]'::jsonb,
    quarters jsonb not null default '[]'::jsonb,
    condition jsonb not null default '{}'::jsonb,
    effect jsonb not null default '{}'::jsonb,
    units text not null default '',
    currency text not null default '',
    exceptions jsonb not null default '[]'::jsonb,
    dependencies jsonb not null default '[]'::jsonb,
    source_id text not null references public.rule_sources(source_id),
    source_page text not null default '',
    pdf_page integer,
    source_section text not null default '',
    confidence text not null default 'high',
    enforcement text not null default 'warning',
    is_blocking boolean not null default false,
    approval_status text not null default 'approved',
    effective_from text not null default 'Q1',
    effective_to text not null default 'Q9',
    description text not null default '',
    test_cases jsonb not null default '[]'::jsonb,
    updated_at timestamptz not null default now(),
    primary key (rule_id, version)
);

create table if not exists public.rule_conflicts (
    id uuid primary key default gen_random_uuid(),
    rule_id text not null default '',
    existing_version text not null default '',
    candidate_source_id text not null default '',
    candidate_value jsonb not null default '{}'::jsonb,
    description text not null default '',
    status text not null default 'open',
    resolution text not null default '',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.document_chunks (
    id uuid primary key default gen_random_uuid(),
    upload_id uuid references public.uploads(id) on delete cascade,
    source_id text not null default '',
    page integer,
    section text not null default '',
    content text not null,
    content_hash text not null default '',
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create table if not exists public.ai_runs (
    id uuid primary key default gen_random_uuid(),
    run_type text not null default 'chat',
    quarter text not null default '',
    model text not null default '',
    status text not null default 'completed',
    input_summary text not null default '',
    output_summary text not null default '',
    tool_calls jsonb not null default '[]'::jsonb,
    sources jsonb not null default '[]'::jsonb,
    error text not null default '',
    created_at timestamptz not null default now()
);

create table if not exists public.forecasts (
    id uuid primary key default gen_random_uuid(),
    quarter text not null,
    forecast_type text not null default 'q9',
    rulebook_version text not null references public.rulebook_versions(version),
    assumptions jsonb not null default '[]'::jsonb,
    result jsonb not null default '{}'::jsonb,
    confidence text not null default 'medium',
    created_at timestamptz not null default now()
);

create table if not exists public.decision_packs (
    id uuid primary key default gen_random_uuid(),
    quarter text not null,
    name text not null,
    status text not null default 'draft',
    rulebook_version text not null references public.rulebook_versions(version),
    scenario_portfolio_id uuid references public.scenario_portfolios(id) on delete set null,
    actions jsonb not null default '[]'::jsonb,
    validation jsonb not null default '{}'::jsonb,
    financial_impact jsonb not null default '{}'::jsonb,
    q9_impact jsonb not null default '{}'::jsonb,
    recommendation text not null default '',
    created_by text not null default 'team',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.recommendation_evidence (
    id uuid primary key default gen_random_uuid(),
    decision_pack_id uuid references public.decision_packs(id) on delete cascade,
    recommendation_key text not null default '',
    evidence_type text not null,
    source_id text not null default '',
    source_page text not null default '',
    rule_id text not null default '',
    payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create table if not exists public.optimization_runs (
    id uuid primary key default gen_random_uuid(),
    quarter text not null,
    optimization_type text not null default 'budget',
    rulebook_version text not null references public.rulebook_versions(version),
    constraints jsonb not null default '{}'::jsonb,
    candidates jsonb not null default '[]'::jsonb,
    result jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create index if not exists rules_domain_idx on public.rules (domain, knowledge_type);
create index if not exists rules_source_idx on public.rules (source_id);
create index if not exists rule_conflicts_status_idx on public.rule_conflicts (status, created_at desc);
create index if not exists document_chunks_upload_idx on public.document_chunks (upload_id, page);
create index if not exists ai_runs_quarter_idx on public.ai_runs (quarter, created_at desc);
create index if not exists forecasts_quarter_idx on public.forecasts (quarter, created_at desc);
create index if not exists decision_packs_quarter_idx on public.decision_packs (quarter, created_at desc);

do $$
declare table_name text;
begin
  foreach table_name in array array[
    'rule_sources', 'rulebook_versions', 'rules', 'rule_conflicts', 'document_chunks',
    'ai_runs', 'forecasts', 'decision_packs', 'recommendation_evidence', 'optimization_runs'
  ]
  loop
    execute format('alter table public.%I enable row level security', table_name);
    execute format('revoke all on table public.%I from anon, authenticated', table_name);
    execute format('grant all on table public.%I to service_role', table_name);
  end loop;
end $$;

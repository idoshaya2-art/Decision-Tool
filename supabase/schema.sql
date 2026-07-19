-- EMBA TAU Simulation v0.5 Decision Intelligence
-- Safe to run over an existing v0.4 database. Existing company data is preserved.

create extension if not exists pgcrypto;

create table if not exists public.settings (
    id integer primary key check (id = 1),
    company_name text not null default '',
    selected_quarter text not null default 'Q4' check (selected_quarter ~ '^Q[1-9]$'),
    startup_quarter text not null default 'Q4' check (startup_quarter ~ '^Q[1-9]$'),
    cash_buffer_sf double precision not null default 0,
    min_rd_sf double precision not null default 0,
    score_model jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

alter table public.settings add column if not exists startup_quarter text not null default 'Q4';
alter table public.settings add column if not exists score_model jsonb not null default '{}'::jsonb;

create table if not exists public.reference_area_product (
    area text not null,
    product text not null,
    currency text not null,
    fx_to_sf double precision not null,
    tax_rate double precision not null,
    plant_capacity double precision not null,
    plant_cost_lc double precision not null,
    initial_price_lc double precision not null,
    inventory_cost double precision not null,
    primary key (area, product)
);

create table if not exists public.quarter_finance (
    quarter text primary key check (quarter ~ '^Q[1-9]$'),
    revenue_sf double precision not null default 0,
    gross_profit_sf double precision not null default 0,
    net_profit_sf double precision not null default 0,
    ending_cash_sf double precision not null default 0,
    debt_sf double precision not null default 0,
    ar_sf double precision not null default 0,
    ap_sf double precision not null default 0,
    research_budget_sf double precision not null default 0,
    rd_x_sf double precision not null default 0,
    rd_y_sf double precision not null default 0,
    partnership_score double precision not null default 0,
    dividends_sf double precision not null default 0,
    notes text not null default '',
    updated_at timestamptz not null default now()
);

create table if not exists public.operations (
    id uuid primary key default gen_random_uuid(),
    quarter text not null check (quarter ~ '^Q[1-9]$'),
    area text not null,
      product text not null,
      model text not null,
      fx_to_sf double precision not null default 1,
      grade integer not null default 0,
    plants double precision not null default 0,
    plant_capacity double precision not null default 0,
    planned_production double precision not null default 0,
    actual_production double precision not null default 0,
    opening_inventory double precision not null default 0,
    planned_sales double precision not null default 0,
    actual_sales double precision not null default 0,
    ending_inventory double precision not null default 0,
    forecast_demand double precision not null default 0,
    planned_price_lc double precision not null default 0,
    actual_price_lc double precision not null default 0,
    advertising_lc double precision not null default 0,
    variable_cost_lc double precision not null default 0,
    fixed_cost_lc double precision not null default 0,
    methods_improvement_lc double precision not null default 0,
    sales_channel text not null default 'Agents',
    actual_market_share double precision not null default 0,
    source text not null default '',
    confidence text not null default 'בינונית',
    notes text not null default '',
    updated_at timestamptz not null default now(),
    unique (quarter, area, product, model)
);

create table if not exists public.facts (
    id uuid primary key default gen_random_uuid(),
    quarter text not null,
    source_type text not null,
    source_name text not null default '',
    area text not null default '',
    product text not null default '',
    company text not null default '',
    metric text not null,
    value double precision,
    text_value text not null default '',
    unit text not null default '',
    confidence text not null default 'בינונית',
    notes text not null default '',
    created_at timestamptz not null default now()
);

create table if not exists public.uploads (
    id uuid primary key default gen_random_uuid(),
    quarter text not null,
    category text not null,
    original_name text not null,
    storage_bucket text not null,
    storage_path text not null,
    mime_type text not null default 'application/octet-stream',
    size_bytes bigint not null default 0 check (size_bytes >= 0),
    sha256 text not null check (length(sha256) = 64),
    etag text not null default '',
    notes text not null default '',
    uploaded_by text not null default 'team',
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    unique (storage_bucket, storage_path)
);

create table if not exists public.decisions (
    id uuid primary key default gen_random_uuid(),
    quarter text not null,
    domain text not null,
    title text not null,
    question text not null default '',
    selected_option text not null default '',
    rationale text not null default '',
    owner text not null default '',
    status text not null default 'פתוח',
    expected_result text not null default '',
    actual_result text not null default '',
    confidence text not null default 'בינונית',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.scenarios (
    id uuid primary key default gen_random_uuid(),
    quarter text not null,
    name text not null,
    area text not null,
    product text not null,
    grade integer not null default 0,
    price_lc double precision not null default 0,
    demand double precision not null default 0,
    production double precision not null default 0,
    opening_inventory double precision not null default 0,
    variable_cost_lc double precision not null default 0,
    advertising_lc double precision not null default 0,
    fixed_cost_lc double precision not null default 0,
    transport_per_unit_lc double precision not null default 0,
    inventory_cost_per_unit_lc double precision not null default 0,
    tax_rate double precision not null default 0,
    fx_to_sf double precision not null default 1,
    notes text not null default '',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.tests (
    id uuid primary key default gen_random_uuid(),
    quarter text not null,
    name text not null,
    hypothesis text not null default '',
    changed_variables text not null default '',
    expected_result text not null default '',
    actual_result text not null default '',
    decision text not null default '',
    confidence text not null default 'בינונית',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.market_research_catalog (
    study_id integer primary key,
    name text not null,
    description text not null,
    cost_k_sf double precision,
    use_case text not null,
    default_priority text not null,
    note text not null default ''
);

create table if not exists public.research_plan (
    id uuid primary key default gen_random_uuid(),
    quarter text not null,
    study_id integer not null references public.market_research_catalog(study_id),
    decision_supported text not null default '',
    key_result text not null default '',
    action text not null default '',
    status text not null default 'מתוכנן',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (quarter, study_id)
);

create table if not exists public.strategy_principles (
    id integer primary key,
    principle text not null,
    rationale text not null,
    leading_metric text not null,
    decision_gate text not null,
    status text not null
);

create table if not exists public.milestones (
    quarter text primary key,
    strategic_goal text not null,
    required_signal text not null,
    positive_action text not null,
    negative_action text not null,
    investment_sf double precision not null default 0,
    owner text not null default '',
    status text not null default 'לא התחיל',
    result text not null default '',
    strategic_update text not null default ''
);

create table if not exists public.audit_log (
    id uuid primary key default gen_random_uuid(),
    action text not null,
    entity text not null,
    record_id text not null default '',
    actor text not null default 'team',
    details jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

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
    confidence text not null default 'בינונית',
    notes text not null default '',
    updated_at timestamptz not null default now(),
    primary key (quarter, area)
);

create table if not exists public.report_imports (
    id uuid primary key default gen_random_uuid(),
    upload_id uuid not null references public.uploads(id) on delete cascade,
    quarter text not null,
    parser_type text not null default '',
    status text not null default 'נדרשת בדיקה',
    confidence text not null default 'נמוכה',
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
    confidence text not null default 'בינונית',
    status text not null default 'מאושר',
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
    objective text not null default 'מקסום ציון Q9',
    budget_sf double precision not null default 0,
    cash_buffer_sf double precision not null default 0,
    actions jsonb not null default '[]'::jsonb,
    result jsonb not null default '{}'::jsonb,
    status text not null default 'טיוטה',
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
    title text not null default 'שיחה חדשה',
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

create index if not exists operations_quarter_idx on public.operations (quarter);
create index if not exists facts_quarter_created_idx on public.facts (quarter, created_at desc);
create index if not exists uploads_quarter_created_idx on public.uploads (quarter, created_at desc);
create index if not exists decisions_quarter_created_idx on public.decisions (quarter, created_at desc);
create index if not exists audit_created_idx on public.audit_log (created_at desc);
create index if not exists finance_area_quarter_idx on public.finance_by_area (quarter);
create index if not exists report_imports_quarter_idx on public.report_imports (quarter, created_at desc);
create index if not exists research_results_quarter_idx on public.research_results (quarter, created_at desc);
create index if not exists scenario_portfolios_quarter_idx on public.scenario_portfolios (quarter, created_at desc);
create index if not exists agent_messages_thread_idx on public.agent_messages (thread_id, created_at);

-- The browser never receives a Supabase key. Only the trusted FastAPI server uses
-- the server secret key. RLS therefore remains enabled with no anon policies.
do $$
declare table_name text;
begin
  foreach table_name in array array[
    'settings', 'reference_area_product', 'quarter_finance', 'operations', 'facts',
    'uploads', 'decisions', 'scenarios', 'tests', 'market_research_catalog',
    'research_plan', 'strategy_principles', 'milestones', 'audit_log',
    'finance_by_area', 'report_imports', 'research_results', 'strategic_assessments',
    'strategy_profiles', 'scenario_portfolios', 'quarter_snapshots', 'agent_threads', 'agent_messages'
  ]
  loop
    execute format('alter table public.%I enable row level security', table_name);
    execute format('revoke all on table public.%I from anon, authenticated', table_name);
    execute format('grant all on table public.%I to service_role', table_name);
  end loop;
end $$;

insert into storage.buckets (id, name, public, file_size_limit)
values ('intopia-files', 'intopia-files', false, 10485760)
on conflict (id) do update
set public = false,
    file_size_limit = excluded.file_size_limit;

insert into public.settings (id, company_name, selected_quarter, created_at, updated_at)
values (1, '', 'Q4', now(), now())
on conflict (id) do nothing;

update public.settings
set selected_quarter = 'Q4', startup_quarter = 'Q4', updated_at = now()
where id = 1
  and selected_quarter = 'Q1'
  and exists (select 1 from public.quarter_finance where quarter = 'Q3');

-- v1.0 Decision OS entities. Kept in the full schema so a new project needs
-- only this file; existing projects can run migration_v1.0.sql instead.
alter table public.report_imports
    add column if not exists rule_validation jsonb not null default '{}'::jsonb;

create table if not exists public.rule_sources (
    source_id text primary key, name text not null, source_type text not null,
    priority integer not null, status text not null, version_label text not null default '',
    notes text not null default '', updated_at timestamptz not null default now()
);
create table if not exists public.rulebook_versions (
    version text primary key, status text not null, name text not null,
    source_priority jsonb not null default '[]'::jsonb, approved_by text not null default '',
    approved_at timestamptz, created_at timestamptz not null default now()
);
create table if not exists public.rules (
    rule_id text not null, version text not null references public.rulebook_versions(version),
    name_he text not null, name_en text not null, knowledge_type text not null, domain text not null,
    areas jsonb not null default '[]'::jsonb, products jsonb not null default '[]'::jsonb,
    quarters jsonb not null default '[]'::jsonb, condition jsonb not null default '{}'::jsonb,
    effect jsonb not null default '{}'::jsonb, units text not null default '', currency text not null default '',
    exceptions jsonb not null default '[]'::jsonb, dependencies jsonb not null default '[]'::jsonb,
    source_id text not null references public.rule_sources(source_id), source_page text not null default '',
    pdf_page integer, source_section text not null default '', confidence text not null default 'high',
    enforcement text not null default 'warning', is_blocking boolean not null default false,
    approval_status text not null default 'approved', effective_from text not null default 'Q1',
    effective_to text not null default 'Q9', description text not null default '',
    test_cases jsonb not null default '[]'::jsonb, updated_at timestamptz not null default now(),
    primary key (rule_id, version)
);
create table if not exists public.rule_conflicts (
    id uuid primary key default gen_random_uuid(), rule_id text not null default '',
    existing_version text not null default '', candidate_source_id text not null default '',
    candidate_value jsonb not null default '{}'::jsonb, description text not null default '',
    status text not null default 'open', resolution text not null default '',
    created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create table if not exists public.document_chunks (
    id uuid primary key default gen_random_uuid(), upload_id uuid references public.uploads(id) on delete cascade,
    source_id text not null default '', page integer, section text not null default '', content text not null,
    content_hash text not null default '', metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);
create table if not exists public.ai_runs (
    id uuid primary key default gen_random_uuid(), run_type text not null default 'chat',
    quarter text not null default '', model text not null default '', status text not null default 'completed',
    input_summary text not null default '', output_summary text not null default '',
    tool_calls jsonb not null default '[]'::jsonb, sources jsonb not null default '[]'::jsonb,
    error text not null default '', created_at timestamptz not null default now()
);
create table if not exists public.forecasts (
    id uuid primary key default gen_random_uuid(), quarter text not null,
    forecast_type text not null default 'q9', rulebook_version text not null references public.rulebook_versions(version),
    assumptions jsonb not null default '[]'::jsonb, result jsonb not null default '{}'::jsonb,
    confidence text not null default 'medium', created_at timestamptz not null default now()
);
create table if not exists public.decision_packs (
    id uuid primary key default gen_random_uuid(), quarter text not null, name text not null,
    status text not null default 'draft', rulebook_version text not null references public.rulebook_versions(version),
    scenario_portfolio_id uuid references public.scenario_portfolios(id) on delete set null,
    actions jsonb not null default '[]'::jsonb, validation jsonb not null default '{}'::jsonb,
    financial_impact jsonb not null default '{}'::jsonb, q9_impact jsonb not null default '{}'::jsonb,
    recommendation text not null default '', created_by text not null default 'team',
    created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create table if not exists public.recommendation_evidence (
    id uuid primary key default gen_random_uuid(),
    decision_pack_id uuid references public.decision_packs(id) on delete cascade,
    recommendation_key text not null default '', evidence_type text not null, source_id text not null default '',
    source_page text not null default '', rule_id text not null default '',
    payload jsonb not null default '{}'::jsonb, created_at timestamptz not null default now()
);
create table if not exists public.optimization_runs (
    id uuid primary key default gen_random_uuid(), quarter text not null,
    optimization_type text not null default 'budget',
    rulebook_version text not null references public.rulebook_versions(version),
    constraints jsonb not null default '{}'::jsonb, candidates jsonb not null default '[]'::jsonb,
    result jsonb not null default '{}'::jsonb, created_at timestamptz not null default now()
);

create index if not exists rules_domain_idx on public.rules (domain, knowledge_type);
create index if not exists rule_conflicts_status_idx on public.rule_conflicts (status, created_at desc);
create index if not exists ai_runs_quarter_idx on public.ai_runs (quarter, created_at desc);
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

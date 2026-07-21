-- EMBA TAU Simulation v1.9 hotfix
-- Adds the v1.4-v1.6 persistence tables that are required by the live UI.
-- Safe to run more than once in the Supabase SQL Editor.

begin;

alter table public.forecasts add column if not exists source_actual_quarter text not null default '';
alter table public.forecasts add column if not exists target_quarter text not null default '';
alter table public.forecasts add column if not exists status text not null default 'open';

update public.forecasts
set target_quarter = quarter
where target_quarter = '';

create table if not exists public.forecast_evaluations (
    id uuid primary key default gen_random_uuid(),
    forecast_id uuid not null references public.forecasts(id) on delete cascade,
    source_actual_quarter text not null default '',
    target_quarter text not null,
    status text not null default 'evaluated',
    summary jsonb not null default '{}'::jsonb,
    metric_errors jsonb not null default '{}'::jsonb,
    driver_analysis jsonb not null default '[]'::jsonb,
    actual_snapshot jsonb not null default '{}'::jsonb,
    evaluated_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    unique (forecast_id)
);

create table if not exists public.calibration_proposals (
    id uuid primary key default gen_random_uuid(),
    evaluation_id uuid not null references public.forecast_evaluations(id) on delete cascade,
    parameter_key text not null,
    metric_key text not null default '',
    scope jsonb not null default '{"level":"global"}'::jsonb,
    previous_value numeric not null default 1,
    proposed_value numeric not null default 1,
    confidence text not null default 'low',
    status text not null default 'draft',
    reason text not null default '',
    evidence jsonb not null default '{}'::jsonb,
    reviewed_by text not null default '',
    approved_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.evidence_gate_runs (
    id uuid primary key default gen_random_uuid(),
    quarter text not null,
    decision_pack_id uuid references public.decision_packs(id) on delete cascade,
    recommendation_key text not null default '',
    status text not null default 'blocked',
    score numeric not null default 0,
    summary jsonb not null default '{}'::jsonb,
    claims jsonb not null default '[]'::jsonb,
    gaps jsonb not null default '[]'::jsonb,
    contradictions jsonb not null default '[]'::jsonb,
    created_at timestamptz not null default now()
);

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

create table if not exists public.market_intelligence_runs (
    id uuid primary key default gen_random_uuid(),
    quarter text not null,
    result jsonb not null default '{}'::jsonb,
    input_fingerprint text not null default '',
    created_at timestamptz not null default now()
);

create table if not exists public.decision_sessions (
    id uuid primary key default gen_random_uuid(),
    quarter text not null,
    name text not null,
    status text not null default 'draft',
    decision_pack_id uuid references public.decision_packs(id) on delete set null,
    optimization_run_id uuid references public.optimization_runs(id) on delete set null,
    rulebook_version text not null references public.rulebook_versions(version),
    snapshot jsonb not null default '{}'::jsonb,
    validation jsonb not null default '{}'::jsonb,
    facilitator text not null default '',
    approved_by jsonb not null default '[]'::jsonb,
    approved_at timestamptz,
    locked boolean not null default false,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.decision_votes (
    id uuid primary key default gen_random_uuid(),
    session_id uuid not null references public.decision_sessions(id) on delete cascade,
    role text not null,
    voter_name text not null,
    vote text not null,
    rationale text not null default '',
    concerns jsonb not null default '[]'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (session_id, role)
);

create index if not exists forecasts_target_idx on public.forecasts (target_quarter, status, created_at desc);
create index if not exists forecast_evaluations_target_idx on public.forecast_evaluations (target_quarter, evaluated_at desc);
create index if not exists calibration_proposals_status_idx on public.calibration_proposals (status, created_at desc);
create index if not exists evidence_gate_runs_quarter_idx on public.evidence_gate_runs (quarter, created_at desc);
create index if not exists digital_twin_runs_quarter_idx on public.digital_twin_runs (quarter, created_at desc);
create index if not exists market_intelligence_runs_quarter_idx on public.market_intelligence_runs (quarter, created_at desc);
create index if not exists decision_sessions_quarter_idx on public.decision_sessions (quarter, created_at desc);
create index if not exists decision_votes_session_idx on public.decision_votes (session_id, updated_at);

alter table public.forecast_evaluations enable row level security;
alter table public.calibration_proposals enable row level security;
alter table public.evidence_gate_runs enable row level security;
alter table public.digital_twin_snapshots enable row level security;
alter table public.digital_twin_runs enable row level security;
alter table public.market_intelligence_runs enable row level security;
alter table public.decision_sessions enable row level security;
alter table public.decision_votes enable row level security;

revoke all on table public.forecast_evaluations from anon, authenticated;
revoke all on table public.calibration_proposals from anon, authenticated;
revoke all on table public.evidence_gate_runs from anon, authenticated;
revoke all on table public.digital_twin_snapshots from anon, authenticated;
revoke all on table public.digital_twin_runs from anon, authenticated;
revoke all on table public.market_intelligence_runs from anon, authenticated;
revoke all on table public.decision_sessions from anon, authenticated;
revoke all on table public.decision_votes from anon, authenticated;

grant all on table public.forecast_evaluations to service_role;
grant all on table public.calibration_proposals to service_role;
grant all on table public.evidence_gate_runs to service_role;
grant all on table public.digital_twin_snapshots to service_role;
grant all on table public.digital_twin_runs to service_role;
grant all on table public.market_intelligence_runs to service_role;
grant all on table public.decision_sessions to service_role;
grant all on table public.decision_votes to service_role;

commit;

notify pgrst, 'reload schema';

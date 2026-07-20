-- EMBA TAU Simulation v1.4: Forecast -> Actual Learning Ledger
-- Safe to run more than once in Supabase SQL Editor.

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

create index if not exists forecasts_target_idx on public.forecasts (target_quarter, status, created_at desc);
create index if not exists forecast_evaluations_target_idx on public.forecast_evaluations (target_quarter, evaluated_at desc);
create index if not exists calibration_proposals_status_idx on public.calibration_proposals (status, created_at desc);

alter table public.forecast_evaluations enable row level security;
alter table public.calibration_proposals enable row level security;
revoke all on table public.forecast_evaluations from anon, authenticated;
revoke all on table public.calibration_proposals from anon, authenticated;
grant all on table public.forecast_evaluations to service_role;
grant all on table public.calibration_proposals to service_role;

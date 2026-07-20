begin;

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

create index if not exists evidence_gate_runs_quarter_idx
    on public.evidence_gate_runs (quarter, created_at desc);

alter table public.evidence_gate_runs enable row level security;
revoke all on table public.evidence_gate_runs from anon, authenticated;
grant all on table public.evidence_gate_runs to service_role;

commit;

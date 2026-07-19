-- INTOPIA DSS v0.6: preserve the quarterly currency conversion together with
-- each operating row. Safe to run more than once.

alter table public.operations
  add column if not exists fx_to_sf double precision not null default 1;

comment on column public.operations.fx_to_sf is
  'Current-quarter conversion factor from local currency to SF, extracted from the Currency sheet.';

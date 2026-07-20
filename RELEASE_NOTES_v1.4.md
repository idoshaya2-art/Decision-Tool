# v1.4 — Forecast→Actual Learning Ledger

## Outcome

The platform now preserves what it predicted before a quarter, compares it with approved Actuals, diagnoses likely drivers, and proposes controlled model calibration. Historical forecasts and Actuals remain immutable.

## Added

- Locked Q+1 and Q9 forecast snapshots.
- Forecast evaluation by revenue, gross profit, net profit, cash, sales, production, inventory and market share.
- Weighted accuracy score and range coverage.
- Driver analysis for demand, margin, operating costs, working capital and inventory.
- Human-approved calibration proposals.
- Learning Ledger UI under cumulative insights.
- Decision Agent access through `get_learning_ledger`.
- Supabase tables `forecast_evaluations` and `calibration_proposals`.
- Backup and restore coverage for all learning records.

## Upgrade

Run `supabase/migration_v1.4_learning.sql` once in the Supabase SQL Editor before deploying this version to an existing project.

## Safety

- Draft calibrations never affect forecasts.
- Approved calibrations affect future forecasts only.
- Actuals and historical forecast snapshots are never rewritten by the learning engine.

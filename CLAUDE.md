# Accurova PhotoVault Tracker — project-specific

## This sheet is shared with the Accurova Workflow Dashboard
When pointed at the same Google Sheet as the
[Workflow Dashboard](../accurova-workflow-dashboard), six columns past
`Remarks` (`Workflow Status`, `Client`, `Type`, `Priority`, `Tags`,
`Client Token`) belong to that app, not this one. `sync_engine.py` never
reads or computes them — `DASHBOARD_COLUMNS` just lists them so every
rewrite path (`sync_to_sheet`, `_bulk_rewrite_preserving_remarks`,
`_full_rewrite`) carries them through untouched, the same treatment
`Remarks` already got. If the dashboard adds another column of its own,
add it to `DASHBOARD_COLUMNS` here too — anything left out gets blanked by
a bulk rewrite.

This script's own `Status` column (`Fully Processed`/`Partially
Processed`/`Unprocessed`, computed here and rewritten on every scan) is
deliberately a different column from the dashboard's `Workflow Status`
(human-set, e.g. `Editing`/`Delivered`). They used to share the name
`Status`, which meant a scan would silently clobber whatever stage was set
on the dashboard. Don't reuse `Status` for anything dashboard-facing.

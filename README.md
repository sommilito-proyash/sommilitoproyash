# সম্মিলিত প্রয়াস — Version 6.4

## What's new
- Per-year Mandatory/Optional month selection for all 12 months.
- Select All / Clear All for Mandatory Months.
- Only unpaid Mandatory months create arrears.
- Optional months can be paid in advance; all actual monthly payments count toward Total Deposit.
- Grand Total Deposit and Grand Total Arrear on the home page.
- Year-by-year Deposit/Arrear summaries, newest year first.
- Blood Group and Personal Email fields for member profiles (both optional).
- Existing Common Member Login remains unchanged.
- Logo and responsive visual refresh across pages.
- Existing Down Payment 1/2 functionality retained.
- Bulk database reads retained for performance.

## Important: run migration first
In Supabase SQL Editor, run **v6.4_supabase_migration.sql** once before deploying/using the new admin fields.

The migration preserves existing data and defaults existing years to all 12 months Mandatory. Admin can then change each year to the desired Mandatory months.

## Calculation rule
For a year with monthly amount M:
- Deposit = every month actually marked paid × M, including optional/advance months.
- Arrear = every Mandatory month not marked paid × M.
- Unpaid Optional months do not create arrears.
- Mandatory Down Payments remain included in arrears until marked paid.

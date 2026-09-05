# সম্মিলিত প্রয়াস — Version 6.5

## V6.5 updates
- Existing V6.4 features and calculations are preserved.
- Admin Dashboard with current-year summary.
- Year-wise Deposit/Arrear visual chart on Home and Admin pages.
- Monthly Collection Report by year/month in Admin.
- Printable annual financial report.
- Downloadable annual CSV report.
- Downloadable database-data backup (JSON).
- Safe Admin option to delete an incorrectly added year.
- The final remaining year cannot be deleted.
- Year deletion removes that year's annual records/settings before removing the year.

## Backup note
The JSON backup contains application/database data: members, years, annual records, annual settings, notices and comments. It intentionally excludes login password hashes and secrets. Member photo files remain in Supabase Storage; their saved URLs are preserved in the member data.

## Calculation rule
The existing V6.4 calculation rules remain unchanged:
- Deposit = every month actually marked paid × that year's monthly amount, including optional/advance months.
- Arrear = every Mandatory month not marked paid × that year's monthly amount.
- Unpaid Optional months do not create arrears.
- Mandatory Down Payments remain included in arrears until marked paid.

## Deployment
No new Supabase migration is required for V6.5 because all new features use the existing V6.4 tables/columns. Deploy the updated project files to the existing GitHub/Render setup.

V6.5.1 adds an English navigation bar with Home icon, selectable year chart types (Bar/Line/Pie), and keeps V6.5 functionality intact.

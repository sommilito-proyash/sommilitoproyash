# সম্মিলিত প্রয়াস — Version 6.2

Version 6.1-এর উপর ভিত্তি করে:
- Common Member Login
- আলাদা Admin Login
- Admin Panel থেকে Common Member Email/Password পরিবর্তন
- Member login ছাড়া website-এর member/accounting information দেখা যাবে না
- Existing Supabase accounting structure unchanged

## Deployment
1. Existing V6.1 files-এর backup রাখুন।
2. এই package-এর changed files repository-তে update করুন।
3. Supabase SQL Editor-এ `v6.2_supabase.sql` একবার Run করুন।
4. Render Environment Variables-এ `MEMBER_EMAIL` এবং `MEMBER_PASSWORD` দিন।
5. Render latest commit deploy করুন।
6. Admin Login করে Member Login Settings থেকে common credentials পরিবর্তন করুন।


## Version 6.3 additions
- Per-year Monthly Contribution setting (blank = member's existing monthly amount).
- Down Payment 1 and 2 can each be Mandatory or Optional per year.
- Each DP has a separate annual amount.
- Admin marks each member's DP Paid/Unpaid with the same ✓/— style as monthly payments.
- Mandatory unpaid DP is included in arrears; optional unpaid DP is not.
- Paid optional/mandatory DP is included in paid totals.
- Home/member pages show all-years Grand Total Paid and Grand Total Arrear.
- Run `v6.3_supabase_migration.sql` once in Supabase SQL Editor before using the new settings.


## Version 6.3.1 — Speed Optimized
This version keeps the V6.3 features and calculation rules unchanged. It reduces Supabase round-trips by loading annual records and annual settings in bulk on Home, Member, and Admin pages. No `.env` file is included; keep the existing `.env` from your working installation private.

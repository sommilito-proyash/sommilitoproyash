# সম্মিলিত প্রয়াস — Version 6.1

V6 is based on the supplied Version 5 project and keeps the existing Supabase tables/data while adding the new yearly accounting rules and member login.

## Version 6.1 improvements
- Faster year switching and page loading: yearly settings and all annual payment records are loaded in bulk instead of one Supabase query per member/year.
- Faster overall totals across all years for the same reason.
- The accounting rules and login model from V6 are unchanged.

## What changed
- Monthly contribution is set **separately for each year**.
- Two Down Payment options remain available every year.
- Each Down Payment can independently be marked **Mandatory** for a selected year and given an amount.
- A mandatory unpaid Down Payment becomes arrear; Admin can mark each member's Down Payment as Paid/Due.
- Yearly Deposit and Arrear include monthly contributions plus mandatory Down Payments.
- Overall Deposit and Arrear are calculated across all years.
- Each member has year-wise and overall totals.
- Public visitors can no longer see financial/member information. Login is required.
- Members log in with their email and password and can view the member information pages.
- Only Admin can edit members, payment records, yearly rules, notices and member status.
- Admin can set/reset a member's login password from Edit Member.
- Existing Notice Board, comments, member add/remove, photos and English month/year labels are retained.

## Important: Supabase SQL
Run `v6_supabase.sql` once in **Supabase → SQL Editor** before starting V6. It adds:
- `annual_settings`
- `annual_records.down_payment_1_paid`
- `annual_records.down_payment_2_paid`
- `members.password_hash`

The old `members.monthly` column is retained for compatibility, but V6 yearly calculations use `annual_settings.monthly_amount`.

## Member login
Each active member needs an email and password. Admin can set or reset both the email and password from **Admin → Edit**. Until an email and password are saved for a member, that member cannot use Member Login. Passwords are stored as hashes, not plain text. Passwords are stored as hashes, not plain text.

## Local run
Keep your existing `.env` file with:
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `SECRET_KEY`
- `ADMIN_PASSWORD`

Then:
```bash
pip install -r requirements.txt
python app.py
```

Do not put the Supabase service-role key in frontend files or GitHub.

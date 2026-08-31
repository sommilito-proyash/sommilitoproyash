-- সম্মিলিত প্রয়াস Version 6.3
-- Safe migration: existing V6.2 tables/data are preserved.
-- Run this ONCE in Supabase SQL Editor before using the new Year Settings / DP toggle.

create table if not exists public.annual_settings (
    year integer primary key references public.years(year) on delete cascade,
    monthly_amount numeric,
    down_payment_1_required boolean not null default false,
    down_payment_1_amount numeric not null default 0,
    down_payment_2_required boolean not null default false,
    down_payment_2_amount numeric not null default 0,
    updated_at timestamptz not null default now()
);

alter table public.annual_records
    add column if not exists down_payment_1_paid boolean not null default false;

alter table public.annual_records
    add column if not exists down_payment_2_paid boolean not null default false;

alter table public.annual_settings enable row level security;

-- Flask uses the Supabase service-role key, so no anon policy is needed.
-- Create a default settings row for every existing year.
insert into public.annual_settings (year, monthly_amount)
select y.year, null
from public.years y
where not exists (
    select 1 from public.annual_settings s where s.year = y.year
);

-- Existing V6.2 records with a positive down_payment amount represented a paid amount.
-- Preserve that information in the new paid flags.
update public.annual_records
set down_payment_1_paid = true
where coalesce(down_payment_1, 0) > 0
  and coalesce(down_payment_1_paid, false) = false;

update public.annual_records
set down_payment_2_paid = true
where coalesce(down_payment_2, 0) > 0
  and coalesce(down_payment_2_paid, false) = false;

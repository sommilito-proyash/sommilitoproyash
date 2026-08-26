-- সম্মিলিত প্রয়াস Version 6
-- Run this in Supabase SQL Editor BEFORE running V6.

create table if not exists annual_settings (
  year integer primary key references years(year) on delete cascade,
  monthly_amount numeric not null default 0,
  down_payment_1_required boolean not null default false,
  down_payment_1_amount numeric not null default 0,
  down_payment_2_required boolean not null default false,
  down_payment_2_amount numeric not null default 0,
  updated_at timestamptz default now()
);

alter table annual_records add column if not exists down_payment_1_paid boolean not null default false;
alter table annual_records add column if not exists down_payment_2_paid boolean not null default false;
alter table members add column if not exists password_hash text;

insert into annual_settings (year)
select year from years
where not exists (select 1 from annual_settings s where s.year=years.year);

-- V6 no longer uses members.monthly for yearly calculations.
-- It keeps the old column so existing V4/V5 data remains intact.

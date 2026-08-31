-- সম্মিলিত প্রয়াস Version 6.4 migration
-- Run once in Supabase SQL Editor.
-- Existing data is preserved. Existing years default to all 12 months Mandatory
-- so their current calculation remains unchanged until Admin edits the months.

alter table public.annual_settings
    add column if not exists mandatory_months jsonb not null default '[true,true,true,true,true,true,true,true,true,true,true,true]'::jsonb;

alter table public.members
    add column if not exists blood_group text;

alter table public.members
    add column if not exists personal_email text;

update public.annual_settings
set mandatory_months = '[true,true,true,true,true,true,true,true,true,true,true,true]'::jsonb
where mandatory_months is null;

-- Helpful indexes for fast year/member reads.
create index if not exists annual_records_year_member_idx
    on public.annual_records (year, member_id);

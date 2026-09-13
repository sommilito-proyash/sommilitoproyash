-- সম্মিলিত প্রয়াস Version 6.5.7 migration
-- Run ONCE in Supabase SQL Editor after the existing V6.5.3 migration.
-- Existing data is preserved.

-- Separate notice audiences: public visitors vs logged-in members.
alter table public.notices add column if not exists audience text not null default 'public';
update public.notices set audience = 'public' where audience is null or audience not in ('public','member');
create index if not exists notices_audience_created_idx on public.notices (audience, created_at desc);

-- Member personal and nominee information.
alter table public.members add column if not exists nid_number text;
alter table public.members add column if not exists nominee_name text;
alter table public.members add column if not exists nominee_mobile text;
alter table public.members add column if not exists nominee_nid text;
alter table public.members add column if not exists nominee_photo text;

-- Admin password stored as a hash in the database.
create table if not exists public.admin_settings (
    id integer primary key default 1 check (id = 1),
    admin_password_hash text,
    updated_at timestamptz not null default now()
);
alter table public.admin_settings enable row level security;
insert into public.admin_settings (id) values (1) on conflict (id) do nothing;

-- Existing notices remain Public unless the Admin changes their audience.

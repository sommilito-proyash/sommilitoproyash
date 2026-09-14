-- সম্মিলিত প্রয়াস Version 6.6.4 migration
-- IMPORTANT: This migration is designed for existing databases where
-- public.site_settings may already exist with a legacy column-based schema.
-- It does NOT delete or recreate existing data.
-- Run ONCE in Supabase SQL Editor. Safe to re-run.

-- 1) Create the KV site_settings table if it does not exist.
create table if not exists public.site_settings (
    key text primary key,
    value text not null default '',
    updated_at timestamptz not null default now()
);

-- 2) If site_settings already exists with a legacy schema (for example
-- id/member_email/member_password_hasl/updated_at), add the KV columns
-- instead of trying to insert into columns that do not exist.
do $$
begin
    if to_regclass('public.site_settings') is not null then
        if not exists (
            select 1 from information_schema.columns
            where table_schema='public' and table_name='site_settings' and column_name='key'
        ) then
            alter table public.site_settings add column key text;
        end if;

        if not exists (
            select 1 from information_schema.columns
            where table_schema='public' and table_name='site_settings' and column_name='value'
        ) then
            alter table public.site_settings add column value text not null default '';
        end if;

        if not exists (
            select 1 from information_schema.columns
            where table_schema='public' and table_name='site_settings' and column_name='updated_at'
        ) then
            alter table public.site_settings add column updated_at timestamptz not null default now();
        end if;
    end if;
end $$;

-- 3) Give any pre-existing legacy rows harmless unique KV keys.
-- Their original legacy columns are preserved untouched.
do $$
begin
    update public.site_settings
       set key = 'legacy_row_' || ctid::text
     where key is null;
end $$;

-- 4) The Flask application uses upsert(..., on_conflict='key'), so key
-- must be unique. A unique index works even if the old table still has
-- its original id primary key.
create unique index if not exists site_settings_key_uidx
    on public.site_settings(key);

alter table public.site_settings enable row level security;

-- 5) Seed/editable website settings. Existing values are preserved.
insert into public.site_settings (key, value)
values
    ('home_title', 'সম্মিলিত প্রয়াস'),
    ('home_purpose_title', 'আমাদের উদ্দেশ্য'),
    ('home_purpose_text', 'সমিতির সদস্যদের সম্মিলিত সঞ্চয়, পারস্পরিক সহযোগিতা এবং ভবিষ্যৎ ফ্ল্যাট নির্মাণ প্রকল্প বাস্তবায়নের লক্ষ্যে এই উদ্যোগ পরিচালিত হচ্ছে।'),
    ('about_title', 'About'),
    ('about_text', 'সম্মিলিত প্রয়াসের উদ্দেশ্য, কার্যক্রম ও সদস্যদের পারস্পরিক সহযোগিতার সংক্ষিপ্ত পরিচিতি এখানে থাকবে।'),
    ('address_text', ''),
    ('social_activity_text', ''),
    ('home_background_url', ''),
    ('private_background_url', '')
on conflict (key) do nothing;

-- 6) Preserve the old common-member login settings if they are present.
-- Supports both the correctly-spelled hash column and the historical
-- member_password_hasl typo seen in older deployments.
do $$
declare
    email_value text;
    password_value text;
    has_email boolean;
    has_hash boolean;
    has_hasl boolean;
begin
    if to_regclass('public.site_settings') is not null then
        select exists (
            select 1 from information_schema.columns
            where table_schema='public' and table_name='site_settings' and column_name='member_email'
        ) into has_email;

        select exists (
            select 1 from information_schema.columns
            where table_schema='public' and table_name='site_settings' and column_name='member_password_hash'
        ) into has_hash;

        select exists (
            select 1 from information_schema.columns
            where table_schema='public' and table_name='site_settings' and column_name='member_password_hasl'
        ) into has_hasl;

        if has_email then
            execute 'select member_email from public.site_settings order by id desc limit 1'
            into email_value;
            if email_value is not null and length(trim(email_value)) > 0 then
                insert into public.site_settings(key,value,updated_at)
                values ('member_email', trim(email_value), now())
                on conflict (key) do update set value=excluded.value, updated_at=now();
            end if;
        end if;

        if has_hash then
            execute 'select member_password_hash from public.site_settings order by id desc limit 1'
            into password_value;
        elsif has_hasl then
            execute 'select member_password_hasl from public.site_settings order by id desc limit 1'
            into password_value;
        end if;

        if password_value is not null and length(password_value) > 0 then
            insert into public.site_settings(key,value,updated_at)
            values ('member_password_hash', password_value, now())
            on conflict (key) do update set value=excluded.value, updated_at=now();
        end if;
    end if;
exception when undefined_column then
    raise notice 'Legacy member-login columns found without an id column; login bridge skipped.';
when others then
    raise notice 'Legacy member-login bridge skipped: %', sqlerrm;
end $$;

-- 7) Dedicated public bucket for Home/Private backgrounds and gallery.
insert into storage.buckets (id, name, public)
values ('site-assets', 'site-assets', true)
on conflict (id) do update set public = true;

-- Public read access is needed by get_public_url() images.
do $$
begin
    if not exists (
        select 1 from pg_policies
        where schemaname='storage'
          and tablename='objects'
          and policyname='Public read site assets'
    ) then
        create policy "Public read site assets"
        on storage.objects for select
        using (bucket_id = 'site-assets');
    end if;
end $$;

create index if not exists site_settings_updated_idx
    on public.site_settings (updated_at desc);

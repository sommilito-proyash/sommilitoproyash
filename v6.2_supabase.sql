-- সম্মিলিত প্রয়াস Version 6.2 - Member Login Migration
-- এই SQL existing data/tables মুছে ফেলবে না।
create table if not exists public.site_settings (
    key text primary key,
    value text not null default '',
    updated_at timestamptz not null default now()
);

-- প্রথমবার login চালু করার জন্য email/password environment variables ব্যবহার করা হবে।
-- Admin Panel থেকে পরে Common Member Email/Password পরিবর্তন করা যাবে।
-- Render Environment Variables:
-- MEMBER_EMAIL = আপনার Common Member Email
-- MEMBER_PASSWORD = আপনার Common Member Password

alter table public.site_settings enable row level security;

-- Service Role key দিয়ে Flask backend কাজ করে; anon user-এর জন্য settings table read policy দেওয়া হচ্ছে না।

-- সম্মিলিত প্রয়াস Version 6.5.8 migration
-- Run ONCE in Supabase SQL Editor after the existing 6.5.7 migration.
-- Existing data is preserved.
-- Nominee PINs are stored as password hashes, never as plain text.

alter table public.members add column if not exists nominee_pin_hash text;

-- Existing members with no PIN use the common initial PIN 1234.
-- The application will accept 1234 only while nominee_pin_hash is NULL,
-- then require the member to choose a different 4-digit PIN.

-- Public bucket for venue logos.
--
-- Owners upload their own logo and guests see it after scanning a table QR, so the
-- objects are world-readable by design — the URL is already printed on a sticker
-- anyone can scan. Writes go only through the API using the service-role key, so
-- no RLS policy grants the anon role insert or delete.

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'venue-logos',
  'venue-logos',
  true,
  2097152,
  array['image/png', 'image/jpeg', 'image/webp']
)
on conflict (id) do update
set public = true,
    file_size_limit = 2097152,
    allowed_mime_types = array['image/png', 'image/jpeg', 'image/webp'];

drop policy if exists "venue logos are publicly readable" on storage.objects;
create policy "venue logos are publicly readable"
  on storage.objects for select
  using (bucket_id = 'venue-logos');

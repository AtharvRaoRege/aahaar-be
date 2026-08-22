-- Instagram profile link for guest "follow us" CTAs.
alter table public.restaurants
  add column if not exists instagram_url varchar(500);

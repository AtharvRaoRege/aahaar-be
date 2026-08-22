-- Platform-wide toggles (super-admin controlled).
create table if not exists public.platform_settings (
  key text primary key,
  value text not null,
  updated_at timestamptz not null default timezone('utc', now())
);

insert into public.platform_settings (key, value)
values ('open_registration', 'false')
on conflict (key) do nothing;

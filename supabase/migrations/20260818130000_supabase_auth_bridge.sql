-- Bridge: link app users to Supabase Auth users
alter table users add column if not exists supabase_auth_id uuid unique;
create index if not exists ix_users_supabase_auth_id on users (supabase_auth_id);

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then
    create role anon nologin;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then
    create role authenticated nologin;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'service_role') then
    create role service_role nologin bypassrls;
  end if;
end $$;

alter table tenants enable row level security;
alter table restaurants enable row level security;
alter table users enable row level security;
alter table categories enable row level security;
alter table customer_sessions enable row level security;
alter table qr_codes enable row level security;
alter table refresh_tokens enable row level security;
alter table menu_items enable row level security;
alter table menu_item_addons enable row level security;
alter table menu_item_variants enable row level security;
alter table orders enable row level security;
alter table order_items enable row level security;
alter table order_status_history enable row level security;
alter table reviews enable row level security;
alter table push_subscriptions enable row level security;

drop policy if exists "Service role full access" on tenants;
drop policy if exists "Service role full access" on restaurants;
drop policy if exists "Service role full access" on users;
drop policy if exists "Service role full access" on categories;
drop policy if exists "Service role full access" on customer_sessions;
drop policy if exists "Service role full access" on qr_codes;
drop policy if exists "Service role full access" on refresh_tokens;
drop policy if exists "Service role full access" on menu_items;
drop policy if exists "Service role full access" on menu_item_addons;
drop policy if exists "Service role full access" on menu_item_variants;
drop policy if exists "Service role full access" on orders;
drop policy if exists "Service role full access" on order_items;
drop policy if exists "Service role full access" on order_status_history;
drop policy if exists "Service role full access" on reviews;
drop policy if exists "Service role full access" on push_subscriptions;

create policy "Service role full access" on tenants for all using (true) with check (true);
create policy "Service role full access" on restaurants for all using (true) with check (true);
create policy "Service role full access" on users for all using (true) with check (true);
create policy "Service role full access" on categories for all using (true) with check (true);
create policy "Service role full access" on customer_sessions for all using (true) with check (true);
create policy "Service role full access" on qr_codes for all using (true) with check (true);
create policy "Service role full access" on refresh_tokens for all using (true) with check (true);
create policy "Service role full access" on menu_items for all using (true) with check (true);
create policy "Service role full access" on menu_item_addons for all using (true) with check (true);
create policy "Service role full access" on menu_item_variants for all using (true) with check (true);
create policy "Service role full access" on orders for all using (true) with check (true);
create policy "Service role full access" on order_items for all using (true) with check (true);
create policy "Service role full access" on order_status_history for all using (true) with check (true);
create policy "Service role full access" on reviews for all using (true) with check (true);
create policy "Service role full access" on push_subscriptions for all using (true) with check (true);

drop policy if exists "Public read menus" on restaurants;
drop policy if exists "Public read categories" on categories;
drop policy if exists "Public read menu items" on menu_items;
drop policy if exists "Public read addons" on menu_item_addons;
drop policy if exists "Public read variants" on menu_item_variants;
drop policy if exists "Public read customer sessions" on customer_sessions;
drop policy if exists "Public insert customer sessions" on customer_sessions;
drop policy if exists "Public read orders" on orders;
drop policy if exists "Public read order items" on order_items;
drop policy if exists "Public insert orders" on orders;
drop policy if exists "Public insert order items" on order_items;
drop policy if exists "Public insert reviews" on reviews;

create policy "Public read menus" on restaurants for select to anon using (is_active = true);
create policy "Public read categories" on categories for select to anon using (is_active = true);
create policy "Public read menu items" on menu_items for select to anon using (is_available = true);
create policy "Public read addons" on menu_item_addons for select to anon using (is_available = true);
create policy "Public read variants" on menu_item_variants for select to anon using (true);
create policy "Public read customer sessions" on customer_sessions for select to anon using (true);
create policy "Public insert customer sessions" on customer_sessions for insert to anon with check (true);
create policy "Public read orders" on orders for select to anon using (true);
create policy "Public read order items" on order_items for select to anon using (true);
create policy "Public insert orders" on orders for insert to anon with check (true);
create policy "Public insert order items" on order_items for insert to anon with check (true);
create policy "Public insert reviews" on reviews for insert to anon with check (true);

do $$
begin
  if exists (select 1 from pg_publication where pubname = 'supabase_realtime') then
    execute 'alter publication supabase_realtime add table orders';
    execute 'alter publication supabase_realtime add table order_items';
    execute 'alter publication supabase_realtime add table order_status_history';
    execute 'alter publication supabase_realtime add table reviews';
  end if;
exception
  when duplicate_object then null;
end $$;

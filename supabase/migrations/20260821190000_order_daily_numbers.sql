-- Daily order numbers: #1 resets each restaurant calendar day.
-- Replaces global unique (restaurant_id, order_number).

alter table public.orders
  add column if not exists service_date date;

update public.orders
set service_date = (created_at at time zone 'utc')::date
where service_date is null;

alter table public.orders
  alter column service_date set not null;

alter table public.orders
  drop constraint if exists uq_orders_restaurant_number;

alter table public.orders
  add constraint uq_orders_restaurant_day_number
  unique (restaurant_id, service_date, order_number);

create index if not exists ix_orders_restaurant_service_date
  on public.orders (restaurant_id, service_date);

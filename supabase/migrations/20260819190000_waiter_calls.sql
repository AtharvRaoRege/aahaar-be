-- Guest "call waiter" plus a per-venue toggle for it.

alter table restaurants
  add column if not exists waiter_call_enabled boolean not null default false;

create table if not exists waiter_calls (
  id uuid primary key default gen_random_uuid(),
  restaurant_id uuid not null references restaurants (id) on delete cascade,
  customer_session_id uuid references customer_sessions (id) on delete set null,
  table_number varchar(32),
  status varchar(20) not null default 'PENDING',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  acknowledged_at timestamptz
);

create index if not exists ix_waiter_calls_restaurant_status
  on waiter_calls (restaurant_id, status);

create unique index if not exists uq_waiter_calls_pending_table
  on waiter_calls (restaurant_id, table_number)
  where status = 'PENDING' and table_number is not null;

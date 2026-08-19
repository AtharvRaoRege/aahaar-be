-- Cafe owners request Pro; super admin approves or rejects. Current plan
-- stays on subscriptions.plan until a request is approved.

create table if not exists plan_requests (
  id uuid primary key default gen_random_uuid(),
  restaurant_id uuid not null references restaurants (id) on delete cascade,
  requested_plan varchar(20) not null,
  status varchar(20) not null default 'PENDING',
  reviewed_at timestamptz,
  reviewed_by uuid references users (id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists uq_plan_requests_pending
  on plan_requests (restaurant_id)
  where status = 'PENDING';

create index if not exists ix_plan_requests_status on plan_requests (status);
create index if not exists ix_plan_requests_restaurant_id on plan_requests (restaurant_id);

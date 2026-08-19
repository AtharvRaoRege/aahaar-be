-- Push notification subscriptions
create table if not exists push_subscriptions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users(id) on delete cascade,
  restaurant_id uuid not null references restaurants(id) on delete cascade,
  endpoint text not null,
  p256dh varchar(255) not null,
  auth varchar(255) not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint uq_push_user_endpoint_venue unique (user_id, endpoint, restaurant_id)
);
create index if not exists ix_push_subscriptions_user_id on push_subscriptions (user_id);
create index if not exists ix_push_subscriptions_restaurant_id on push_subscriptions (restaurant_id);

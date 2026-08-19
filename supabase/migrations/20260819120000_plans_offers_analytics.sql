-- Monetization + engagement foundations:
--   subscriptions (plan gating, trial/grace lifecycle)
--   offers (display-only promotions on the customer menu)
--   analytics_events (append-only engagement log)
--   menu_item_upsells + menu_items.cost_price (upsell engine, menu engineering)
--   restaurant publish state, maps/review links, UPI payee, opening hours

-- ---------------------------------------------------------------- restaurants
alter table restaurants
  add column if not exists is_published boolean not null default false,
  add column if not exists maps_url varchar(500),
  add column if not exists google_review_url varchar(500),
  add column if not exists upi_vpa varchar(120),
  add column if not exists upi_payee_name varchar(120),
  add column if not exists opening_hours jsonb;

-- Venues that already went live keep serving; only new venues start as drafts.
update restaurants set is_published = true where is_active = true and is_published = false;

-- ---------------------------------------------------------------- menu_items
alter table menu_items
  add column if not exists cost_price numeric(10, 2);

create table if not exists menu_item_upsells (
  id uuid primary key default gen_random_uuid(),
  menu_item_id uuid not null references menu_items(id) on delete cascade,
  suggested_item_id uuid not null references menu_items(id) on delete cascade,
  sort_order integer not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint uq_upsell_pair unique (menu_item_id, suggested_item_id),
  constraint ck_upsell_not_self check (menu_item_id <> suggested_item_id)
);
create index if not exists ix_menu_item_upsells_menu_item_id on menu_item_upsells (menu_item_id);
create index if not exists ix_menu_item_upsells_suggested_item_id
  on menu_item_upsells (suggested_item_id);

-- -------------------------------------------------------------- subscriptions
create table if not exists subscriptions (
  id uuid primary key default gen_random_uuid(),
  restaurant_id uuid not null unique references restaurants(id) on delete cascade,
  plan varchar(20) not null default 'BASIC',
  status varchar(20) not null default 'TRIALING',
  monthly_price numeric(10, 2) not null,
  trial_ends_at timestamptz,
  current_period_end timestamptz,
  grace_ends_at timestamptz,
  pro_trial_used boolean not null default false,
  scheduled_plan varchar(20),
  cancel_at_period_end boolean not null default false,
  cancelled_at timestamptz,
  cancel_reason text,
  payment_method_ref varchar(120),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists ix_subscriptions_restaurant_id on subscriptions (restaurant_id);
create index if not exists ix_subscriptions_status on subscriptions (status);

-- Backfill: every existing venue gets a Basic trial running 90 days from now.
insert into subscriptions (restaurant_id, plan, status, monthly_price, trial_ends_at)
select r.id, 'BASIC', 'TRIALING', 750.00, now() + interval '90 days'
from restaurants r
where not exists (select 1 from subscriptions s where s.restaurant_id = r.id);

-- --------------------------------------------------------------------- offers
create table if not exists offers (
  id uuid primary key default gen_random_uuid(),
  restaurant_id uuid not null references restaurants(id) on delete cascade,
  kind varchar(20) not null default 'PERCENT',
  title varchar(120) not null,
  description text,
  terms text,
  image_url varchar(500),
  coupon_code varchar(32),
  value numeric(10, 2),
  starts_at timestamptz,
  ends_at timestamptz,
  is_active boolean not null default false,
  sort_order integer not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint ck_offers_value_nonneg check (value is null or value >= 0)
);
create index if not exists ix_offers_restaurant_id on offers (restaurant_id);

-- ----------------------------------------------------------- analytics_events
create table if not exists analytics_events (
  id uuid primary key default gen_random_uuid(),
  restaurant_id uuid not null references restaurants(id) on delete cascade,
  event_type varchar(24) not null,
  customer_session_id uuid references customer_sessions(id) on delete set null,
  table_number varchar(32),
  visitor_key varchar(64),
  target_id uuid,
  meta jsonb,
  created_at timestamptz not null default now()
);
create index if not exists ix_analytics_events_restaurant_id on analytics_events (restaurant_id);
create index if not exists ix_analytics_events_created_at on analytics_events (created_at);
create index if not exists ix_analytics_events_visitor_key on analytics_events (visitor_key);
create index if not exists ix_analytics_restaurant_type_time
  on analytics_events (restaurant_id, event_type, created_at);

-- Initial schema: tenants, users, restaurants, menu, orders, customer sessions
create extension if not exists pgcrypto;

create table tenants (
  id uuid primary key default gen_random_uuid(),
  name varchar(120) not null,
  slug varchar(120) not null,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create unique index ix_tenants_slug on tenants (slug);

create table restaurants (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  name varchar(160) not null,
  slug varchar(160) not null,
  description text,
  logo_url varchar(500),
  cover_image_url varchar(500),
  phone varchar(32),
  address text,
  currency varchar(8) not null default 'INR',
  timezone varchar(64) not null default 'Asia/Kolkata',
  primary_color varchar(9) not null default '#E7B230',
  secondary_color varchar(9) not null default '#1A1A1A',
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create unique index ix_restaurants_slug on restaurants (slug);
create index ix_restaurants_tenant_id on restaurants (tenant_id);

create table users (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  email varchar(255) not null,
  full_name varchar(120) not null,
  hashed_password varchar(255),
  role varchar(20) not null default 'OWNER',
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create unique index ix_users_email on users (email);
create index ix_users_tenant_id on users (tenant_id);

create table categories (
  id uuid primary key default gen_random_uuid(),
  restaurant_id uuid not null references restaurants(id) on delete cascade,
  name varchar(120) not null,
  sort_order integer not null default 0,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index ix_categories_restaurant_id on categories (restaurant_id);

create table customer_sessions (
  id uuid primary key default gen_random_uuid(),
  restaurant_id uuid not null references restaurants(id) on delete cascade,
  name varchar(120) not null,
  contact_number varchar(32),
  guest_count integer not null default 1,
  table_number varchar(32),
  room_number varchar(32),
  created_at timestamptz not null default now(),
  expires_at timestamptz not null
);
create index ix_customer_sessions_restaurant_id on customer_sessions (restaurant_id);

create table qr_codes (
  id uuid primary key default gen_random_uuid(),
  restaurant_id uuid not null references restaurants(id) on delete cascade,
  label varchar(120) not null,
  table_number varchar(32),
  target_url varchar(600) not null,
  image_data_url text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index ix_qr_codes_restaurant_id on qr_codes (restaurant_id);

create table refresh_tokens (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users(id) on delete cascade,
  token_hash varchar(64) not null,
  expires_at timestamptz not null,
  revoked boolean not null default false,
  created_at timestamptz not null default now()
);
create unique index ix_refresh_tokens_token_hash on refresh_tokens (token_hash);
create index ix_refresh_tokens_user_id on refresh_tokens (user_id);

create table menu_items (
  id uuid primary key default gen_random_uuid(),
  restaurant_id uuid not null references restaurants(id) on delete cascade,
  category_id uuid references categories(id) on delete set null,
  name varchar(160) not null,
  description text,
  image_url varchar(500),
  base_price numeric(10,2) not null,
  is_available boolean not null default true,
  is_vegetarian boolean not null default false,
  is_vegan boolean not null default false,
  spice_level integer not null default 0,
  sort_order integer not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint ck_menu_items_base_price_nonneg check (base_price >= 0),
  constraint ck_menu_items_spice_level check (spice_level >= 0 and spice_level <= 3)
);
create index ix_menu_items_restaurant_id on menu_items (restaurant_id);
create index ix_menu_items_category_id on menu_items (category_id);

create table menu_item_addons (
  id uuid primary key default gen_random_uuid(),
  menu_item_id uuid not null references menu_items(id) on delete cascade,
  name varchar(120) not null,
  price numeric(10,2) not null,
  is_available boolean not null default true,
  sort_order integer not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint ck_menu_item_addons_price_nonneg check (price >= 0)
);
create index ix_menu_item_addons_menu_item_id on menu_item_addons (menu_item_id);

create table menu_item_variants (
  id uuid primary key default gen_random_uuid(),
  menu_item_id uuid not null references menu_items(id) on delete cascade,
  name varchar(120) not null,
  price_delta numeric(10,2) not null default 0,
  is_default boolean not null default false,
  sort_order integer not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index ix_menu_item_variants_menu_item_id on menu_item_variants (menu_item_id);

create table orders (
  id uuid primary key default gen_random_uuid(),
  restaurant_id uuid not null references restaurants(id) on delete cascade,
  customer_session_id uuid references customer_sessions(id) on delete set null,
  order_number integer not null,
  status varchar(20) not null default 'PENDING',
  subtotal numeric(10,2) not null,
  discount numeric(10,2) not null default 0,
  tax numeric(10,2) not null default 0,
  total numeric(10,2) not null,
  table_number varchar(32),
  room_number varchar(32),
  notes text,
  idempotency_key varchar(64),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint ck_orders_total_nonneg check (total >= 0),
  constraint uq_orders_restaurant_number unique (restaurant_id, order_number),
  constraint uq_orders_restaurant_idempotency unique (restaurant_id, idempotency_key)
);
create index ix_orders_restaurant_id on orders (restaurant_id);
create index ix_orders_customer_session_id on orders (customer_session_id);
create index ix_orders_status on orders (status);

create table order_items (
  id uuid primary key default gen_random_uuid(),
  order_id uuid not null references orders(id) on delete cascade,
  menu_item_id uuid references menu_items(id) on delete set null,
  name_snapshot varchar(160) not null,
  price_snapshot numeric(10,2) not null,
  quantity integer not null,
  variant_snapshot jsonb,
  addon_snapshot jsonb,
  notes text,
  subtotal numeric(10,2) not null,
  constraint ck_order_items_quantity_positive check (quantity > 0)
);
create index ix_order_items_order_id on order_items (order_id);

create table order_status_history (
  id uuid primary key default gen_random_uuid(),
  order_id uuid not null references orders(id) on delete cascade,
  old_status varchar(20),
  new_status varchar(20) not null,
  changed_by uuid references users(id) on delete set null,
  note text,
  created_at timestamptz not null default now()
);
create index ix_order_status_history_order_id on order_status_history (order_id);

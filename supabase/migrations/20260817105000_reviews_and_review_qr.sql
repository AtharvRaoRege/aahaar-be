-- Reviews table and review QR kind
create table if not exists reviews (
  id uuid primary key default gen_random_uuid(),
  restaurant_id uuid not null references restaurants(id) on delete cascade,
  order_id uuid references orders(id) on delete set null,
  rating integer not null,
  comment text,
  improvement text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint ck_reviews_rating_range check (rating >= 1 and rating <= 5),
  constraint uq_reviews_order_id unique (order_id)
);
create index if not exists ix_reviews_restaurant_id on reviews (restaurant_id);
create index if not exists ix_reviews_order_id on reviews (order_id);

alter table qr_codes add column if not exists kind varchar(20) not null default 'TABLE';
create index if not exists ix_qr_codes_kind on qr_codes (kind);
create unique index if not exists uq_qr_codes_review_per_restaurant on qr_codes (restaurant_id) where kind = 'REVIEW';

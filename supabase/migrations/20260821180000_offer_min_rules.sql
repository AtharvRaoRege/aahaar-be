-- Add offer eligibility rules for cart discounts.

ALTER TABLE offers
  ADD COLUMN IF NOT EXISTS min_item_count integer NOT NULL DEFAULT 1;

ALTER TABLE offers
  ADD COLUMN IF NOT EXISTS min_order_amount numeric(10, 2) NOT NULL DEFAULT 0;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'ck_offers_min_item_count'
  ) THEN
    ALTER TABLE offers
      ADD CONSTRAINT ck_offers_min_item_count CHECK (min_item_count >= 1);
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'ck_offers_min_order_amount'
  ) THEN
    ALTER TABLE offers
      ADD CONSTRAINT ck_offers_min_order_amount CHECK (min_order_amount >= 0);
  END IF;
END $$;

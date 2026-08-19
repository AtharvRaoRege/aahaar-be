-- Menu engineering now ranks dishes by what they actually sell, not by margin.
-- Owners were being asked for a cost price they do not want to maintain, so the
-- column and the margin axis are gone.
alter table menu_items drop column if exists cost_price;

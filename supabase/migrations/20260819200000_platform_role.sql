-- Platform access moves from an env allow-list to a column on the user.
--
-- Super admin used to be granted by matching the login email against
-- SUPER_ADMIN_EMAILS on every sign-in, which meant the running process — not the
-- database — decided who could approve kitchens. It is now a role you set on the
-- row, so promoting someone is one UPDATE and demoting them actually sticks.
--
-- `platform_role` is separate from `users.role` on purpose: `role` says what
-- someone does inside their own venue (OWNER, KITCHEN, …), this says whether they
-- can act across the whole platform.

alter table users
  add column if not exists platform_role varchar(20) not null default 'USER';

-- Carry over anyone the retired flag had already promoted.
update users set platform_role = 'SUPER_ADMIN' where is_super_admin = true;

-- These values get edited by hand, so a typo must fail loudly rather than
-- silently read as "not a super admin".
alter table users drop constraint if exists users_platform_role_check;
alter table users
  add constraint users_platform_role_check
  check (platform_role in ('USER', 'SUPER_ADMIN'));

create index if not exists ix_users_platform_role on users (platform_role);

-- One source of truth: the flag would otherwise keep disagreeing with the role.
alter table users drop column if exists is_super_admin;

-- Add clerk_user_id for Google SSO, make password optional
alter table users add column if not exists clerk_user_id varchar(64);
alter table users alter column hashed_password drop not null;
create unique index if not exists ix_users_clerk_user_id on users (clerk_user_id);

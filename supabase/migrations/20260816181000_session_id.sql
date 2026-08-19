-- Single-device login: session_id on users
alter table users add column if not exists session_id uuid not null default gen_random_uuid();
create index if not exists ix_users_session_id on users (session_id);

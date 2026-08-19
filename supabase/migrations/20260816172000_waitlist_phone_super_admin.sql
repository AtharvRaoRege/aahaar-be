-- Waitlist, phone, super admin, venue kind
alter table users add column if not exists phone varchar(32);
alter table users add column if not exists approval_status varchar(20) not null default 'APPROVED';
alter table users add column if not exists is_super_admin boolean not null default false;
alter table users add column if not exists waitlist_notified_at timestamptz;
create index if not exists ix_users_approval_status on users (approval_status);

alter table restaurants add column if not exists venue_kind varchar(20) not null default 'RESTAURANT';

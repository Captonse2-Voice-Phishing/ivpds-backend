-- One row per "forgot password" request. Only a hash of the emailed code is stored.
create table password_reset_tokens (
    id         uuid primary key default gen_random_uuid(),
    user_id    uuid         not null,
    code_hash  varchar(100) not null,
    expires_at timestamptz  not null,
    attempts   smallint     not null default 0,
    used_at    timestamptz,
    created_at timestamptz  not null default now(),
    constraint fk_password_reset_tokens_user foreign key (user_id) references users (id) on delete cascade,
    constraint ck_password_reset_tokens_attempts check (attempts >= 0)
);

create index ix_password_reset_tokens_user_created on password_reset_tokens (user_id, created_at desc);

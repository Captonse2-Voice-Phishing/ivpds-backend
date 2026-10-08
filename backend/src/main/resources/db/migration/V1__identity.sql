create table roles (
    id   smallint generated always as identity primary key,
    name varchar(30) not null,
    constraint uq_roles_name unique (name)
);

create table users (
    id                      uuid primary key default gen_random_uuid(),
    email                   varchar(255) not null,
    password_hash           varchar(100) not null,
    full_name               varchar(100) not null,
    phone_number            varchar(20),
    status                  varchar(20)  not null default 'ACTIVE',
    blacklist_alert_enabled boolean      not null default true,
    created_at              timestamptz  not null default now(),
    updated_at              timestamptz  not null default now(),
    constraint ck_users_status check (status in ('ACTIVE', 'LOCKED')),
    constraint ck_users_phone_number check (phone_number ~ '^\+?[0-9]{6,15}$')
);

-- Emails are unique regardless of letter case.
create unique index uq_users_email on users (lower(email));

create table user_roles (
    user_id uuid     not null,
    role_id smallint not null,
    constraint pk_user_roles primary key (user_id, role_id),
    constraint fk_user_roles_user foreign key (user_id) references users (id) on delete cascade,
    constraint fk_user_roles_role foreign key (role_id) references roles (id)
);

create index ix_user_roles_role on user_roles (role_id);

-- Only the SHA-256 hash of a refresh token is stored, never the token itself.
create table refresh_tokens (
    id         uuid primary key default gen_random_uuid(),
    user_id    uuid        not null,
    token_hash char(64)    not null,
    expires_at timestamptz not null,
    revoked_at timestamptz,
    created_at timestamptz not null default now(),
    constraint uq_refresh_tokens_token_hash unique (token_hash),
    constraint fk_refresh_tokens_user foreign key (user_id) references users (id) on delete cascade
);

create index ix_refresh_tokens_user on refresh_tokens (user_id);

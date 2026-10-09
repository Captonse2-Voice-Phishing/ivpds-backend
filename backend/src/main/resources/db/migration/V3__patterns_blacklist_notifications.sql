create table phishing_patterns (
    id             uuid primary key default gen_random_uuid(),
    name           varchar(150) not null,
    indicator_code varchar(50)  not null,
    pattern        text         not null,
    description    text,
    active         boolean      not null default true,
    created_by     uuid,
    created_at     timestamptz  not null default now(),
    updated_at     timestamptz  not null default now(),
    constraint fk_phishing_patterns_created_by foreign key (created_by) references users (id) on delete set null
);

create index ix_phishing_patterns_indicator on phishing_patterns (indicator_code);

create table blacklist_numbers (
    id           uuid primary key default gen_random_uuid(),
    phone_number varchar(20) not null,
    reason       text,
    active       boolean     not null default true,
    created_by   uuid,
    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now(),
    constraint uq_blacklist_numbers_phone_number unique (phone_number),
    constraint ck_blacklist_numbers_phone_number check (phone_number ~ '^\+?[0-9]{6,15}$'),
    constraint fk_blacklist_numbers_created_by foreign key (created_by) references users (id) on delete set null
);

create table notifications (
    id          uuid primary key default gen_random_uuid(),
    user_id     uuid         not null,
    type        varchar(30)  not null,
    title       varchar(200) not null,
    message     text         not null,
    analysis_id uuid,
    read_at     timestamptz,
    created_at  timestamptz  not null default now(),
    constraint fk_notifications_user foreign key (user_id) references users (id) on delete cascade,
    constraint fk_notifications_analysis foreign key (analysis_id) references analyses (id) on delete set null
);

create index ix_notifications_user_created on notifications (user_id, created_at desc);

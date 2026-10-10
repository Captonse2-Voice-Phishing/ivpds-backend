-- Phone numbers reported by users; an administrator approves a report before the number is blacklisted.
create table blacklist_reports (
    id             uuid primary key default gen_random_uuid(),
    phone_number   varchar(20) not null,
    reporter_id    uuid        not null,
    call_record_id uuid,
    reason         text,
    status         varchar(20) not null default 'PENDING',
    reviewed_by    uuid,
    reviewed_at    timestamptz,
    created_at     timestamptz not null default now(),
    constraint fk_blacklist_reports_reporter foreign key (reporter_id) references users (id) on delete cascade,
    constraint fk_blacklist_reports_call foreign key (call_record_id) references call_records (id) on delete set null,
    constraint fk_blacklist_reports_reviewer foreign key (reviewed_by) references users (id) on delete set null,
    constraint ck_blacklist_reports_phone_number check (phone_number ~ '^\+?[0-9]{6,15}$'),
    constraint ck_blacklist_reports_status check (status in ('PENDING', 'APPROVED', 'REJECTED')),
    -- One user reports a number once; many users reporting the same number is the signal administrators look for.
    constraint uq_blacklist_reports_reporter_number unique (reporter_id, phone_number)
);

create index ix_blacklist_reports_status_created on blacklist_reports (status, created_at desc);
create index ix_blacklist_reports_phone_number on blacklist_reports (phone_number);

-- Devices that receive push notifications (Expo push tokens).
create table push_devices (
    id           uuid primary key default gen_random_uuid(),
    user_id      uuid         not null,
    token        varchar(255) not null,
    platform     varchar(20)  not null,
    created_at   timestamptz  not null default now(),
    last_seen_at timestamptz  not null default now(),
    constraint fk_push_devices_user foreign key (user_id) references users (id) on delete cascade,
    -- A token identifies one app installation; it belongs to whoever signed in on that device last.
    constraint uq_push_devices_token unique (token),
    constraint ck_push_devices_platform check (platform in ('IOS', 'ANDROID', 'WEB'))
);

create index ix_push_devices_user on push_devices (user_id);

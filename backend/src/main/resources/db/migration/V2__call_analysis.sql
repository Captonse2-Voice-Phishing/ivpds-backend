create table call_records (
    id            uuid primary key default gen_random_uuid(),
    user_id       uuid        not null,
    caller_number varchar(20),
    called_at     timestamptz,
    source        varchar(20) not null,
    created_at    timestamptz not null default now(),
    constraint fk_call_records_user foreign key (user_id) references users (id) on delete cascade,
    constraint ck_call_records_source check (source in ('RECORDED', 'UPLOADED')),
    constraint ck_call_records_caller_number check (caller_number ~ '^\+?[0-9]{6,15}$')
);

create index ix_call_records_user_created on call_records (user_id, created_at desc);

-- The audio itself lives in object storage; this table only holds its metadata and location.
create table audio_files (
    id                uuid primary key default gen_random_uuid(),
    call_record_id    uuid         not null,
    bucket            varchar(63)  not null,
    object_key        varchar(512) not null,
    original_filename varchar(255),
    content_type      varchar(100) not null,
    size_bytes        bigint       not null,
    duration_seconds  numeric(10, 3),
    checksum_sha256   char(64),
    created_at        timestamptz  not null default now(),
    constraint fk_audio_files_call_record foreign key (call_record_id) references call_records (id) on delete cascade,
    constraint uq_audio_files_call_record unique (call_record_id),
    constraint uq_audio_files_object unique (bucket, object_key),
    constraint ck_audio_files_size check (size_bytes > 0),
    constraint ck_audio_files_duration check (duration_seconds >= 0)
);

create table analyses (
    id             uuid primary key default gen_random_uuid(),
    call_record_id uuid        not null,
    status         varchar(20) not null default 'PENDING',
    error_code     varchar(50),
    error_message  text,
    started_at     timestamptz,
    completed_at   timestamptz,
    created_at     timestamptz not null default now(),
    updated_at     timestamptz not null default now(),
    constraint fk_analyses_call_record foreign key (call_record_id) references call_records (id) on delete cascade,
    constraint ck_analyses_status check (status in ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED'))
);

create index ix_analyses_call_record on analyses (call_record_id);
create index ix_analyses_status_created on analyses (status, created_at);

create table transcripts (
    id          uuid primary key default gen_random_uuid(),
    analysis_id uuid        not null,
    content     text        not null,
    language    varchar(10) not null default 'vi',
    stt_model   varchar(100),
    created_at  timestamptz not null default now(),
    constraint fk_transcripts_analysis foreign key (analysis_id) references analyses (id) on delete cascade,
    constraint uq_transcripts_analysis unique (analysis_id)
);

create table risk_results (
    id          uuid primary key default gen_random_uuid(),
    analysis_id uuid        not null,
    risk_score  smallint    not null,
    risk_level  varchar(10) not null,
    confidence  numeric(5, 4),
    created_at  timestamptz not null default now(),
    constraint fk_risk_results_analysis foreign key (analysis_id) references analyses (id) on delete cascade,
    constraint uq_risk_results_analysis unique (analysis_id),
    constraint ck_risk_results_score check (risk_score between 0 and 100),
    constraint ck_risk_results_level check (risk_level in ('LOW', 'MEDIUM', 'HIGH')),
    constraint ck_risk_results_confidence check (confidence between 0 and 1)
);

create index ix_risk_results_level_created on risk_results (risk_level, created_at desc);

create table risk_indicators (
    id             uuid primary key default gen_random_uuid(),
    risk_result_id uuid        not null,
    indicator_code varchar(50) not null,
    constraint fk_risk_indicators_risk_result foreign key (risk_result_id) references risk_results (id) on delete cascade,
    constraint uq_risk_indicators_result_code unique (risk_result_id, indicator_code)
);

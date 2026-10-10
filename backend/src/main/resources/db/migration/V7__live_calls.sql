-- Calls analysed while they are in progress (VoIP calls made inside the app).
alter table call_records drop constraint ck_call_records_source;
alter table call_records
    add constraint ck_call_records_source check (source in ('RECORDED', 'UPLOADED', 'LIVE'));

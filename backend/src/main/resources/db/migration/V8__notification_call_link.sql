-- A notification can point at the call it is about (a blacklisted caller has no analysis yet).
alter table notifications
    add column call_record_id uuid,
    add constraint fk_notifications_call_record foreign key (call_record_id) references call_records (id)
        on delete set null;

-- Unread notifications are counted on every app start.
create index ix_notifications_user_unread on notifications (user_id) where read_at is null;

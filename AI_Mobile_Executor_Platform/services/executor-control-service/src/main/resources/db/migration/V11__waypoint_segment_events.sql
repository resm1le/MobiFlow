ALTER TABLE run_events
    ADD COLUMN event_key varchar(320) DEFAULT NULL AFTER event_type,
    ADD COLUMN payload_json json DEFAULT NULL AFTER message,
    ADD UNIQUE KEY uk_run_events_attempt_event_key (attempt_id, event_key);

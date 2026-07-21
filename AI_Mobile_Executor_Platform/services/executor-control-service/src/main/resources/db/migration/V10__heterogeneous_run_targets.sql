ALTER TABLE experiment_run_targets
    ADD COLUMN sequence_id varchar(255) DEFAULT NULL AFTER device_id,
    ADD KEY idx_run_targets_run_sequence (run_id, sequence_id);

ALTER TABLE experiment_runs
    MODIFY COLUMN profile_package varchar(255) DEFAULT NULL;

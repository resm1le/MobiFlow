ALTER TABLE tasks
    ADD COLUMN run_id varchar(64) DEFAULT NULL AFTER task_id,
    ADD COLUMN run_target_id varchar(64) DEFAULT NULL AFTER run_id,
    ADD COLUMN target_device_id varchar(128) DEFAULT NULL AFTER run_target_id,
    ADD KEY idx_tasks_run_id (run_id),
    ADD KEY idx_tasks_target_device_status (target_device_id, status);

CREATE TABLE IF NOT EXISTS device_pools (
    pool_id varchar(64) NOT NULL,
    name varchar(128) NOT NULL,
    description varchar(1024) DEFAULT NULL,
    host_group varchar(64) DEFAULT NULL,
    device_ids_json json NOT NULL,
    required_tags_json json NOT NULL,
    excluded_tags_json json NOT NULL,
    created_by varchar(64) NOT NULL,
    created_at bigint NOT NULL,
    updated_at bigint NOT NULL,
    PRIMARY KEY (pool_id),
    KEY idx_device_pools_created_at (created_at)
);

CREATE TABLE IF NOT EXISTS experiment_runs (
    run_id varchar(64) NOT NULL,
    name varchar(128) NOT NULL,
    description varchar(1024) DEFAULT NULL,
    pool_id varchar(64) NOT NULL,
    status varchar(32) NOT NULL,
    final_state varchar(32) DEFAULT NULL,
    task_type varchar(32) NOT NULL,
    profile_package varchar(255) NOT NULL,
    task_payload_json json NOT NULL,
    run_config_json json NOT NULL,
    artifact_policy_json json NOT NULL,
    priority int NOT NULL,
    labels_json json NOT NULL,
    source varchar(32) NOT NULL,
    created_by varchar(64) NOT NULL,
    max_retries_per_device int NOT NULL,
    queue_timeout_ms bigint NOT NULL,
    cancel_requested tinyint(1) NOT NULL,
    created_at bigint NOT NULL,
    updated_at bigint NOT NULL,
    started_at bigint DEFAULT NULL,
    finished_at bigint DEFAULT NULL,
    PRIMARY KEY (run_id),
    KEY idx_experiment_runs_status_created (status, created_at),
    KEY idx_experiment_runs_pool (pool_id)
);

CREATE TABLE IF NOT EXISTS experiment_run_targets (
    run_target_id varchar(64) NOT NULL,
    run_id varchar(64) NOT NULL,
    device_id varchar(128) NOT NULL,
    status varchar(32) NOT NULL,
    attempt_count int NOT NULL,
    current_task_id varchar(64) DEFAULT NULL,
    latest_attempt_id varchar(64) DEFAULT NULL,
    failure_reason varchar(512) DEFAULT NULL,
    created_at bigint NOT NULL,
    updated_at bigint NOT NULL,
    started_at bigint DEFAULT NULL,
    finished_at bigint DEFAULT NULL,
    PRIMARY KEY (run_target_id),
    KEY idx_run_targets_run_status (run_id, status),
    KEY idx_run_targets_device_status (device_id, status),
    KEY idx_run_targets_current_task (current_task_id),
    KEY idx_run_targets_latest_attempt (latest_attempt_id)
);

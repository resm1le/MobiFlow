CREATE TABLE IF NOT EXISTS devices (
    device_id varchar(128) NOT NULL,
    protocol_version varchar(16) NOT NULL,
    executor_version varchar(32) NOT NULL,
    brand varchar(64) NOT NULL,
    model varchar(128) NOT NULL,
    android_version varchar(32) NOT NULL,
    screen_width int NOT NULL,
    screen_height int NOT NULL,
    installed_profiles_json json NOT NULL,
    tags_json json NOT NULL,
    host_group varchar(64) NOT NULL,
    created_at bigint NOT NULL,
    updated_at bigint NOT NULL,
    PRIMARY KEY (device_id),
    KEY idx_devices_host_group (host_group),
    KEY idx_devices_updated_at (updated_at)
);

CREATE TABLE IF NOT EXISTS device_runtime_state (
    device_id varchar(128) NOT NULL,
    registered tinyint(1) NOT NULL,
    online tinyint(1) NOT NULL,
    busy tinyint(1) NOT NULL,
    status varchar(32) NOT NULL,
    current_task_id varchar(64) DEFAULT NULL,
    current_attempt_id varchar(64) DEFAULT NULL,
    current_task_type varchar(32) DEFAULT NULL,
    config_version varchar(64) NOT NULL,
    lease_expire_at bigint DEFAULT NULL,
    last_heartbeat_at bigint NOT NULL,
    last_command varchar(64) DEFAULT NULL,
    health_json json NOT NULL,
    updated_at bigint NOT NULL,
    PRIMARY KEY (device_id),
    KEY idx_device_runtime_online_busy (online, busy),
    KEY idx_device_runtime_heartbeat (last_heartbeat_at),
    KEY idx_device_runtime_attempt (current_attempt_id)
);

CREATE TABLE IF NOT EXISTS device_commands (
    command_id bigint NOT NULL AUTO_INCREMENT,
    device_id varchar(128) NOT NULL,
    type varchar(64) NOT NULL,
    attempt_id varchar(64) DEFAULT NULL,
    status varchar(32) NOT NULL,
    payload_json json DEFAULT NULL,
    issued_at bigint NOT NULL,
    acked_at bigint DEFAULT NULL,
    expire_at bigint DEFAULT NULL,
    PRIMARY KEY (command_id),
    KEY idx_device_commands_device_status (device_id, status),
    KEY idx_device_commands_attempt (attempt_id)
);

CREATE TABLE IF NOT EXISTS tasks (
    task_id varchar(64) NOT NULL,
    task_type varchar(32) NOT NULL,
    profile_package varchar(255) NOT NULL,
    task_payload_json json NOT NULL,
    run_config_json json NOT NULL,
    artifact_policy_json json NOT NULL,
    priority int NOT NULL,
    labels_json json NOT NULL,
    source varchar(32) NOT NULL,
    schedule_version varchar(64) DEFAULT NULL,
    idempotency_key varchar(128) NOT NULL,
    status varchar(32) NOT NULL,
    created_by varchar(64) NOT NULL,
    created_at bigint NOT NULL,
    updated_at bigint NOT NULL,
    PRIMARY KEY (task_id),
    UNIQUE KEY uk_tasks_idempotency_key (idempotency_key),
    KEY idx_tasks_status_priority_created (status, priority, created_at),
    KEY idx_tasks_profile_package (profile_package)
);

CREATE TABLE IF NOT EXISTS task_attempts (
    attempt_id varchar(64) NOT NULL,
    task_id varchar(64) NOT NULL,
    device_id varchar(128) NOT NULL,
    run_id varchar(64) DEFAULT NULL,
    status varchar(32) NOT NULL,
    final_state varchar(32) DEFAULT NULL,
    lease_expire_at bigint DEFAULT NULL,
    failure_reason varchar(512) DEFAULT NULL,
    started_at bigint DEFAULT NULL,
    finished_at bigint DEFAULT NULL,
    created_at bigint NOT NULL,
    updated_at bigint NOT NULL,
    PRIMARY KEY (attempt_id),
    KEY idx_attempts_task (task_id),
    KEY idx_attempts_device_status (device_id, status),
    KEY idx_attempts_lease_expire_at (lease_expire_at),
    KEY idx_attempts_started_at (started_at)
);

CREATE TABLE IF NOT EXISTS run_events (
    id bigint NOT NULL AUTO_INCREMENT,
    attempt_id varchar(64) NOT NULL,
    task_id varchar(64) NOT NULL,
    device_id varchar(128) NOT NULL,
    run_id varchar(64) DEFAULT NULL,
    scenario_id varchar(255) DEFAULT NULL,
    step_index int DEFAULT NULL,
    action_index int DEFAULT NULL,
    event_type varchar(64) NOT NULL,
    state varchar(64) DEFAULT NULL,
    code varchar(64) DEFAULT NULL,
    message varchar(1024) NOT NULL,
    ts bigint NOT NULL,
    PRIMARY KEY (id),
    KEY idx_run_events_attempt_ts (attempt_id, ts),
    KEY idx_run_events_task_ts (task_id, ts),
    KEY idx_run_events_device_ts (device_id, ts)
);

CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id varchar(64) NOT NULL,
    attempt_id varchar(64) NOT NULL,
    task_id varchar(64) NOT NULL,
    run_id varchar(64) DEFAULT NULL,
    artifact_type varchar(32) NOT NULL,
    file_name varchar(255) NOT NULL,
    mime_type varchar(128) NOT NULL,
    size_bytes bigint NOT NULL,
    object_key varchar(512) NOT NULL,
    created_at bigint NOT NULL,
    PRIMARY KEY (artifact_id),
    KEY idx_artifacts_attempt_type (attempt_id, artifact_type),
    KEY idx_artifacts_task (task_id)
);

CREATE TABLE IF NOT EXISTS outbox_jobs (
    job_id bigint NOT NULL AUTO_INCREMENT,
    topic varchar(64) NOT NULL,
    payload_json json NOT NULL,
    status varchar(32) NOT NULL,
    retry_count int NOT NULL,
    run_after bigint NOT NULL,
    created_at bigint NOT NULL,
    updated_at bigint NOT NULL,
    PRIMARY KEY (job_id),
    KEY idx_outbox_status_run_after (status, run_after)
);

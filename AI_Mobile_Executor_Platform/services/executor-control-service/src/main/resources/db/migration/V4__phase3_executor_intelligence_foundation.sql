ALTER TABLE task_attempts
    ADD COLUMN preflight_summary_json json DEFAULT NULL AFTER failure_reason,
    ADD COLUMN failure_detail_json json DEFAULT NULL AFTER preflight_summary_json;

CREATE TABLE IF NOT EXISTS ai_run_plan_requests (
    request_id varchar(64) NOT NULL,
    goal_text text NOT NULL,
    constraints_json json DEFAULT NULL,
    context_json json NOT NULL,
    status varchar(32) NOT NULL,
    created_at bigint NOT NULL,
    updated_at bigint NOT NULL,
    PRIMARY KEY (request_id),
    KEY idx_ai_run_plan_requests_status_created (status, created_at)
);

CREATE TABLE IF NOT EXISTS ai_run_plan_results (
    request_id varchar(64) NOT NULL,
    result_json json NOT NULL,
    validation_json json NOT NULL,
    model_meta_json json DEFAULT NULL,
    status varchar(32) NOT NULL,
    created_at bigint NOT NULL,
    updated_at bigint NOT NULL,
    PRIMARY KEY (request_id),
    KEY idx_ai_run_plan_results_status_created (status, created_at)
);

CREATE TABLE IF NOT EXISTS ai_failure_triage_results (
    triage_result_id varchar(64) NOT NULL,
    run_id varchar(64) DEFAULT NULL,
    run_target_id varchar(64) DEFAULT NULL,
    attempt_id varchar(64) DEFAULT NULL,
    context_json json NOT NULL,
    result_json json DEFAULT NULL,
    validation_json json DEFAULT NULL,
    model_meta_json json DEFAULT NULL,
    status varchar(32) NOT NULL,
    created_at bigint NOT NULL,
    updated_at bigint NOT NULL,
    PRIMARY KEY (triage_result_id),
    KEY idx_ai_failure_triage_results_run_target (run_target_id, created_at),
    KEY idx_ai_failure_triage_results_attempt (attempt_id, created_at)
);

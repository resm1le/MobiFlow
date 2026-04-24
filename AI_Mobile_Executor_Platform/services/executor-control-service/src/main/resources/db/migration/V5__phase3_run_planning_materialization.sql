ALTER TABLE ai_run_plan_requests
    ADD COLUMN materialized_run_id varchar(64) DEFAULT NULL AFTER status,
    ADD COLUMN materialized_by varchar(128) DEFAULT NULL AFTER materialized_run_id,
    ADD COLUMN materialized_at bigint DEFAULT NULL AFTER materialized_by;

CREATE INDEX idx_ai_run_plan_requests_materialized_run
    ON ai_run_plan_requests (materialized_run_id);

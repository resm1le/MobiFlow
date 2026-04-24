CREATE TABLE IF NOT EXISTS ai_run_summary_results (
    summary_id VARCHAR(64) PRIMARY KEY,
    run_id VARCHAR(64) NOT NULL,
    context_json JSON NOT NULL,
    result_json JSON NULL,
    validation_json JSON NULL,
    model_meta_json JSON NULL,
    status VARCHAR(32) NOT NULL,
    created_at BIGINT NOT NULL,
    updated_at BIGINT NOT NULL,
    KEY idx_ai_run_summary_results_run (run_id, created_at)
);

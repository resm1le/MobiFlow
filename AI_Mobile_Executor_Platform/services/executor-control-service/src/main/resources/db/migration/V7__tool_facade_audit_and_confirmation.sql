CREATE TABLE IF NOT EXISTS tool_execution_audits (
    audit_id VARCHAR(64) PRIMARY KEY,
    request_id VARCHAR(128) NOT NULL,
    session_id VARCHAR(128) NOT NULL,
    tool_name VARCHAR(128) NOT NULL,
    risk_level VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL,
    request_json JSON NOT NULL,
    response_json JSON NULL,
    created_at BIGINT NOT NULL,
    updated_at BIGINT NOT NULL,
    UNIQUE KEY uk_tool_execution_audits_request (request_id),
    KEY idx_tool_execution_audits_tool (tool_name, created_at),
    KEY idx_tool_execution_audits_session (session_id, created_at)
);

CREATE TABLE IF NOT EXISTS tool_confirmation_tokens (
    confirmation_id VARCHAR(64) PRIMARY KEY,
    audit_id VARCHAR(64) NOT NULL,
    tool_name VARCHAR(128) NOT NULL,
    session_id VARCHAR(128) NOT NULL,
    arguments_json JSON NOT NULL,
    token_hash VARCHAR(128) NOT NULL,
    status VARCHAR(32) NOT NULL,
    expires_at BIGINT NOT NULL,
    used_at BIGINT NULL,
    created_at BIGINT NOT NULL,
    updated_at BIGINT NOT NULL,
    UNIQUE KEY uk_tool_confirmation_tokens_hash (token_hash),
    KEY idx_tool_confirmation_tokens_audit (audit_id),
    KEY idx_tool_confirmation_tokens_expiry (expires_at)
);

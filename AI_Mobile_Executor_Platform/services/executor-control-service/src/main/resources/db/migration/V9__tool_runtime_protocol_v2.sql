ALTER TABLE tool_execution_audits
    ADD COLUMN caller_context_json JSON NULL AFTER request_json;

ALTER TABLE tool_execution_audits
    ADD COLUMN entity_refs_json JSON NULL AFTER response_json;

ALTER TABLE tool_confirmation_tokens
    ADD COLUMN caller_context_json JSON NULL AFTER arguments_json;

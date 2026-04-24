package com.example.platform.control.application;

public final class ControlErrorCode {

    public static final String EXECUTOR_UNAUTHORIZED = "EXECUTOR_UNAUTHORIZED";
    public static final String EXECUTOR_IDENTITY_MISMATCH = "EXECUTOR_IDENTITY_MISMATCH";
    public static final String ATTEMPT_OWNERSHIP_INVALID = "ATTEMPT_OWNERSHIP_INVALID";
    public static final String ADMIN_UNAUTHORIZED = "ADMIN_UNAUTHORIZED";
    public static final String ADMIN_FORBIDDEN = "ADMIN_FORBIDDEN";
    public static final String DEVICE_NOT_FOUND = "DEVICE_NOT_FOUND";
    public static final String DEVICE_POOL_NOT_FOUND = "DEVICE_POOL_NOT_FOUND";
    public static final String TASK_NOT_FOUND = "TASK_NOT_FOUND";
    public static final String ATTEMPT_NOT_FOUND = "ATTEMPT_NOT_FOUND";
    public static final String EXPERIMENT_RUN_NOT_FOUND = "EXPERIMENT_RUN_NOT_FOUND";
    public static final String RUN_TARGET_NOT_FOUND = "RUN_TARGET_NOT_FOUND";
    public static final String AI_PROVIDER_FAILURE = "AI_PROVIDER_FAILURE";
    public static final String AI_RUN_PLAN_INVALID = "AI_RUN_PLAN_INVALID";
    public static final String AI_RUN_PLAN_NOT_READY = "AI_RUN_PLAN_NOT_READY";
    public static final String AI_RUN_PLAN_ALREADY_MATERIALIZED = "AI_RUN_PLAN_ALREADY_MATERIALIZED";
    public static final String AI_RUN_PLAN_NOT_FOUND = "AI_RUN_PLAN_NOT_FOUND";
    public static final String AI_RUN_PLAN_CONTEXT_UNAVAILABLE = "AI_RUN_PLAN_CONTEXT_UNAVAILABLE";
    public static final String AI_RUN_SUMMARY_NOT_FOUND = "AI_RUN_SUMMARY_NOT_FOUND";
    public static final String AI_FAILURE_TRIAGE_NOT_FOUND = "AI_FAILURE_TRIAGE_NOT_FOUND";
    public static final String AI_FAILURE_TRIAGE_NOT_ALLOWED = "AI_FAILURE_TRIAGE_NOT_ALLOWED";
    public static final String TOOL_UNAUTHORIZED = "TOOL_UNAUTHORIZED";
    public static final String TOOL_NOT_FOUND = "TOOL_NOT_FOUND";
    public static final String TOOL_DISABLED = "TOOL_DISABLED";
    public static final String TOOL_ARGUMENT_INVALID = "TOOL_ARGUMENT_INVALID";
    public static final String TOOL_REQUEST_INVALID = "TOOL_REQUEST_INVALID";
    public static final String TOOL_CONFIRMATION_REQUIRED = "TOOL_CONFIRMATION_REQUIRED";
    public static final String TOOL_CONFIRMATION_INVALID = "TOOL_CONFIRMATION_INVALID";
    public static final String TOOL_PROPOSAL_INVALID = "TOOL_PROPOSAL_INVALID";
    public static final String TOOL_PROPOSAL_PRECONDITION_FAILED = "TOOL_PROPOSAL_PRECONDITION_FAILED";
    public static final String TOOL_RESOURCE_INVALID = "TOOL_RESOURCE_INVALID";
    public static final String TOOL_RESOURCE_NOT_FOUND = "TOOL_RESOURCE_NOT_FOUND";
    public static final String TOOL_RESOURCE_NOT_READABLE = "TOOL_RESOURCE_NOT_READABLE";
    public static final String LEGACY_AI_TASK_PLAN_REMOVED = "LEGACY_AI_TASK_PLAN_REMOVED";
    public static final String LEGACY_AI_ATTEMPT_SUMMARY_REMOVED = "LEGACY_AI_ATTEMPT_SUMMARY_REMOVED";
    public static final String LEGACY_AI_ATTEMPT_FAILURE_ANALYSIS_REMOVED = "LEGACY_AI_ATTEMPT_FAILURE_ANALYSIS_REMOVED";
    public static final String COMMAND_NOT_ALLOWED = "COMMAND_NOT_ALLOWED";
    public static final String PROFILE_PACKAGE_INVALID = "PROFILE_PACKAGE_INVALID";
    public static final String ARTIFACT_NOT_FOUND = "ARTIFACT_NOT_FOUND";
    public static final String ARTIFACT_OBJECT_MISSING = "ARTIFACT_OBJECT_MISSING";
    public static final String ARTIFACT_DOWNLOAD_FAILED = "ARTIFACT_DOWNLOAD_FAILED";
    public static final String ARTIFACT_UPLOAD_FAILED = "ARTIFACT_UPLOAD_FAILED";
    public static final String ARTIFACT_UPLOAD_V1_REMOVED = "ARTIFACT_UPLOAD_V1_REMOVED";
    public static final String ARTIFACT_UPLOAD_SESSION_NOT_FOUND = "ARTIFACT_UPLOAD_SESSION_NOT_FOUND";
    public static final String ARTIFACT_UPLOAD_SESSION_MISMATCH = "ARTIFACT_UPLOAD_SESSION_MISMATCH";
    public static final String ARTIFACT_UPLOAD_OBJECT_MISSING = "ARTIFACT_UPLOAD_OBJECT_MISSING";
    public static final String ARTIFACT_UPLOAD_ALREADY_FINALIZED = "ARTIFACT_UPLOAD_ALREADY_FINALIZED";
    public static final String TASK_STATE_INVALID = "TASK_STATE_INVALID";
    public static final String ATTEMPT_STATE_INVALID = "ATTEMPT_STATE_INVALID";
    public static final String DEVICE_STATE_INVALID = "DEVICE_STATE_INVALID";
    public static final String DEVICE_POOL_INVALID = "DEVICE_POOL_INVALID";
    public static final String EXPERIMENT_RUN_INVALID = "EXPERIMENT_RUN_INVALID";

    private ControlErrorCode() {
    }
}

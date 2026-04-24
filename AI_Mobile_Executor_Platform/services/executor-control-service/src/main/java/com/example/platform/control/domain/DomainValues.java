package com.example.platform.control.domain;

import java.util.Set;

public final class DomainValues {

    public static final String DEVICE_STATUS_ONLINE = "ONLINE";
    public static final String DEVICE_STATUS_OFFLINE = "OFFLINE";
    public static final String DEVICE_STATUS_QUIESCED = "QUIESCED";

    public static final String TASK_STATUS_DRAFT = "DRAFT";
    public static final String TASK_STATUS_QUEUED = "QUEUED";
    public static final String TASK_STATUS_RUNNING = "RUNNING";
    public static final String TASK_STATUS_SUCCEEDED = "SUCCEEDED";
    public static final String TASK_STATUS_FAILED = "FAILED";
    public static final String TASK_STATUS_CANCELLED = "CANCELLED";

    public static final String RUN_STATUS_QUEUED = "QUEUED";
    public static final String RUN_STATUS_RUNNING = "RUNNING";
    public static final String RUN_STATUS_CANCELLING = "CANCELLING";
    public static final String RUN_STATUS_TERMINAL = "TERMINAL";

    public static final String RUN_FINAL_STATE_SUCCEEDED = "SUCCEEDED";
    public static final String RUN_FINAL_STATE_FAILED = "FAILED";
    public static final String RUN_FINAL_STATE_CANCELLED = "CANCELLED";
    public static final String RUN_FINAL_STATE_PARTIAL = "PARTIAL";

    public static final String RUN_TARGET_STATUS_QUEUED = "QUEUED";
    public static final String RUN_TARGET_STATUS_RUNNING = "RUNNING";
    public static final String RUN_TARGET_STATUS_RETRY_PENDING = "RETRY_PENDING";
    public static final String RUN_TARGET_STATUS_SUCCEEDED = "SUCCEEDED";
    public static final String RUN_TARGET_STATUS_FAILED = "FAILED";
    public static final String RUN_TARGET_STATUS_CANCELLED = "CANCELLED";

    public static final String AI_RUN_PLAN_STATUS_CREATED = "CREATED";
    public static final String AI_RUN_PLAN_STATUS_READY = "READY";
    public static final String AI_RUN_PLAN_STATUS_FAILED = "FAILED";
    public static final String AI_RUN_PLAN_STATUS_MATERIALIZED = "MATERIALIZED";
    public static final String AI_TRIAGE_STATUS_CREATED = "CREATED";
    public static final String AI_TRIAGE_STATUS_READY = "READY";
    public static final String AI_TRIAGE_STATUS_FAILED = "FAILED";
    public static final String AI_RUN_SUMMARY_STATUS_CREATED = "CREATED";
    public static final String AI_RUN_SUMMARY_STATUS_READY = "READY";
    public static final String AI_RUN_SUMMARY_STATUS_FAILED = "FAILED";

    public static final String ATTEMPT_STATUS_CREATED = "CREATED";
    public static final String ATTEMPT_STATUS_LEASED = "LEASED";
    public static final String ATTEMPT_STATUS_RUNNING = "RUNNING";
    public static final String ATTEMPT_STATUS_SUCCEEDED = "SUCCEEDED";
    public static final String ATTEMPT_STATUS_FAILED = "FAILED";
    public static final String ATTEMPT_STATUS_CANCELLED = "CANCELLED";
    public static final String ATTEMPT_STATUS_PRECHECK_FAILED = "PRECHECK_FAILED";
    public static final String ATTEMPT_STATUS_SYSTEM_ABORTED = "SYSTEM_ABORTED";
    public static final String ATTEMPT_STATUS_LEASE_EXPIRED = "LEASE_EXPIRED";

    public static final String COMMAND_STATUS_PENDING = "PENDING";
    public static final String COMMAND_STATUS_DELIVERED = "DELIVERED";

    public static final Set<String> ALLOWED_COMMAND_TYPES = Set.of(
            "STOP_LOOP",
            "CANCEL_ATTEMPT",
            "FORCE_HEALTH_CHECK",
            "REREGISTER",
            "REFRESH_CONFIG",
            "QUIESCE"
    );

    public static final Set<String> ACTIVE_ATTEMPT_STATUSES = Set.of(
            ATTEMPT_STATUS_CREATED,
            ATTEMPT_STATUS_LEASED,
            ATTEMPT_STATUS_RUNNING
    );

    public static final Set<String> TERMINAL_RUN_TARGET_STATUSES = Set.of(
            RUN_TARGET_STATUS_SUCCEEDED,
            RUN_TARGET_STATUS_FAILED,
            RUN_TARGET_STATUS_CANCELLED
    );

    public static final Set<String> ALLOWED_AI_TASK_TYPES = Set.of(
            "PLUGIN_RUN",
            "PLUGIN_SMOKE"
    );

    public static final Set<String> PHASE3_FAILURE_CATEGORIES = Set.of(
            "PROFILE_NOT_READY",
            "UI_NOT_FOUND",
            "NETWORK_ERROR",
            "PERMISSION_MISSING",
            "DEVICE_STATE_MISMATCH",
            "LEASE_INTERRUPTED",
            "PRECHECK_FAILED",
            "QUEUE_TIMEOUT",
            "RUN_CANCELLED",
            "UNKNOWN"
    );

    public static final Set<String> PHASE3_RETRY_RECOMMENDATIONS = Set.of(
            "NO_RETRY",
            "RETRY_SAME_DEVICE",
            "RETRY_OTHER_DEVICE",
            "INSPECT_PROFILE",
            "INSPECT_ENVIRONMENT",
            "ESCALATE_OPERATOR"
    );

    public static final Set<String> PHASE3_SUGGESTED_NEXT_ACTIONS = Set.of(
            "NONE",
            "RETRY_TARGET",
            "RETRY_ON_OTHER_DEVICE",
            "INSPECT_ARTIFACTS",
            "INSPECT_DEVICE_HEALTH",
            "INSPECT_PROFILE_LOGIC",
            "CHECK_CONTROL_PLANE",
            "MANUAL_REVIEW"
    );

    public static final Set<String> PHASE3_DEVICE_SNAPSHOT_TYPES = Set.of(
            "HEARTBEAT",
            "PREFLIGHT",
            "FAILURE"
    );

    public static final Set<String> ALLOWED_TASK_TYPES = Set.of(
            "demo.navigate",
            "PLUGIN_RUN",
            "PLUGIN_SMOKE",
            "LOCAL_DEBUG"
    );

    private DomainValues() {
    }

    public static String toTaskStatusFromFinalState(String finalState) {
        if ("SUCCESS".equals(finalState)) {
            return TASK_STATUS_SUCCEEDED;
        }
        if ("CANCELLED".equals(finalState)) {
            return TASK_STATUS_CANCELLED;
        }
        return TASK_STATUS_FAILED;
    }

    public static String toAttemptStatusFromFinalState(String finalState) {
        return switch (finalState) {
            case "SUCCESS" -> ATTEMPT_STATUS_SUCCEEDED;
            case "FAILED" -> ATTEMPT_STATUS_FAILED;
            case "CANCELLED" -> ATTEMPT_STATUS_CANCELLED;
            case "PRECHECK_FAILED" -> ATTEMPT_STATUS_PRECHECK_FAILED;
            case "SYSTEM_ABORTED" -> ATTEMPT_STATUS_SYSTEM_ABORTED;
            case "LEASE_EXPIRED" -> ATTEMPT_STATUS_LEASE_EXPIRED;
            default -> ATTEMPT_STATUS_FAILED;
        };
    }
}

package com.example.platform.control.application;

import java.util.List;
import java.util.Map;

public final class Phase3AiModels {

    private Phase3AiModels() {
    }

    public enum FailureCategory {
        PROFILE_NOT_READY,
        UI_NOT_FOUND,
        NETWORK_ERROR,
        PERMISSION_MISSING,
        DEVICE_STATE_MISMATCH,
        LEASE_INTERRUPTED,
        PRECHECK_FAILED,
        QUEUE_TIMEOUT,
        RUN_CANCELLED,
        UNKNOWN
    }

    public enum RetryRecommendation {
        NO_RETRY,
        RETRY_SAME_DEVICE,
        RETRY_OTHER_DEVICE,
        INSPECT_PROFILE,
        INSPECT_ENVIRONMENT,
        ESCALATE_OPERATOR
    }

    public enum SuggestedNextAction {
        NONE,
        RETRY_TARGET,
        RETRY_ON_OTHER_DEVICE,
        INSPECT_ARTIFACTS,
        INSPECT_DEVICE_HEALTH,
        INSPECT_PROFILE_LOGIC,
        CHECK_CONTROL_PLANE,
        MANUAL_REVIEW
    }

    public enum DeviceOperationalSnapshotType {
        HEARTBEAT,
        PREFLIGHT,
        FAILURE
    }

    public record RunPlanningContext(
            String goal,
            Map<String, Object> constraints,
            List<AvailableDevicePool> availableDevicePools,
            List<AvailableProfile> availableProfiles,
            DefaultRunPolicy defaultRunPolicy,
            List<String> allowedTaskTypes
    ) {
    }

    public record AvailableDevicePool(
            String poolId,
            String name,
            String hostGroup,
            int deviceCount,
            List<String> requiredTags,
            List<String> excludedTags
    ) {
    }

    public record AvailableProfile(
            String profilePackage,
            int installedDeviceCount,
            List<String> supportedTaskTypes,
            List<String> requiredTaskPayloadFields,
            Map<String, Object> recommendedDefaults,
            List<String> knownLimitations
    ) {
    }

    public record DefaultRunPolicy(
            int priority,
            int maxRetriesPerDevice,
            long queueTimeoutMs,
            Map<String, Object> defaultRunConfig,
            Map<String, Object> defaultArtifactPolicy
    ) {
    }

    public record RunDraft(
            String name,
            String description,
            String devicePoolId,
            String taskType,
            String profilePackage,
            Map<String, Object> taskPayload,
            Map<String, Object> runConfig,
            Map<String, Object> artifactPolicy,
            int priority,
            List<String> labels,
            int maxRetriesPerDevice,
            long queueTimeoutMs
    ) {
    }

    public record RunDraftResult(
            RunDraft runDraft,
            List<String> warnings,
            List<String> reviewHints
    ) {
    }

    public record FailureTriageContext(
            RunSummary run,
            RunTargetSummary target,
            AttemptSummary latestAttempt,
            AttemptHistorySummary attemptHistorySummary,
            FailureContext failureContext,
            List<KeyEvent> keyEvents,
            List<ArtifactManifestItem> artifactManifest,
            DeviceOperationalSnapshot deviceOperationalSnapshot
    ) {
    }

    public record RunSummary(
            String runId,
            String poolId,
            String status,
            String finalState,
            String taskType,
            String profilePackage,
            int priority,
            List<String> labels,
            int maxRetriesPerDevice,
            long queueTimeoutMs,
            boolean cancelRequested,
            Long startedAt,
            Long finishedAt
    ) {
    }

    public record RunSummaryContext(
            RunSummary run,
            RunCounts counts,
            List<RunTargetSummary> targets,
            List<AttemptSummary> representativeAttempts,
            List<KeyEvent> keyEvents,
            List<ArtifactManifestItem> artifactManifest
    ) {
    }

    public record RunCounts(
            int totalTargets,
            int queued,
            int running,
            int retryPending,
            int succeeded,
            int failed,
            int cancelled
    ) {
    }

    public record RunTargetSummary(
            String runTargetId,
            String deviceId,
            String status,
            int attemptCount,
            String currentTaskId,
            String latestAttemptId,
            String failureReason,
            Long startedAt,
            Long finishedAt
    ) {
    }

    public record AttemptSummary(
            String attemptId,
            String taskId,
            String deviceId,
            String runId,
            String status,
            String finalState,
            String failureReason,
            Map<String, Object> preflightSummary,
            Map<String, Object> failureDetail,
            Long startedAt,
            Long finishedAt,
            long createdAt
    ) {
    }

    public record AttemptHistorySummary(
            int attemptCount,
            List<AttemptHistoryEntry> recentAttempts,
            boolean queueTimeoutObserved,
            boolean cancelObserved
    ) {
    }

    public record AttemptHistoryEntry(
            String attemptId,
            String status,
            String finalState,
            String failureReason,
            Long finishedAt,
            String deviceId
    ) {
    }

    public record FailureContext(
            String finalState,
            String failureReason,
            String lastError,
            boolean queueTimeout,
            boolean cancelled,
            boolean leaseLost,
            boolean precheckFailed,
            Map<String, Object> preflightSummary,
            Map<String, Object> failureDetail
    ) {
    }

    public record KeyEvent(
            String eventType,
            String state,
            String code,
            String message,
            long ts
    ) {
    }

    public record ArtifactManifestItem(
            String artifactId,
            String artifactType,
            String fileName,
            String mimeType,
            long sizeBytes,
            String objectKey
    ) {
    }

    public record DeviceOperationalSnapshot(
            DeviceOperationalSnapshotType snapshotType,
            long capturedAt,
            String deviceId,
            String hostGroup,
            List<String> profilePackages,
            Map<String, Object> capabilities,
            Map<String, Object> healthSnapshot,
            Map<String, Object> preflightSummary,
            Long lastHeartbeatAt
    ) {
    }

    public record FailureTriageResult(
            FailureCategory failureCategory,
            String probableCause,
            double confidence,
            RetryRecommendation retryRecommendation,
            SuggestedNextAction suggestedNextAction,
            List<String> operatorReviewHints,
            List<String> evidence
    ) {
    }

    public record RunSummaryKeyMoment(
            String title,
            String eventType,
            Integer stepIndex,
            String message
    ) {
    }

    public record RunSummaryResult(
            String summaryText,
            List<RunSummaryKeyMoment> keyMoments,
            String finalJudgement,
            List<String> evidence
    ) {
    }

    public record ValidationResult(
            boolean valid,
            List<String> errors,
            List<String> warnings
    ) {
    }
}

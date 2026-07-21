package com.example.platform.control.api;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.PositiveOrZero;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;

import java.util.List;
import java.util.Map;

public final class AdminApiModels {

    private AdminApiModels() {
    }

    public record CreateTaskRequest(
            @NotBlank String taskType,
            @NotBlank
            @Pattern(regexp = "^[A-Za-z0-9_]+(\\.[A-Za-z0-9_]+)+$", message = "PROFILE_PACKAGE_INVALID")
            String profilePackage,
            @NotNull Map<String, Object> taskPayload,
            @NotNull ExecutorApiModels.RunConfig runConfig,
            @NotNull ExecutorApiModels.ArtifactPolicy artifactPolicy,
            Integer priority,
            List<String> labels,
            String source,
            String createdBy,
            String idempotencyKey
    ) {
    }

    public record TaskResponse(
            String taskId,
            String runId,
            String runTargetId,
            String targetDeviceId,
            String taskType,
            String profilePackage,
            Map<String, Object> taskPayload,
            ExecutorApiModels.RunConfig runConfig,
            ExecutorApiModels.ArtifactPolicy artifactPolicy,
            int priority,
            List<String> labels,
            String source,
            String scheduleVersion,
            String idempotencyKey,
            String status,
            String createdBy,
            long createdAt,
            long updatedAt,
            AttemptSummary latestAttempt
    ) {
    }

    public record AttemptSummary(
            String attemptId,
            String taskId,
            String deviceId,
            String runId,
            String status,
            String finalState,
            Long leaseExpireAt,
            String failureReason,
            Long startedAt,
            Long finishedAt,
            long createdAt,
            long updatedAt
    ) {
    }

    public record DeviceResponse(
            String deviceId,
            String protocolVersion,
            String executorVersion,
            String brand,
            String model,
            String androidVersion,
            int screenWidth,
            int screenHeight,
            List<String> installedProfiles,
            List<String> tags,
            String hostGroup,
            boolean registered,
            boolean online,
            boolean busy,
            String status,
            String currentTaskId,
            String currentAttemptId,
            String currentTaskType,
            String configVersion,
            boolean authConfigured,
            Long leaseExpireAt,
            long lastHeartbeatAt,
            String lastCommand,
            Map<String, Object> health,
            long updatedAt
    ) {
    }

    public record CreateCommandRequest(
            @NotBlank String type,
            String attemptId,
            Long expireInMs
    ) {
    }

    public record AttemptDetailResponse(
            AttemptSummary attempt,
            List<RunEventResponse> events,
            List<ArtifactResponse> artifacts
    ) {
    }

    public record RunEventResponse(
            Long id,
            String attemptId,
            String taskId,
            String deviceId,
            String runId,
            String scenarioId,
            Integer stepIndex,
            Integer actionIndex,
            String eventType,
            String state,
            String code,
            String message,
            Map<String, Object> payload,
            long ts
    ) {
    }

    public record ArtifactResponse(
            String artifactId,
            String attemptId,
            String taskId,
            String runId,
            String artifactType,
            String fileName,
            String mimeType,
            long sizeBytes,
            String objectKey,
            String downloadPath,
            long createdAt
    ) {
    }

    public record CommandAcceptedResponse(
            String deviceId,
            String type,
            String attemptId
    ) {
    }

    public record CreateDevicePoolRequest(
            @NotBlank String name,
            String description,
            String hostGroup,
            List<String> deviceIds,
            List<String> requiredTags,
            List<String> excludedTags,
            String createdBy
    ) {
    }

    public record DevicePoolResponse(
            String poolId,
            String name,
            String description,
            String hostGroup,
            List<String> deviceIds,
            List<String> requiredTags,
            List<String> excludedTags,
            String createdBy,
            long createdAt,
            long updatedAt
    ) {
    }

    public record CreateExperimentRunRequest(
            @NotBlank String name,
            String description,
            @NotBlank String devicePoolId,
            @NotBlank String taskType,
            @NotBlank
            @Pattern(regexp = "^[A-Za-z0-9_]+(\\.[A-Za-z0-9_]+)+$", message = "PROFILE_PACKAGE_INVALID")
            String profilePackage,
            @NotNull Map<String, Object> taskPayload,
            @NotNull ExecutorApiModels.RunConfig runConfig,
            @NotNull ExecutorApiModels.ArtifactPolicy artifactPolicy,
            Integer priority,
            List<String> labels,
            String source,
            String createdBy,
            @PositiveOrZero Integer maxRetriesPerDevice,
            @PositiveOrZero Long queueTimeoutMs
    ) {
    }

    public record CreateSingleDeviceRunRequest(
            @NotBlank String name,
            String description,
            @NotBlank String deviceId,
            @NotBlank String taskType,
            @NotBlank
            @Pattern(regexp = "^[A-Za-z0-9_]+(\\.[A-Za-z0-9_]+)+$", message = "PROFILE_PACKAGE_INVALID")
            String profilePackage,
            @NotNull Map<String, Object> taskPayload,
            @NotNull ExecutorApiModels.RunConfig runConfig,
            @NotNull ExecutorApiModels.ArtifactPolicy artifactPolicy,
            Integer priority,
            List<String> labels,
            String source,
            String createdBy,
            @PositiveOrZero Integer maxRetriesPerDevice,
            @PositiveOrZero Long queueTimeoutMs
    ) {
    }

    public record CreateHeterogeneousRunRequest(
            @NotBlank String name,
            String description,
            @NotBlank String taskType,
            @NotNull ExecutorApiModels.RunConfig runConfig,
            @NotNull ExecutorApiModels.ArtifactPolicy artifactPolicy,
            Integer priority,
            List<String> labels,
            String source,
            String createdBy,
            @PositiveOrZero Integer maxRetriesPerDevice,
            @PositiveOrZero Long queueTimeoutMs,
            @NotNull List<HeterogeneousDispatchEntry> dispatch
    ) {
    }

    public record HeterogeneousDispatchEntry(
            @NotBlank String sequenceId,
            @NotBlank
            @Pattern(regexp = "^[A-Za-z0-9_]+(\\.[A-Za-z0-9_]+)+$", message = "PROFILE_PACKAGE_INVALID")
            String profilePackage,
            @NotNull Map<String, Object> taskPayload,
            @NotNull DeviceSelector select
    ) {
    }

    public record DeviceSelector(
            Integer count,
            List<String> deviceIds,
            List<String> requiredTags,
            List<String> excludedTags
    ) {
    }

    public record RunStatusCounts(
            int totalTargets,
            int queued,
            int running,
            int retryPending,
            int succeeded,
            int failed,
            int cancelled
    ) {
    }

    public record ExperimentRunTargetResponse(
            String runTargetId,
            String deviceId,
            String sequenceId,
            String status,
            int attemptCount,
            String currentTaskId,
            String latestAttemptId,
            String failureReason,
            Long startedAt,
            Long finishedAt,
            TaskResponse task,
            AttemptSummary latestAttempt
    ) {
    }

    public record ExperimentRunSummaryResponse(
            String runId,
            String name,
            String description,
            String poolId,
            String status,
            String finalState,
            String taskType,
            String profilePackage,
            int priority,
            List<String> labels,
            String source,
            String createdBy,
            int maxRetriesPerDevice,
            long queueTimeoutMs,
            boolean cancelRequested,
            long createdAt,
            long updatedAt,
            Long startedAt,
            Long finishedAt,
            RunStatusCounts counts
    ) {
    }

    public record ExperimentRunDetailResponse(
            ExperimentRunSummaryResponse run,
            Map<String, Object> taskPayload,
            ExecutorApiModels.RunConfig runConfig,
            ExecutorApiModels.ArtifactPolicy artifactPolicy,
            List<ExperimentRunTargetResponse> targets
    ) {
    }
}

package com.example.platform.control.api;

import com.example.platform.control.application.ArtifactUploadMode;
import com.fasterxml.jackson.annotation.JsonAnySetter;
import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.PositiveOrZero;
import jakarta.validation.constraints.Size;

import java.util.List;
import java.util.Map;

public final class ExecutorApiModels {

    private ExecutorApiModels() {
    }

    public record ExecutorIdentityRequest(
            @NotBlank String deviceId,
            @NotBlank String protocolVersion,
            @NotBlank String executorVersion,
            @NotBlank String brand,
            @NotBlank String model,
            @NotBlank String androidVersion,
            int screenWidth,
            int screenHeight,
            @NotNull Capabilities capabilities,
            @NotNull List<String> installedProfiles,
            @NotNull List<String> tags,
            @NotBlank String hostGroup,
            HealthSnapshot healthSnapshot,
            String currentAttemptId
    ) {
    }

    public record Capabilities(
            boolean accessibilityEnabled,
            boolean rootAvailable,
            boolean shellAvailable,
            boolean networkIsolationAvailable,
            Boolean screenshotCapable,
            Boolean uiDumpCapable
    ) {
    }

    public record HealthSnapshot(
            boolean backendReachable,
            boolean accessibilityEnabled,
            boolean rootAvailable,
            boolean shellAvailable,
            boolean networkIsolationAvailable,
            String foregroundPackage,
            Integer batteryLevel,
            String thermalStatus,
            long capturedAt
    ) {
    }

    public record ExecutorAckResponse(
            boolean registered,
            long serverTimeMs,
            String configVersion
    ) {
    }

    public record HeartbeatResponse(
            boolean registered,
            long serverTimeMs,
            String configVersion,
            RunConfig runConfig,
            List<Command> commands
    ) {
    }

    public record ClaimTaskResponse(
            boolean hasTask,
            ClaimedTask task
    ) {
    }

    public record ClaimedTask(
            String taskId,
            String attemptId,
            String runId,
            String taskType,
            String profilePackage,
            Map<String, Object> taskPayload,
            RunConfig runConfig,
            ArtifactPolicy artifactPolicy,
            int priority,
            List<String> labels,
            ArtifactUploadMode artifactUploadMode,
            long leaseExpireAt,
            String scheduleVersion,
            String idempotencyKey,
            String source
    ) {
    }

    public record RunConfig(
            int loopCount,
            long budgetMs,
            long loopIntervalMs,
            boolean networkIsolationEnabled,
            long pollIntervalMs,
            long heartbeatIntervalMs
    ) {
    }

    public record ArtifactPolicy(
            boolean uploadLog,
            boolean uploadScreenshot,
            boolean uploadDump
    ) {
    }

    public record Command(
            @NotBlank String type,
            String attemptId
    ) {
    }

    public record StartRequest(
            @NotBlank String taskId,
            @NotBlank String attemptId,
            @NotBlank String runId,
            @NotBlank String profilePackage,
            @NotBlank String taskType,
            @NotBlank String source
    ) {
    }

    public record EventsRequest(
            @NotEmpty @Valid List<RunEvent> events
    ) {
    }

    public record RunEvent(
            @NotBlank String attemptId,
            @NotBlank String taskId,
            @NotBlank String deviceId,
            @NotBlank String runId,
            String scenarioId,
            Integer stepIndex,
            Integer actionIndex,
            @NotBlank String eventType,
            String state,
            String code,
            @NotBlank String message,
            long ts
    ) {
    }

    public record ExecutorWaypointSegmentsRequest(
            @NotEmpty @Size(max = 256) @Valid List<ExecutorWaypointSegment> waypointSegments
    ) {
        @JsonAnySetter
        public void rejectUnknownField(String name, Object value) {
            throw new IllegalArgumentException("Unknown executor waypoint request field: " + name);
        }
    }

    public record ExecutorWaypointSegment(
            @JsonProperty("step_id") @NotBlank String stepId,
            @JsonProperty("behavior_label") @NotBlank String behaviorLabel,
            @JsonProperty("entered_at_ms") Long enteredAtMs,
            @JsonProperty("arrived_at_ms") Long arrivedAtMs,
            @JsonProperty("dwell_ms") Long dwellMs
    ) {
        @JsonAnySetter
        public void rejectUnknownField(String name, Object value) {
            throw new IllegalArgumentException("Unknown executor waypoint segment field: " + name);
        }
    }

    public record ExecutorWaypointSegmentsResponse(
            String runTargetId,
            String attemptId,
            int recordedCount
    ) {
    }

    public record FinishRequest(
            @NotBlank String taskId,
            @NotBlank String attemptId,
            @NotBlank String runId,
            @NotBlank String status,
            PreflightSummary preflightSummary,
            FailureDetail failureDetail,
            String message
    ) {
    }

    public record PreflightSummary(
            boolean ok,
            @NotBlank String failureCode,
            @NotBlank String failureMessage,
            @NotBlank String targetProfilePackage,
            boolean networkIsolationRequired,
            long capturedAt
    ) {
    }

    public record FailureDetail(
            @NotBlank String failureCode,
            @NotBlank String failureStage,
            @NotBlank String lastError,
            long capturedAt
    ) {
    }

    public record ArtifactUploadTicketRequest(
            @NotBlank String taskId,
            @NotBlank String runId,
            @NotBlank String artifactId,
            @NotBlank String artifactType,
            @NotBlank String fileName,
            @NotBlank String mimeType,
            @PositiveOrZero long sizeBytes
    ) {
    }

    public record ArtifactUploadTicketResponse(
            String artifactId,
            ArtifactUploadMode artifactUploadMode,
            String uploadUrl,
            String httpMethod,
            Map<String, String> requiredHeaders,
            String objectKey,
            long expiresAt
    ) {
    }

    public record ArtifactUploadFinalizeRequest(
            @NotBlank String taskId,
            @NotBlank String runId,
            @NotBlank String artifactId,
            String etag
    ) {
    }

    public record ArtifactUploadFinalizeResponse(
            boolean accepted,
            String artifactId,
            long sizeBytes
    ) {
    }
}

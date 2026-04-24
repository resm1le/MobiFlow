package com.example.platform.ai.api.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.databind.JsonNode;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import java.util.List;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record FailureTriageContext(
        @Valid @NotNull RunDto run,
        @Valid @NotNull RunTargetDto target,
        @Valid @NotNull AttemptDto latestAttempt,
        @Valid @NotNull AttemptHistorySummaryDto attemptHistorySummary,
        @Valid @NotNull FailureContextDto failureContext,
        @NotNull List<@Valid KeyEventDto> keyEvents,
        @NotNull List<@Valid ArtifactManifestItemDto> artifactManifest,
        @Valid @NotNull DeviceOperationalSnapshot deviceOperationalSnapshot
) {
    public record RunDto(
            @NotBlank String runId,
            @NotBlank String poolId,
            @NotBlank String status,
            String finalState,
            @NotBlank String taskType,
            @NotBlank String profilePackage,
            int priority,
            @NotNull List<@NotBlank String> labels,
            int maxRetriesPerDevice,
            long queueTimeoutMs,
            boolean cancelRequested,
            Long startedAt,
            Long finishedAt
    ) {
    }

    public record RunTargetDto(
            @NotBlank String runTargetId,
            @NotBlank String deviceId,
            @NotBlank String status,
            int attemptCount,
            String currentTaskId,
            String latestAttemptId,
            String failureReason,
            Long startedAt,
            Long finishedAt
    ) {
    }

    public record AttemptDto(
            @NotBlank String attemptId,
            @NotBlank String taskId,
            @NotBlank String deviceId,
            @NotBlank String runId,
            @NotBlank String status,
            String finalState,
            String failureReason,
            @NotNull JsonNode preflightSummary,
            @NotNull JsonNode failureDetail,
            Long startedAt,
            Long finishedAt,
            long createdAt
    ) {
    }

    public record AttemptHistorySummaryDto(
            int attemptCount,
            @NotNull List<@Valid AttemptHistoryEntryDto> recentAttempts,
            boolean queueTimeoutObserved,
            boolean cancelObserved
    ) {
    }

    public record AttemptHistoryEntryDto(
            @NotBlank String attemptId,
            @NotBlank String status,
            String finalState,
            String failureReason,
            Long finishedAt,
            @NotBlank String deviceId
    ) {
    }

    public record FailureContextDto(
            String finalState,
            String failureReason,
            String lastError,
            boolean queueTimeout,
            boolean cancelled,
            boolean leaseLost,
            boolean precheckFailed,
            @NotNull JsonNode preflightSummary,
            @NotNull JsonNode failureDetail
    ) {
    }

    public record KeyEventDto(
            @NotBlank String eventType,
            String state,
            String code,
            @NotBlank String message,
            long ts
    ) {
    }

    public record ArtifactManifestItemDto(
            @NotBlank String artifactId,
            @NotBlank String artifactType,
            @NotBlank String fileName,
            @NotBlank String mimeType,
            long sizeBytes,
            @NotBlank String objectKey
    ) {
    }
}

package com.example.platform.ai.api.dto;

import com.example.platform.ai.api.dto.FailureTriageContext.ArtifactManifestItemDto;
import com.example.platform.ai.api.dto.FailureTriageContext.AttemptDto;
import com.example.platform.ai.api.dto.FailureTriageContext.KeyEventDto;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import java.util.List;

public record RunSummaryContext(
        @Valid @NotNull RunDto run,
        @Valid @NotNull CountsDto counts,
        @NotNull List<@Valid RunTargetDto> targets,
        @NotNull List<@Valid AttemptDto> representativeAttempts,
        @NotNull List<@Valid KeyEventDto> keyEvents,
        @NotNull List<@Valid ArtifactManifestItemDto> artifactManifest
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

    public record CountsDto(
            int totalTargets,
            int queued,
            int running,
            int retryPending,
            int succeeded,
            int failed,
            int cancelled
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
}

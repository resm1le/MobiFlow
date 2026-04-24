package com.example.platform.ai.api.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.databind.JsonNode;
import jakarta.validation.constraints.NotBlank;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record AttemptInputDto(
        @NotBlank String attemptId,
        @NotBlank String taskId,
        String deviceId,
        @NotBlank String status,
        String finalState,
        String failureReason,
        String profilePackage,
        String taskType,
        JsonNode taskPayload,
        JsonNode runConfig,
        Long startedAt,
        Long finishedAt
) {
}

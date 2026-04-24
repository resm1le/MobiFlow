package com.example.platform.ai.api.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import jakarta.validation.constraints.NotBlank;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record RunEventInputDto(
        String attemptId,
        String taskId,
        String deviceId,
        String runId,
        String scenarioId,
        Integer stepIndex,
        Integer actionIndex,
        @NotBlank String eventType,
        String state,
        String code,
        @NotBlank String message,
        Long ts
) {
}

package com.example.platform.ai.api.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.databind.JsonNode;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import java.util.List;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record RunDraftResult(
        @Valid @NotNull RunDraftDto runDraft,
        @NotNull List<@NotBlank String> warnings,
        @NotNull List<@NotBlank String> reviewHints
) {
    public record RunDraftDto(
            @NotBlank String name,
            String description,
            @NotBlank String devicePoolId,
            @NotBlank String taskType,
            @NotBlank String profilePackage,
            @NotNull JsonNode taskPayload,
            @NotNull JsonNode runConfig,
            @NotNull JsonNode artifactPolicy,
            int priority,
            @NotNull List<@NotBlank String> labels,
            int maxRetriesPerDevice,
            long queueTimeoutMs
    ) {
    }
}

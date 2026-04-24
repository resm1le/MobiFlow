package com.example.platform.ai.api.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.databind.JsonNode;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

import java.util.List;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record RunPlanningContext(
        @NotBlank String goal,
        JsonNode constraints,
        @NotEmpty List<@Valid AvailableDevicePoolDto> availableDevicePools,
        @NotEmpty List<@Valid AvailableProfileDto> availableProfiles,
        @Valid @NotNull DefaultRunPolicyDto defaultRunPolicy,
        @NotEmpty List<@NotBlank String> allowedTaskTypes
) {
    public record AvailableDevicePoolDto(
            @NotBlank String poolId,
            @NotBlank String name,
            String hostGroup,
            int deviceCount,
            @NotNull List<@NotBlank String> requiredTags,
            @NotNull List<@NotBlank String> excludedTags
    ) {
    }

    public record AvailableProfileDto(
            @NotBlank String profilePackage,
            int installedDeviceCount,
            @NotNull List<@NotBlank String> supportedTaskTypes,
            @NotNull List<@NotBlank String> requiredTaskPayloadFields,
            @NotNull JsonNode recommendedDefaults,
            @NotNull List<@NotBlank String> knownLimitations
    ) {
    }

    public record DefaultRunPolicyDto(
            int priority,
            int maxRetriesPerDevice,
            long queueTimeoutMs,
            @NotNull JsonNode defaultRunConfig,
            @NotNull JsonNode defaultArtifactPolicy
    ) {
    }
}

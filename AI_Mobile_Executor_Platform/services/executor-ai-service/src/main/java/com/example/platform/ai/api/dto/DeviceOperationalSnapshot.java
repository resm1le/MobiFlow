package com.example.platform.ai.api.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.databind.JsonNode;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import java.util.List;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record DeviceOperationalSnapshot(
        @NotNull DeviceOperationalSnapshotType snapshotType,
        long capturedAt,
        @NotBlank String deviceId,
        String hostGroup,
        @NotNull List<@NotBlank String> profilePackages,
        @NotNull JsonNode capabilities,
        @NotNull JsonNode healthSnapshot,
        @NotNull JsonNode preflightSummary,
        Long lastHeartbeatAt
) {
}

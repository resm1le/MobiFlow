package com.example.platform.ai.api.dto;

import com.fasterxml.jackson.annotation.JsonInclude;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record ArtifactPolicyDto(
        boolean uploadLog,
        boolean uploadScreenshot,
        boolean uploadDump
) {
}

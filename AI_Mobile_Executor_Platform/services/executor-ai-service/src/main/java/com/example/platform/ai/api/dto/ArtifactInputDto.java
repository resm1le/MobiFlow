package com.example.platform.ai.api.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import jakarta.validation.constraints.NotBlank;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record ArtifactInputDto(
        String artifactId,
        @NotBlank String artifactType,
        @NotBlank String fileName,
        String mimeType,
        Long sizeBytes,
        String objectKey
) {
}

package com.example.platform.ai.api.dto;

import com.fasterxml.jackson.annotation.JsonInclude;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record ModelMetaDto(
        String provider,
        String model,
        long generatedAt
) {
}

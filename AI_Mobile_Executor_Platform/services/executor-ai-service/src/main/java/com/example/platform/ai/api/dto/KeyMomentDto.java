package com.example.platform.ai.api.dto;

import com.fasterxml.jackson.annotation.JsonInclude;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record KeyMomentDto(
        String title,
        String eventType,
        Integer stepIndex,
        String message
) {
}

package com.example.platform.ai.api.dto;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;

public record FailureTriageResponse(
        @Valid @NotNull FailureTriageResult result,
        @Valid @NotNull ModelMetaDto modelMeta
) {
}

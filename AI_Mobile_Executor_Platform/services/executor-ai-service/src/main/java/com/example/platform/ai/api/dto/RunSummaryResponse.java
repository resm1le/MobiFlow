package com.example.platform.ai.api.dto;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;

public record RunSummaryResponse(
        @Valid @NotNull RunSummaryResult result,
        @Valid @NotNull ModelMetaDto modelMeta
) {
}

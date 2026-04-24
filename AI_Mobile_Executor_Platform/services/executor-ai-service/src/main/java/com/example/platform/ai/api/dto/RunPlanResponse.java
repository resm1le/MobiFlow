package com.example.platform.ai.api.dto;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;

import java.util.List;

public record RunPlanResponse(
        @Valid @NotNull RunDraftResult.RunDraftDto runDraft,
        @NotNull List<String> warnings,
        @NotNull List<String> reviewHints,
        @Valid @NotNull ModelMetaDto modelMeta
) {
}

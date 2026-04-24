package com.example.platform.ai.api.dto;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import java.util.List;

public record RunSummaryResult(
        @NotBlank String summaryText,
        @NotNull List<@Valid KeyMomentDto> keyMoments,
        @NotBlank String finalJudgement,
        @NotNull List<@NotBlank String> evidence
) {
}

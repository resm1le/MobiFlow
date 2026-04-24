package com.example.platform.ai.api.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import java.util.List;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record FailureTriageResult(
        @NotNull FailureCategoryDto failureCategory,
        @NotBlank String probableCause,
        double confidence,
        @NotNull RetryRecommendationDto retryRecommendation,
        @NotNull SuggestedNextActionDto suggestedNextAction,
        @NotNull List<@NotBlank String> operatorReviewHints,
        @NotNull List<@NotBlank String> evidence
) {
}

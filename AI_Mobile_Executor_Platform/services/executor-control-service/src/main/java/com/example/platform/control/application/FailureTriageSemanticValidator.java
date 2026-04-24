package com.example.platform.control.application;

import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.EnumSet;
import java.util.List;
import java.util.Set;

@Component
public class FailureTriageSemanticValidator {

    private static final Set<Phase3AiModels.FailureCategory> RETRYABLE_CATEGORIES = EnumSet.of(
            Phase3AiModels.FailureCategory.NETWORK_ERROR,
            Phase3AiModels.FailureCategory.UI_NOT_FOUND,
            Phase3AiModels.FailureCategory.LEASE_INTERRUPTED,
            Phase3AiModels.FailureCategory.PRECHECK_FAILED,
            Phase3AiModels.FailureCategory.QUEUE_TIMEOUT,
            Phase3AiModels.FailureCategory.UNKNOWN
    );
    private static final Set<Phase3AiModels.FailureCategory> PROFILE_FOCUSED_CATEGORIES = EnumSet.of(
            Phase3AiModels.FailureCategory.PROFILE_NOT_READY,
            Phase3AiModels.FailureCategory.UI_NOT_FOUND
    );
    private static final Set<Phase3AiModels.FailureCategory> DEVICE_FOCUSED_CATEGORIES = EnumSet.of(
            Phase3AiModels.FailureCategory.PERMISSION_MISSING,
            Phase3AiModels.FailureCategory.DEVICE_STATE_MISMATCH,
            Phase3AiModels.FailureCategory.PRECHECK_FAILED
    );

    public Phase3AiModels.ValidationResult validate(Phase3AiModels.FailureTriageResult result) {
        List<String> errors = new ArrayList<>();
        List<String> warnings = new ArrayList<>();
        if (result == null) {
            return new Phase3AiModels.ValidationResult(false, List.of("failure triage result must be present"), List.of());
        }
        if (result.probableCause() == null || result.probableCause().isBlank()) {
            errors.add("probableCause must be non-blank");
        }
        if (result.confidence() < 0.0d || result.confidence() > 1.0d) {
            errors.add("confidence must be between 0 and 1");
        }
        if (!isRetryCompatible(result.failureCategory(), result.retryRecommendation())) {
            errors.add("retryRecommendation is incompatible with failureCategory");
        }
        if (!isSuggestedActionCompatible(result.failureCategory(), result.suggestedNextAction())) {
            errors.add("suggestedNextAction is incompatible with failureCategory");
        }
        if (result.evidence() == null || result.evidence().isEmpty()) {
            warnings.add("triage result should include at least one evidence item");
        }
        return new Phase3AiModels.ValidationResult(errors.isEmpty(), List.copyOf(errors), List.copyOf(warnings));
    }

    private boolean isRetryCompatible(Phase3AiModels.FailureCategory category,
                                      Phase3AiModels.RetryRecommendation recommendation) {
        if (recommendation == Phase3AiModels.RetryRecommendation.NO_RETRY
                || recommendation == Phase3AiModels.RetryRecommendation.ESCALATE_OPERATOR) {
            return true;
        }
        if (recommendation == Phase3AiModels.RetryRecommendation.INSPECT_PROFILE) {
            return PROFILE_FOCUSED_CATEGORIES.contains(category);
        }
        if (recommendation == Phase3AiModels.RetryRecommendation.INSPECT_ENVIRONMENT) {
            return DEVICE_FOCUSED_CATEGORIES.contains(category)
                    || category == Phase3AiModels.FailureCategory.NETWORK_ERROR;
        }
        return RETRYABLE_CATEGORIES.contains(category);
    }

    private boolean isSuggestedActionCompatible(Phase3AiModels.FailureCategory category,
                                                Phase3AiModels.SuggestedNextAction action) {
        return switch (action) {
            case NONE, MANUAL_REVIEW, INSPECT_ARTIFACTS -> true;
            case RETRY_TARGET, RETRY_ON_OTHER_DEVICE -> RETRYABLE_CATEGORIES.contains(category);
            case INSPECT_DEVICE_HEALTH -> DEVICE_FOCUSED_CATEGORIES.contains(category)
                    || category == Phase3AiModels.FailureCategory.NETWORK_ERROR;
            case INSPECT_PROFILE_LOGIC -> PROFILE_FOCUSED_CATEGORIES.contains(category);
            case CHECK_CONTROL_PLANE -> category == Phase3AiModels.FailureCategory.LEASE_INTERRUPTED
                    || category == Phase3AiModels.FailureCategory.QUEUE_TIMEOUT;
        };
    }
}

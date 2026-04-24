package com.example.platform.control.application;

import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class FailureTriageSemanticValidatorTest {

    private final FailureTriageSemanticValidator validator = new FailureTriageSemanticValidator();

    @Test
    void rejectsIncompatibleActionAndRetryCombination() {
        Phase3AiModels.ValidationResult result = validator.validate(new Phase3AiModels.FailureTriageResult(
                Phase3AiModels.FailureCategory.PERMISSION_MISSING,
                "permission dialog blocked execution",
                0.9d,
                Phase3AiModels.RetryRecommendation.RETRY_OTHER_DEVICE,
                Phase3AiModels.SuggestedNextAction.INSPECT_PROFILE_LOGIC,
                List.of("check accessibility permission"),
                List.of("failure_detail.permission_missing")
        ));

        assertFalse(result.valid());
        assertTrue(result.errors().stream().anyMatch(error -> error.contains("retryRecommendation")));
        assertTrue(result.errors().stream().anyMatch(error -> error.contains("suggestedNextAction")));
    }
}

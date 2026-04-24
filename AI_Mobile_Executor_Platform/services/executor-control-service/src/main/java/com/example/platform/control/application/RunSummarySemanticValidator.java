package com.example.platform.control.application;

import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.List;

@Component
public class RunSummarySemanticValidator {

    public Phase3AiModels.ValidationResult validate(Phase3AiModels.RunSummaryResult result) {
        List<String> errors = new ArrayList<>();
        List<String> warnings = new ArrayList<>();
        if (result == null) {
            errors.add("run summary result is required");
            return new Phase3AiModels.ValidationResult(false, errors, warnings);
        }
        if (result.summaryText() == null || result.summaryText().isBlank()) {
            errors.add("summaryText must be non-blank");
        }
        if (result.finalJudgement() == null || result.finalJudgement().isBlank()) {
            errors.add("finalJudgement must be non-blank");
        }
        if (result.keyMoments() == null) {
            errors.add("keyMoments must be present");
        } else {
            for (int index = 0; index < result.keyMoments().size(); index++) {
                Phase3AiModels.RunSummaryKeyMoment keyMoment = result.keyMoments().get(index);
                if (keyMoment == null || keyMoment.title() == null || keyMoment.title().isBlank()) {
                    errors.add("keyMoments[" + index + "].title must be non-blank");
                }
            }
        }
        if (result.evidence() == null) {
            errors.add("evidence must be present");
        } else if (result.evidence().isEmpty()) {
            warnings.add("evidence should include at least one concrete item");
        }
        return new Phase3AiModels.ValidationResult(errors.isEmpty(), List.copyOf(errors), List.copyOf(warnings));
    }
}

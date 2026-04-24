package com.example.platform.control.api;

import jakarta.validation.constraints.NotBlank;

import java.util.List;
import java.util.Map;

public final class AiRunPlanApiModels {

    private AiRunPlanApiModels() {
    }

    public record CreateRunPlanRequest(
            @NotBlank String goal,
            Map<String, Object> constraints
    ) {
    }

    public record MaterializeRunPlanRequest(
            @NotBlank String createdBy
    ) {
    }

    public record PlanValidationResponse(
            boolean materializable,
            List<String> errors,
            List<String> warnings
    ) {
    }

    public record CreateRunPlanResponse(
            String requestId,
            com.example.platform.control.application.Phase3AiModels.RunDraft runDraft,
            List<String> warnings,
            List<String> reviewHints,
            PlanValidationResponse validation,
            Map<String, Object> modelMeta
    ) {
    }

    public record RunPlanResponse(
            String requestId,
            String status,
            String goal,
            Map<String, Object> constraints,
            com.example.platform.control.application.Phase3AiModels.RunDraft runDraft,
            List<String> warnings,
            List<String> reviewHints,
            PlanValidationResponse validation,
            Map<String, Object> modelMeta,
            String materializedRunId,
            String materializedBy,
            Long materializedAt,
            long generatedAt
    ) {
    }
}

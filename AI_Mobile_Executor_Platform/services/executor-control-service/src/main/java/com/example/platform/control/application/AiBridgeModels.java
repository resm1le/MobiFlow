package com.example.platform.control.application;

import java.util.List;
import java.util.Map;

public final class AiBridgeModels {

    private AiBridgeModels() {
    }

    public record RunPlanResponse(
            Phase3AiModels.RunDraft runDraft,
            List<String> warnings,
            List<String> reviewHints,
            Map<String, Object> modelMeta
    ) {
    }

    public record FailureTriageResponse(
            Phase3AiModels.FailureTriageResult result,
            Map<String, Object> modelMeta
    ) {
    }

    public record RunSummaryResponse(
            Phase3AiModels.RunSummaryResult result,
            Map<String, Object> modelMeta
    ) {
    }
}

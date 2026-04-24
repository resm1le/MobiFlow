package com.example.platform.control.api;

import com.example.platform.control.application.Phase3AiModels;

import java.util.List;
import java.util.Map;

public final class AiRunSummaryApiModels {

    private AiRunSummaryApiModels() {
    }

    public record ValidationResponse(
            boolean valid,
            List<String> errors,
            List<String> warnings
    ) {
    }

    public record RunSummaryResponse(
            String summaryId,
            String runId,
            Phase3AiModels.RunSummaryResult result,
            ValidationResponse validation,
            Map<String, Object> modelMeta,
            long generatedAt
    ) {
    }
}

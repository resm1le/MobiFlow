package com.example.platform.control.api;

import com.example.platform.control.application.Phase3AiModels;

import java.util.List;
import java.util.Map;

public final class AiFailureTriageApiModels {

    private AiFailureTriageApiModels() {
    }

    public record ValidationResponse(
            boolean valid,
            List<String> errors,
            List<String> warnings
    ) {
    }

    public record FailureTriageResponse(
            String triageResultId,
            String runTargetId,
            Phase3AiModels.FailureTriageResult result,
            ValidationResponse validation,
            Map<String, Object> modelMeta,
            long generatedAt
    ) {
    }
}

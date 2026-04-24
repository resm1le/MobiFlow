package com.example.platform.control.application;

public interface AiBridgeClient {

    AiBridgeModels.RunPlanResponse createRunPlan(Phase3AiModels.RunPlanningContext request);

    AiBridgeModels.FailureTriageResponse createFailureTriage(Phase3AiModels.FailureTriageContext request);

    AiBridgeModels.RunSummaryResponse createRunSummary(Phase3AiModels.RunSummaryContext request);
}

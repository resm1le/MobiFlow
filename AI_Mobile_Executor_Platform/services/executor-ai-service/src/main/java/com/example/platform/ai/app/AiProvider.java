package com.example.platform.ai.app;

import com.example.platform.ai.api.dto.FailureTriageContext;
import com.example.platform.ai.api.dto.RunPlanningContext;
import com.example.platform.ai.api.dto.RunSummaryContext;

public interface AiProvider {

    AiProviderMode mode();

    ProviderResult generateRunPlan(RunPlanningContext context);

    ProviderResult generateFailureTriage(FailureTriageContext context);

    ProviderResult generateRunSummary(RunSummaryContext context);
}

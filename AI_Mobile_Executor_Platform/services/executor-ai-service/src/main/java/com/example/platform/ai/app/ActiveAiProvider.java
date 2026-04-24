package com.example.platform.ai.app;

import com.example.platform.ai.api.dto.FailureTriageContext;
import com.example.platform.ai.api.dto.RunPlanningContext;
import com.example.platform.ai.api.dto.RunSummaryContext;
import org.springframework.stereotype.Service;

import java.util.EnumMap;
import java.util.List;
import java.util.Map;

@Service
public class ActiveAiProvider {

    private final Map<AiProviderMode, AiProvider> providers;
    private final AiProperties properties;

    public ActiveAiProvider(List<AiProvider> providers, AiProperties properties) {
        this.properties = properties;
        this.providers = new EnumMap<>(AiProviderMode.class);
        for (AiProvider provider : providers) {
            this.providers.put(provider.mode(), provider);
        }
    }

    public ProviderResult generateRunPlan(RunPlanningContext context) {
        return currentProvider().generateRunPlan(context);
    }

    public ProviderResult generateFailureTriage(FailureTriageContext context) {
        return currentProvider().generateFailureTriage(context);
    }

    public ProviderResult generateRunSummary(RunSummaryContext context) {
        return currentProvider().generateRunSummary(context);
    }

    private AiProvider currentProvider() {
        AiProviderMode configuredMode = properties.getProvider().getMode();
        AiProvider provider = providers.get(configuredMode);
        if (provider == null) {
            throw AiServiceException.providerUnavailable("No AI provider registered for mode " + configuredMode);
        }
        return provider;
    }
}

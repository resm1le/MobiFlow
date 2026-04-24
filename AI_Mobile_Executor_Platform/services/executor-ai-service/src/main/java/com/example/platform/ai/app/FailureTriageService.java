package com.example.platform.ai.app;

import com.example.platform.ai.api.dto.FailureTriageContext;
import com.example.platform.ai.api.dto.FailureTriageResponse;
import com.example.platform.ai.api.dto.ModelMetaDto;
import org.springframework.stereotype.Service;

@Service
public class FailureTriageService {

    private final ActiveAiProvider activeAiProvider;
    private final Phase3StructuredOutputValidator phase3StructuredOutputValidator;

    public FailureTriageService(ActiveAiProvider activeAiProvider,
                                Phase3StructuredOutputValidator phase3StructuredOutputValidator) {
        this.activeAiProvider = activeAiProvider;
        this.phase3StructuredOutputValidator = phase3StructuredOutputValidator;
    }

    public FailureTriageResponse createFailureTriage(FailureTriageContext context) {
        ProviderResult providerResult = activeAiProvider.generateFailureTriage(context);
        var validated = phase3StructuredOutputValidator.validateFailureTriageResult(providerResult.payload());
        ModelMetaDto modelMeta = providerResult.modelMeta() == null
                ? new ModelMetaDto("unknown", "unknown", System.currentTimeMillis())
                : providerResult.modelMeta();
        return new FailureTriageResponse(validated, modelMeta);
    }
}

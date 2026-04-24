package com.example.platform.ai.app;

import com.example.platform.ai.api.dto.ModelMetaDto;
import com.example.platform.ai.api.dto.RunSummaryContext;
import com.example.platform.ai.api.dto.RunSummaryResponse;
import com.example.platform.ai.api.dto.RunSummaryResult;
import org.springframework.stereotype.Service;

@Service
public class RunSummaryService {

    private final ActiveAiProvider activeAiProvider;
    private final Phase3StructuredOutputValidator phase3StructuredOutputValidator;

    public RunSummaryService(ActiveAiProvider activeAiProvider,
                             Phase3StructuredOutputValidator phase3StructuredOutputValidator) {
        this.activeAiProvider = activeAiProvider;
        this.phase3StructuredOutputValidator = phase3StructuredOutputValidator;
    }

    public RunSummaryResponse createRunSummary(RunSummaryContext context) {
        ProviderResult providerResult = activeAiProvider.generateRunSummary(context);
        RunSummaryResult validated = phase3StructuredOutputValidator.validateRunSummaryResult(
                providerResult.payload(),
                context
        );
        ModelMetaDto modelMeta = providerResult.modelMeta() == null
                ? new ModelMetaDto("unknown", "unknown", System.currentTimeMillis())
                : providerResult.modelMeta();
        return new RunSummaryResponse(validated, modelMeta);
    }
}

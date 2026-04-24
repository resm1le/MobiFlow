package com.example.platform.ai.app;

import com.example.platform.ai.api.dto.ModelMetaDto;
import com.example.platform.ai.api.dto.RunDraftResult;
import com.example.platform.ai.api.dto.RunPlanResponse;
import com.example.platform.ai.api.dto.RunPlanningContext;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;

@Service
public class RunPlanningService {

    private final ActiveAiProvider activeAiProvider;
    private final Phase3StructuredOutputValidator phase3StructuredOutputValidator;
    private final RunPlanningIntentExtractor runPlanningIntentExtractor;
    private final RunPlanningSemanticCanonicalizer runPlanningSemanticCanonicalizer;

    public RunPlanningService(ActiveAiProvider activeAiProvider,
                              Phase3StructuredOutputValidator phase3StructuredOutputValidator,
                              RunPlanningIntentExtractor runPlanningIntentExtractor,
                              RunPlanningSemanticCanonicalizer runPlanningSemanticCanonicalizer) {
        this.activeAiProvider = activeAiProvider;
        this.phase3StructuredOutputValidator = phase3StructuredOutputValidator;
        this.runPlanningIntentExtractor = runPlanningIntentExtractor;
        this.runPlanningSemanticCanonicalizer = runPlanningSemanticCanonicalizer;
    }

    public RunPlanResponse createRunPlan(RunPlanningContext context) {
        RunPlanningIntentSignals signals = runPlanningIntentExtractor.extract(context);
        ProviderResult providerResult = activeAiProvider.generateRunPlan(context);
        RunDraftResult validated = phase3StructuredOutputValidator.validateRunDraftResult(providerResult.payload(), context);
        RunPlanningSemanticCanonicalizer.CanonicalRunPlanningResult canonical = runPlanningSemanticCanonicalizer.canonicalize(
                validated.runDraft(),
                signals,
                context
        );

        LinkedHashSet<String> warnings = new LinkedHashSet<>(validated.warnings());
        warnings.addAll(providerResult.warnings());
        warnings.addAll(canonical.warnings());
        List<String> reviewHints = new ArrayList<>(validated.reviewHints());
        reviewHints.addAll(canonical.reviewHints());
        ModelMetaDto modelMeta = providerResult.modelMeta() == null
                ? new ModelMetaDto("unknown", "unknown", System.currentTimeMillis())
                : providerResult.modelMeta();
        return new RunPlanResponse(
                canonical.runDraft(),
                List.copyOf(warnings),
                List.copyOf(reviewHints),
                modelMeta
        );
    }
}

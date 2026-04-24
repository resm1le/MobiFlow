package com.example.platform.ai.app;

import com.example.platform.ai.api.dto.FailureCategoryDto;
import com.example.platform.ai.api.dto.FailureTriageContext;
import com.example.platform.ai.api.dto.ModelMetaDto;
import com.example.platform.ai.api.dto.RetryRecommendationDto;
import com.example.platform.ai.api.dto.RunDraftResult;
import com.example.platform.ai.api.dto.RunPlanningContext;
import com.example.platform.ai.api.dto.RunSummaryContext;
import com.example.platform.ai.api.dto.SuggestedNextActionDto;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.springframework.stereotype.Component;

import java.time.Instant;
import java.util.List;

@Component
public class StubAiProvider implements AiProvider {

    private final ObjectMapper objectMapper;
    private final RunPlanningIntentExtractor runPlanningIntentExtractor;
    private final RunPlanningSemanticCanonicalizer runPlanningSemanticCanonicalizer;

    public StubAiProvider(ObjectMapper objectMapper,
                          RunPlanningIntentExtractor runPlanningIntentExtractor,
                          RunPlanningSemanticCanonicalizer runPlanningSemanticCanonicalizer) {
        this.objectMapper = objectMapper;
        this.runPlanningIntentExtractor = runPlanningIntentExtractor;
        this.runPlanningSemanticCanonicalizer = runPlanningSemanticCanonicalizer;
    }

    @Override
    public AiProviderMode mode() {
        return AiProviderMode.STUB;
    }

    @Override
    public ProviderResult generateRunPlan(RunPlanningContext context) {
        RunPlanningIntentSignals signals = runPlanningIntentExtractor.extract(context);
        RunDraftResult.RunDraftDto runDraft = runPlanningSemanticCanonicalizer.defaultDraft(context, signals, context.goal());
        ObjectNode payload = objectMapper.createObjectNode();
        payload.set("runDraft", objectMapper.valueToTree(runDraft));
        payload.set("warnings", arrayOf("Stub provider returned a deterministic run draft."));
        payload.set("reviewHints", objectMapper.createArrayNode());
        return new ProviderResult(payload, List.of(), modelMeta());
    }

    @Override
    public ProviderResult generateFailureTriage(FailureTriageContext context) {
        FailureCategoryDto category = chooseFailureTriageCategory(context);
        ObjectNode payload = objectMapper.createObjectNode();
        payload.put("failureCategory", category.name());
        payload.put("probableCause", buildFailureTriageProbableCause(context, category));
        payload.put("confidence", category == FailureCategoryDto.UNKNOWN ? 0.55d : 0.82d);
        payload.put("retryRecommendation", chooseRetryRecommendation(category).name());
        payload.put("suggestedNextAction", chooseSuggestedNextAction(category).name());
        payload.set("operatorReviewHints", arrayOf(buildOperatorReviewHint(context, category)));
        payload.set("evidence", buildFailureTriageEvidence(context));
        return new ProviderResult(payload, List.of(), modelMeta());
    }

    @Override
    public ProviderResult generateRunSummary(RunSummaryContext context) {
        ObjectNode payload = objectMapper.createObjectNode();
        payload.put("summaryText", buildRunSummaryText(context));
        payload.set("keyMoments", buildRunSummaryKeyMoments(context));
        payload.put("finalJudgement", buildRunSummaryFinalJudgement(context));
        payload.set("evidence", buildRunSummaryEvidence(context));
        return new ProviderResult(payload, List.of(), modelMeta());
    }

    private ArrayNode arrayOf(String... values) {
        ArrayNode node = objectMapper.createArrayNode();
        for (String value : values) {
            node.add(value);
        }
        return node;
    }

    private FailureCategoryDto chooseFailureTriageCategory(FailureTriageContext context) {
        if (context.failureContext().precheckFailed()) {
            return FailureCategoryDto.PRECHECK_FAILED;
        }
        if (context.failureContext().queueTimeout()) {
            return FailureCategoryDto.QUEUE_TIMEOUT;
        }
        if (context.failureContext().cancelled()) {
            return FailureCategoryDto.RUN_CANCELLED;
        }
        if (context.failureContext().leaseLost()) {
            return FailureCategoryDto.LEASE_INTERRUPTED;
        }
        String lastError = context.failureContext().lastError() == null
                ? ""
                : context.failureContext().lastError().toLowerCase();
        if (lastError.contains("permission")) {
            return FailureCategoryDto.PERMISSION_MISSING;
        }
        if (lastError.contains("network")) {
            return FailureCategoryDto.NETWORK_ERROR;
        }
        if (lastError.contains("profile")) {
            return FailureCategoryDto.PROFILE_NOT_READY;
        }
        if (lastError.contains("ui") || lastError.contains("not found")) {
            return FailureCategoryDto.UI_NOT_FOUND;
        }
        return FailureCategoryDto.UNKNOWN;
    }

    private String buildFailureTriageProbableCause(FailureTriageContext context, FailureCategoryDto category) {
        return "Stub triage classified target " + context.target().runTargetId()
                + " as " + category.name()
                + " using failureReason=\"" + context.failureContext().failureReason()
                + "\" and lastError=\"" + context.failureContext().lastError() + "\".";
    }

    private RetryRecommendationDto chooseRetryRecommendation(FailureCategoryDto category) {
        return switch (category) {
            case NETWORK_ERROR, UI_NOT_FOUND, LEASE_INTERRUPTED, PRECHECK_FAILED, QUEUE_TIMEOUT, UNKNOWN ->
                    RetryRecommendationDto.RETRY_SAME_DEVICE;
            case PROFILE_NOT_READY -> RetryRecommendationDto.INSPECT_PROFILE;
            case PERMISSION_MISSING, DEVICE_STATE_MISMATCH -> RetryRecommendationDto.INSPECT_ENVIRONMENT;
            case RUN_CANCELLED -> RetryRecommendationDto.NO_RETRY;
        };
    }

    private SuggestedNextActionDto chooseSuggestedNextAction(FailureCategoryDto category) {
        return switch (category) {
            case NETWORK_ERROR, PRECHECK_FAILED -> SuggestedNextActionDto.INSPECT_DEVICE_HEALTH;
            case UI_NOT_FOUND, PROFILE_NOT_READY -> SuggestedNextActionDto.INSPECT_PROFILE_LOGIC;
            case LEASE_INTERRUPTED, QUEUE_TIMEOUT -> SuggestedNextActionDto.CHECK_CONTROL_PLANE;
            case RUN_CANCELLED, UNKNOWN -> SuggestedNextActionDto.MANUAL_REVIEW;
            case PERMISSION_MISSING, DEVICE_STATE_MISMATCH -> SuggestedNextActionDto.INSPECT_DEVICE_HEALTH;
        };
    }

    private String buildOperatorReviewHint(FailureTriageContext context, FailureCategoryDto category) {
        return "Review target " + context.target().runTargetId()
                + ", latest attempt " + context.latestAttempt().attemptId()
                + ", and category " + category.name() + " evidence before deciding retry.";
    }

    private ArrayNode buildFailureTriageEvidence(FailureTriageContext context) {
        ArrayNode evidence = objectMapper.createArrayNode();
        if (context.failureContext().lastError() != null) {
            evidence.add("lastError:" + context.failureContext().lastError());
        }
        context.keyEvents().stream()
                .limit(2)
                .forEach(event -> evidence.add("event:%s:%s".formatted(event.eventType(), event.message())));
        context.artifactManifest().stream()
                .limit(1)
                .forEach(artifact -> evidence.add("artifact:%s:%s".formatted(artifact.artifactType(), artifact.fileName())));
        if (evidence.isEmpty()) {
            evidence.add("attempt:" + context.latestAttempt().attemptId());
        }
        return evidence;
    }

    private String buildRunSummaryText(RunSummaryContext context) {
        return "Run " + context.run().runId()
                + " ended with status " + context.run().status()
                + " / finalState " + context.run().finalState()
                + " across " + context.counts().totalTargets() + " targets.";
    }

    private String buildRunSummaryFinalJudgement(RunSummaryContext context) {
        if ("SUCCEEDED".equals(context.run().finalState())) {
            return "Run completed successfully and target outcomes are consistent.";
        }
        if ("PARTIAL".equals(context.run().finalState())) {
            return "Run completed with mixed outcomes and should be reviewed target by target.";
        }
        return "Run did not complete cleanly and should be reviewed alongside triage and artifacts.";
    }

    private ArrayNode buildRunSummaryKeyMoments(RunSummaryContext context) {
        ArrayNode keyMoments = objectMapper.createArrayNode();
        context.keyEvents().stream().limit(3).forEach(event -> {
            ObjectNode keyMoment = objectMapper.createObjectNode();
            keyMoment.put("title", "Event");
            if (event.eventType() != null) {
                keyMoment.put("eventType", event.eventType());
            }
            keyMoment.put("message", event.message());
            keyMoments.add(keyMoment);
        });
        if (keyMoments.isEmpty()) {
            ObjectNode fallback = objectMapper.createObjectNode();
            fallback.put("title", "Target outcome snapshot");
            fallback.put("message", "Summary generated from target counts and representative attempts.");
            keyMoments.add(fallback);
        }
        return keyMoments;
    }

    private ArrayNode buildRunSummaryEvidence(RunSummaryContext context) {
        ArrayNode evidence = objectMapper.createArrayNode();
        evidence.add("targets:succeeded=" + context.counts().succeeded());
        evidence.add("targets:failed=" + context.counts().failed());
        context.artifactManifest().stream()
                .limit(2)
                .forEach(artifact -> evidence.add("artifact:%s:%s".formatted(artifact.artifactType(), artifact.fileName())));
        return evidence;
    }

    private ModelMetaDto modelMeta() {
        return new ModelMetaDto("stub", "local-stub", Instant.now().toEpochMilli());
    }
}

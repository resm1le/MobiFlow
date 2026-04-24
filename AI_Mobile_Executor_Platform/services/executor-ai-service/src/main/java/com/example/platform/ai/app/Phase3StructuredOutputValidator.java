package com.example.platform.ai.app;

import com.example.platform.ai.api.dto.FailureCategoryDto;
import com.example.platform.ai.api.dto.FailureTriageResult;
import com.example.platform.ai.api.dto.RetryRecommendationDto;
import com.example.platform.ai.api.dto.RunDraftResult;
import com.example.platform.ai.api.dto.RunPlanningContext;
import com.example.platform.ai.api.dto.RunSummaryContext;
import com.example.platform.ai.api.dto.RunSummaryResult;
import com.example.platform.ai.api.dto.SuggestedNextActionDto;
import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.Set;

@Component
public class Phase3StructuredOutputValidator {

    private static final Set<String> RUN_DRAFT_RESULT_FIELDS = Set.of("runDraft", "warnings", "reviewHints");
    private static final Set<String> RUN_DRAFT_FIELDS = Set.of(
            "name",
            "description",
            "devicePoolId",
            "taskType",
            "profilePackage",
            "taskPayload",
            "runConfig",
            "artifactPolicy",
            "priority",
            "labels",
            "maxRetriesPerDevice",
            "queueTimeoutMs"
    );
    private static final Set<String> RUN_CONFIG_FIELDS = Set.of(
            "loopCount",
            "budgetMs",
            "loopIntervalMs",
            "networkIsolationEnabled",
            "pollIntervalMs",
            "heartbeatIntervalMs"
    );
    private static final Set<String> ARTIFACT_POLICY_FIELDS = Set.of("uploadLog", "uploadScreenshot", "uploadDump");
    private static final Set<String> FAILURE_TRIAGE_FIELDS = Set.of(
            "failureCategory",
            "probableCause",
            "confidence",
            "retryRecommendation",
            "suggestedNextAction",
            "operatorReviewHints",
            "evidence"
    );
    private static final Set<String> RUN_SUMMARY_FIELDS = Set.of(
            "summaryText",
            "keyMoments",
            "finalJudgement",
            "evidence"
    );
    private static final Set<String> RUN_SUMMARY_KEY_MOMENT_FIELDS = Set.of(
            "title",
            "eventType",
            "stepIndex",
            "message"
    );

    public RunDraftResult validateRunDraftResult(JsonNode payload, RunPlanningContext context) {
        requireObject(payload, "run draft result payload must be a JSON object");
        rejectUnknownFields(payload, RUN_DRAFT_RESULT_FIELDS, "run draft result contains unsupported fields");
        JsonNode runDraftNode = requireObject(payload.get("runDraft"), "runDraft must be an object");
        rejectUnknownFields(runDraftNode, RUN_DRAFT_FIELDS, "runDraft contains unsupported fields");
        String profilePackage = requireText(runDraftNode, "profilePackage");
        if (context.availableProfiles().stream().noneMatch(profile -> profile.profilePackage().equals(profilePackage))) {
            throw AiServiceException.providerOutputInvalid("profilePackage must exist in availableProfiles");
        }
        String taskType = requireText(runDraftNode, "taskType");
        if (context.allowedTaskTypes().stream().noneMatch(taskType::equals)) {
            throw AiServiceException.providerOutputInvalid("taskType must exist in allowedTaskTypes");
        }
        String devicePoolId = requireText(runDraftNode, "devicePoolId");
        if (context.availableDevicePools().stream().noneMatch(pool -> pool.poolId().equals(devicePoolId))) {
            throw AiServiceException.providerOutputInvalid("devicePoolId must exist in availableDevicePools");
        }
        JsonNode taskPayload = requireObject(runDraftNode.get("taskPayload"), "taskPayload must be an object");
        requireNonBlankText(taskPayload, "goal", "taskPayload.goal must be a non-blank string");
        JsonNode runConfig = requireObject(runDraftNode.get("runConfig"), "runConfig must be an object");
        rejectUnknownFields(runConfig, RUN_CONFIG_FIELDS, "runConfig contains unsupported fields");
        ensureRunConfigTypes(runConfig);
        JsonNode artifactPolicy = requireObject(runDraftNode.get("artifactPolicy"), "artifactPolicy must be an object");
        rejectUnknownFields(artifactPolicy, ARTIFACT_POLICY_FIELDS, "artifactPolicy contains unsupported fields");
        ensureArtifactPolicyTypes(artifactPolicy);

        return new RunDraftResult(
                new RunDraftResult.RunDraftDto(
                        requireText(runDraftNode, "name"),
                        optionalText(runDraftNode, "description"),
                        devicePoolId,
                        taskType,
                        profilePackage,
                        taskPayload,
                        runConfig,
                        artifactPolicy,
                        requireInteger(runDraftNode, "priority"),
                        readStringArray(runDraftNode.get("labels"), "labels"),
                        requireInteger(runDraftNode, "maxRetriesPerDevice"),
                        requireLong(runDraftNode, "queueTimeoutMs")
                ),
                readStringArray(payload.get("warnings"), "warnings"),
                readStringArray(payload.get("reviewHints"), "reviewHints")
        );
    }

    public FailureTriageResult validateFailureTriageResult(JsonNode payload) {
        requireObject(payload, "failure triage payload must be a JSON object");
        rejectUnknownFields(payload, FAILURE_TRIAGE_FIELDS, "failure triage payload contains unsupported fields");
        String failureCategory = requireText(payload, "failureCategory");
        String retryRecommendation = requireText(payload, "retryRecommendation");
        String suggestedNextAction = requireText(payload, "suggestedNextAction");
        try {
            return new FailureTriageResult(
                    FailureCategoryDto.valueOf(failureCategory),
                    requireText(payload, "probableCause"),
                    requireDouble(payload, "confidence"),
                    RetryRecommendationDto.valueOf(retryRecommendation),
                    SuggestedNextActionDto.valueOf(suggestedNextAction),
                    readStringArray(payload.get("operatorReviewHints"), "operatorReviewHints"),
                    readStringArray(payload.get("evidence"), "evidence")
            );
        } catch (IllegalArgumentException exception) {
            throw AiServiceException.providerOutputInvalid("phase3 triage enums must be valid canonical values");
        }
    }

    public RunSummaryResult validateRunSummaryResult(JsonNode payload, RunSummaryContext context) {
        requireObject(payload, "run summary payload must be a JSON object");
        rejectUnknownFields(payload, RUN_SUMMARY_FIELDS, "run summary payload contains unsupported fields");
        JsonNode keyMomentsNode = payload.get("keyMoments");
        if (keyMomentsNode == null || !keyMomentsNode.isArray()) {
            throw AiServiceException.providerOutputInvalid("keyMoments must be an array");
        }
        List<com.example.platform.ai.api.dto.KeyMomentDto> keyMoments = new ArrayList<>();
        for (JsonNode keyMomentNode : keyMomentsNode) {
            JsonNode objectNode = requireObject(keyMomentNode, "keyMoments entries must be objects");
            rejectUnknownFields(objectNode, RUN_SUMMARY_KEY_MOMENT_FIELDS, "keyMoment contains unsupported fields");
            keyMoments.add(new com.example.platform.ai.api.dto.KeyMomentDto(
                    requireText(objectNode, "title"),
                    optionalText(objectNode, "eventType"),
                    optionalInteger(objectNode, "stepIndex"),
                    optionalText(objectNode, "message")
            ));
        }
        List<String> evidence = readStringArray(payload.get("evidence"), "evidence");
        if (context.keyEvents().isEmpty() && context.artifactManifest().isEmpty() && evidence.isEmpty()) {
            throw AiServiceException.providerOutputInvalid("run summary evidence must not be empty");
        }
        return new RunSummaryResult(
                requireText(payload, "summaryText"),
                keyMoments,
                requireText(payload, "finalJudgement"),
                evidence
        );
    }

    private JsonNode requireObject(JsonNode node, String message) {
        if (node == null || !node.isObject()) {
            throw AiServiceException.providerOutputInvalid(message);
        }
        return node;
    }

    private String requireText(JsonNode node, String fieldName) {
        JsonNode value = node.get(fieldName);
        if (value == null || !value.isTextual() || value.asText().isBlank()) {
            throw AiServiceException.providerOutputInvalid(fieldName + " must be a non-blank string");
        }
        return value.asText();
    }

    private String requireNonBlankText(JsonNode node, String fieldName, String message) {
        JsonNode value = node.get(fieldName);
        if (value == null || !value.isTextual() || value.asText().isBlank()) {
            throw AiServiceException.providerOutputInvalid(message);
        }
        return value.asText();
    }

    private String optionalText(JsonNode node, String fieldName) {
        JsonNode value = node.get(fieldName);
        if (value == null || value.isNull()) {
            return null;
        }
        if (!value.isTextual()) {
            throw AiServiceException.providerOutputInvalid(fieldName + " must be a string when provided");
        }
        return value.asText();
    }

    private int requireInteger(JsonNode node, String fieldName) {
        JsonNode value = node.get(fieldName);
        if (value == null || !value.canConvertToInt()) {
            throw AiServiceException.providerOutputInvalid(fieldName + " must be an integer");
        }
        return value.asInt();
    }

    private Integer optionalInteger(JsonNode node, String fieldName) {
        JsonNode value = node.get(fieldName);
        if (value == null || value.isNull()) {
            return null;
        }
        if (!value.canConvertToInt()) {
            throw AiServiceException.providerOutputInvalid(fieldName + " must be an integer when provided");
        }
        return value.asInt();
    }

    private long requireLong(JsonNode node, String fieldName) {
        JsonNode value = node.get(fieldName);
        if (value == null || !value.canConvertToLong()) {
            throw AiServiceException.providerOutputInvalid(fieldName + " must be a long");
        }
        return value.asLong();
    }

    private double requireDouble(JsonNode node, String fieldName) {
        JsonNode value = node.get(fieldName);
        if (value == null || !value.isNumber()) {
            throw AiServiceException.providerOutputInvalid(fieldName + " must be numeric");
        }
        double number = value.asDouble();
        if (number < 0.0d || number > 1.0d) {
            throw AiServiceException.providerOutputInvalid(fieldName + " must be between 0 and 1");
        }
        return number;
    }

    private boolean requireBoolean(JsonNode node, String fieldName) {
        JsonNode value = node.get(fieldName);
        if (value == null || !value.isBoolean()) {
            throw AiServiceException.providerOutputInvalid(fieldName + " must be a boolean");
        }
        return value.asBoolean();
    }

    private List<String> readStringArray(JsonNode node, String fieldName) {
        if (node == null || !node.isArray()) {
            throw AiServiceException.providerOutputInvalid(fieldName + " must be an array");
        }
        List<String> values = new ArrayList<>();
        for (JsonNode child : node) {
            if (!child.isTextual() || child.asText().isBlank()) {
                throw AiServiceException.providerOutputInvalid(fieldName + " must contain non-blank strings");
            }
            values.add(child.asText());
        }
        return values;
    }

    private void ensureRunConfigTypes(JsonNode runConfig) {
        requireInteger(runConfig, "loopCount");
        requireLong(runConfig, "budgetMs");
        requireLong(runConfig, "loopIntervalMs");
        requireBoolean(runConfig, "networkIsolationEnabled");
        requireLong(runConfig, "pollIntervalMs");
        requireLong(runConfig, "heartbeatIntervalMs");
    }

    private void ensureArtifactPolicyTypes(JsonNode artifactPolicy) {
        requireBoolean(artifactPolicy, "uploadLog");
        requireBoolean(artifactPolicy, "uploadScreenshot");
        requireBoolean(artifactPolicy, "uploadDump");
    }

    private void rejectUnknownFields(JsonNode node, Set<String> allowedFields, String message) {
        Iterator<String> fieldNames = node.fieldNames();
        while (fieldNames.hasNext()) {
            String fieldName = fieldNames.next();
            if (!allowedFields.contains(fieldName)) {
                throw AiServiceException.providerOutputInvalid(message + ": " + fieldName);
            }
        }
    }
}

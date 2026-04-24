package com.example.platform.ai.app;

import com.example.platform.ai.api.dto.FailureCategoryDto;
import com.example.platform.ai.api.dto.FailureTriageContext;
import com.example.platform.ai.api.dto.ModelMetaDto;
import com.example.platform.ai.api.dto.RetryRecommendationDto;
import com.example.platform.ai.api.dto.RunPlanningContext;
import com.example.platform.ai.api.dto.RunSummaryContext;
import com.example.platform.ai.api.dto.SuggestedNextActionDto;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClientRequestException;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;

import java.time.Instant;
import java.util.concurrent.Semaphore;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import java.util.List;

@Component
public class OpenAiCompatibleProvider implements AiProvider {

    private final WebClient webClient;
    private final AiProperties properties;
    private final ObjectMapper objectMapper;
    private final Phase3ProviderContractBuilder phase3ProviderContractBuilder;
    private final Semaphore providerPermits;
    private final AtomicInteger consecutiveFailures = new AtomicInteger();
    private final AtomicLong cooldownUntilEpochMs = new AtomicLong();

    @Autowired
    public OpenAiCompatibleProvider(WebClient.Builder webClientBuilder,
                                    AiProperties properties,
                                    ObjectMapper objectMapper,
                                    Phase3ProviderContractBuilder phase3ProviderContractBuilder) {
        this(
                webClientBuilder.baseUrl(properties.getProvider().getOpenAiCompatible().getBaseUrl()).build(),
                properties,
                objectMapper,
                phase3ProviderContractBuilder
        );
    }

    OpenAiCompatibleProvider(WebClient webClient,
                             AiProperties properties,
                             ObjectMapper objectMapper,
                             Phase3ProviderContractBuilder phase3ProviderContractBuilder) {
        this.webClient = webClient;
        this.properties = properties;
        this.objectMapper = objectMapper;
        this.phase3ProviderContractBuilder = phase3ProviderContractBuilder;
        int maxConcurrent = Math.max(1, properties.getProvider().getOpenAiCompatible().getMaxConcurrent());
        this.providerPermits = new Semaphore(maxConcurrent, true);
    }

    @Override
    public AiProviderMode mode() {
        return AiProviderMode.OPENAI_COMPATIBLE;
    }

    @Override
    public ProviderResult generateRunPlan(RunPlanningContext context) {
        return invokeModel(
                "Generate a run draft using only the provided RunPlanningContext. "
                        + "Use valid availableDevicePool, availableProfile, and allowedTaskType values. "
                        + "Do not invent source or createdBy.",
                buildRunPlanningContractPrompt(context),
                objectMapper.valueToTree(context)
        );
    }

    @Override
    public ProviderResult generateFailureTriage(FailureTriageContext context) {
        return invokeModel(
                "Generate a failure triage result using only the provided FailureTriageContext. "
                        + "Use only canonical enums and do not trigger or imply automatic platform side effects.",
                buildFailureTriageContractPrompt(context),
                objectMapper.valueToTree(context)
        );
    }

    @Override
    public ProviderResult generateRunSummary(RunSummaryContext context) {
        return invokeModel(
                "Generate a run summary result using only the provided RunSummaryContext. "
                        + "Use concrete target counts, key events, representative attempts, and artifacts as evidence.",
                buildRunSummaryContractPrompt(context),
                objectMapper.valueToTree(context)
        );
    }

    private ProviderResult invokeModel(String taskInstruction, String contractPrompt, JsonNode input) {
        AiProperties.OpenAiCompatible providerProperties = properties.getProvider().getOpenAiCompatible();
        String apiKey = providerProperties.getApiKey();
        if (apiKey == null || apiKey.isBlank()) {
            throw AiServiceException.providerUnavailable("OPENAI-compatible provider requires executor.ai.provider.open-ai-compatible.api-key");
        }
        ensureProviderAvailable();
        if (!providerPermits.tryAcquire()) {
            throw AiServiceException.providerFailed("Provider request rejected because max concurrent limit is reached");
        }

        ObjectNode requestBody = objectMapper.createObjectNode();
        requestBody.put("model", providerProperties.getModel());
        requestBody.set("response_format", jsonObjectResponseFormat());
        requestBody.set("messages", buildMessages(taskInstruction, contractPrompt, input));

        try {
            JsonNode responseBody = invokeWithRetry(requestBody, apiKey, providerProperties);
            JsonNode payload = extractStructuredPayload(responseBody);
            recordSuccess();
            return new ProviderResult(
                    payload,
                    List.of(),
                    new ModelMetaDto(
                            "openai-compatible",
                            providerProperties.getModel(),
                            Instant.now().toEpochMilli()
                    )
            );
        } catch (WebClientResponseException exception) {
            recordFailure();
            throw AiServiceException.providerFailed("Provider request failed with status " + exception.getStatusCode().value());
        } catch (WebClientRequestException exception) {
            recordFailure();
            throw AiServiceException.providerFailed("Provider request failed: " + exception.getMessage());
        } catch (AiServiceException exception) {
            if (!"PROVIDER_UNAVAILABLE".equals(exception.getErrorCode())
                    && !"PROVIDER_OUTPUT_INVALID".equals(exception.getErrorCode())
                    && !"REQUEST_INVALID".equals(exception.getErrorCode())) {
                recordFailure();
            }
            throw exception;
        } catch (Exception exception) {
            recordFailure();
            throw AiServiceException.providerFailed("Provider request failed: " + exception.getMessage());
        } finally {
            providerPermits.release();
        }
    }

    private JsonNode invokeWithRetry(ObjectNode requestBody,
                                     String apiKey,
                                     AiProperties.OpenAiCompatible providerProperties) {
        int maxAttempts = Math.max(1, providerProperties.getRetry429MaxAttempts());
        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            try {
                return webClient.post()
                        .uri("/chat/completions")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + apiKey)
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_JSON)
                        .bodyValue(requestBody)
                        .retrieve()
                        .bodyToMono(JsonNode.class)
                        .block(providerProperties.getTimeout());
            } catch (WebClientResponseException exception) {
                if (!shouldRetry(exception, attempt, maxAttempts)) {
                    throw exception;
                }
                sleepBackoff(providerProperties, attempt);
            } catch (WebClientRequestException exception) {
                if (attempt >= maxAttempts) {
                    throw exception;
                }
                sleepBackoff(providerProperties, attempt);
            }
        }
        throw AiServiceException.providerFailed("Provider request failed after retry budget was exhausted");
    }

    private boolean shouldRetry(WebClientResponseException exception, int attempt, int maxAttempts) {
        int status = exception.getStatusCode().value();
        if (attempt >= maxAttempts) {
            return false;
        }
        return status == 429 || status >= 500;
    }

    private void sleepBackoff(AiProperties.OpenAiCompatible providerProperties, int attempt) {
        long backoffMs = Math.max(0L, providerProperties.getRetry429Backoff().toMillis()) * attempt;
        if (backoffMs <= 0L) {
            return;
        }
        try {
            Thread.sleep(backoffMs);
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw AiServiceException.providerFailed("Provider request retry interrupted");
        }
    }

    private void ensureProviderAvailable() {
        long cooldownUntil = cooldownUntilEpochMs.get();
        if (cooldownUntil > System.currentTimeMillis()) {
            throw AiServiceException.providerFailed("Provider request rejected because upstream is cooling down");
        }
        if (cooldownUntil > 0L) {
            cooldownUntilEpochMs.compareAndSet(cooldownUntil, 0L);
        }
    }

    private void recordSuccess() {
        consecutiveFailures.set(0);
        cooldownUntilEpochMs.set(0L);
    }

    private void recordFailure() {
        int failures = consecutiveFailures.incrementAndGet();
        AiProperties.OpenAiCompatible providerProperties = properties.getProvider().getOpenAiCompatible();
        int failureThreshold = Math.max(1, providerProperties.getFailureThreshold());
        if (failures >= failureThreshold) {
            long cooldownMs = Math.max(0L, providerProperties.getCooldown().toMillis());
            cooldownUntilEpochMs.set(System.currentTimeMillis() + cooldownMs);
        }
    }

    private ArrayNode buildMessages(String taskInstruction, String contractPrompt, JsonNode input) {
        ArrayNode messages = objectMapper.createArrayNode();
        messages.add(message("system",
                "You are a structured planning and analysis service for an AI mobile executor platform. "
                        + "Return strict JSON only. Do not include markdown. Do not include prose outside JSON. "
                        + "Do not add extra keys. Do not emit scripts, commands, device identifiers, or attempt identifiers."));
        messages.add(message("system", contractPrompt));
        messages.add(message("user", taskInstruction + "\nInput JSON:\n" + serialize(input)));
        return messages;
    }

    private ObjectNode message(String role, String content) {
        ObjectNode node = objectMapper.createObjectNode();
        node.put("role", role);
        node.put("content", content);
        return node;
    }

    private ObjectNode jsonObjectResponseFormat() {
        ObjectNode node = objectMapper.createObjectNode();
        node.put("type", "json_object");
        return node;
    }

    private JsonNode extractStructuredPayload(JsonNode responseBody) {
        JsonNode contentNode = responseBody.path("choices").path(0).path("message").path("content");
        String content = extractContentString(contentNode);
        if (content == null || content.isBlank()) {
            throw AiServiceException.providerOutputInvalid("Provider response did not contain JSON content");
        }
        try {
            JsonNode parsed = objectMapper.readTree(content);
            if (!parsed.isObject()) {
                throw AiServiceException.providerOutputInvalid("Provider content must be a JSON object");
            }
            return parsed;
        } catch (JsonProcessingException exception) {
            throw AiServiceException.providerOutputInvalid("Provider content was not valid JSON");
        }
    }

    private String extractContentString(JsonNode contentNode) {
        if (contentNode == null || contentNode.isMissingNode() || contentNode.isNull()) {
            return null;
        }
        if (contentNode.isTextual()) {
            return contentNode.asText();
        }
        if (contentNode.isArray()) {
            StringBuilder builder = new StringBuilder();
            for (JsonNode part : contentNode) {
                JsonNode text = part.get("text");
                if (text != null && text.isTextual()) {
                    builder.append(text.asText());
                }
            }
            return builder.toString();
        }
        return null;
    }

    private String buildRunPlanningContractPrompt(RunPlanningContext context) {
        return """
                Return a single JSON object with exactly these keys:
                runDraft, warnings, reviewHints.
                runDraft must contain exactly these keys:
                name, description, devicePoolId, taskType, profilePackage, taskPayload, runConfig,
                artifactPolicy, priority, labels, maxRetriesPerDevice, queueTimeoutMs.
                devicePoolId must be selected from availableDevicePools.
                taskType must be selected from allowedTaskTypes.
                profilePackage must be selected from availableProfiles.
                taskPayload must be a JSON object and must contain a non-empty string field named goal.
                runConfig must contain exactly:
                loopCount, budgetMs, loopIntervalMs, networkIsolationEnabled, pollIntervalMs, heartbeatIntervalMs.
                artifactPolicy must contain exactly:
                uploadLog, uploadScreenshot, uploadDump.
                warnings and reviewHints must be arrays of non-empty strings.
                Do not include source, createdBy, templateId, inline selector, deviceId, or extra keys.
                Contract JSON:
                %s
                """.formatted(serialize(objectMapper.valueToTree(phase3ProviderContractBuilder.buildRunPlanningContract(context))));
    }

    private String buildFailureTriageContractPrompt(FailureTriageContext context) {
        return """
                Return a single JSON object with exactly these keys:
                failureCategory, probableCause, confidence, retryRecommendation, suggestedNextAction,
                operatorReviewHints, evidence.
                failureCategory must be one of: %s.
                probableCause must be a non-empty string grounded in the supplied context.
                confidence must be a number between 0 and 1.
                retryRecommendation must be one of: %s.
                suggestedNextAction must be one of: %s.
                operatorReviewHints and evidence must be arrays of non-empty strings.
                Evidence strings must cite concrete lastError, eventType, artifactType, failureReason, or snapshot clues from the input.
                Do not include extra keys.
                Contract JSON:
                %s
                """.formatted(
                List.of(FailureCategoryDto.values()),
                List.of(RetryRecommendationDto.values()),
                List.of(SuggestedNextActionDto.values()),
                serialize(objectMapper.valueToTree(phase3ProviderContractBuilder.buildFailureTriageContract(context)))
        );
    }

    private String buildRunSummaryContractPrompt(RunSummaryContext context) {
        return """
                Return a single JSON object with exactly these keys:
                summaryText, keyMoments, finalJudgement, evidence.
                summaryText must be a non-empty string grounded in the supplied run context.
                keyMoments must be an array of JSON objects. Each keyMoment object may only contain:
                title, eventType, stepIndex, message.
                title must be a non-empty string.
                finalJudgement must be a non-empty string.
                evidence must be an array of non-empty strings that cite concrete target counts, eventType, stepIndex, artifactType, or representative attempt facts from the input.
                Do not include extra keys.
                Contract JSON:
                %s
                """.formatted(serialize(objectMapper.valueToTree(phase3ProviderContractBuilder.buildRunSummaryContract(context))));
    }

    private String serialize(JsonNode input) {
        try {
            return objectMapper.writerWithDefaultPrettyPrinter().writeValueAsString(input);
        } catch (JsonProcessingException exception) {
            throw AiServiceException.requestInvalid("Failed to serialize request payload for provider");
        }
    }
}

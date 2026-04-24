package com.example.platform.ai.app;

import com.example.platform.ai.api.dto.DeviceOperationalSnapshot;
import com.example.platform.ai.api.dto.DeviceOperationalSnapshotType;
import com.example.platform.ai.api.dto.FailureTriageContext;
import com.example.platform.ai.api.dto.RunPlanningContext;
import com.example.platform.ai.api.dto.RunSummaryContext;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.ExchangeFunction;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

import java.lang.reflect.Method;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class OpenAiCompatibleProviderTest {

    private final ObjectMapper objectMapper = new ObjectMapper();

    @Test
    void parsesStrictJsonFromChatCompletions() {
        OpenAiCompatibleProvider provider = providerReturning("""
                        {
                          "choices": [
                            {
                              "message": {
                                "content": "{\\"summaryText\\":\\"Run ended cleanly.\\",\\"keyMoments\\":[{\\"title\\":\\"Launch\\",\\"eventType\\":\\"action_end\\",\\"message\\":\\"Tap ok\\"}],\\"finalJudgement\\":\\"Healthy run.\\",\\"evidence\\":[\\"targets:succeeded=1\\"]}"
                              }
                            }
                          ]
                        }
                        """);

        ProviderResult result = provider.generateRunSummary(runSummaryContext());

        assertThat(result.payload().get("summaryText").asText()).isEqualTo("Run ended cleanly.");
        assertThat(result.modelMeta().provider()).isEqualTo("openai-compatible");
    }

    @Test
    void rejectsInvalidJsonContent() {
        OpenAiCompatibleProvider provider = providerReturning("""
                        {
                          "choices": [
                            {
                              "message": {
                                "content": "not-json"
                              }
                            }
                          ]
                        }
                        """);

        assertThatThrownBy(() -> provider.generateRunPlan(runPlanningContext()))
                .isInstanceOf(AiServiceException.class)
                .hasMessageContaining("valid JSON");
    }

    @Test
    void surfacesProviderHttpFailure() {
        OpenAiCompatibleProvider provider = providerWithExchange(request -> Mono.just(
                ClientResponse.create(HttpStatus.BAD_GATEWAY)
                        .header(HttpHeaders.CONTENT_TYPE, MediaType.APPLICATION_JSON_VALUE)
                        .body("{\"error\":\"upstream\"}")
                        .build()
        ));

        assertThatThrownBy(() -> provider.generateFailureTriage(failureTriageContext()))
                .isInstanceOf(AiServiceException.class)
                .hasMessageContaining("Provider request failed");
    }

    @Test
    void retries429WithinConfiguredBudget() {
        AtomicInteger requests = new AtomicInteger();
        OpenAiCompatibleProvider provider = providerWithExchange(request -> {
            if (requests.incrementAndGet() == 1) {
                return Mono.just(
                        ClientResponse.create(HttpStatus.TOO_MANY_REQUESTS)
                                .header(HttpHeaders.CONTENT_TYPE, MediaType.APPLICATION_JSON_VALUE)
                                .body("{\"error\":\"rate limit\"}")
                                .build()
                );
            }
            return Mono.just(
                    ClientResponse.create(HttpStatus.OK)
                            .header(HttpHeaders.CONTENT_TYPE, MediaType.APPLICATION_JSON_VALUE)
                            .body("""
                                    {
                                      "choices": [
                                        {
                                          "message": {
                                            "content": "{\\"summaryText\\":\\"retried\\",\\"keyMoments\\":[],\\"finalJudgement\\":\\"ok\\",\\"evidence\\":[\\"targets:succeeded=1\\"]}"
                                          }
                                        }
                                      ]
                                    }
                                    """)
                            .build()
            );
        });

        ProviderResult result = provider.generateRunSummary(runSummaryContext());

        assertThat(result.payload().get("summaryText").asText()).isEqualTo("retried");
        assertThat(requests.get()).isEqualTo(2);
    }

    @Test
    void entersCooldownAfterConsecutiveFailures() {
        AiProperties properties = configuredProperties();
        properties.getProvider().getOpenAiCompatible().setFailureThreshold(2);
        properties.getProvider().getOpenAiCompatible().setCooldown(Duration.ofSeconds(5));
        OpenAiCompatibleProvider provider = providerWithExchange(
                request -> Mono.just(
                        ClientResponse.create(HttpStatus.BAD_GATEWAY)
                                .header(HttpHeaders.CONTENT_TYPE, MediaType.APPLICATION_JSON_VALUE)
                                .body("{\"error\":\"upstream\"}")
                                .build()
                ),
                properties
        );

        assertThatThrownBy(() -> provider.generateRunSummary(runSummaryContext()))
                .isInstanceOf(AiServiceException.class)
                .hasMessageContaining("Provider request failed");
        assertThatThrownBy(() -> provider.generateRunSummary(runSummaryContext()))
                .isInstanceOf(AiServiceException.class)
                .hasMessageContaining("Provider request failed");
        assertThatThrownBy(() -> provider.generateRunSummary(runSummaryContext()))
                .isInstanceOf(AiServiceException.class)
                .hasMessageContaining("cooling down");
    }

    @Test
    void rejectsWhenConcurrencyLimitIsReached() throws Exception {
        AiProperties properties = configuredProperties();
        properties.getProvider().getOpenAiCompatible().setMaxConcurrent(1);
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        OpenAiCompatibleProvider provider = providerWithExchange(
                request -> {
                    started.countDown();
                    try {
                        if (!release.await(5, TimeUnit.SECONDS)) {
                            throw new IllegalStateException("timed out");
                        }
                    } catch (InterruptedException exception) {
                        Thread.currentThread().interrupt();
                        return Mono.error(exception);
                    }
                    return Mono.just(
                            ClientResponse.create(HttpStatus.OK)
                                    .header(HttpHeaders.CONTENT_TYPE, MediaType.APPLICATION_JSON_VALUE)
                                    .body("""
                                            {
                                              "choices": [
                                                {
                                                  "message": {
                                                    "content": "{\\"summaryText\\":\\"ok\\",\\"keyMoments\\":[],\\"finalJudgement\\":\\"ok\\",\\"evidence\\":[\\"targets:succeeded=1\\"]}"
                                                  }
                                                }
                                              ]
                                            }
                                            """)
                                    .build()
                    );
                },
                properties
        );

        CompletableFuture<ProviderResult> inFlight = CompletableFuture.supplyAsync(() -> provider.generateRunSummary(runSummaryContext()));
        assertThat(started.await(5, TimeUnit.SECONDS)).isTrue();

        assertThatThrownBy(() -> provider.generateRunSummary(runSummaryContext()))
                .isInstanceOf(AiServiceException.class)
                .hasMessageContaining("max concurrent limit");

        release.countDown();
        assertThat(inFlight.get(5, TimeUnit.SECONDS).payload().get("summaryText").asText()).isEqualTo("ok");
    }

    @Test
    void runPlanningContractPromptRequiresCanonicalRunDraftFields() {
        OpenAiCompatibleProvider provider = providerReturning("{}");

        String contract = invokeMethod(provider, "buildRunPlanningContractPrompt", RunPlanningContext.class, runPlanningContext());

        assertThat(contract)
                .contains("runDraft, warnings, reviewHints")
                .contains("devicePoolId must be selected from availableDevicePools")
                .contains("taskPayload must be a JSON object and must contain a non-empty string field named goal")
                .contains("Do not include source, createdBy, templateId, inline selector");
    }

    @Test
    void failureTriageContractPromptRequiresCanonicalEnumsAndEvidence() {
        OpenAiCompatibleProvider provider = providerReturning("{}");

        String contract = invokeMethod(provider, "buildFailureTriageContractPrompt", FailureTriageContext.class, failureTriageContext());

        assertThat(contract)
                .contains("retryRecommendation must be one of")
                .contains("suggestedNextAction must be one of")
                .contains("Evidence strings must cite concrete");
    }

    @Test
    void runSummaryContractPromptRequiresGroundedEvidence() {
        OpenAiCompatibleProvider provider = providerReturning("{}");

        String contract = invokeMethod(provider, "buildRunSummaryContractPrompt", RunSummaryContext.class, runSummaryContext());

        assertThat(contract)
                .contains("summaryText must be a non-empty string grounded in the supplied run context")
                .contains("evidence must be an array of non-empty strings that cite concrete target counts");
    }

    private AiProperties configuredProperties() {
        AiProperties properties = new AiProperties();
        properties.getProvider().setMode(AiProviderMode.OPENAI_COMPATIBLE);
        properties.getProvider().getOpenAiCompatible().setApiKey("test-key");
        properties.getProvider().getOpenAiCompatible().setBaseUrl("https://example.invalid/v1");
        properties.getProvider().getOpenAiCompatible().setModel("gpt-5.4");
        properties.getProvider().getOpenAiCompatible().setRetry429Backoff(Duration.ofMillis(1));
        return properties;
    }

    private WebClient webClientWithExchange(ExchangeFunction exchangeFunction) {
        return WebClient.builder().exchangeFunction(exchangeFunction).build();
    }

    private OpenAiCompatibleProvider providerReturning(String body) {
        return providerWithExchange(request -> Mono.just(
                ClientResponse.create(HttpStatus.OK)
                        .header(HttpHeaders.CONTENT_TYPE, MediaType.APPLICATION_JSON_VALUE)
                        .body(body)
                        .build()
        ));
    }

    private OpenAiCompatibleProvider providerWithExchange(ExchangeFunction exchangeFunction) {
        return providerWithExchange(exchangeFunction, configuredProperties());
    }

    private OpenAiCompatibleProvider providerWithExchange(ExchangeFunction exchangeFunction, AiProperties properties) {
        return new OpenAiCompatibleProvider(
                webClientWithExchange(exchangeFunction),
                properties,
                objectMapper,
                new Phase3ProviderContractBuilder()
        );
    }

    private <T> String invokeMethod(OpenAiCompatibleProvider provider, String methodName, Class<T> parameterType, T argument) {
        try {
            Method method = OpenAiCompatibleProvider.class.getDeclaredMethod(methodName, parameterType);
            method.setAccessible(true);
            return (String) method.invoke(provider, argument);
        } catch (ReflectiveOperationException exception) {
            throw new AssertionError(exception);
        }
    }

    private RunPlanningContext runPlanningContext() {
        return new RunPlanningContext(
                "navigate to ikea",
                objectMapper.createObjectNode(),
                List.of(new RunPlanningContext.AvailableDevicePoolDto("pool-1", "Pool 1", "default", 1, List.of(), List.of())),
                List.of(new RunPlanningContext.AvailableProfileDto(
                        "com.google.android.apps.maps",
                        1,
                        List.of("PLUGIN_RUN", "PLUGIN_SMOKE"),
                        List.of("goal"),
                        objectMapper.createObjectNode(),
                        List.of()
                )),
                new RunPlanningContext.DefaultRunPolicyDto(
                        100,
                        0,
                        300000,
                        objectMapper.createObjectNode()
                                .put("loopCount", 1)
                                .put("budgetMs", 60000)
                                .put("loopIntervalMs", 0)
                                .put("networkIsolationEnabled", false)
                                .put("pollIntervalMs", 15000)
                                .put("heartbeatIntervalMs", 30000),
                        objectMapper.createObjectNode()
                                .put("uploadLog", true)
                                .put("uploadScreenshot", true)
                                .put("uploadDump", false)
                ),
                List.of("PLUGIN_RUN", "PLUGIN_SMOKE")
        );
    }

    private FailureTriageContext failureTriageContext() {
        ObjectNode empty = objectMapper.createObjectNode();
        return new FailureTriageContext(
                new FailureTriageContext.RunDto(
                        "run-1", "pool-1", "TERMINAL", "FAILED",
                        "PLUGIN_RUN", "com.google.android.apps.maps", 100, List.of("ai"),
                        0, 300000L, false, null, null
                ),
                new FailureTriageContext.RunTargetDto(
                        "target-1", "device-1", "FAILED", 1,
                        "task-1", "attempt-1", "network timeout", null, null
                ),
                new FailureTriageContext.AttemptDto(
                        "attempt-1", "task-1", "device-1", "run-1",
                        "FAILED", "FAILED", "network timeout",
                        empty, empty, 1L, 2L, 1L
                ),
                new FailureTriageContext.AttemptHistorySummaryDto(
                        1,
                        List.of(new FailureTriageContext.AttemptHistoryEntryDto("attempt-1", "FAILED", "FAILED", "network timeout", 2L, "device-1")),
                        false,
                        false
                ),
                new FailureTriageContext.FailureContextDto(
                        "FAILED", "network timeout", "network timeout",
                        false, false, false, false, empty, empty
                ),
                List.of(new FailureTriageContext.KeyEventDto("action_end", "FAILED", null, "request timed out", 2L)),
                List.of(),
                new DeviceOperationalSnapshot(
                        DeviceOperationalSnapshotType.FAILURE,
                        3L,
                        "device-1",
                        "default",
                        List.of("com.google.android.apps.maps"),
                        empty,
                        empty,
                        empty,
                        2L
                )
        );
    }

    private RunSummaryContext runSummaryContext() {
        ObjectNode empty = objectMapper.createObjectNode();
        return new RunSummaryContext(
                new RunSummaryContext.RunDto(
                        "run-1", "pool-1", "TERMINAL", "PARTIAL",
                        "PLUGIN_RUN", "com.google.android.apps.maps", 100, List.of("ai"),
                        0, 300000L, false, null, null
                ),
                new RunSummaryContext.CountsDto(2, 0, 0, 0, 1, 1, 0),
                List.of(
                        new RunSummaryContext.RunTargetDto("target-1", "device-1", "SUCCEEDED", 1, "task-1", "attempt-1", null, null, null),
                        new RunSummaryContext.RunTargetDto("target-2", "device-2", "FAILED", 2, "task-2", "attempt-2", "network timeout", null, null)
                ),
                List.of(
                        new FailureTriageContext.AttemptDto("attempt-1", "task-1", "device-1", "run-1", "SUCCEEDED", "SUCCEEDED", null, empty, empty, 1L, 2L, 1L),
                        new FailureTriageContext.AttemptDto("attempt-2", "task-2", "device-2", "run-1", "FAILED", "FAILED", "network timeout", empty, empty, 3L, 4L, 3L)
                ),
                List.of(new FailureTriageContext.KeyEventDto("action_end", "FAILED", null, "request timed out", 4L)),
                List.of()
        );
    }
}

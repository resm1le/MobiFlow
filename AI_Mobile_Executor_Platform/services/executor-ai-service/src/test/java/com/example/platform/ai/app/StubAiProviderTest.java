package com.example.platform.ai.app;

import com.example.platform.ai.api.dto.DeviceOperationalSnapshot;
import com.example.platform.ai.api.dto.DeviceOperationalSnapshotType;
import com.example.platform.ai.api.dto.FailureTriageContext;
import com.example.platform.ai.api.dto.RunPlanningContext;
import com.example.platform.ai.api.dto.RunSummaryContext;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

class StubAiProviderTest {

    private final ObjectMapper objectMapper = new ObjectMapper();
    private final StubAiProvider provider = new StubAiProvider(
            objectMapper,
            new RunPlanningIntentExtractor(),
            new RunPlanningSemanticCanonicalizer(objectMapper)
    );

    @Test
    void generateRunPlanReturnsDeterministicRunDraft() throws Exception {
        ProviderResult result = provider.generateRunPlan(new RunPlanningContext(
                "Create a TikTok smoke run for 77 seconds",
                objectMapper.createObjectNode(),
                List.of(new RunPlanningContext.AvailableDevicePoolDto("pool-1", "Pool 1", "default", 1, List.of(), List.of())),
                List.of(new RunPlanningContext.AvailableProfileDto(
                        "com.zhiliaoapp.musically",
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
                        objectMapper.readTree("""
                                {
                                  "loopCount": 1,
                                  "budgetMs": 60000,
                                  "loopIntervalMs": 0,
                                  "networkIsolationEnabled": false,
                                  "pollIntervalMs": 15000,
                                  "heartbeatIntervalMs": 30000
                                }
                                """),
                        objectMapper.readTree("""
                                {
                                  "uploadLog": true,
                                  "uploadScreenshot": true,
                                  "uploadDump": false
                                }
                                """)
                ),
                List.of("PLUGIN_RUN", "PLUGIN_SMOKE")
        ));

        assertThat(result.payload().get("runDraft").get("devicePoolId").asText()).isEqualTo("pool-1");
        assertThat(result.payload().get("runDraft").get("profilePackage").asText()).isEqualTo("com.zhiliaoapp.musically");
        assertThat(result.payload().get("warnings").get(0).asText()).contains("deterministic run draft");
    }

    @Test
    void generateFailureTriageBuildsCanonicalPayload() {
        ProviderResult result = provider.generateFailureTriage(failureTriageContext());

        assertThat(result.payload().get("failureCategory").asText()).isEqualTo("UI_NOT_FOUND");
        assertThat(result.payload().get("probableCause").asText()).contains("target-1");
        assertThat(result.payload().get("retryRecommendation").asText()).isEqualTo("RETRY_SAME_DEVICE");
        assertThat(result.payload().get("evidence").isArray()).isTrue();
    }

    @Test
    void generateRunSummaryBuildsStructuredSummaryPayload() {
        ProviderResult result = provider.generateRunSummary(runSummaryContext());

        assertThat(result.payload().get("summaryText").asText()).contains("run-1");
        assertThat(result.payload().get("keyMoments").isArray()).isTrue();
        assertThat(result.payload().get("finalJudgement").asText()).isNotBlank();
        assertThat(result.payload().get("evidence").isArray()).isTrue();
    }

    private FailureTriageContext failureTriageContext() {
        ObjectNode empty = objectMapper.createObjectNode();
        return new FailureTriageContext(
                new FailureTriageContext.RunDto(
                        "run-1", "pool-1", "TERMINAL", "FAILED",
                        "PLUGIN_RUN", "com.zhiliaoapp.musically", 100, List.of("ai"),
                        0, 300000L, false, null, null
                ),
                new FailureTriageContext.RunTargetDto(
                        "target-1", "device-1", "FAILED", 1,
                        "task-1", "attempt-1", "ui target not found", null, null
                ),
                new FailureTriageContext.AttemptDto(
                        "attempt-1", "task-1", "device-1", "run-1",
                        "FAILED", "FAILED", "ui target not found",
                        empty, empty, 1_770_000_000_000L, 1_770_000_005_000L, 1_770_000_000_000L
                ),
                new FailureTriageContext.AttemptHistorySummaryDto(
                        1,
                        List.of(new FailureTriageContext.AttemptHistoryEntryDto(
                                "attempt-1", "FAILED", "FAILED", "ui target not found", 1_770_000_005_000L, "device-1"
                        )),
                        false,
                        false
                ),
                new FailureTriageContext.FailureContextDto(
                        "FAILED", "ui target not found", "ui target not found",
                        false, false, false, false, empty, empty
                ),
                List.of(new FailureTriageContext.KeyEventDto(
                        "action_end", "FAILED", null, "Tap target missing", 1_770_000_004_000L
                )),
                List.of(),
                new DeviceOperationalSnapshot(
                        DeviceOperationalSnapshotType.FAILURE,
                        1_770_000_004_500L,
                        "device-1",
                        "default",
                        List.of("com.zhiliaoapp.musically"),
                        empty,
                        empty,
                        empty,
                        1_770_000_004_400L
                )
        );
    }

    private RunSummaryContext runSummaryContext() {
        ObjectNode empty = objectMapper.createObjectNode();
        return new RunSummaryContext(
                new RunSummaryContext.RunDto(
                        "run-1", "pool-1", "TERMINAL", "PARTIAL",
                        "PLUGIN_RUN", "com.zhiliaoapp.musically", 100, List.of("ai"),
                        0, 300000L, false, null, null
                ),
                new RunSummaryContext.CountsDto(2, 0, 0, 0, 1, 1, 0),
                List.of(
                        new RunSummaryContext.RunTargetDto("target-1", "device-1", "SUCCEEDED", 1, "task-1", "attempt-1", null, null, null),
                        new RunSummaryContext.RunTargetDto("target-2", "device-2", "FAILED", 2, "task-2", "attempt-2", "ui target not found", null, null)
                ),
                List.of(
                        new FailureTriageContext.AttemptDto("attempt-1", "task-1", "device-1", "run-1", "SUCCEEDED", "SUCCEEDED", null, empty, empty, 1L, 2L, 1L),
                        new FailureTriageContext.AttemptDto("attempt-2", "task-2", "device-2", "run-1", "FAILED", "FAILED", "ui target not found", empty, empty, 3L, 4L, 3L)
                ),
                List.of(new FailureTriageContext.KeyEventDto("action_end", "FAILED", null, "Tap target missing", 1_770_000_004_000L)),
                List.of()
        );
    }
}

package com.example.platform.control.application;

import com.example.platform.control.api.AiFailureTriageApiModels;
import com.example.platform.control.domain.PersistenceModels.AiFailureTriageResultEntity;
import com.example.platform.control.infrastructure.mapper.AiFailureTriageResultMapper;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.web.server.ResponseStatusException;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class AiFailureTriageServiceTest {

    private FailureTriageContextBuilder failureTriageContextBuilder;
    private Phase3AiAuditService phase3AiAuditService;
    private AiBridgeClient aiBridgeClient;
    private FailureTriageSemanticValidator failureTriageSemanticValidator;
    private AiFailureTriageResultMapper aiFailureTriageResultMapper;
    private JsonCodec jsonCodec;
    private AiFailureTriageService service;

    @BeforeEach
    void setUp() {
        failureTriageContextBuilder = Mockito.mock(FailureTriageContextBuilder.class);
        phase3AiAuditService = Mockito.mock(Phase3AiAuditService.class);
        aiBridgeClient = Mockito.mock(AiBridgeClient.class);
        failureTriageSemanticValidator = Mockito.mock(FailureTriageSemanticValidator.class);
        aiFailureTriageResultMapper = Mockito.mock(AiFailureTriageResultMapper.class);
        jsonCodec = new JsonCodec(new ObjectMapper());
        service = new AiFailureTriageService(
                failureTriageContextBuilder,
                phase3AiAuditService,
                aiBridgeClient,
                failureTriageSemanticValidator,
                aiFailureTriageResultMapper,
                jsonCodec
        );
    }

    @Test
    void createFailureTriageBuildsContextCallsBridgeAndReturnsValidation() {
        Phase3AiModels.FailureTriageContext context = triageContext("FAILED");
        Phase3AiModels.FailureTriageResult triageResult = triageResult(Phase3AiModels.FailureCategory.UI_NOT_FOUND);
        when(failureTriageContextBuilder.build("target-1")).thenReturn(context);
        when(phase3AiAuditService.recordFailureTriageContext("run-1", "target-1", "attempt-1", context))
                .thenReturn("triage-1");
        when(aiBridgeClient.createFailureTriage(context)).thenReturn(new AiBridgeModels.FailureTriageResponse(
                triageResult,
                Map.of("provider", "stub")
        ));
        when(failureTriageSemanticValidator.validate(triageResult)).thenReturn(new Phase3AiModels.ValidationResult(
                true,
                List.of(),
                List.of("triage warning")
        ));

        AiFailureTriageApiModels.FailureTriageResponse response = service.createFailureTriage("target-1");

        assertEquals("triage-1", response.triageResultId());
        assertEquals("target-1", response.runTargetId());
        assertEquals("UI_NOT_FOUND", response.result().failureCategory().name());
        assertEquals(true, response.validation().valid());
        verify(phase3AiAuditService).recordFailureTriageResult(
                eq("triage-1"),
                eq(triageResult),
                any(Phase3AiModels.ValidationResult.class),
                eq(Map.of("provider", "stub"))
        );
    }

    @Test
    void createFailureTriageRejectsNonFailedTargets() {
        when(failureTriageContextBuilder.build("target-1")).thenReturn(triageContext("SUCCEEDED"));

        ResponseStatusException exception = assertThrows(ResponseStatusException.class, () ->
                service.createFailureTriage("target-1")
        );

        assertEquals(ControlErrorCode.AI_FAILURE_TRIAGE_NOT_ALLOWED, exception.getReason());
    }

    @Test
    void getLatestFailureTriageReturnsStoredResult() {
        AiFailureTriageResultEntity entity = new AiFailureTriageResultEntity();
        entity.setTriageResultId("triage-1");
        entity.setRunTargetId("target-1");
        entity.setResultJson(jsonCodec.write(triageResult(Phase3AiModels.FailureCategory.QUEUE_TIMEOUT)));
        entity.setValidationJson(jsonCodec.write(new Phase3AiModels.ValidationResult(false, List.of("manual review"), List.of())));
        entity.setModelMetaJson(jsonCodec.write(Map.of("provider", "stub")));
        entity.setCreatedAt(1770000000000L);
        when(aiFailureTriageResultMapper.findLatestByRunTargetId("target-1")).thenReturn(entity);

        AiFailureTriageApiModels.FailureTriageResponse response = service.getLatestFailureTriage("target-1");

        assertEquals("triage-1", response.triageResultId());
        assertFalse(response.validation().valid());
        assertEquals("QUEUE_TIMEOUT", response.result().failureCategory().name());
    }

    private Phase3AiModels.FailureTriageContext triageContext(String targetStatus) {
        return new Phase3AiModels.FailureTriageContext(
                new Phase3AiModels.RunSummary(
                        "run-1",
                        "pool-1",
                        "TERMINAL",
                        "FAILED",
                        "PLUGIN_RUN",
                        "com.google.android.apps.maps",
                        100,
                        List.of("phase3"),
                        0,
                        300000L,
                        false,
                        1L,
                        2L
                ),
                new Phase3AiModels.RunTargetSummary(
                        "target-1",
                        "device-1",
                        targetStatus,
                        1,
                        "task-1",
                        "attempt-1",
                        "UI target not found",
                        1L,
                        2L
                ),
                new Phase3AiModels.AttemptSummary(
                        "attempt-1",
                        "task-1",
                        "device-1",
                        "run-1",
                        "FAILED",
                        "FAILED",
                        "UI target not found",
                        Map.of(),
                        Map.of("lastError", "ui target not found"),
                        1L,
                        2L,
                        1L
                ),
                new Phase3AiModels.AttemptHistorySummary(1, List.of(
                        new Phase3AiModels.AttemptHistoryEntry(
                                "attempt-1",
                                "FAILED",
                                "FAILED",
                                "UI target not found",
                                2L,
                                "device-1"
                        )
                ), false, false),
                new Phase3AiModels.FailureContext(
                        "FAILED",
                        "UI target not found",
                        "ui target not found",
                        false,
                        false,
                        false,
                        false,
                        Map.of(),
                        Map.of("lastError", "ui target not found")
                ),
                List.of(new Phase3AiModels.KeyEvent("STEP", null, null, "search", 1L)),
                List.of(new Phase3AiModels.ArtifactManifestItem("artifact-1", "run_log", "run.log", "text/plain", 12L, "object")),
                new Phase3AiModels.DeviceOperationalSnapshot(
                        Phase3AiModels.DeviceOperationalSnapshotType.FAILURE,
                        2L,
                        "device-1",
                        "default",
                        List.of("com.google.android.apps.maps"),
                        Map.of(),
                        Map.of(),
                        Map.of(),
                        2L
                )
        );
    }

    private Phase3AiModels.FailureTriageResult triageResult(Phase3AiModels.FailureCategory category) {
        return new Phase3AiModels.FailureTriageResult(
                category,
                "UI target never appeared.",
                0.8d,
                Phase3AiModels.RetryRecommendation.RETRY_SAME_DEVICE,
                Phase3AiModels.SuggestedNextAction.INSPECT_ARTIFACTS,
                List.of("check the latest screenshot"),
                List.of("lastError:ui target not found")
        );
    }
}

package com.example.platform.control.application;

import com.example.platform.control.api.AdminApiModels.CreateExperimentRunRequest;
import com.example.platform.control.api.AdminApiModels.ExperimentRunDetailResponse;
import com.example.platform.control.api.AdminApiModels.ExperimentRunSummaryResponse;
import com.example.platform.control.api.AdminApiModels.RunStatusCounts;
import com.example.platform.control.api.AiRunPlanApiModels;
import com.example.platform.control.domain.DomainValues;
import com.example.platform.control.domain.PersistenceModels.AiRunPlanRequestEntity;
import com.example.platform.control.domain.PersistenceModels.AiRunPlanResultEntity;
import com.example.platform.control.infrastructure.mapper.AiRunPlanRequestMapper;
import com.example.platform.control.infrastructure.mapper.AiRunPlanResultMapper;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.mockito.Mockito;
import org.springframework.web.server.ResponseStatusException;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class AiRunPlanningServiceTest {

    private RunPlanningContextBuilder runPlanningContextBuilder;
    private Phase3AiAuditService phase3AiAuditService;
    private AiBridgeClient aiBridgeClient;
    private RunDraftSemanticValidator runDraftSemanticValidator;
    private AiRunPlanRequestMapper aiRunPlanRequestMapper;
    private AiRunPlanResultMapper aiRunPlanResultMapper;
    private ExperimentRunService experimentRunService;
    private JsonCodec jsonCodec;
    private AiRunPlanningService service;

    @BeforeEach
    void setUp() {
        runPlanningContextBuilder = Mockito.mock(RunPlanningContextBuilder.class);
        phase3AiAuditService = Mockito.mock(Phase3AiAuditService.class);
        aiBridgeClient = Mockito.mock(AiBridgeClient.class);
        runDraftSemanticValidator = Mockito.mock(RunDraftSemanticValidator.class);
        aiRunPlanRequestMapper = Mockito.mock(AiRunPlanRequestMapper.class);
        aiRunPlanResultMapper = Mockito.mock(AiRunPlanResultMapper.class);
        experimentRunService = Mockito.mock(ExperimentRunService.class);
        jsonCodec = new JsonCodec(new ObjectMapper());
        service = new AiRunPlanningService(
                runPlanningContextBuilder,
                phase3AiAuditService,
                aiBridgeClient,
                runDraftSemanticValidator,
                aiRunPlanRequestMapper,
                aiRunPlanResultMapper,
                experimentRunService,
                jsonCodec
        );
    }

    @Test
    void createRunPlanBuildsContextCallsBridgeAndReturnsValidation() {
        Phase3AiModels.RunPlanningContext context = runPlanningContext();
        Phase3AiModels.RunDraft draft = runDraft("pool-1", "com.google.android.apps.maps");
        when(runPlanningContextBuilder.build("navigate to ikea", Map.of("locale", "zh-CN"))).thenReturn(context);
        when(phase3AiAuditService.recordRunPlanningRequest(context)).thenReturn("run-plan-1");
        when(aiBridgeClient.createRunPlan(context)).thenReturn(new AiBridgeModels.RunPlanResponse(
                draft,
                List.of("soft warning"),
                List.of("review pool"),
                Map.of("provider", "stub")
        ));
        when(runDraftSemanticValidator.validate(any())).thenReturn(new Phase3AiModels.ValidationResult(
                true,
                List.of(),
                List.of("validation warning")
        ));

        AiRunPlanApiModels.CreateRunPlanResponse response = service.createRunPlan(
                new AiRunPlanApiModels.CreateRunPlanRequest("navigate to ikea", Map.of("locale", "zh-CN"))
        );

        assertEquals("run-plan-1", response.requestId());
        assertEquals("pool-1", response.runDraft().devicePoolId());
        assertEquals(true, response.validation().materializable());
        assertEquals(List.of("validation warning"), response.validation().warnings());
        verify(phase3AiAuditService).recordRunPlanningResult(
                eq("run-plan-1"),
                any(Phase3AiModels.RunDraftResult.class),
                any(Phase3AiModels.ValidationResult.class),
                eq(Map.of("provider", "stub"))
        );
    }

    @Test
    void materializeRunPlanCreatesExperimentRunAndMarksRequestMaterialized() {
        AiRunPlanRequestEntity requestEntity = new AiRunPlanRequestEntity();
        requestEntity.setRequestId("run-plan-1");
        requestEntity.setGoalText("navigate to ikea");
        requestEntity.setConstraintsJson(jsonCodec.write(Map.of("locale", "zh-CN")));
        requestEntity.setStatus(DomainValues.AI_RUN_PLAN_STATUS_READY);

        Phase3AiModels.RunDraft draft = runDraft("pool-1", "com.google.android.apps.maps");
        Phase3AiModels.RunDraftResult result = new Phase3AiModels.RunDraftResult(draft, List.of(), List.of());
        AiRunPlanResultEntity resultEntity = new AiRunPlanResultEntity();
        resultEntity.setRequestId("run-plan-1");
        resultEntity.setResultJson(jsonCodec.write(result));
        resultEntity.setValidationJson(jsonCodec.write(new Phase3AiModels.ValidationResult(true, List.of(), List.of())));
        when(aiRunPlanRequestMapper.lockById("run-plan-1")).thenReturn(requestEntity);
        when(aiRunPlanResultMapper.findById("run-plan-1")).thenReturn(resultEntity);
        when(runPlanningContextBuilder.build("navigate to ikea", Map.of("locale", "zh-CN"))).thenReturn(runPlanningContext());
        when(runDraftSemanticValidator.validate(any())).thenReturn(new Phase3AiModels.ValidationResult(true, List.of(), List.of()));
        when(experimentRunService.createRun(any())).thenReturn(runDetail("run-1", "operator"));

        ExperimentRunDetailResponse response = service.materializeRunPlan("run-plan-1", "operator");

        assertEquals("run-1", response.run().runId());
        ArgumentCaptor<CreateExperimentRunRequest> requestCaptor = ArgumentCaptor.forClass(CreateExperimentRunRequest.class);
        verify(experimentRunService).createRun(requestCaptor.capture());
        assertEquals("ai-run-planning", requestCaptor.getValue().source());
        assertEquals("operator", requestCaptor.getValue().createdBy());
        verify(aiRunPlanRequestMapper).updateMaterialization(any(AiRunPlanRequestEntity.class));
    }

    @Test
    void materializeRunPlanRejectsRepeatedMaterialization() {
        AiRunPlanRequestEntity requestEntity = new AiRunPlanRequestEntity();
        requestEntity.setRequestId("run-plan-1");
        requestEntity.setStatus(DomainValues.AI_RUN_PLAN_STATUS_READY);
        requestEntity.setMaterializedRunId("run-1");
        when(aiRunPlanRequestMapper.lockById("run-plan-1")).thenReturn(requestEntity);

        ResponseStatusException exception = assertThrows(ResponseStatusException.class, () ->
                service.materializeRunPlan("run-plan-1", "operator")
        );

        assertEquals(ControlErrorCode.AI_RUN_PLAN_ALREADY_MATERIALIZED, exception.getReason());
        verify(experimentRunService, never()).createRun(any());
    }

    @Test
    void materializeRunPlanRejectsSemanticDrift() {
        AiRunPlanRequestEntity requestEntity = new AiRunPlanRequestEntity();
        requestEntity.setRequestId("run-plan-1");
        requestEntity.setGoalText("navigate to ikea");
        requestEntity.setConstraintsJson(jsonCodec.write(Map.of()));
        requestEntity.setStatus(DomainValues.AI_RUN_PLAN_STATUS_READY);

        Phase3AiModels.RunDraftResult result = new Phase3AiModels.RunDraftResult(
                runDraft("pool-1", "com.google.android.apps.maps"),
                List.of(),
                List.of()
        );
        AiRunPlanResultEntity resultEntity = new AiRunPlanResultEntity();
        resultEntity.setRequestId("run-plan-1");
        resultEntity.setResultJson(jsonCodec.write(result));
        resultEntity.setValidationJson(jsonCodec.write(new Phase3AiModels.ValidationResult(true, List.of(), List.of())));
        when(aiRunPlanRequestMapper.lockById("run-plan-1")).thenReturn(requestEntity);
        when(aiRunPlanResultMapper.findById("run-plan-1")).thenReturn(resultEntity);
        when(runPlanningContextBuilder.build("navigate to ikea", Map.of())).thenReturn(runPlanningContext());
        when(runDraftSemanticValidator.validate(any())).thenReturn(new Phase3AiModels.ValidationResult(false, List.of("profile drift"), List.of()));

        ResponseStatusException exception = assertThrows(ResponseStatusException.class, () ->
                service.materializeRunPlan("run-plan-1", "operator")
        );

        assertEquals(ControlErrorCode.AI_RUN_PLAN_INVALID, exception.getReason());
        verify(experimentRunService, never()).createRun(any());
    }

    @Test
    void getRunPlanReturnsStoredDraftAndMaterializationState() {
        AiRunPlanRequestEntity requestEntity = new AiRunPlanRequestEntity();
        requestEntity.setRequestId("run-plan-1");
        requestEntity.setGoalText("navigate to ikea");
        requestEntity.setConstraintsJson(jsonCodec.write(Map.of("locale", "zh-CN")));
        requestEntity.setStatus(DomainValues.AI_RUN_PLAN_STATUS_MATERIALIZED);
        requestEntity.setMaterializedRunId("run-1");
        requestEntity.setMaterializedBy("operator");
        requestEntity.setMaterializedAt(5L);

        AiRunPlanResultEntity resultEntity = new AiRunPlanResultEntity();
        resultEntity.setRequestId("run-plan-1");
        resultEntity.setResultJson(jsonCodec.write(new Phase3AiModels.RunDraftResult(
                runDraft("pool-1", "com.google.android.apps.maps"),
                List.of("soft warning"),
                List.of("review pool")
        )));
        resultEntity.setValidationJson(jsonCodec.write(new Phase3AiModels.ValidationResult(true, List.of(), List.of("validation warning"))));
        resultEntity.setModelMetaJson(jsonCodec.write(Map.of("provider", "stub")));
        resultEntity.setCreatedAt(7L);
        when(aiRunPlanRequestMapper.findById("run-plan-1")).thenReturn(requestEntity);
        when(aiRunPlanResultMapper.findById("run-plan-1")).thenReturn(resultEntity);

        AiRunPlanApiModels.RunPlanResponse response = service.getRunPlan("run-plan-1");

        assertEquals("run-plan-1", response.requestId());
        assertEquals("run-1", response.materializedRunId());
        assertEquals("operator", response.materializedBy());
        assertNotNull(response.runDraft());
        assertEquals(List.of("soft warning"), response.warnings());
    }

    private Phase3AiModels.RunPlanningContext runPlanningContext() {
        return new Phase3AiModels.RunPlanningContext(
                "navigate to ikea",
                Map.of(),
                List.of(new Phase3AiModels.AvailableDevicePool("pool-1", "Pool 1", "default", 1, List.of(), List.of())),
                List.of(new Phase3AiModels.AvailableProfile(
                        "com.google.android.apps.maps",
                        1,
                        List.of("PLUGIN_RUN", "PLUGIN_SMOKE"),
                        List.of("goal"),
                        Map.of(),
                        List.of()
                )),
                new Phase3AiModels.DefaultRunPolicy(
                        100,
                        0,
                        300000,
                        Map.of(
                                "loopCount", 1,
                                "budgetMs", 60000,
                                "loopIntervalMs", 0,
                                "networkIsolationEnabled", false,
                                "pollIntervalMs", 15000,
                                "heartbeatIntervalMs", 30000
                        ),
                        Map.of(
                                "uploadLog", true,
                                "uploadScreenshot", true,
                                "uploadDump", false
                        )
                ),
                List.of("PLUGIN_RUN", "PLUGIN_SMOKE")
        );
    }

    private Phase3AiModels.RunDraft runDraft(String poolId, String profilePackage) {
        return new Phase3AiModels.RunDraft(
                "AI run",
                "navigate to ikea",
                poolId,
                "PLUGIN_RUN",
                profilePackage,
                Map.of("goal", "navigate to ikea"),
                Map.of(
                        "loopCount", 1,
                        "budgetMs", 60000,
                        "loopIntervalMs", 0,
                        "networkIsolationEnabled", false,
                        "pollIntervalMs", 15000,
                        "heartbeatIntervalMs", 30000
                ),
                Map.of(
                        "uploadLog", true,
                        "uploadScreenshot", true,
                        "uploadDump", false
                ),
                100,
                List.of("ai", "run-draft"),
                0,
                300000
        );
    }

    private ExperimentRunDetailResponse runDetail(String runId, String createdBy) {
        return new ExperimentRunDetailResponse(
                new ExperimentRunSummaryResponse(
                        runId,
                        "AI run",
                        "navigate to ikea",
                        "pool-1",
                        DomainValues.RUN_STATUS_QUEUED,
                        null,
                        "PLUGIN_RUN",
                        "com.google.android.apps.maps",
                        100,
                        List.of("ai", "run-draft"),
                        "ai-run-planning",
                        createdBy,
                        0,
                        300000,
                        false,
                        1L,
                        1L,
                        null,
                        null,
                        new RunStatusCounts(1, 1, 0, 0, 0, 0, 0)
                ),
                Map.of("goal", "navigate to ikea"),
                new com.example.platform.control.api.ExecutorApiModels.RunConfig(1, 60000, 0, false, 15000, 30000),
                new com.example.platform.control.api.ExecutorApiModels.ArtifactPolicy(true, true, false),
                List.of()
        );
    }
}

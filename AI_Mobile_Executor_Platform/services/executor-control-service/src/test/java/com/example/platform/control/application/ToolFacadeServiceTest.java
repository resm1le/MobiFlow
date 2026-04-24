package com.example.platform.control.application;

import com.example.platform.control.api.AdminApiModels;
import com.example.platform.control.api.ExecutorApiModels;
import com.example.platform.control.api.ToolApiModels;
import com.example.platform.control.domain.PersistenceModels.ToolConfirmationTokenEntity;
import com.example.platform.control.domain.PersistenceModels.ToolExecutionAuditEntity;
import com.example.platform.control.infrastructure.mapper.ToolConfirmationTokenMapper;
import com.example.platform.control.infrastructure.mapper.ToolExecutionAuditMapper;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class ToolFacadeServiceTest {

    private AdminApiService adminApiService;
    private ExperimentRunService experimentRunService;
    private AiRunPlanningService aiRunPlanningService;
    private AiRunSummaryService aiRunSummaryService;
    private AiFailureTriageService aiFailureTriageService;
    private RunPlanningContextBuilder runPlanningContextBuilder;
    private ToolResourceService toolResourceService;
    private ToolExecutionAuditMapper toolExecutionAuditMapper;
    private ToolConfirmationTokenMapper toolConfirmationTokenMapper;
    private ToolFacadeService toolFacadeService;

    private final Map<String, ToolExecutionAuditEntity> auditsByRequestId = new LinkedHashMap<>();
    private final Map<String, ToolExecutionAuditEntity> auditsById = new LinkedHashMap<>();
    private final Map<String, ToolConfirmationTokenEntity> confirmationsById = new LinkedHashMap<>();

    @BeforeEach
    void setUp() {
        adminApiService = Mockito.mock(AdminApiService.class);
        experimentRunService = Mockito.mock(ExperimentRunService.class);
        aiRunPlanningService = Mockito.mock(AiRunPlanningService.class);
        aiRunSummaryService = Mockito.mock(AiRunSummaryService.class);
        aiFailureTriageService = Mockito.mock(AiFailureTriageService.class);
        runPlanningContextBuilder = Mockito.mock(RunPlanningContextBuilder.class);
        toolResourceService = Mockito.mock(ToolResourceService.class);
        toolExecutionAuditMapper = Mockito.mock(ToolExecutionAuditMapper.class);
        toolConfirmationTokenMapper = Mockito.mock(ToolConfirmationTokenMapper.class);

        doAnswer(invocation -> {
            ToolExecutionAuditEntity audit = invocation.getArgument(0);
            auditsByRequestId.put(audit.getRequestId(), audit);
            auditsById.put(audit.getAuditId(), audit);
            return null;
        }).when(toolExecutionAuditMapper).insert(any(ToolExecutionAuditEntity.class));
        when(toolExecutionAuditMapper.findByRequestId(any())).thenAnswer(invocation ->
                auditsByRequestId.get(invocation.getArgument(0, String.class)));
        when(toolExecutionAuditMapper.findById(any())).thenAnswer(invocation ->
                auditsById.get(invocation.getArgument(0, String.class)));
        when(toolExecutionAuditMapper.findBySessionId(any())).thenAnswer(invocation ->
                auditsByRequestId.values().stream()
                        .filter(audit -> audit.getSessionId().equals(invocation.getArgument(0, String.class)))
                        .toList());
        when(toolExecutionAuditMapper.findByRunId(any())).thenAnswer(invocation ->
                auditsByRequestId.values().stream()
                        .filter(audit -> audit.getEntityRefsJson() != null
                                && audit.getEntityRefsJson().contains("\"runId\":\"" + invocation.getArgument(0, String.class) + "\""))
                        .toList());
        when(toolExecutionAuditMapper.findByAttemptId(any())).thenAnswer(invocation ->
                auditsByRequestId.values().stream()
                        .filter(audit -> audit.getEntityRefsJson() != null
                                && audit.getEntityRefsJson().contains("\"attemptId\":\"" + invocation.getArgument(0, String.class) + "\""))
                        .toList());
        when(toolExecutionAuditMapper.findBySessionIdAndRunId(any(), any())).thenAnswer(invocation ->
                auditsByRequestId.values().stream()
                        .filter(audit -> audit.getSessionId().equals(invocation.getArgument(0, String.class)))
                        .filter(audit -> audit.getEntityRefsJson() != null
                                && audit.getEntityRefsJson().contains("\"runId\":\"" + invocation.getArgument(1, String.class) + "\""))
                        .toList());
        when(toolExecutionAuditMapper.listAll()).thenAnswer(invocation -> List.copyOf(auditsByRequestId.values()));
        doAnswer(invocation -> {
            ToolExecutionAuditEntity audit = invocation.getArgument(0);
            auditsByRequestId.put(audit.getRequestId(), audit);
            auditsById.put(audit.getAuditId(), audit);
            return null;
        }).when(toolExecutionAuditMapper).update(any(ToolExecutionAuditEntity.class));

        doAnswer(invocation -> {
            ToolConfirmationTokenEntity token = invocation.getArgument(0);
            confirmationsById.put(token.getConfirmationId(), token);
            return null;
        }).when(toolConfirmationTokenMapper).insert(any(ToolConfirmationTokenEntity.class));
        when(toolConfirmationTokenMapper.findById(any())).thenAnswer(invocation ->
                confirmationsById.get(invocation.getArgument(0, String.class)));
        doAnswer(invocation -> {
            ToolConfirmationTokenEntity token = invocation.getArgument(0);
            confirmationsById.put(token.getConfirmationId(), token);
            return null;
        }).when(toolConfirmationTokenMapper).update(any(ToolConfirmationTokenEntity.class));

        ControlProperties properties = new ControlProperties();
        properties.getTools().setConfirmationTtlMs(300_000L);

        toolFacadeService = new ToolFacadeService(
                adminApiService,
                experimentRunService,
                aiRunPlanningService,
                aiRunSummaryService,
                aiFailureTriageService,
                runPlanningContextBuilder,
                toolResourceService,
                new IdGenerator(),
                new JsonCodec(new ObjectMapper()),
                new ObjectMapper(),
                toolExecutionAuditMapper,
                toolConfirmationTokenMapper,
                properties
        );
    }

    @Test
    void catalogIncludesGovernanceMetadata() {
        ToolApiModels.ToolCatalogResponse response = toolFacadeService.catalog();

        ToolApiModels.ToolCatalogItem readTool = response.tools().stream()
                .filter(item -> item.name().equals("list_devices"))
                .findFirst()
                .orElseThrow();
        ToolApiModels.ToolCatalogItem sideEffectTool = response.tools().stream()
                .filter(item -> item.name().equals("create_single_device_run"))
                .findFirst()
                .orElseThrow();

        assertEquals(ToolFacadeService.PROTOCOL_VERSION, response.version());
        assertEquals("read", readTool.toolKind());
        assertFalse(readTool.governance().requiresApproval());
        assertEquals("side_effect", sideEffectTool.toolKind());
        assertTrue(sideEffectTool.governance().requiresApproval());
        assertEquals("explicit", sideEffectTool.governance().confirmationMode());
        assertTrue(sideEffectTool.semanticTags().contains("governed"));
        assertTrue(response.tools().stream().anyMatch(item ->
                item.name().equals("get_run_governance_snapshot")
                        && item.toolKind().equals("read")
                        && !item.governance().requiresApproval()
        ));
    }

    @Test
    void readToolReturnsCompletedEnvelopeWithAuditAndEntityRefs() {
        when(adminApiService.listDevices()).thenReturn(List.of(new AdminApiModels.DeviceResponse(
                "device-1",
                "v1",
                "1.0",
                "google",
                "Pixel 6",
                "13",
                1080,
                2400,
                List.of("com.demo.profile"),
                List.of("android-executor"),
                "default",
                true,
                true,
                false,
                "ONLINE",
                null,
                null,
                null,
                "cfg-v1",
                true,
                null,
                0L,
                "QUIESCE",
                Map.of("authConfigured", true),
                0L
        )));

        ToolApiModels.ExecuteToolResponse response = toolFacadeService.execute(executeRequest(
                "req-read-1",
                "list_devices",
                Map.of()
        ));

        assertEquals("completed", response.status());
        assertNull(response.error());
        assertNotNull(response.audit());
        assertEquals("DISCOVERY", response.audit().riskLevel());
        assertNotNull(response.entityRefs());
        assertTrue(response.entityRefs().artifactIds().isEmpty());
    }

    @Test
    void sideEffectExecuteReturnsApprovalRequiredWithoutMutatingPlatformState() {
        ToolApiModels.ExecuteToolResponse response = toolFacadeService.execute(executeRequest(
                "req-side-1",
                "create_single_device_run",
                createSingleDeviceRunArguments("device-1")
        ));

        assertEquals("approval_required", response.status());
        assertNull(response.result());
        assertNull(response.error());
        assertNotNull(response.confirmation());
        assertNotNull(response.audit());
        verify(experimentRunService, never()).createSingleDeviceRun(any());
    }

    @Test
    void resolveApproveExecutesExactlyOnce() {
        when(experimentRunService.createSingleDeviceRun(any())).thenReturn(singleDeviceRunDetail("run-single-1", "device-1"));

        ToolApiModels.ExecuteToolResponse staged = toolFacadeService.execute(executeRequest(
                "req-side-2",
                "create_single_device_run",
                createSingleDeviceRunArguments("device-1")
        ));
        ToolApiModels.ExecuteToolResponse approved = toolFacadeService.resolveConfirmation(resolveRequest(
                staged.confirmation().confirmationId(),
                "approve"
        ));
        ToolApiModels.ExecuteToolResponse duplicate = toolFacadeService.resolveConfirmation(resolveRequest(
                staged.confirmation().confirmationId(),
                "approve"
        ));

        assertEquals("completed", approved.status());
        assertNull(approved.error());
        assertEquals("run-single-1", approved.entityRefs().runId());
        assertEquals(ControlErrorCode.TOOL_CONFIRMATION_INVALID, duplicate.error().code());
        verify(experimentRunService).createSingleDeviceRun(any());
    }

    @Test
    void resolveRejectClosesConfirmationWithoutExecutingSideEffect() {
        ToolApiModels.ExecuteToolResponse staged = toolFacadeService.execute(executeRequest(
                "req-side-3",
                "create_task",
                Map.of(
                        "taskType", "PLUGIN_RUN",
                        "profilePackage", "com.demo.profile",
                        "taskPayload", Map.of("goal", "open maps"),
                        "runConfig", Map.of(),
                        "artifactPolicy", Map.of()
                )
        ));

        ToolApiModels.ExecuteToolResponse rejected = toolFacadeService.resolveConfirmation(resolveRequest(
                staged.confirmation().confirmationId(),
                "reject"
        ));

        assertEquals("failed", rejected.status());
        assertEquals("TOOL_CONFIRMATION_REJECTED", rejected.error().code());
        verify(adminApiService, never()).createTask(any());
    }

    @Test
    void requestReplayReturnsStoredApprovalRequiredEnvelope() {
        ToolApiModels.ExecuteToolResponse first = toolFacadeService.execute(executeRequest(
                "req-side-4",
                "cancel_run",
                Map.of("runId", "run-1")
        ));
        ToolApiModels.ExecuteToolResponse second = toolFacadeService.execute(executeRequest(
                "req-side-4",
                "cancel_run",
                Map.of("runId", "run-1")
        ));

        assertEquals(first.audit().auditId(), second.audit().auditId());
        assertEquals(first.confirmation().confirmationId(), second.confirmation().confirmationId());
    }

    @Test
    void governedProposalExecutesUnderlyingActionAfterApproval() {
        when(adminApiService.getDevice("device-1")).thenReturn(deviceResponse("device-1", true));
        when(experimentRunService.createSingleDeviceRun(any())).thenReturn(singleDeviceRunDetail("run-single-2", "device-1"));

        ToolApiModels.ExecuteToolResponse staged = toolFacadeService.execute(executeRequest(
                "req-proposal-1",
                "propose_governed_action",
                Map.of(
                        "proposalId", "proposal-1",
                        "actionToolName", "create_single_device_run",
                        "arguments", createSingleDeviceRunArguments("device-1"),
                        "targetKind", "device",
                        "targetId", "device-1",
                        "rationale", "The device is online and eligible.",
                        "preconditions", Map.of("deviceId", "device-1")
                )
        ));

        assertEquals("approval_required", staged.status());
        assertEquals("proposal-1", staged.entityRefs().proposalId());

        ToolApiModels.ExecuteToolResponse approved = toolFacadeService.resolveConfirmation(resolveRequest(
                staged.confirmation().confirmationId(),
                "approve"
        ));

        assertEquals("completed", approved.status());
        assertEquals("proposal-1", approved.entityRefs().proposalId());
        assertEquals("run-single-2", approved.entityRefs().runId());
        Map<String, Object> payload = new ObjectMapper().convertValue(approved.result(), Map.class);
        assertEquals("executed", payload.get("proposalState"));
        assertEquals("matched", payload.get("consistencyStatus"));
    }

    @Test
    void governedProposalFailsWhenPreconditionsNoLongerMatch() {
        when(experimentRunService.getRun("run-cancelled")).thenReturn(runDetail(
                "run-cancelled",
                "CANCELLED",
                "CANCELLED",
                "pool-1",
                true,
                new AdminApiModels.RunStatusCounts(1, 0, 0, 0, 0, 0, 1),
                "CANCELLED",
                "USER_CANCELLED"
        ));

        ToolApiModels.ExecuteToolResponse staged = toolFacadeService.execute(executeRequest(
                "req-proposal-2",
                "propose_governed_action",
                Map.of(
                        "proposalId", "proposal-2",
                        "actionToolName", "cancel_run",
                        "arguments", Map.of("runId", "run-cancelled"),
                        "targetKind", "run",
                        "targetId", "run-cancelled",
                        "rationale", "Cancel the blocked run.",
                        "preconditions", Map.of("runId", "run-cancelled", "status", "RUNNING")
                )
        ));

        ToolApiModels.ExecuteToolResponse rejected = toolFacadeService.resolveConfirmation(resolveRequest(
                staged.confirmation().confirmationId(),
                "approve"
        ));

        assertEquals("failed", rejected.status());
        assertEquals(ControlErrorCode.TOOL_PROPOSAL_PRECONDITION_FAILED, rejected.error().code());
        verify(experimentRunService, never()).cancelRun("run-cancelled");
    }

    @Test
    void runGovernanceSnapshotReturnsStructuredObservation() {
        when(experimentRunService.getRun("run-blocked")).thenReturn(runDetail(
                "run-blocked",
                "RUNNING",
                null,
                "pool-1",
                false,
                new AdminApiModels.RunStatusCounts(1, 0, 0, 1, 0, 0, 0),
                "RETRY_PENDING",
                "QUEUE_TIMEOUT"
        ));
        when(adminApiService.listAttempts()).thenReturn(List.of(
                new AdminApiModels.AttemptSummary(
                        "attempt-1",
                        "task-1",
                        "device-1",
                        "run-blocked",
                        "RUNNING",
                        null,
                        null,
                        null,
                        null,
                        null,
                        1L,
                        2L
                )
        ));

        ToolApiModels.ExecuteToolResponse response = toolFacadeService.execute(executeRequest(
                "req-governance-1",
                "get_run_governance_snapshot",
                Map.of("runId", "run-blocked")
        ));

        assertEquals("completed", response.status());
        Map<String, Object> payload = new ObjectMapper().convertValue(response.result(), Map.class);
        assertEquals("run-blocked", payload.get("runId"));
        assertEquals("RUNNING", payload.get("status"));
        assertEquals(List.of("QUEUE_TIMEOUT"), payload.get("blockers"));
        assertEquals("run-blocked", response.entityRefs().runId());
    }

    @Test
    void runBlockageSummaryClassifiesQueueTimeout() {
        when(experimentRunService.getRun("run-blocked")).thenReturn(runDetail(
                "run-blocked",
                "RUNNING",
                null,
                "pool-1",
                false,
                new AdminApiModels.RunStatusCounts(1, 0, 0, 1, 0, 0, 0),
                "RETRY_PENDING",
                "QUEUE_TIMEOUT"
        ));

        ToolApiModels.ExecuteToolResponse response = toolFacadeService.execute(executeRequest(
                "req-governance-2",
                "get_run_blockage_summary",
                Map.of("runId", "run-blocked")
        ));

        assertEquals("completed", response.status());
        Map<String, Object> payload = new ObjectMapper().convertValue(response.result(), Map.class);
        assertEquals("queue_timeout", payload.get("blockageCategory"));
        assertEquals("cancel_run", payload.get("recommendedAction"));
        assertEquals(Boolean.TRUE, payload.get("retryable"));
    }

    @Test
    void runRecoveryOptionsRecommendSingleDeviceRerun() {
        when(experimentRunService.getRun("run-failed")).thenReturn(runDetail(
                "run-failed",
                "TERMINAL",
                "FAILED",
                null,
                false,
                new AdminApiModels.RunStatusCounts(1, 0, 0, 0, 0, 1, 0),
                "FAILED",
                "PRECHECK_FAILED"
        ));

        ToolApiModels.ExecuteToolResponse response = toolFacadeService.execute(executeRequest(
                "req-governance-3",
                "get_run_recovery_options",
                Map.of("runId", "run-failed")
        ));

        assertEquals("completed", response.status());
        Map<String, Object> payload = new ObjectMapper().convertValue(response.result(), Map.class);
        assertEquals("create_single_device_run", payload.get("recommendedAction"));
        assertEquals(Boolean.TRUE, payload.get("requiresApproval"));
    }

    @Test
    void runLineageSnapshotReturnsBundledObservation() {
        when(experimentRunService.getRun("run-blocked")).thenReturn(runDetail(
                "run-blocked",
                "RUNNING",
                null,
                "pool-1",
                false,
                new AdminApiModels.RunStatusCounts(1, 0, 0, 1, 0, 0, 0),
                "RETRY_PENDING",
                "QUEUE_TIMEOUT"
        ));
        when(adminApiService.listAttempts()).thenReturn(List.of(
                new AdminApiModels.AttemptSummary(
                        "attempt-1",
                        "task-1",
                        "device-1",
                        "run-blocked",
                        "RUNNING",
                        null,
                        null,
                        null,
                        null,
                        null,
                        1L,
                        2L
                )
        ));
        when(adminApiService.getAttemptArtifacts("attempt-1")).thenReturn(List.of());

        ToolApiModels.ExecuteToolResponse response = toolFacadeService.execute(executeRequest(
                "req-lineage-1",
                "get_run_lineage_snapshot",
                Map.of("runId", "run-blocked")
        ));

        assertEquals("completed", response.status());
        Map<String, Object> payload = new ObjectMapper().convertValue(response.result(), Map.class);
        assertEquals("run-blocked", payload.get("runId"));
        assertTrue(payload.containsKey("auditRefs"));
        assertTrue(payload.containsKey("currentGovernedOptions"));
    }

    @Test
    void auditQueryReturnsTimelineEntriesForRun() {
        when(experimentRunService.getRun("run-blocked")).thenReturn(runDetail(
                "run-blocked",
                "RUNNING",
                null,
                "pool-1",
                false,
                new AdminApiModels.RunStatusCounts(1, 0, 0, 1, 0, 0, 0),
                "RETRY_PENDING",
                "QUEUE_TIMEOUT"
        ));
        when(adminApiService.listAttempts()).thenReturn(List.of());

        toolFacadeService.execute(executeRequest(
                "req-governance-query",
                "get_run_governance_snapshot",
                Map.of("runId", "run-blocked")
        ));

        ToolApiModels.AuditQueryResponse response = toolFacadeService.queryAudits(
                new ToolApiModels.AuditQueryRequest("session-1", null, null, "run-blocked", null, null)
        );

        assertEquals(ToolFacadeService.PROTOCOL_VERSION, response.version());
        assertEquals(1, response.entries().size());
        assertEquals("get_run_governance_snapshot", response.entries().get(0).tool());
        assertEquals("run-blocked", response.entries().get(0).entityRefs().runId());
    }

    private ToolApiModels.ExecuteToolRequest executeRequest(
            String requestId,
            String tool,
            Map<String, Object> arguments
    ) {
        return new ToolApiModels.ExecuteToolRequest(
                null,
                requestId,
                "session-1",
                tool,
                arguments,
                callerContext("task-1", "turn-1", "step-1")
        );
    }

    private ToolApiModels.ResolveConfirmationRequest resolveRequest(String confirmationId, String decision) {
        return new ToolApiModels.ResolveConfirmationRequest(
                null,
                confirmationId,
                decision,
                "session-1",
                callerContext("task-1", "turn-1", "step-1")
        );
    }

    private ToolApiModels.CallerContext callerContext(String taskId, String turnId, String stepId) {
        return new ToolApiModels.CallerContext(taskId, turnId, stepId);
    }

    private Map<String, Object> createSingleDeviceRunArguments(String deviceId) {
        return Map.of(
                "name", "single",
                "deviceId", deviceId,
                "taskType", "PLUGIN_RUN",
                "profilePackage", "com.demo.profile",
                "taskPayload", Map.of("goal", "open maps"),
                "runConfig", Map.of(
                        "loopCount", 1,
                        "budgetMs", 1000,
                        "loopIntervalMs", 0,
                        "networkIsolationEnabled", false,
                        "pollIntervalMs", 1000,
                        "heartbeatIntervalMs", 1000
                ),
                "artifactPolicy", Map.of(
                        "uploadLog", true,
                        "uploadScreenshot", true,
                        "uploadDump", false
                )
        );
    }

    private AdminApiModels.ExperimentRunDetailResponse singleDeviceRunDetail(String runId, String deviceId) {
        return new AdminApiModels.ExperimentRunDetailResponse(
                new AdminApiModels.ExperimentRunSummaryResponse(
                        runId, "single", null, null, "QUEUED", null,
                        "PLUGIN_RUN", "com.demo.profile", 100, List.of("single"), "agent", "agent",
                        0, 300000L, false, 1L, 1L, null, null,
                        new AdminApiModels.RunStatusCounts(1, 1, 0, 0, 0, 0, 0)
                ),
                Map.of("goal", "open maps"),
                new ExecutorApiModels.RunConfig(1, 1000L, 0L, false, 1000L, 1000L),
                new ExecutorApiModels.ArtifactPolicy(true, true, false),
                List.of(new AdminApiModels.ExperimentRunTargetResponse(
                        "target-1",
                        deviceId,
                        "QUEUED",
                        1,
                        "task-1",
                        null,
                        null,
                        null,
                        null,
                        null,
                        null
                ))
        );
    }

    private AdminApiModels.ExperimentRunDetailResponse runDetail(
            String runId,
            String status,
            String finalState,
            String poolId,
            boolean cancelRequested,
            AdminApiModels.RunStatusCounts counts,
            String targetStatus,
            String failureReason
    ) {
        return new AdminApiModels.ExperimentRunDetailResponse(
                new AdminApiModels.ExperimentRunSummaryResponse(
                        runId,
                        "governance",
                        null,
                        poolId,
                        status,
                        finalState,
                        "PLUGIN_RUN",
                        "com.demo.profile",
                        100,
                        List.of("governance"),
                        "agent",
                        "agent",
                        0,
                        300000L,
                        cancelRequested,
                        1L,
                        2L,
                        null,
                        null,
                        counts
                ),
                Map.of("goal", "inspect run"),
                new ExecutorApiModels.RunConfig(1, 1000L, 0L, false, 1000L, 1000L),
                new ExecutorApiModels.ArtifactPolicy(true, true, false),
                List.of(new AdminApiModels.ExperimentRunTargetResponse(
                        "target-1",
                        "device-1",
                        targetStatus,
                        1,
                        "task-1",
                        "attempt-1",
                        failureReason,
                        null,
                        null,
                        null,
                        null
                ))
        );
    }

    private AdminApiModels.DeviceResponse deviceResponse(String deviceId, boolean online) {
        return new AdminApiModels.DeviceResponse(
                deviceId,
                "v1",
                "1.0",
                "google",
                "Pixel 7",
                "14",
                1080,
                2400,
                List.of("com.demo.profile"),
                List.of("android-executor"),
                "default",
                true,
                online,
                false,
                online ? "ONLINE" : "OFFLINE",
                null,
                null,
                null,
                "cfg-v1",
                true,
                null,
                1L,
                null,
                Map.of("authConfigured", true),
                2L
        );
    }
}

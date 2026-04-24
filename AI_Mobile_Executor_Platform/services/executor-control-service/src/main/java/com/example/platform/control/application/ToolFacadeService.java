package com.example.platform.control.application;

import com.example.platform.control.api.AdminApiModels;
import com.example.platform.control.api.AiRunPlanApiModels;
import com.example.platform.control.api.ExecutorApiModels;
import com.example.platform.control.api.ToolApiModels;
import com.example.platform.control.domain.PersistenceModels.ToolConfirmationTokenEntity;
import com.example.platform.control.domain.PersistenceModels.ToolExecutionAuditEntity;
import com.example.platform.control.infrastructure.mapper.ToolConfirmationTokenMapper;
import com.example.platform.control.infrastructure.mapper.ToolExecutionAuditMapper;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

@Service
public class ToolFacadeService {

    static final String PROTOCOL_VERSION = "tool-envelope-v2";
    static final String STATUS_CREATED = "CREATED";
    static final String STATUS_APPROVAL_REQUIRED = "APPROVAL_REQUIRED";
    static final String STATUS_SUCCEEDED = "SUCCEEDED";
    static final String STATUS_FAILED = "FAILED";
    static final String STATUS_REJECTED = "REJECTED";
    static final String RESPONSE_STATUS_COMPLETED = "completed";
    static final String RESPONSE_STATUS_FAILED = "failed";
    static final String RESPONSE_STATUS_APPROVAL_REQUIRED = "approval_required";
    static final String TOKEN_STATUS_PENDING = "PENDING";
    static final String TOKEN_STATUS_APPROVED = "APPROVED";
    static final String TOKEN_STATUS_REJECTED = "REJECTED";
    static final String TOKEN_STATUS_EXPIRED = "EXPIRED";
    static final String TOKEN_STATUS_USED = "USED";
    static final String STABILITY_STABLE = "stable";
    static final String RESULT_MODE_INLINE = "inline";
    static final String RISK_DISCOVERY = "DISCOVERY";
    static final String RISK_ADVISORY = "ADVISORY";
    static final String RISK_EXECUTION = "EXECUTION";
    static final String TOOL_KIND_READ = "read";
    static final String TOOL_KIND_ANALYZE = "analyze";
    static final String TOOL_KIND_SIDE_EFFECT = "side_effect";
    static final String CONFIRMATION_MODE_EXPLICIT = "explicit";
    static final String CONFIRMATION_REJECTED = "TOOL_CONFIRMATION_REJECTED";

    private final AdminApiService adminApiService;
    private final ExperimentRunService experimentRunService;
    private final AiRunPlanningService aiRunPlanningService;
    private final AiRunSummaryService aiRunSummaryService;
    private final AiFailureTriageService aiFailureTriageService;
    private final RunPlanningContextBuilder runPlanningContextBuilder;
    private final ToolResourceService toolResourceService;
    private final IdGenerator idGenerator;
    private final JsonCodec jsonCodec;
    private final ObjectMapper objectMapper;
    private final ToolExecutionAuditMapper toolExecutionAuditMapper;
    private final ToolConfirmationTokenMapper toolConfirmationTokenMapper;
    private final ControlProperties controlProperties;
    private final Map<String, ToolDefinition<?>> toolDefinitions;

    public ToolFacadeService(AdminApiService adminApiService,
                             ExperimentRunService experimentRunService,
                             AiRunPlanningService aiRunPlanningService,
                             AiRunSummaryService aiRunSummaryService,
                             AiFailureTriageService aiFailureTriageService,
                             RunPlanningContextBuilder runPlanningContextBuilder,
                             ToolResourceService toolResourceService,
                             IdGenerator idGenerator,
                             JsonCodec jsonCodec,
                             ObjectMapper objectMapper,
                             ToolExecutionAuditMapper toolExecutionAuditMapper,
                             ToolConfirmationTokenMapper toolConfirmationTokenMapper,
                             ControlProperties controlProperties) {
        this.adminApiService = adminApiService;
        this.experimentRunService = experimentRunService;
        this.aiRunPlanningService = aiRunPlanningService;
        this.aiRunSummaryService = aiRunSummaryService;
        this.aiFailureTriageService = aiFailureTriageService;
        this.runPlanningContextBuilder = runPlanningContextBuilder;
        this.toolResourceService = toolResourceService;
        this.idGenerator = idGenerator;
        this.jsonCodec = jsonCodec;
        this.objectMapper = objectMapper;
        this.toolExecutionAuditMapper = toolExecutionAuditMapper;
        this.toolConfirmationTokenMapper = toolConfirmationTokenMapper;
        this.controlProperties = controlProperties;
        this.toolDefinitions = buildDefinitions();
    }

    public ToolApiModels.ToolCatalogResponse catalog() {
        List<ToolApiModels.ToolCatalogItem> tools = toolDefinitions.values().stream()
                .sorted(java.util.Comparator.comparing(ToolDefinition::name))
                .map(definition -> new ToolApiModels.ToolCatalogItem(
                        definition.name(),
                        definition.title(),
                        definition.description(),
                        definition.inputSchema(),
                        definition.outputSchema(),
                        definition.resultMode(),
                        definition.stability(),
                        definition.toolKind(),
                        definition.riskLevel(),
                        new ToolApiModels.ToolGovernance(
                                definition.requiresApproval(),
                                definition.requiresApproval() ? CONFIRMATION_MODE_EXPLICIT : null
                        ),
                        definition.semanticTags()
                ))
                .toList();
        return new ToolApiModels.ToolCatalogResponse(PROTOCOL_VERSION, tools);
    }

    public ToolApiModels.ExecuteToolResponse execute(ToolApiModels.ExecuteToolRequest request) {
        try {
            ToolApiModels.ExecuteToolRequest normalized = normalizeRequest(request);
            String requestIdentityJson = jsonCodec.write(requestIdentity(normalized));
            ToolExecutionAuditEntity existingAudit = toolExecutionAuditMapper.findByRequestId(normalized.requestId());
            if (existingAudit != null) {
                return handleExistingAudit(existingAudit, normalized, requestIdentityJson);
            }
            return handleNewRequest(normalized, requestIdentityJson);
        } catch (ResponseStatusException exception) {
            return invalidRequestResponse(request, mapErrorCode(exception));
        }
    }

    public ToolApiModels.ExecuteToolResponse resolveConfirmation(ToolApiModels.ResolveConfirmationRequest request) {
        try {
            ToolApiModels.ResolveConfirmationRequest normalized = normalizeResolveRequest(request);
            ToolConfirmationTokenEntity token = toolConfirmationTokenMapper.findById(normalized.confirmationId());
            if (token == null) {
                return invalidConfirmationResponse(null, null, normalized, ControlErrorCode.TOOL_CONFIRMATION_INVALID);
            }
            ToolExecutionAuditEntity audit = toolExecutionAuditMapper.findById(token.getAuditId());
            if (audit == null) {
                return invalidConfirmationResponse(token, null, normalized, ControlErrorCode.TOOL_CONFIRMATION_INVALID);
            }
            ToolApiModels.ExecuteToolRequest originalRequest = parseAuditRequest(audit);
            if (!Objects.equals(token.getSessionId(), normalized.sessionId())
                    || !Objects.equals(audit.getSessionId(), normalized.sessionId())
                    || !callerContextMatches(token.getCallerContextJson(), normalized.callerContext())) {
                return invalidConfirmationResponse(token, originalRequest, normalized, ControlErrorCode.TOOL_CONFIRMATION_INVALID);
            }
            long now = System.currentTimeMillis();
            if (token.getExpiresAt() < now) {
                token.setStatus(TOKEN_STATUS_EXPIRED);
                token.setUpdatedAt(now);
                toolConfirmationTokenMapper.update(token);
                return invalidConfirmationResponse(token, originalRequest, normalized, ControlErrorCode.TOOL_CONFIRMATION_INVALID);
            }
            if (!TOKEN_STATUS_PENDING.equals(token.getStatus())) {
                return invalidConfirmationResponse(token, originalRequest, normalized, ControlErrorCode.TOOL_CONFIRMATION_INVALID);
            }
            if ("reject".equalsIgnoreCase(normalized.decision())) {
                token.setStatus(TOKEN_STATUS_REJECTED);
                token.setUsedAt(now);
                token.setUpdatedAt(now);
                toolConfirmationTokenMapper.update(token);
                ToolApiModels.ExecuteToolResponse response = failedResponse(
                        originalRequest,
                        audit,
                        CONFIRMATION_REJECTED,
                        false,
                        emptyEntityRefs()
                );
                updateAudit(audit, STATUS_REJECTED, response);
                return response;
            }
            ToolDefinition<?> definition = toolDefinitions.get(token.getToolName());
            if (definition == null) {
                return invalidConfirmationResponse(token, originalRequest, normalized, ControlErrorCode.TOOL_NOT_FOUND);
            }
            token.setStatus(TOKEN_STATUS_APPROVED);
            token.setUpdatedAt(now);
            toolConfirmationTokenMapper.update(token);
            ToolApiModels.ExecuteToolResponse response = executeAuditedRequest(audit, originalRequest, definition);
            token.setStatus(TOKEN_STATUS_USED);
            token.setUsedAt(System.currentTimeMillis());
            token.setUpdatedAt(token.getUsedAt());
            toolConfirmationTokenMapper.update(token);
            return response;
        } catch (ResponseStatusException exception) {
            return invalidResolveRequestResponse(request, mapErrorCode(exception));
        }
    }

    public ToolApiModels.AuditQueryResponse queryAudits(ToolApiModels.AuditQueryRequest request) {
        List<ToolExecutionAuditEntity> audits;
        if (request.sessionId() != null && !request.sessionId().isBlank()
                && request.runId() != null && !request.runId().isBlank()) {
            audits = toolExecutionAuditMapper.findBySessionIdAndRunId(request.sessionId(), request.runId());
        } else if (request.attemptId() != null && !request.attemptId().isBlank()) {
            audits = toolExecutionAuditMapper.findByAttemptId(request.attemptId());
        } else if (request.runId() != null && !request.runId().isBlank()) {
            audits = toolExecutionAuditMapper.findByRunId(request.runId());
        } else if (request.sessionId() != null && !request.sessionId().isBlank()) {
            audits = toolExecutionAuditMapper.findBySessionId(request.sessionId());
        } else {
            audits = toolExecutionAuditMapper.listAll();
        }
        if (audits == null) {
            audits = List.of();
        }
        List<ToolApiModels.AuditTimelineEntry> entries = audits.stream()
                .filter(audit -> matchesAuditQuery(audit, request))
                .sorted(java.util.Comparator.comparingLong(ToolExecutionAuditEntity::getCreatedAt))
                .map(this::toAuditTimelineEntry)
                .toList();
        return new ToolApiModels.AuditQueryResponse(PROTOCOL_VERSION, entries);
    }

    private ToolApiModels.ExecuteToolResponse handleExistingAudit(ToolExecutionAuditEntity existingAudit,
                                                                  ToolApiModels.ExecuteToolRequest request,
                                                                  String requestIdentityJson) {
        if (!Objects.equals(existingAudit.getSessionId(), request.sessionId())
                || !Objects.equals(existingAudit.getToolName(), request.tool())
                || !Objects.equals(existingAudit.getRequestJson(), requestIdentityJson)) {
            return failedResponse(request, existingAudit, ControlErrorCode.TOOL_REQUEST_INVALID, false, parseEntityRefs(existingAudit.getEntityRefsJson()));
        }
        return readStoredResponse(existingAudit, request);
    }

    private ToolApiModels.ExecuteToolResponse handleNewRequest(ToolApiModels.ExecuteToolRequest request,
                                                               String requestIdentityJson) {
        ToolDefinition<?> definition = toolDefinitions.get(request.tool());
        if (definition == null) {
            return failedResponse(request, null, ControlErrorCode.TOOL_NOT_FOUND, false, emptyEntityRefs());
        }
        ToolExecutionAuditEntity audit = createAudit(request, requestIdentityJson, jsonCodec.write(request.callerContext()), definition);
        if (definition.requiresApproval()) {
            ToolConfirmationTokenEntity confirmation = createConfirmation(request, audit);
            ToolApiModels.ExecuteToolResponse response = approvalRequiredResponse(request, audit, confirmation);
            updateAudit(audit, STATUS_APPROVAL_REQUIRED, response);
            return response;
        }
        return executeAuditedRequest(audit, request, definition);
    }

    private Map<String, ToolDefinition<?>> buildDefinitions() {
        Map<String, ToolDefinition<?>> definitions = new LinkedHashMap<>();
        registerDiscoveryTools(definitions);
        registerPlanningTools(definitions);
        registerExecutionTools(definitions);
        return Map.copyOf(definitions);
    }

    private void registerDiscoveryTools(Map<String, ToolDefinition<?>> definitions) {
        register(definitions, definition(
                "list_devices",
                "List Devices",
                "List registered devices and their current runtime state.",
                RISK_DISCOVERY,
                noArgsSchema(),
                arraySchema(deviceSchema()),
                NoArgs.class,
                args -> result(adminApiService.listDevices())
        ));
        register(definitions, definition(
                "get_device",
                "Get Device",
                "Get a single device by id.",
                RISK_DISCOVERY,
                idArgsSchema("deviceId"),
                deviceSchema(),
                DeviceIdArgs.class,
                args -> result(adminApiService.getDevice(requireNonBlank(args.deviceId(), ControlErrorCode.TOOL_ARGUMENT_INVALID)))
        ));
        register(definitions, definition(
                "list_device_attempts",
                "List Device Attempts",
                "List recent attempts for a device.",
                RISK_DISCOVERY,
                idArgsSchema("deviceId"),
                arraySchema(attemptSummarySchema()),
                DeviceIdArgs.class,
                args -> result(adminApiService.getDeviceAttempts(requireNonBlank(args.deviceId(), ControlErrorCode.TOOL_ARGUMENT_INVALID)))
        ));
        register(definitions, definition(
                "list_device_pools",
                "List Device Pools",
                "List device pools available for experiment runs.",
                RISK_DISCOVERY,
                noArgsSchema(),
                arraySchema(devicePoolSchema()),
                NoArgs.class,
                args -> result(experimentRunService.listDevicePools())
        ));
        register(definitions, definition(
                "get_device_pool",
                "Get Device Pool",
                "Get one device pool by id.",
                RISK_DISCOVERY,
                idArgsSchema("poolId"),
                devicePoolSchema(),
                PoolIdArgs.class,
                args -> result(experimentRunService.getDevicePool(requireNonBlank(args.poolId(), ControlErrorCode.TOOL_ARGUMENT_INVALID)))
        ));
        register(definitions, definition(
                "list_runs",
                "List Runs",
                "List experiment runs.",
                RISK_DISCOVERY,
                noArgsSchema(),
                arraySchema(runSummarySchema()),
                NoArgs.class,
                args -> result(experimentRunService.listRuns())
        ));
        register(definitions, definition(
                "get_run",
                "Get Run",
                "Get one experiment run with targets.",
                RISK_DISCOVERY,
                idArgsSchema("runId"),
                runDetailSchema(),
                RunIdArgs.class,
                args -> result(experimentRunService.getRun(requireNonBlank(args.runId(), ControlErrorCode.TOOL_ARGUMENT_INVALID)))
        ));
        register(definitions, definition(
                "get_run_governance_snapshot",
                "Get Run Governance Snapshot",
                "Get a run-governance snapshot tailored for agent observation and decision making.",
                RISK_DISCOVERY,
                idArgsSchema("runId"),
                runGovernanceSnapshotSchema(),
                RunIdArgs.class,
                args -> result(buildRunGovernanceSnapshot(requireNonBlank(args.runId(), ControlErrorCode.TOOL_ARGUMENT_INVALID)))
        ));
        register(definitions, definition(
                "get_run_blockage_summary",
                "Get Run Blockage Summary",
                "Classify the current blockage state for a run.",
                RISK_DISCOVERY,
                idArgsSchema("runId"),
                runBlockageSummarySchema(),
                RunIdArgs.class,
                args -> result(buildRunBlockageSummary(requireNonBlank(args.runId(), ControlErrorCode.TOOL_ARGUMENT_INVALID)))
        ));
        register(definitions, definition(
                "get_run_recovery_options",
                "Get Run Recovery Options",
                "Return governed recovery options for a run without changing state.",
                RISK_DISCOVERY,
                idArgsSchema("runId"),
                runRecoveryOptionsSchema(),
                RunIdArgs.class,
                args -> result(buildRunRecoveryOptions(requireNonBlank(args.runId(), ControlErrorCode.TOOL_ARGUMENT_INVALID)))
        ));
        register(definitions, definition(
                "get_run_lineage_snapshot",
                "Get Run Lineage Snapshot",
                "Get a bundled run-centric lineage snapshot for agent observation and replay.",
                RISK_DISCOVERY,
                idArgsSchema("runId"),
                runLineageSnapshotSchema(),
                RunIdArgs.class,
                args -> result(buildRunLineageSnapshot(requireNonBlank(args.runId(), ControlErrorCode.TOOL_ARGUMENT_INVALID)))
        ));
        register(definitions, definition(
                "get_attempt_diagnosis_bundle",
                "Get Attempt Diagnosis Bundle",
                "Get a normalized diagnosis bundle for one attempt.",
                RISK_DISCOVERY,
                idArgsSchema("attemptId"),
                attemptDiagnosisBundleSchema(),
                AttemptIdArgs.class,
                args -> result(buildAttemptDiagnosisBundle(requireNonBlank(args.attemptId(), ControlErrorCode.TOOL_ARGUMENT_INVALID)))
        ));
        register(definitions, definition(
                "get_recovery_guidance_context",
                "Get Recovery Guidance Context",
                "Get an agent-native recovery guidance context for one run.",
                RISK_DISCOVERY,
                idArgsSchema("runId"),
                recoveryGuidanceContextSchema(),
                RunIdArgs.class,
                args -> result(buildRecoveryGuidanceContext(requireNonBlank(args.runId(), ControlErrorCode.TOOL_ARGUMENT_INVALID)))
        ));
        register(definitions, definition(
                "list_run_targets",
                "List Run Targets",
                "List targets that belong to a run.",
                RISK_DISCOVERY,
                idArgsSchema("runId"),
                arraySchema(runTargetSchema()),
                RunIdArgs.class,
                args -> result(experimentRunService.listRunTargets(requireNonBlank(args.runId(), ControlErrorCode.TOOL_ARGUMENT_INVALID)))
        ));
        register(definitions, definition(
                "get_run_target",
                "Get Run Target",
                "Get one run target by id.",
                RISK_DISCOVERY,
                idArgsSchema("runTargetId"),
                runTargetSchema(),
                RunTargetIdArgs.class,
                args -> result(experimentRunService.getRunTarget(requireNonBlank(args.runTargetId(), ControlErrorCode.TOOL_ARGUMENT_INVALID)))
        ));
        register(definitions, definition(
                "list_tasks",
                "List Tasks",
                "List tasks.",
                RISK_DISCOVERY,
                noArgsSchema(),
                arraySchema(taskSchema()),
                NoArgs.class,
                args -> result(adminApiService.listTasks())
        ));
        register(definitions, definition(
                "get_task",
                "Get Task",
                "Get one task by id.",
                RISK_DISCOVERY,
                idArgsSchema("taskId"),
                taskSchema(),
                TaskIdArgs.class,
                args -> result(adminApiService.getTask(requireNonBlank(args.taskId(), ControlErrorCode.TOOL_ARGUMENT_INVALID)))
        ));
        register(definitions, definition(
                "list_attempts",
                "List Attempts",
                "List attempts.",
                RISK_DISCOVERY,
                noArgsSchema(),
                arraySchema(attemptSummarySchema()),
                NoArgs.class,
                args -> result(adminApiService.listAttempts())
        ));
        register(definitions, definition(
                "get_attempt",
                "Get Attempt",
                "Get an attempt together with events and artifact handles.",
                RISK_DISCOVERY,
                idArgsSchema("attemptId"),
                attemptDetailSchema(),
                AttemptIdArgs.class,
                args -> result(buildAttemptDetail(requireNonBlank(args.attemptId(), ControlErrorCode.TOOL_ARGUMENT_INVALID)))
        ));
        register(definitions, definition(
                "get_attempt_events",
                "Get Attempt Events",
                "Get events recorded for an attempt.",
                RISK_DISCOVERY,
                idArgsSchema("attemptId"),
                arraySchema(runEventSchema()),
                AttemptIdArgs.class,
                args -> result(adminApiService.getAttemptEvents(requireNonBlank(args.attemptId(), ControlErrorCode.TOOL_ARGUMENT_INVALID)))
        ));
        register(definitions, definition(
                "get_attempt_artifacts",
                "Get Attempt Artifacts",
                "Get artifact metadata and resource handles for an attempt.",
                RISK_DISCOVERY,
                idArgsSchema("attemptId"),
                arraySchema(attemptArtifactSchema()),
                AttemptIdArgs.class,
                args -> result(buildAttemptArtifacts(requireNonBlank(args.attemptId(), ControlErrorCode.TOOL_ARGUMENT_INVALID)))
        ));
    }

    private void registerPlanningTools(Map<String, ToolDefinition<?>> definitions) {
        register(definitions, definition(
                "get_run_planning_catalog",
                "Get Run Planning Catalog",
                "Get available pools, profiles, and default run policy for AI planning.",
                RISK_ADVISORY,
                noArgsSchema(),
                runPlanningCatalogSchema(),
                NoArgs.class,
                args -> {
                    Phase3AiModels.RunPlanningContext context = runPlanningContextBuilder.build("", Map.of());
                    return result(new RunPlanningCatalogResult(
                            context.availableDevicePools(),
                            context.availableProfiles(),
                            context.defaultRunPolicy(),
                            context.allowedTaskTypes()
                    ));
                }
        ));
        register(definitions, definition(
                "draft_run_plan",
                "Draft Run Plan",
                "Create an AI-generated run draft from a goal and constraints.",
                RISK_ADVISORY,
                draftRunPlanArgsSchema(),
                runPlanDraftSchema(),
                DraftRunPlanArgs.class,
                args -> result(aiRunPlanningService.createRunPlan(new AiRunPlanApiModels.CreateRunPlanRequest(
                        requireNonBlank(args.goal(), ControlErrorCode.TOOL_ARGUMENT_INVALID),
                        mapOrEmpty(args.constraints())
                )))
        ));
        register(definitions, definition(
                "get_run_plan",
                "Get Run Plan",
                "Get a drafted run plan by request id.",
                RISK_ADVISORY,
                idArgsSchema("planRequestId"),
                runPlanSchema(),
                PlanRequestIdArgs.class,
                args -> result(aiRunPlanningService.getRunPlan(requireNonBlank(args.planRequestId(), ControlErrorCode.TOOL_ARGUMENT_INVALID)))
        ));
        register(definitions, definition(
                "materialize_run_plan",
                "Materialize Run Plan",
                "Materialize a validated run plan into a run.",
                RISK_EXECUTION,
                materializeRunPlanArgsSchema(),
                runDetailSchema(),
                MaterializeRunPlanArgs.class,
                args -> result(aiRunPlanningService.materializeRunPlan(
                        requireNonBlank(args.planRequestId(), ControlErrorCode.TOOL_ARGUMENT_INVALID),
                        args.createdBy()
                ))
        ));
        register(definitions, definition(
                "generate_run_summary",
                "Generate Run Summary",
                "Generate an AI summary for a run.",
                RISK_ADVISORY,
                idArgsSchema("runId"),
                runSummaryResultSchema(),
                RunIdArgs.class,
                args -> result(aiRunSummaryService.createRunSummary(requireNonBlank(args.runId(), ControlErrorCode.TOOL_ARGUMENT_INVALID)))
        ));
        register(definitions, definition(
                "get_latest_run_summary",
                "Get Latest Run Summary",
                "Get the latest AI summary for a run.",
                RISK_ADVISORY,
                idArgsSchema("runId"),
                runSummaryResultSchema(),
                RunIdArgs.class,
                args -> result(aiRunSummaryService.getLatestRunSummary(requireNonBlank(args.runId(), ControlErrorCode.TOOL_ARGUMENT_INVALID)))
        ));
        register(definitions, definition(
                "get_run_summary",
                "Get Run Summary",
                "Get one AI summary by summary id.",
                RISK_ADVISORY,
                idArgsSchema("summaryId"),
                runSummaryResultSchema(),
                SummaryIdArgs.class,
                args -> result(aiRunSummaryService.getRunSummary(requireNonBlank(args.summaryId(), ControlErrorCode.TOOL_ARGUMENT_INVALID)))
        ));
        register(definitions, definition(
                "generate_failure_triage",
                "Generate Failure Triage",
                "Generate AI failure triage for a run target.",
                RISK_ADVISORY,
                idArgsSchema("runTargetId"),
                failureTriageSchema(),
                RunTargetIdArgs.class,
                args -> result(aiFailureTriageService.createFailureTriage(requireNonBlank(args.runTargetId(), ControlErrorCode.TOOL_ARGUMENT_INVALID)))
        ));
        register(definitions, definition(
                "get_latest_failure_triage",
                "Get Latest Failure Triage",
                "Get the latest AI failure triage for a run target.",
                RISK_ADVISORY,
                idArgsSchema("runTargetId"),
                failureTriageSchema(),
                RunTargetIdArgs.class,
                args -> result(aiFailureTriageService.getLatestFailureTriage(requireNonBlank(args.runTargetId(), ControlErrorCode.TOOL_ARGUMENT_INVALID)))
        ));
        register(definitions, definition(
                "get_failure_triage",
                "Get Failure Triage",
                "Get one AI failure triage result by id.",
                RISK_ADVISORY,
                idArgsSchema("triageResultId"),
                failureTriageSchema(),
                TriageResultIdArgs.class,
                args -> result(aiFailureTriageService.getFailureTriage(requireNonBlank(args.triageResultId(), ControlErrorCode.TOOL_ARGUMENT_INVALID)))
        ));
    }

    private void registerExecutionTools(Map<String, ToolDefinition<?>> definitions) {
        register(definitions, definition(
                "propose_governed_action",
                "Propose Governed Action",
                "Persist and confirm a governed decision proposal before executing the underlying action.",
                RISK_EXECUTION,
                proposeGovernedActionArgsSchema(),
                governedProposalResultSchema(),
                ProposeGovernedActionArgs.class,
                args -> result(executeGovernedProposal(args))
        ));
        register(definitions, definition(
                "create_device_pool",
                "Create Device Pool",
                "Create a new device pool.",
                RISK_EXECUTION,
                createDevicePoolArgsSchema(),
                devicePoolSchema(),
                CreateDevicePoolArgs.class,
                args -> result(experimentRunService.createDevicePool(new AdminApiModels.CreateDevicePoolRequest(
                        requireNonBlank(args.name(), ControlErrorCode.TOOL_ARGUMENT_INVALID),
                        args.description(),
                        args.hostGroup(),
                        listOrEmpty(args.deviceIds()),
                        listOrEmpty(args.requiredTags()),
                        listOrEmpty(args.excludedTags()),
                        args.createdBy()
                )))
        ));
        register(definitions, definition(
                "create_task",
                "Create Task",
                "Create a queued task.",
                RISK_EXECUTION,
                createTaskArgsSchema(),
                taskSchema(),
                CreateTaskArgs.class,
                args -> result(adminApiService.createTask(new AdminApiModels.CreateTaskRequest(
                        requireNonBlank(args.taskType(), ControlErrorCode.TOOL_ARGUMENT_INVALID),
                        requireNonBlank(args.profilePackage(), ControlErrorCode.TOOL_ARGUMENT_INVALID),
                        mapOrEmpty(args.taskPayload()),
                        objectMapper.convertValue(args.runConfig(), ExecutorApiModels.RunConfig.class),
                        objectMapper.convertValue(args.artifactPolicy(), ExecutorApiModels.ArtifactPolicy.class),
                        args.priority(),
                        listOrEmpty(args.labels()),
                        args.source(),
                        args.createdBy(),
                        args.idempotencyKey()
                )))
        ));
        register(definitions, definition(
                "create_single_device_run",
                "Create Single Device Run",
                "Create a new experiment run targeted to a single device.",
                RISK_EXECUTION,
                createSingleDeviceRunArgsSchema(),
                runDetailSchema(),
                CreateSingleDeviceRunArgs.class,
                args -> result(experimentRunService.createSingleDeviceRun(new AdminApiModels.CreateSingleDeviceRunRequest(
                        requireNonBlank(args.name(), ControlErrorCode.TOOL_ARGUMENT_INVALID),
                        args.description(),
                        requireNonBlank(args.deviceId(), ControlErrorCode.TOOL_ARGUMENT_INVALID),
                        requireNonBlank(args.taskType(), ControlErrorCode.TOOL_ARGUMENT_INVALID),
                        requireNonBlank(args.profilePackage(), ControlErrorCode.TOOL_ARGUMENT_INVALID),
                        mapOrEmpty(args.taskPayload()),
                        objectMapper.convertValue(args.runConfig(), ExecutorApiModels.RunConfig.class),
                        objectMapper.convertValue(args.artifactPolicy(), ExecutorApiModels.ArtifactPolicy.class),
                        args.priority(),
                        listOrEmpty(args.labels()),
                        args.source(),
                        args.createdBy(),
                        args.maxRetriesPerDevice(),
                        args.queueTimeoutMs()
                )))
        ));
        register(definitions, definition(
                "create_run",
                "Create Run",
                "Create a new experiment run.",
                RISK_EXECUTION,
                createRunArgsSchema(),
                runDetailSchema(),
                CreateRunArgs.class,
                args -> result(experimentRunService.createRun(new AdminApiModels.CreateExperimentRunRequest(
                        requireNonBlank(args.name(), ControlErrorCode.TOOL_ARGUMENT_INVALID),
                        args.description(),
                        requireNonBlank(args.devicePoolId(), ControlErrorCode.TOOL_ARGUMENT_INVALID),
                        requireNonBlank(args.taskType(), ControlErrorCode.TOOL_ARGUMENT_INVALID),
                        requireNonBlank(args.profilePackage(), ControlErrorCode.TOOL_ARGUMENT_INVALID),
                        mapOrEmpty(args.taskPayload()),
                        objectMapper.convertValue(args.runConfig(), ExecutorApiModels.RunConfig.class),
                        objectMapper.convertValue(args.artifactPolicy(), ExecutorApiModels.ArtifactPolicy.class),
                        args.priority(),
                        listOrEmpty(args.labels()),
                        args.source(),
                        args.createdBy(),
                        args.maxRetriesPerDevice(),
                        args.queueTimeoutMs()
                )))
        ));
        register(definitions, definition(
                "cancel_run",
                "Cancel Run",
                "Cancel a run using the existing run cancellation semantics.",
                RISK_EXECUTION,
                idArgsSchema("runId"),
                runActionSchema(),
                RunIdArgs.class,
                args -> {
                    String runId = requireNonBlank(args.runId(), ControlErrorCode.TOOL_ARGUMENT_INVALID);
                    experimentRunService.cancelRun(runId);
                    return result(new RunActionResult(runId, true, experimentRunService.getRun(runId).run().status()));
                }
        ));
        register(definitions, definition(
                "cancel_task",
                "Cancel Task",
                "Cancel a task.",
                RISK_EXECUTION,
                idArgsSchema("taskId"),
                taskActionSchema(),
                TaskIdArgs.class,
                args -> {
                    String taskId = requireNonBlank(args.taskId(), ControlErrorCode.TOOL_ARGUMENT_INVALID);
                    adminApiService.cancelTask(taskId);
                    return result(new TaskActionResult(taskId, true, adminApiService.getTask(taskId).status()));
                }
        ));
        register(definitions, definition(
                "resume_device",
                "Resume Device",
                "Resume a device from its current runtime state.",
                RISK_EXECUTION,
                idArgsSchema("deviceId"),
                deviceSchema(),
                DeviceIdArgs.class,
                args -> result(adminApiService.resumeDevice(requireNonBlank(args.deviceId(), ControlErrorCode.TOOL_ARGUMENT_INVALID)))
        ));
        register(definitions, definition(
                "send_device_command",
                "Send Device Command",
                "Send an operational command to a device.",
                RISK_EXECUTION,
                sendDeviceCommandArgsSchema(),
                commandAcceptedSchema(),
                SendDeviceCommandArgs.class,
                args -> result(adminApiService.enqueueCommand(
                        requireNonBlank(args.deviceId(), ControlErrorCode.TOOL_ARGUMENT_INVALID),
                        new AdminApiModels.CreateCommandRequest(
                                requireNonBlank(args.type(), ControlErrorCode.TOOL_ARGUMENT_INVALID),
                                args.attemptId(),
                                args.expireInMs()
                        )
                ))
        ));
    }

    private AttemptDetailResult buildAttemptDetail(String attemptId) {
        AdminApiModels.AttemptDetailResponse detail = adminApiService.getAttempt(attemptId);
        return new AttemptDetailResult(
                detail.attempt(),
                detail.events(),
                buildAttemptArtifacts(attemptId)
        );
    }

    private List<ToolApiModels.AttemptArtifactResource> buildAttemptArtifacts(String attemptId) {
        return adminApiService.getAttemptArtifacts(attemptId).stream()
                .map(artifact -> new ToolApiModels.AttemptArtifactResource(
                        artifact.artifactId(),
                        artifact.attemptId(),
                        artifact.taskId(),
                        artifact.runId(),
                        artifact.artifactType(),
                        artifact.fileName(),
                        artifact.mimeType(),
                        artifact.sizeBytes(),
                        artifact.createdAt(),
                        toolResourceService.createAttemptArtifactHandle(artifact)
                ))
                .toList();
    }

    private RunGovernanceSnapshotResult buildRunGovernanceSnapshot(String runId) {
        AdminApiModels.ExperimentRunDetailResponse detail = experimentRunService.getRun(runId);
        List<AdminApiModels.AttemptSummary> attempts = adminApiService.listAttempts().stream()
                .filter(attempt -> Objects.equals(attempt.runId(), runId))
                .toList();
        RunAttemptCounts attemptCounts = new RunAttemptCounts(
                attempts.size(),
                (int) attempts.stream().filter(attempt -> "RUNNING".equalsIgnoreCase(attempt.status())).count(),
                (int) attempts.stream().filter(attempt -> "FAILED".equalsIgnoreCase(attempt.status())).count(),
                (int) attempts.stream().filter(attempt -> "SUCCEEDED".equalsIgnoreCase(attempt.status())).count()
        );
        List<String> latestAttemptIds = detail.targets().stream()
                .map(AdminApiModels.ExperimentRunTargetResponse::latestAttemptId)
                .filter(Objects::nonNull)
                .distinct()
                .toList();
        List<String> blockers = detail.targets().stream()
                .map(target -> {
                    if (target.failureReason() != null && !target.failureReason().isBlank()) {
                        return target.failureReason();
                    }
                    if ("RETRY_PENDING".equalsIgnoreCase(target.status())) {
                        return "RETRY_PENDING";
                    }
                    return null;
                })
                .filter(Objects::nonNull)
                .distinct()
                .toList();
        return new RunGovernanceSnapshotResult(
                detail.run().runId(),
                detail.run().status(),
                detail.run().counts(),
                attemptCounts,
                latestAttemptIds,
                blockers,
                detail.run().updatedAt()
        );
    }

    private RunBlockageSummaryResult buildRunBlockageSummary(String runId) {
        AdminApiModels.ExperimentRunDetailResponse detail = experimentRunService.getRun(runId);
        boolean singleDeviceRun = detail.run().poolId() == null;
        boolean queueTimeout = detail.targets().stream().anyMatch(target ->
                "RETRY_PENDING".equalsIgnoreCase(target.status()) || "QUEUE_TIMEOUT".equalsIgnoreCase(target.failureReason()));
        if (queueTimeout) {
            return new RunBlockageSummaryResult(
                    runId,
                    "queue_timeout",
                    "The run is stuck with a retry-pending target after queue timeout.",
                    true,
                    List.of(),
                    "cancel_run"
            );
        }
        if (detail.run().cancelRequested() && !"CANCELLED".equalsIgnoreCase(detail.run().status())) {
            return new RunBlockageSummaryResult(
                    runId,
                    "cancellation_in_progress",
                    "Cancellation has been requested and the run is still draining work.",
                    false,
                    List.of(),
                    "continue_observe"
            );
        }
        boolean terminalFailure = detail.run().counts().failed() > 0
                || "FAILED".equalsIgnoreCase(detail.run().status())
                || "TERMINAL".equalsIgnoreCase(detail.run().status())
                || "FAILED".equalsIgnoreCase(detail.run().finalState());
        if (terminalFailure) {
            return new RunBlockageSummaryResult(
                    runId,
                    "terminal_failure",
                    "The run reached a terminal failed state and needs governed recovery.",
                    true,
                    List.of(),
                    singleDeviceRun ? "create_single_device_run" : "create_run"
            );
        }
        return new RunBlockageSummaryResult(
                runId,
                "not_blocked",
                "The run is progressing normally.",
                false,
                List.of(),
                "continue_observe"
        );
    }

    private RunRecoveryOptionsResult buildRunRecoveryOptions(String runId) {
        AdminApiModels.ExperimentRunDetailResponse detail = experimentRunService.getRun(runId);
        RunBlockageSummaryResult blockageSummary = buildRunBlockageSummary(runId);
        String recommendedAction = blockageSummary.recommendedAction();
        List<String> allowedActions;
        boolean requiresApproval;
        if ("cancel_run".equals(recommendedAction)) {
            allowedActions = List.of("cancel_run", "continue_observe");
            requiresApproval = true;
        } else if ("create_run".equals(recommendedAction) || "create_single_device_run".equals(recommendedAction)) {
            allowedActions = List.of(recommendedAction, "continue_observe");
            requiresApproval = true;
        } else {
            allowedActions = List.of("continue_observe");
            requiresApproval = false;
        }
        String explanation = blockageSummary.blockageReason();
        if ("continue_observe".equals(recommendedAction) && detail.run().cancelRequested()) {
            explanation = "Cancellation is already in progress. Continue observing until the run reaches a terminal state.";
        }
        return new RunRecoveryOptionsResult(
                runId,
                allowedActions,
                recommendedAction,
                !blockageSummary.missingInputs().isEmpty(),
                requiresApproval,
                explanation
        );
    }

    private RunLineageSnapshotResult buildRunLineageSnapshot(String runId) {
        AdminApiModels.ExperimentRunDetailResponse detail = experimentRunService.getRun(runId);
        List<AdminApiModels.AttemptSummary> attempts = adminApiService.listAttempts().stream()
                .filter(attempt -> Objects.equals(attempt.runId(), runId))
                .toList();
        List<ToolApiModels.AttemptArtifactResource> artifacts = detail.targets().stream()
                .map(AdminApiModels.ExperimentRunTargetResponse::latestAttemptId)
                .filter(Objects::nonNull)
                .distinct()
                .flatMap(attemptId -> buildAttemptArtifacts(attemptId).stream())
                .limit(5)
                .toList();
        List<ToolApiModels.AuditTimelineEntry> auditRefs = queryAudits(new ToolApiModels.AuditQueryRequest(
                null,
                null,
                null,
                runId,
                null,
                null
        )).entries();
        return new RunLineageSnapshotResult(
                runId,
                detail,
                detail.targets(),
                attempts,
                artifacts,
                auditRefs,
                buildRunBlockageSummary(runId).missingInputs().isEmpty()
                        ? buildRunGovernanceSnapshot(runId).blockers()
                        : List.of("MISSING_INPUT"),
                buildRunRecoveryOptions(runId).allowedActions()
        );
    }

    private AttemptDiagnosisBundleResult buildAttemptDiagnosisBundle(String attemptId) {
        AttemptDetailResult detail = buildAttemptDetail(attemptId);
        List<String> failureSignals = detail.events().stream()
                .map(AdminApiModels.RunEventResponse::code)
                .filter(Objects::nonNull)
                .filter(code -> !code.isBlank())
                .distinct()
                .toList();
        String artifactSummary = detail.artifacts().isEmpty()
                ? "No artifacts are currently available."
                : "Artifacts available: " + detail.artifacts().stream()
                .map(ToolApiModels.AttemptArtifactResource::fileName)
                .limit(3)
                .reduce((left, right) -> left + ", " + right)
                .orElse("unknown");
        String summary = "Attempt `%s` is `%s`. %s".formatted(
                detail.attempt().attemptId(),
                detail.attempt().status(),
                artifactSummary
        );
        return new AttemptDiagnosisBundleResult(
                detail.attempt().attemptId(),
                detail.attempt().status(),
                detail.events(),
                artifactSummary,
                failureSignals,
                Map.of("confidence", failureSignals.isEmpty() ? 0.52 : 0.84),
                summary
        );
    }

    private RecoveryGuidanceContextResult buildRecoveryGuidanceContext(String runId) {
        RunRecoveryOptionsResult recoveryOptions = buildRunRecoveryOptions(runId);
        return new RecoveryGuidanceContextResult(
                "run",
                runId,
                recoveryOptions.allowedActions(),
                recoveryOptions.recommendedAction(),
                recoveryOptions.requiresApproval(),
                recoveryOptions.requiresUserInput() ? List.of("runId") : List.of(),
                List.of("runId"),
                List.of("confirmation_pending", "user_input_required"),
                "Stop if the run context changes or the task starts waiting for confirmation.",
                "Alternative paths are weaker because they either avoid the current blocker or require unnecessary risk.",
                recoveryOptions.explanation(),
                recoveryOptions.requiresApproval() ? 0.88 : 0.73
        );
    }

    private GovernedProposalResult executeGovernedProposal(ProposeGovernedActionArgs args) {
        String proposalId = requireNonBlank(args.proposalId(), ControlErrorCode.TOOL_ARGUMENT_INVALID);
        String actionToolName = requireNonBlank(args.actionToolName(), ControlErrorCode.TOOL_ARGUMENT_INVALID);
        if ("propose_governed_action".equals(actionToolName)) {
            throw ControlApiExceptions.badRequest(ControlErrorCode.TOOL_PROPOSAL_INVALID);
        }
        ToolDefinition<?> actionDefinition = toolDefinitions.get(actionToolName);
        if (actionDefinition == null) {
            throw ControlApiExceptions.badRequest(ControlErrorCode.TOOL_NOT_FOUND);
        }
        if (!actionDefinition.requiresApproval()) {
            throw ControlApiExceptions.badRequest(ControlErrorCode.TOOL_PROPOSAL_INVALID);
        }
        validateGovernedProposalPreconditions(args, actionDefinition);
        ToolResult executedAction = invokeUntyped(actionDefinition, mapOrEmpty(args.arguments()));
        return new GovernedProposalResult(
                proposalId,
                "executed",
                actionToolName,
                args.targetKind(),
                args.targetId(),
                mapOrEmpty(args.preconditions()),
                args.rationale(),
                "matched",
                System.currentTimeMillis(),
                executedAction.result()
        );
    }

    private void validateGovernedProposalPreconditions(ProposeGovernedActionArgs args, ToolDefinition<?> actionDefinition) {
        String actionToolName = actionDefinition.name();
        Map<String, Object> preconditions = mapOrEmpty(args.preconditions());
        if ("cancel_run".equals(actionToolName)) {
            String runId = requireNonBlank(
                    valueAsString(firstPresent(mapOrEmpty(args.arguments()), "runId", "run_id", "targetId", "target_id")),
                    ControlErrorCode.TOOL_ARGUMENT_INVALID
            );
            AdminApiModels.ExperimentRunDetailResponse run = experimentRunService.getRun(runId);
            String expectedRunId = valueAsString(firstPresent(preconditions, "runId", "run_id"));
            if (expectedRunId != null && !Objects.equals(expectedRunId, run.run().runId())) {
                throw ControlApiExceptions.badRequest(ControlErrorCode.TOOL_PROPOSAL_PRECONDITION_FAILED);
            }
            String expectedStatus = valueAsString(firstPresent(preconditions, "status", "runStatus"));
            if (expectedStatus != null && !Objects.equals(expectedStatus, run.run().status())) {
                throw ControlApiExceptions.badRequest(ControlErrorCode.TOOL_PROPOSAL_PRECONDITION_FAILED);
            }
            if ("CANCELLED".equalsIgnoreCase(run.run().status()) || Boolean.TRUE.equals(run.run().cancelRequested())) {
                throw ControlApiExceptions.badRequest(ControlErrorCode.TOOL_PROPOSAL_PRECONDITION_FAILED);
            }
            return;
        }
        if ("create_single_device_run".equals(actionToolName)) {
            String deviceId = requireNonBlank(
                    valueAsString(firstPresent(mapOrEmpty(args.arguments()), "deviceId", "device_id")),
                    ControlErrorCode.TOOL_ARGUMENT_INVALID
            );
            AdminApiModels.DeviceResponse device = adminApiService.getDevice(deviceId);
            String expectedDeviceId = valueAsString(firstPresent(preconditions, "deviceId", "device_id", "targetDeviceId"));
            if (expectedDeviceId != null && !Objects.equals(expectedDeviceId, device.deviceId())) {
                throw ControlApiExceptions.badRequest(ControlErrorCode.TOOL_PROPOSAL_PRECONDITION_FAILED);
            }
            if (!device.online()) {
                throw ControlApiExceptions.badRequest(ControlErrorCode.TOOL_PROPOSAL_PRECONDITION_FAILED);
            }
        }
    }

    private <A> ToolResult invoke(ToolDefinition<A> definition, Map<String, Object> arguments) {
        A typedArguments = objectMapper.convertValue(arguments == null ? Map.of() : arguments, definition.argumentsType());
        return definition.executor().execute(typedArguments);
    }

    @SuppressWarnings("unchecked")
    private ToolResult invokeUntyped(ToolDefinition<?> definition, Map<String, Object> arguments) {
        return invoke((ToolDefinition<Object>) definition, arguments);
    }

    private ToolApiModels.ExecuteToolResponse executeAuditedRequest(ToolExecutionAuditEntity audit,
                                                                    ToolApiModels.ExecuteToolRequest request,
                                                                    ToolDefinition<?> definition) {
        try {
            ToolResult toolResult = invoke(definition, request.arguments());
            ToolApiModels.EntityRefs entityRefs = extractEntityRefs(objectMapper.convertValue(toolResult.result(), Object.class));
            ToolApiModels.ExecuteToolResponse response = completedResponse(request, audit, toolResult, entityRefs);
            updateAudit(audit, STATUS_SUCCEEDED, response);
            return response;
        } catch (ResponseStatusException exception) {
            return persistFailure(audit, request, mapErrorCode(exception), exception.getStatusCode().is5xxServerError());
        } catch (IllegalArgumentException exception) {
            return persistFailure(audit, request, ControlErrorCode.TOOL_ARGUMENT_INVALID, false);
        } catch (RuntimeException exception) {
            return persistFailure(audit, request, "INTERNAL_SERVER_ERROR", true);
        }
    }

    private ToolExecutionAuditEntity createAudit(ToolApiModels.ExecuteToolRequest request,
                                                 String requestIdentityJson,
                                                 String callerContextJson,
                                                 ToolDefinition<?> definition) {
        long now = System.currentTimeMillis();
        ToolExecutionAuditEntity audit = new ToolExecutionAuditEntity();
        audit.setAuditId(idGenerator.nextToolAuditId());
        audit.setRequestId(request.requestId());
        audit.setSessionId(request.sessionId());
        audit.setToolName(request.tool());
        audit.setRiskLevel(definition.riskLevel());
        audit.setStatus(STATUS_CREATED);
        audit.setRequestJson(requestIdentityJson);
        audit.setCallerContextJson(callerContextJson);
        audit.setEntityRefsJson(jsonCodec.write(entityRefsForRequest(request)));
        audit.setCreatedAt(now);
        audit.setUpdatedAt(now);
        toolExecutionAuditMapper.insert(audit);
        return audit;
    }

    private ToolConfirmationTokenEntity createConfirmation(ToolApiModels.ExecuteToolRequest request,
                                                           ToolExecutionAuditEntity audit) {
        long now = System.currentTimeMillis();
        ToolConfirmationTokenEntity confirmation = new ToolConfirmationTokenEntity();
        confirmation.setConfirmationId(idGenerator.nextToolConfirmationId());
        confirmation.setAuditId(audit.getAuditId());
        confirmation.setToolName(request.tool());
        confirmation.setSessionId(request.sessionId());
        confirmation.setArgumentsJson(jsonCodec.write(mapOrEmpty(request.arguments())));
        confirmation.setCallerContextJson(jsonCodec.write(request.callerContext()));
        confirmation.setTokenHash(confirmation.getConfirmationId());
        confirmation.setStatus(TOKEN_STATUS_PENDING);
        confirmation.setExpiresAt(now + controlProperties.getTools().getConfirmationTtlMs());
        confirmation.setCreatedAt(now);
        confirmation.setUpdatedAt(now);
        toolConfirmationTokenMapper.insert(confirmation);
        return confirmation;
    }

    private ToolApiModels.ExecuteToolResponse completedResponse(ToolApiModels.ExecuteToolRequest request,
                                                                ToolExecutionAuditEntity audit,
                                                                ToolResult toolResult,
                                                                ToolApiModels.EntityRefs entityRefs) {
        return new ToolApiModels.ExecuteToolResponse(
                PROTOCOL_VERSION,
                request.requestId(),
                request.sessionId(),
                request.tool(),
                RESPONSE_STATUS_COMPLETED,
                toolResult.result(),
                toolResult.warnings(),
                null,
                new ToolApiModels.ToolAudit(audit.getAuditId(), audit.getRiskLevel()),
                entityRefs,
                null
        );
    }

    private ToolApiModels.ExecuteToolResponse approvalRequiredResponse(ToolApiModels.ExecuteToolRequest request,
                                                                       ToolExecutionAuditEntity audit,
                                                                       ToolConfirmationTokenEntity confirmation) {
        ToolApiModels.EntityRefs entityRefs = parseEntityRefs(audit.getEntityRefsJson());
        String summary = "Approval required before executing `" + request.tool() + "`.";
        if ("propose_governed_action".equals(request.tool())) {
            String proposalId = valueAsString(request.arguments().get("proposalId"));
            String actionToolName = valueAsString(request.arguments().get("actionToolName"));
            summary = "Approval required before executing governed proposal `"
                    + blankToDefault(proposalId, "unknown-proposal")
                    + "` for `" + blankToDefault(actionToolName, "unknown-action") + "`.";
        }
        return new ToolApiModels.ExecuteToolResponse(
                PROTOCOL_VERSION,
                request.requestId(),
                request.sessionId(),
                request.tool(),
                RESPONSE_STATUS_APPROVAL_REQUIRED,
                null,
                List.of(),
                null,
                new ToolApiModels.ToolAudit(audit.getAuditId(), audit.getRiskLevel()),
                entityRefs,
                new ToolApiModels.ToolConfirmation(
                        confirmation.getConfirmationId(),
                        confirmation.getExpiresAt(),
                        summary
                )
        );
    }

    private ToolApiModels.ExecuteToolResponse persistFailure(ToolExecutionAuditEntity audit,
                                                             ToolApiModels.ExecuteToolRequest request,
                                                             String errorCode,
                                                             boolean retryable) {
        ToolApiModels.ExecuteToolResponse response = failedResponse(
                request,
                audit,
                errorCode,
                retryable,
                parseEntityRefs(audit.getEntityRefsJson())
        );
        updateAudit(audit, STATUS_FAILED, response);
        return response;
    }

    private ToolApiModels.ExecuteToolResponse failedResponse(ToolApiModels.ExecuteToolRequest request,
                                                             ToolExecutionAuditEntity audit,
                                                             String errorCode,
                                                             boolean retryable,
                                                             ToolApiModels.EntityRefs entityRefs) {
        return new ToolApiModels.ExecuteToolResponse(
                request == null ? PROTOCOL_VERSION : blankToDefault(request.version(), PROTOCOL_VERSION),
                request == null ? null : request.requestId(),
                request == null ? null : request.sessionId(),
                request == null ? null : request.tool(),
                RESPONSE_STATUS_FAILED,
                null,
                List.of(),
                new ToolApiModels.ToolError(errorCode, errorCode, retryable),
                audit == null ? null : new ToolApiModels.ToolAudit(audit.getAuditId(), audit.getRiskLevel()),
                entityRefs == null ? emptyEntityRefs() : entityRefs,
                null
        );
    }

    private ToolApiModels.ExecuteToolResponse invalidRequestResponse(ToolApiModels.ExecuteToolRequest request, String errorCode) {
        return new ToolApiModels.ExecuteToolResponse(
                request == null ? PROTOCOL_VERSION : blankToDefault(request.version(), PROTOCOL_VERSION),
                request == null ? null : request.requestId(),
                request == null ? null : request.sessionId(),
                request == null ? null : request.tool(),
                RESPONSE_STATUS_FAILED,
                null,
                List.of(),
                new ToolApiModels.ToolError(errorCode, errorCode, false),
                null,
                emptyEntityRefs(),
                null
        );
    }

    private ToolApiModels.ExecuteToolResponse invalidResolveRequestResponse(ToolApiModels.ResolveConfirmationRequest request,
                                                                            String errorCode) {
        return new ToolApiModels.ExecuteToolResponse(
                request == null ? PROTOCOL_VERSION : blankToDefault(request.version(), PROTOCOL_VERSION),
                null,
                request == null ? null : request.sessionId(),
                null,
                RESPONSE_STATUS_FAILED,
                null,
                List.of(),
                new ToolApiModels.ToolError(errorCode, errorCode, false),
                null,
                emptyEntityRefs(),
                null
        );
    }

    private ToolApiModels.ExecuteToolResponse invalidConfirmationResponse(ToolConfirmationTokenEntity token,
                                                                          ToolApiModels.ExecuteToolRequest request,
                                                                          ToolApiModels.ResolveConfirmationRequest resolveRequest,
                                                                          String errorCode) {
        ToolExecutionAuditEntity audit = token == null ? null : toolExecutionAuditMapper.findById(token.getAuditId());
        ToolApiModels.ExecuteToolRequest effectiveRequest = request;
        if (effectiveRequest == null && audit != null) {
            effectiveRequest = parseAuditRequest(audit);
        }
        if (effectiveRequest == null) {
            effectiveRequest = new ToolApiModels.ExecuteToolRequest(
                    PROTOCOL_VERSION,
                    null,
                    resolveRequest == null ? null : resolveRequest.sessionId(),
                    token == null ? null : token.getToolName(),
                    Map.of(),
                    null
            );
        }
        return failedResponse(effectiveRequest, audit, errorCode, false, audit == null ? emptyEntityRefs() : parseEntityRefs(audit.getEntityRefsJson()));
    }

    private ToolApiModels.ExecuteToolResponse readStoredResponse(ToolExecutionAuditEntity audit,
                                                                 ToolApiModels.ExecuteToolRequest request) {
        if (audit.getResponseJson() == null || audit.getResponseJson().isBlank()) {
            return failedResponse(request, audit, ControlErrorCode.TOOL_REQUEST_INVALID, false, emptyEntityRefs());
        }
        try {
            return objectMapper.readValue(audit.getResponseJson(), ToolApiModels.ExecuteToolResponse.class);
        } catch (JsonProcessingException exception) {
            throw ControlApiExceptions.internal("JSON_DESERIALIZATION_FAILED", exception);
        }
    }

    private void updateAudit(ToolExecutionAuditEntity audit, String status, ToolApiModels.ExecuteToolResponse response) {
        audit.setStatus(status);
        audit.setResponseJson(jsonCodec.write(response));
        audit.setEntityRefsJson(jsonCodec.write(response.entityRefs()));
        audit.setUpdatedAt(System.currentTimeMillis());
        toolExecutionAuditMapper.update(audit);
    }

    private ToolApiModels.ExecuteToolRequest normalizeRequest(ToolApiModels.ExecuteToolRequest request) {
        if (request == null) {
            throw ControlApiExceptions.badRequest(ControlErrorCode.TOOL_REQUEST_INVALID);
        }
        return new ToolApiModels.ExecuteToolRequest(
                blankToDefault(request.version(), PROTOCOL_VERSION),
                requireNonBlank(request.requestId(), ControlErrorCode.TOOL_REQUEST_INVALID),
                requireNonBlank(request.sessionId(), ControlErrorCode.TOOL_REQUEST_INVALID),
                requireNonBlank(request.tool(), ControlErrorCode.TOOL_REQUEST_INVALID),
                request.arguments() == null ? Map.of() : request.arguments(),
                normalizeCallerContext(request.callerContext())
        );
    }

    private ToolApiModels.ResolveConfirmationRequest normalizeResolveRequest(ToolApiModels.ResolveConfirmationRequest request) {
        if (request == null) {
            throw ControlApiExceptions.badRequest(ControlErrorCode.TOOL_REQUEST_INVALID);
        }
        String decision = requireNonBlank(request.decision(), ControlErrorCode.TOOL_REQUEST_INVALID).toLowerCase();
        if (!Objects.equals(decision, "approve") && !Objects.equals(decision, "reject")) {
            throw ControlApiExceptions.badRequest(ControlErrorCode.TOOL_REQUEST_INVALID);
        }
        return new ToolApiModels.ResolveConfirmationRequest(
                blankToDefault(request.version(), PROTOCOL_VERSION),
                requireNonBlank(request.confirmationId(), ControlErrorCode.TOOL_REQUEST_INVALID),
                decision,
                requireNonBlank(request.sessionId(), ControlErrorCode.TOOL_REQUEST_INVALID),
                normalizeCallerContext(request.callerContext())
        );
    }

    private ToolApiModels.CallerContext normalizeCallerContext(ToolApiModels.CallerContext callerContext) {
        if (callerContext == null) {
            throw ControlApiExceptions.badRequest(ControlErrorCode.TOOL_REQUEST_INVALID);
        }
        return new ToolApiModels.CallerContext(
                requireNonBlank(callerContext.agentTaskId(), ControlErrorCode.TOOL_REQUEST_INVALID),
                requireNonBlank(callerContext.turnId(), ControlErrorCode.TOOL_REQUEST_INVALID),
                requireNonBlank(callerContext.stepId(), ControlErrorCode.TOOL_REQUEST_INVALID)
        );
    }

    private Map<String, Object> requestIdentity(ToolApiModels.ExecuteToolRequest request) {
        return Map.of(
                "version", request.version(),
                "requestId", request.requestId(),
                "sessionId", request.sessionId(),
                "tool", request.tool(),
                "arguments", mapOrEmpty(request.arguments()),
                "callerContext", callerContextMap(request.callerContext())
        );
    }

    private Map<String, Object> callerContextMap(ToolApiModels.CallerContext callerContext) {
        if (callerContext == null) {
            return Map.of();
        }
        return Map.of(
                "agentTaskId", callerContext.agentTaskId(),
                "turnId", callerContext.turnId(),
                "stepId", callerContext.stepId()
        );
    }

    private String mapErrorCode(ResponseStatusException exception) {
        String reason = exception.getReason();
        if (reason == null || reason.isBlank()) {
            HttpStatus status = HttpStatus.resolve(exception.getStatusCode().value());
            return status == null ? "INTERNAL_SERVER_ERROR" : status.name();
        }
        return reason;
    }

    private ToolApiModels.ExecuteToolRequest parseAuditRequest(ToolExecutionAuditEntity audit) {
        try {
            return objectMapper.readValue(audit.getRequestJson(), ToolApiModels.ExecuteToolRequest.class);
        } catch (JsonProcessingException exception) {
            throw ControlApiExceptions.internal("JSON_DESERIALIZATION_FAILED", exception);
        }
    }

    private boolean callerContextMatches(String serializedCallerContext, ToolApiModels.CallerContext callerContext) {
        if (serializedCallerContext == null || serializedCallerContext.isBlank()) {
            return callerContext == null;
        }
        try {
            ToolApiModels.CallerContext stored = objectMapper.readValue(serializedCallerContext, ToolApiModels.CallerContext.class);
            return Objects.equals(stored, callerContext);
        } catch (JsonProcessingException exception) {
            throw ControlApiExceptions.internal("JSON_DESERIALIZATION_FAILED", exception);
        }
    }

    private ToolApiModels.EntityRefs emptyEntityRefs() {
        return new ToolApiModels.EntityRefs(null, null, null, null, null, List.of());
    }

    private ToolApiModels.EntityRefs entityRefsForRequest(ToolApiModels.ExecuteToolRequest request) {
        if (!"propose_governed_action".equals(request.tool())) {
            return emptyEntityRefs();
        }
        Map<String, Object> arguments = mapOrEmpty(request.arguments());
        String proposalId = valueAsString(arguments.get("proposalId"));
        String targetKind = valueAsString(arguments.get("targetKind"));
        String targetId = valueAsString(arguments.get("targetId"));
        Map<String, Object> nestedArguments = arguments.get("arguments") instanceof Map<?, ?> map
                ? objectMapper.convertValue(map, Map.class)
                : Map.of();
        String runId = "run".equals(targetKind) ? targetId : valueAsString(firstPresent(nestedArguments, "runId", "run_id"));
        String runTargetId = "run_target".equals(targetKind) ? targetId : valueAsString(firstPresent(nestedArguments, "runTargetId", "run_target_id", "targetId"));
        String taskId = "task".equals(targetKind) ? targetId : valueAsString(firstPresent(nestedArguments, "taskId", "task_id"));
        String attemptId = "attempt".equals(targetKind) ? targetId : valueAsString(firstPresent(nestedArguments, "attemptId", "attempt_id"));
        return new ToolApiModels.EntityRefs(proposalId, runId, runTargetId, taskId, attemptId, List.of());
    }

    private ToolApiModels.EntityRefs parseEntityRefs(String entityRefsJson) {
        if (entityRefsJson == null || entityRefsJson.isBlank()) {
            return emptyEntityRefs();
        }
        try {
            return objectMapper.readValue(entityRefsJson, ToolApiModels.EntityRefs.class);
        } catch (JsonProcessingException exception) {
            throw ControlApiExceptions.internal("JSON_DESERIALIZATION_FAILED", exception);
        }
    }

    private boolean matchesAuditQuery(ToolExecutionAuditEntity audit, ToolApiModels.AuditQueryRequest request) {
        ToolApiModels.CallerContext callerContext = parseCallerContext(audit.getCallerContextJson());
        ToolApiModels.EntityRefs entityRefs = parseEntityRefs(audit.getEntityRefsJson());
        return matchesNullable(request.sessionId(), audit.getSessionId())
                && matchesNullable(request.agentTaskId(), callerContext == null ? null : callerContext.agentTaskId())
                && matchesNullable(request.turnId(), callerContext == null ? null : callerContext.turnId())
                && matchesNullable(request.runId(), entityRefs.runId())
                && matchesNullable(request.runTargetId(), entityRefs.runTargetId())
                && matchesNullable(request.attemptId(), entityRefs.attemptId());
    }

    private ToolApiModels.AuditTimelineEntry toAuditTimelineEntry(ToolExecutionAuditEntity audit) {
        return new ToolApiModels.AuditTimelineEntry(
                audit.getAuditId(),
                audit.getRequestId(),
                audit.getSessionId(),
                audit.getToolName(),
                audit.getStatus(),
                audit.getRiskLevel(),
                parseCallerContext(audit.getCallerContextJson()),
                parseEntityRefs(audit.getEntityRefsJson()),
                audit.getCreatedAt(),
                audit.getUpdatedAt()
        );
    }

    private ToolApiModels.CallerContext parseCallerContext(String callerContextJson) {
        if (callerContextJson == null || callerContextJson.isBlank()) {
            return null;
        }
        try {
            return objectMapper.readValue(callerContextJson, ToolApiModels.CallerContext.class);
        } catch (JsonProcessingException exception) {
            throw ControlApiExceptions.internal("JSON_DESERIALIZATION_FAILED", exception);
        }
    }

    private boolean matchesNullable(String expected, String actual) {
        return expected == null || expected.isBlank() || Objects.equals(expected, actual);
    }

    private ToolApiModels.EntityRefs extractEntityRefs(Object result) {
        Map<String, Object> flattened = new LinkedHashMap<>();
        collectEntityRefs(result, flattened);
        Object artifactIds = flattened.get("artifactIds");
        List<String> normalizedArtifactIds;
        if (artifactIds instanceof List<?> list) {
            normalizedArtifactIds = list.stream().map(String::valueOf).distinct().toList();
        } else {
            normalizedArtifactIds = List.of();
        }
        return new ToolApiModels.EntityRefs(
                valueAsString(flattened.get("proposalId")),
                valueAsString(flattened.get("runId")),
                valueAsString(flattened.get("runTargetId")),
                valueAsString(flattened.get("taskId")),
                valueAsString(flattened.get("attemptId")),
                normalizedArtifactIds
        );
    }

    @SuppressWarnings("unchecked")
    private void collectEntityRefs(Object value, Map<String, Object> flattened) {
        if (value instanceof Map<?, ?> map) {
            Map<String, Object> stringMap = (Map<String, Object>) map;
            captureFirst(flattened, "proposalId", stringMap, "proposalId", "proposal_id", "decisionProposalId");
            captureFirst(flattened, "runId", stringMap, "runId", "run_id");
            captureFirst(flattened, "runTargetId", stringMap, "runTargetId", "run_target_id", "targetId");
            captureFirst(flattened, "taskId", stringMap, "taskId", "task_id");
            captureFirst(flattened, "attemptId", stringMap, "attemptId", "attempt_id");
            captureMany(flattened, "artifactIds", stringMap, "artifactIds", "artifact_ids");
            Object artifactId = firstPresent(stringMap, "artifactId", "artifact_id");
            if (artifactId != null) {
                flattened.computeIfAbsent("artifactIds", key -> new ArrayList<String>());
                @SuppressWarnings("unchecked")
                List<String> ids = (List<String>) flattened.get("artifactIds");
                ids.add(String.valueOf(artifactId));
            }
            for (Object nested : stringMap.values()) {
                collectEntityRefs(nested, flattened);
            }
            return;
        }
        if (value instanceof List<?> list) {
            for (Object nested : list) {
                collectEntityRefs(nested, flattened);
            }
        }
    }

    private void captureFirst(Map<String, Object> flattened, String key, Map<String, Object> source, String... aliases) {
        if (flattened.get(key) != null) {
            return;
        }
        Object present = firstPresent(source, aliases);
        if (present != null) {
            flattened.put(key, present);
        }
    }

    private void captureMany(Map<String, Object> flattened, String key, Map<String, Object> source, String... aliases) {
        Object present = firstPresent(source, aliases);
        if (!(present instanceof List<?> list)) {
            return;
        }
        List<String> values = new ArrayList<>();
        if (flattened.get(key) instanceof List<?> existing) {
            for (Object item : existing) {
                values.add(String.valueOf(item));
            }
        }
        for (Object item : list) {
            values.add(String.valueOf(item));
        }
        flattened.put(key, values);
    }

    private Object firstPresent(Map<String, Object> source, String... aliases) {
        for (String alias : aliases) {
            if (source.containsKey(alias) && source.get(alias) != null) {
                return source.get(alias);
            }
        }
        return null;
    }

    private String valueAsString(Object value) {
        return value == null ? null : String.valueOf(value);
    }

    private void register(Map<String, ToolDefinition<?>> definitions, ToolDefinition<?> definition) {
        definitions.put(definition.name(), definition);
    }

    private <A> ToolDefinition<A> definition(String name,
                                             String title,
                                             String description,
                                             String riskLevel,
                                             Map<String, Object> inputSchema,
                                             Map<String, Object> outputSchema,
                                             Class<A> argumentsType,
                                             ToolExecutor<A> executor) {
        return new ToolDefinition<>(
                name,
                title,
                description,
                toolKindForRisk(riskLevel),
                riskLevel,
                semanticTagsForRisk(riskLevel),
                Objects.equals(riskLevel, RISK_EXECUTION),
                inputSchema,
                outputSchema,
                RESULT_MODE_INLINE,
                STABILITY_STABLE,
                argumentsType,
                executor
        );
    }

    private ToolResult result(Object value) {
        return new ToolResult(value, List.of());
    }

    private String blankToDefault(String value, String defaultValue) {
        return value == null || value.isBlank() ? defaultValue : value;
    }

    private String requireNonBlank(String value, String errorCode) {
        if (value == null || value.isBlank()) {
            throw ControlApiExceptions.badRequest(errorCode);
        }
        return value;
    }

    private Map<String, Object> mapOrEmpty(Map<String, Object> value) {
        return value == null ? Map.of() : value;
    }

    private List<String> listOrEmpty(List<String> value) {
        return value == null ? List.of() : value;
    }

    private Map<String, Object> noArgsSchema() {
        return objectSchema(props(), List.of());
    }

    private Map<String, Object> idArgsSchema(String propertyName) {
        return objectSchema(props(propertyName, stringSchema()), List.of(propertyName));
    }

    private Map<String, Object> draftRunPlanArgsSchema() {
        return objectSchema(props(
                "goal", stringSchema(),
                "constraints", mapSchema()
        ), List.of("goal"));
    }

    private Map<String, Object> materializeRunPlanArgsSchema() {
        return objectSchema(props(
                "planRequestId", stringSchema(),
                "createdBy", stringSchema()
        ), List.of("planRequestId"));
    }

    private Map<String, Object> createDevicePoolArgsSchema() {
        return objectSchema(props(
                "name", stringSchema(),
                "description", nullableStringSchema(),
                "hostGroup", nullableStringSchema(),
                "deviceIds", arraySchema(stringSchema()),
                "requiredTags", arraySchema(stringSchema()),
                "excludedTags", arraySchema(stringSchema()),
                "createdBy", nullableStringSchema()
        ), List.of("name"));
    }

    private Map<String, Object> createTaskArgsSchema() {
        return objectSchema(props(
                "taskType", stringSchema(),
                "profilePackage", stringSchema(),
                "taskPayload", mapSchema(),
                "runConfig", runConfigSchema(),
                "artifactPolicy", artifactPolicySchema(),
                "priority", integerSchema(),
                "labels", arraySchema(stringSchema()),
                "source", stringSchema(),
                "createdBy", stringSchema(),
                "idempotencyKey", nullableStringSchema()
        ), List.of("taskType", "profilePackage", "taskPayload", "runConfig", "artifactPolicy"));
    }

    private Map<String, Object> createRunArgsSchema() {
        return objectSchema(props(
                "name", stringSchema(),
                "description", nullableStringSchema(),
                "devicePoolId", stringSchema(),
                "taskType", stringSchema(),
                "profilePackage", stringSchema(),
                "taskPayload", mapSchema(),
                "runConfig", runConfigSchema(),
                "artifactPolicy", artifactPolicySchema(),
                "priority", integerSchema(),
                "labels", arraySchema(stringSchema()),
                "source", stringSchema(),
                "createdBy", stringSchema(),
                "maxRetriesPerDevice", integerSchema(),
                "queueTimeoutMs", integerSchema()
        ), List.of("name", "devicePoolId", "taskType", "profilePackage", "taskPayload", "runConfig", "artifactPolicy"));
    }

    private Map<String, Object> createSingleDeviceRunArgsSchema() {
        return objectSchema(props(
                "name", stringSchema(),
                "description", nullableStringSchema(),
                "deviceId", stringSchema(),
                "taskType", stringSchema(),
                "profilePackage", stringSchema(),
                "taskPayload", mapSchema(),
                "runConfig", runConfigSchema(),
                "artifactPolicy", artifactPolicySchema(),
                "priority", integerSchema(),
                "labels", arraySchema(stringSchema()),
                "source", stringSchema(),
                "createdBy", stringSchema(),
                "maxRetriesPerDevice", integerSchema(),
                "queueTimeoutMs", integerSchema()
        ), List.of("name", "deviceId", "taskType", "profilePackage", "taskPayload", "runConfig", "artifactPolicy"));
    }

    private Map<String, Object> proposeGovernedActionArgsSchema() {
        return objectSchema(props(
                "proposalId", stringSchema(),
                "actionToolName", stringSchema(),
                "arguments", mapSchema(),
                "targetKind", nullableStringSchema(),
                "targetId", nullableStringSchema(),
                "rationale", nullableStringSchema(),
                "preconditions", mapSchema(),
                "confidence", Map.of("type", "number")
        ), List.of("proposalId", "actionToolName", "arguments", "preconditions"));
    }

    private Map<String, Object> sendDeviceCommandArgsSchema() {
        return objectSchema(props(
                "deviceId", stringSchema(),
                "type", stringSchema(),
                "attemptId", nullableStringSchema(),
                "expireInMs", nullableIntegerSchema()
        ), List.of("deviceId", "type"));
    }

    private Map<String, Object> deviceSchema() {
        return objectSchema(props(
                "deviceId", stringSchema(),
                "protocolVersion", stringSchema(),
                "executorVersion", stringSchema(),
                "brand", stringSchema(),
                "model", stringSchema(),
                "androidVersion", stringSchema(),
                "screenWidth", integerSchema(),
                "screenHeight", integerSchema(),
                "installedProfiles", arraySchema(stringSchema()),
                "tags", arraySchema(stringSchema()),
                "hostGroup", stringSchema(),
                "registered", booleanSchema(),
                "online", booleanSchema(),
                "busy", booleanSchema(),
                "status", stringSchema(),
                "currentTaskId", nullableStringSchema(),
                "currentAttemptId", nullableStringSchema(),
                "currentTaskType", nullableStringSchema(),
                "configVersion", nullableStringSchema(),
                "authConfigured", booleanSchema(),
                "leaseExpireAt", nullableIntegerSchema(),
                "lastHeartbeatAt", integerSchema(),
                "lastCommand", nullableStringSchema(),
                "health", mapSchema(),
                "updatedAt", integerSchema()
        ), List.of("deviceId", "status", "registered", "online", "busy"));
    }

    private Map<String, Object> devicePoolSchema() {
        return objectSchema(props(
                "poolId", stringSchema(),
                "name", stringSchema(),
                "description", nullableStringSchema(),
                "hostGroup", nullableStringSchema(),
                "deviceIds", arraySchema(stringSchema()),
                "requiredTags", arraySchema(stringSchema()),
                "excludedTags", arraySchema(stringSchema()),
                "createdBy", nullableStringSchema(),
                "createdAt", integerSchema(),
                "updatedAt", integerSchema()
        ), List.of("poolId", "name", "deviceIds", "requiredTags", "excludedTags"));
    }

    private Map<String, Object> attemptSummarySchema() {
        return objectSchema(props(
                "attemptId", stringSchema(),
                "taskId", stringSchema(),
                "deviceId", stringSchema(),
                "runId", stringSchema(),
                "status", stringSchema(),
                "finalState", nullableStringSchema(),
                "leaseExpireAt", nullableIntegerSchema(),
                "failureReason", nullableStringSchema(),
                "startedAt", nullableIntegerSchema(),
                "finishedAt", nullableIntegerSchema(),
                "createdAt", integerSchema(),
                "updatedAt", integerSchema()
        ), List.of("attemptId", "taskId", "deviceId", "runId", "status"));
    }

    private Map<String, Object> taskSchema() {
        return objectSchema(props(
                "taskId", stringSchema(),
                "runId", nullableStringSchema(),
                "runTargetId", nullableStringSchema(),
                "targetDeviceId", nullableStringSchema(),
                "taskType", stringSchema(),
                "profilePackage", stringSchema(),
                "taskPayload", mapSchema(),
                "runConfig", runConfigSchema(),
                "artifactPolicy", artifactPolicySchema(),
                "priority", integerSchema(),
                "labels", arraySchema(stringSchema()),
                "source", stringSchema(),
                "scheduleVersion", nullableStringSchema(),
                "idempotencyKey", stringSchema(),
                "status", stringSchema(),
                "createdBy", stringSchema(),
                "createdAt", integerSchema(),
                "updatedAt", integerSchema(),
                "latestAttempt", nullableSchema(attemptSummarySchema())
        ), List.of("taskId", "taskType", "profilePackage", "taskPayload", "runConfig", "artifactPolicy", "priority", "labels", "source", "idempotencyKey", "status", "createdBy"));
    }

    private Map<String, Object> runCountsSchema() {
        return objectSchema(props(
                "totalTargets", integerSchema(),
                "queued", integerSchema(),
                "running", integerSchema(),
                "retryPending", integerSchema(),
                "succeeded", integerSchema(),
                "failed", integerSchema(),
                "cancelled", integerSchema()
        ), List.of("totalTargets", "queued", "running", "retryPending", "succeeded", "failed", "cancelled"));
    }

    private Map<String, Object> runSummarySchema() {
        return objectSchema(props(
                "runId", stringSchema(),
                "name", stringSchema(),
                "description", nullableStringSchema(),
                "poolId", nullableStringSchema(),
                "status", stringSchema(),
                "finalState", nullableStringSchema(),
                "taskType", stringSchema(),
                "profilePackage", stringSchema(),
                "priority", integerSchema(),
                "labels", arraySchema(stringSchema()),
                "source", stringSchema(),
                "createdBy", stringSchema(),
                "maxRetriesPerDevice", integerSchema(),
                "queueTimeoutMs", integerSchema(),
                "cancelRequested", booleanSchema(),
                "createdAt", integerSchema(),
                "updatedAt", integerSchema(),
                "startedAt", nullableIntegerSchema(),
                "finishedAt", nullableIntegerSchema(),
                "counts", runCountsSchema()
        ), List.of("runId", "name", "poolId", "status", "taskType", "profilePackage", "priority", "labels", "source", "createdBy", "maxRetriesPerDevice", "queueTimeoutMs", "cancelRequested", "counts"));
    }

    private Map<String, Object> runTargetSchema() {
        return objectSchema(props(
                "runTargetId", stringSchema(),
                "deviceId", stringSchema(),
                "status", stringSchema(),
                "attemptCount", integerSchema(),
                "currentTaskId", nullableStringSchema(),
                "latestAttemptId", nullableStringSchema(),
                "failureReason", nullableStringSchema(),
                "startedAt", nullableIntegerSchema(),
                "finishedAt", nullableIntegerSchema(),
                "task", nullableSchema(taskSchema()),
                "latestAttempt", nullableSchema(attemptSummarySchema())
        ), List.of("runTargetId", "deviceId", "status", "attemptCount"));
    }

    private Map<String, Object> runDetailSchema() {
        return objectSchema(props(
                "run", runSummarySchema(),
                "taskPayload", mapSchema(),
                "runConfig", runConfigSchema(),
                "artifactPolicy", artifactPolicySchema(),
                "targets", arraySchema(runTargetSchema())
        ), List.of("run", "taskPayload", "runConfig", "artifactPolicy", "targets"));
    }

    private Map<String, Object> runEventSchema() {
        return objectSchema(props(
                "id", nullableIntegerSchema(),
                "attemptId", stringSchema(),
                "taskId", stringSchema(),
                "deviceId", stringSchema(),
                "runId", stringSchema(),
                "scenarioId", nullableStringSchema(),
                "stepIndex", nullableIntegerSchema(),
                "actionIndex", nullableIntegerSchema(),
                "eventType", stringSchema(),
                "state", nullableStringSchema(),
                "code", nullableStringSchema(),
                "message", stringSchema(),
                "ts", integerSchema()
        ), List.of("attemptId", "taskId", "deviceId", "runId", "eventType", "message", "ts"));
    }

    private Map<String, Object> resourceHandleSchema() {
        return objectSchema(props(
                "handle", stringSchema(),
                "kind", stringSchema(),
                "mimeType", stringSchema(),
                "sizeBytes", integerSchema(),
                "fileName", nullableStringSchema(),
                "title", nullableStringSchema()
        ), List.of("handle", "kind", "mimeType", "sizeBytes"));
    }

    private Map<String, Object> attemptArtifactSchema() {
        return objectSchema(props(
                "artifactId", stringSchema(),
                "attemptId", stringSchema(),
                "taskId", stringSchema(),
                "runId", stringSchema(),
                "artifactType", stringSchema(),
                "fileName", stringSchema(),
                "mimeType", stringSchema(),
                "sizeBytes", integerSchema(),
                "createdAt", integerSchema(),
                "resource", resourceHandleSchema()
        ), List.of("artifactId", "attemptId", "taskId", "runId", "artifactType", "fileName", "mimeType", "sizeBytes", "createdAt", "resource"));
    }

    private Map<String, Object> attemptDetailSchema() {
        return objectSchema(props(
                "attempt", attemptSummarySchema(),
                "events", arraySchema(runEventSchema()),
                "artifacts", arraySchema(attemptArtifactSchema())
        ), List.of("attempt", "events", "artifacts"));
    }

    private Map<String, Object> runConfigSchema() {
        return objectSchema(props(
                "loopCount", integerSchema(),
                "budgetMs", integerSchema(),
                "loopIntervalMs", integerSchema(),
                "networkIsolationEnabled", booleanSchema(),
                "pollIntervalMs", integerSchema(),
                "heartbeatIntervalMs", integerSchema()
        ), List.of("loopCount", "budgetMs", "loopIntervalMs", "networkIsolationEnabled", "pollIntervalMs", "heartbeatIntervalMs"));
    }

    private Map<String, Object> artifactPolicySchema() {
        return objectSchema(props(
                "uploadLog", booleanSchema(),
                "uploadScreenshot", booleanSchema(),
                "uploadDump", booleanSchema()
        ), List.of("uploadLog", "uploadScreenshot", "uploadDump"));
    }

    private Map<String, Object> runPlanningCatalogSchema() {
        return objectSchema(props(
                "availableDevicePools", arraySchema(objectSchema(props(
                        "poolId", stringSchema(),
                        "name", stringSchema(),
                        "hostGroup", nullableStringSchema(),
                        "deviceCount", integerSchema(),
                        "requiredTags", arraySchema(stringSchema()),
                        "excludedTags", arraySchema(stringSchema())
                ), List.of("poolId", "name", "deviceCount", "requiredTags", "excludedTags"))),
                "availableProfiles", arraySchema(objectSchema(props(
                        "profilePackage", stringSchema(),
                        "installedDeviceCount", integerSchema(),
                        "supportedTaskTypes", arraySchema(stringSchema()),
                        "requiredTaskPayloadFields", arraySchema(stringSchema()),
                        "recommendedDefaults", mapSchema(),
                        "knownLimitations", arraySchema(stringSchema())
                ), List.of("profilePackage", "installedDeviceCount", "supportedTaskTypes", "requiredTaskPayloadFields", "recommendedDefaults", "knownLimitations"))),
                "defaultRunPolicy", objectSchema(props(
                        "priority", integerSchema(),
                        "maxRetriesPerDevice", integerSchema(),
                        "queueTimeoutMs", integerSchema(),
                        "defaultRunConfig", mapSchema(),
                        "defaultArtifactPolicy", mapSchema()
                ), List.of("priority", "maxRetriesPerDevice", "queueTimeoutMs", "defaultRunConfig", "defaultArtifactPolicy")),
                "allowedTaskTypes", arraySchema(stringSchema())
        ), List.of("availableDevicePools", "availableProfiles", "defaultRunPolicy", "allowedTaskTypes"));
    }

    private Map<String, Object> runDraftSchema() {
        return objectSchema(props(
                "name", stringSchema(),
                "description", nullableStringSchema(),
                "devicePoolId", stringSchema(),
                "taskType", stringSchema(),
                "profilePackage", stringSchema(),
                "taskPayload", mapSchema(),
                "runConfig", mapSchema(),
                "artifactPolicy", mapSchema(),
                "priority", integerSchema(),
                "labels", arraySchema(stringSchema()),
                "maxRetriesPerDevice", integerSchema(),
                "queueTimeoutMs", integerSchema()
        ), List.of("name", "devicePoolId", "taskType", "profilePackage", "taskPayload", "runConfig", "artifactPolicy", "priority", "labels", "maxRetriesPerDevice", "queueTimeoutMs"));
    }

    private Map<String, Object> runPlanDraftSchema() {
        return objectSchema(props(
                "requestId", stringSchema(),
                "runDraft", runDraftSchema(),
                "warnings", arraySchema(stringSchema()),
                "reviewHints", arraySchema(stringSchema()),
                "validation", objectSchema(props(
                        "materializable", booleanSchema(),
                        "errors", arraySchema(stringSchema()),
                        "warnings", arraySchema(stringSchema())
                ), List.of("materializable", "errors", "warnings")),
                "modelMeta", mapSchema()
        ), List.of("requestId", "runDraft", "warnings", "reviewHints", "validation", "modelMeta"));
    }

    private Map<String, Object> runPlanSchema() {
        return objectSchema(props(
                "requestId", stringSchema(),
                "status", stringSchema(),
                "goal", stringSchema(),
                "constraints", mapSchema(),
                "runDraft", runDraftSchema(),
                "warnings", arraySchema(stringSchema()),
                "reviewHints", arraySchema(stringSchema()),
                "validation", objectSchema(props(
                        "materializable", booleanSchema(),
                        "errors", arraySchema(stringSchema()),
                        "warnings", arraySchema(stringSchema())
                ), List.of("materializable", "errors", "warnings")),
                "modelMeta", mapSchema(),
                "materializedRunId", nullableStringSchema(),
                "materializedBy", nullableStringSchema(),
                "materializedAt", nullableIntegerSchema(),
                "generatedAt", integerSchema()
        ), List.of("requestId", "status", "goal", "constraints", "runDraft", "warnings", "reviewHints", "validation", "modelMeta", "generatedAt"));
    }

    private Map<String, Object> runSummaryResultSchema() {
        return objectSchema(props(
                "summaryId", stringSchema(),
                "runId", stringSchema(),
                "result", mapSchema(),
                "validation", objectSchema(props(
                        "valid", booleanSchema(),
                        "errors", arraySchema(stringSchema()),
                        "warnings", arraySchema(stringSchema())
                ), List.of("valid", "errors", "warnings")),
                "modelMeta", mapSchema(),
                "generatedAt", integerSchema()
        ), List.of("summaryId", "runId", "result", "validation", "modelMeta", "generatedAt"));
    }

    private Map<String, Object> failureTriageSchema() {
        return objectSchema(props(
                "triageResultId", stringSchema(),
                "runTargetId", stringSchema(),
                "result", mapSchema(),
                "validation", objectSchema(props(
                        "valid", booleanSchema(),
                        "errors", arraySchema(stringSchema()),
                        "warnings", arraySchema(stringSchema())
                ), List.of("valid", "errors", "warnings")),
                "modelMeta", mapSchema(),
                "generatedAt", integerSchema()
        ), List.of("triageResultId", "runTargetId", "result", "validation", "modelMeta", "generatedAt"));
    }

    private Map<String, Object> runActionSchema() {
        return objectSchema(props(
                "runId", stringSchema(),
                "accepted", booleanSchema(),
                "status", stringSchema()
        ), List.of("runId", "accepted", "status"));
    }

    private Map<String, Object> governedProposalResultSchema() {
        return objectSchema(props(
                "proposalId", stringSchema(),
                "proposalState", stringSchema(),
                "actionToolName", stringSchema(),
                "targetKind", nullableStringSchema(),
                "targetId", nullableStringSchema(),
                "preconditions", mapSchema(),
                "rationale", nullableStringSchema(),
                "consistencyStatus", stringSchema(),
                "executedAt", integerSchema(),
                "executedAction", mapSchema()
        ), List.of("proposalId", "proposalState", "actionToolName", "preconditions", "consistencyStatus", "executedAt", "executedAction"));
    }

    private Map<String, Object> runAttemptCountsSchema() {
        return objectSchema(props(
                "total", integerSchema(),
                "running", integerSchema(),
                "failed", integerSchema(),
                "succeeded", integerSchema()
        ), List.of("total", "running", "failed", "succeeded"));
    }

    private Map<String, Object> runGovernanceSnapshotSchema() {
        return objectSchema(props(
                "runId", stringSchema(),
                "status", stringSchema(),
                "targetCounts", runCountsSchema(),
                "attemptCounts", runAttemptCountsSchema(),
                "latestAttemptIds", arraySchema(stringSchema()),
                "blockers", arraySchema(stringSchema()),
                "lastUpdatedAt", integerSchema()
        ), List.of("runId", "status", "targetCounts", "attemptCounts", "latestAttemptIds", "blockers", "lastUpdatedAt"));
    }

    private Map<String, Object> runBlockageSummarySchema() {
        return objectSchema(props(
                "runId", stringSchema(),
                "blockageCategory", stringSchema(),
                "blockageReason", stringSchema(),
                "retryable", booleanSchema(),
                "missingInputs", arraySchema(stringSchema()),
                "recommendedAction", stringSchema()
        ), List.of("runId", "blockageCategory", "blockageReason", "retryable", "missingInputs", "recommendedAction"));
    }

    private Map<String, Object> runRecoveryOptionsSchema() {
        return objectSchema(props(
                "runId", stringSchema(),
                "allowedActions", arraySchema(stringSchema()),
                "recommendedAction", stringSchema(),
                "requiresUserInput", booleanSchema(),
                "requiresApproval", booleanSchema(),
                "explanation", stringSchema()
        ), List.of("runId", "allowedActions", "recommendedAction", "requiresUserInput", "requiresApproval", "explanation"));
    }

    private Map<String, Object> auditTimelineEntrySchema() {
        return objectSchema(props(
                "auditId", stringSchema(),
                "requestId", stringSchema(),
                "sessionId", stringSchema(),
                "tool", stringSchema(),
                "status", stringSchema(),
                "riskLevel", stringSchema(),
                "callerContext", objectSchema(props(
                        "agentTaskId", nullableStringSchema(),
                        "turnId", nullableStringSchema(),
                        "stepId", nullableStringSchema()
                ), List.of()),
                "entityRefs", objectSchema(props(
                        "proposalId", nullableStringSchema(),
                        "runId", nullableStringSchema(),
                        "runTargetId", nullableStringSchema(),
                        "taskId", nullableStringSchema(),
                        "attemptId", nullableStringSchema(),
                        "artifactIds", arraySchema(stringSchema())
                ), List.of("artifactIds")),
                "createdAt", integerSchema(),
                "updatedAt", integerSchema()
        ), List.of("auditId", "requestId", "sessionId", "tool", "status", "riskLevel", "createdAt", "updatedAt"));
    }

    private Map<String, Object> runLineageSnapshotSchema() {
        return objectSchema(props(
                "runId", stringSchema(),
                "run", runDetailSchema(),
                "targets", arraySchema(runTargetSchema()),
                "attempts", arraySchema(attemptSummarySchema()),
                "latestArtifacts", arraySchema(attemptArtifactSchema()),
                "auditRefs", arraySchema(auditTimelineEntrySchema()),
                "blockers", arraySchema(stringSchema()),
                "currentGovernedOptions", arraySchema(stringSchema())
        ), List.of("runId", "run", "targets", "attempts", "latestArtifacts", "auditRefs", "blockers", "currentGovernedOptions"));
    }

    private Map<String, Object> attemptDiagnosisBundleSchema() {
        return objectSchema(props(
                "attemptId", stringSchema(),
                "status", stringSchema(),
                "keyEvents", arraySchema(runEventSchema()),
                "normalizedArtifactSummary", stringSchema(),
                "failureSignals", arraySchema(stringSchema()),
                "confidenceHints", mapSchema(),
                "summary", stringSchema()
        ), List.of("attemptId", "status", "keyEvents", "normalizedArtifactSummary", "failureSignals", "confidenceHints", "summary"));
    }

    private Map<String, Object> recoveryGuidanceContextSchema() {
        return objectSchema(props(
                "entityKind", stringSchema(),
                "entityId", stringSchema(),
                "allowedActions", arraySchema(stringSchema()),
                "recommendedAction", stringSchema(),
                "requiresApproval", booleanSchema(),
                "requiredInputs", arraySchema(stringSchema()),
                "prerequisites", arraySchema(stringSchema()),
                "stopConditions", arraySchema(stringSchema()),
                "stopConditionsSummary", stringSchema(),
                "whyNotOthers", stringSchema(),
                "explanation", stringSchema(),
                "confidence", Map.of("type", "number")
        ), List.of("entityKind", "entityId", "allowedActions", "recommendedAction", "requiresApproval", "requiredInputs", "prerequisites", "stopConditions", "stopConditionsSummary", "whyNotOthers", "explanation", "confidence"));
    }

    private Map<String, Object> taskActionSchema() {
        return objectSchema(props(
                "taskId", stringSchema(),
                "accepted", booleanSchema(),
                "status", stringSchema()
        ), List.of("taskId", "accepted", "status"));
    }

    private Map<String, Object> commandAcceptedSchema() {
        return objectSchema(props(
                "deviceId", stringSchema(),
                "type", stringSchema(),
                "attemptId", nullableStringSchema()
        ), List.of("deviceId", "type"));
    }

    private Map<String, Object> objectSchema(Map<String, Object> properties, List<String> required) {
        Map<String, Object> schema = new LinkedHashMap<>();
        schema.put("$schema", "https://json-schema.org/draft/2020-12/schema");
        schema.put("type", "object");
        schema.put("properties", properties);
        schema.put("additionalProperties", false);
        if (!required.isEmpty()) {
            schema.put("required", required);
        }
        return Map.copyOf(schema);
    }

    private Map<String, Object> props(Object... keyValues) {
        Map<String, Object> map = new LinkedHashMap<>();
        for (int index = 0; index < keyValues.length; index += 2) {
            map.put((String) keyValues[index], keyValues[index + 1]);
        }
        return Map.copyOf(map);
    }

    private Map<String, Object> arraySchema(Map<String, Object> itemSchema) {
        return Map.of("type", "array", "items", itemSchema);
    }

    private Map<String, Object> stringSchema() {
        return Map.of("type", "string");
    }

    private Map<String, Object> nullableStringSchema() {
        return nullableSchema(stringSchema());
    }

    private Map<String, Object> integerSchema() {
        return Map.of("type", "integer");
    }

    private Map<String, Object> nullableIntegerSchema() {
        return nullableSchema(integerSchema());
    }

    private Map<String, Object> booleanSchema() {
        return Map.of("type", "boolean");
    }

    private Map<String, Object> mapSchema() {
        return Map.of("type", "object", "additionalProperties", true);
    }

    private String toolKindForRisk(String riskLevel) {
        if (Objects.equals(riskLevel, RISK_EXECUTION)) {
            return TOOL_KIND_SIDE_EFFECT;
        }
        if (Objects.equals(riskLevel, RISK_ADVISORY)) {
            return TOOL_KIND_ANALYZE;
        }
        return TOOL_KIND_READ;
    }

    private List<String> semanticTagsForRisk(String riskLevel) {
        List<String> tags = new ArrayList<>();
        if (Objects.equals(riskLevel, RISK_EXECUTION)) {
            tags.add("execution");
            tags.add("governed");
        } else if (Objects.equals(riskLevel, RISK_ADVISORY)) {
            tags.add("analysis");
            tags.add("planning");
        } else {
            tags.add("observation");
            tags.add("discovery");
        }
        return List.copyOf(tags);
    }

    private Map<String, Object> nullableSchema(Map<String, Object> schema) {
        return Map.of("anyOf", List.of(schema, Map.of("type", "null")));
    }

    private record ToolDefinition<A>(
            String name,
            String title,
            String description,
            String toolKind,
            String riskLevel,
            List<String> semanticTags,
            boolean requiresApproval,
            Map<String, Object> inputSchema,
            Map<String, Object> outputSchema,
            String resultMode,
            String stability,
            Class<A> argumentsType,
            ToolExecutor<A> executor
    ) {
    }

    @FunctionalInterface
    private interface ToolExecutor<A> {
        ToolResult execute(A arguments);
    }

    private record ToolResult(Object result, List<String> warnings) {
    }

    private record NoArgs() {
    }

    private record DeviceIdArgs(String deviceId) {
    }

    private record PoolIdArgs(String poolId) {
    }

    private record RunIdArgs(String runId) {
    }

    private record RunTargetIdArgs(String runTargetId) {
    }

    private record TaskIdArgs(String taskId) {
    }

    private record AttemptIdArgs(String attemptId) {
    }

    private record PlanRequestIdArgs(String planRequestId) {
    }

    private record SummaryIdArgs(String summaryId) {
    }

    private record TriageResultIdArgs(String triageResultId) {
    }

    private record DraftRunPlanArgs(String goal, Map<String, Object> constraints) {
    }

    private record MaterializeRunPlanArgs(String planRequestId, String createdBy) {
    }

    private record CreateDevicePoolArgs(
            String name,
            String description,
            String hostGroup,
            List<String> deviceIds,
            List<String> requiredTags,
            List<String> excludedTags,
            String createdBy
    ) {
    }

    private record CreateTaskArgs(
            String taskType,
            String profilePackage,
            Map<String, Object> taskPayload,
            Map<String, Object> runConfig,
            Map<String, Object> artifactPolicy,
            Integer priority,
            List<String> labels,
            String source,
            String createdBy,
            String idempotencyKey
    ) {
    }

    private record CreateRunArgs(
            String name,
            String description,
            String devicePoolId,
            String taskType,
            String profilePackage,
            Map<String, Object> taskPayload,
            Map<String, Object> runConfig,
            Map<String, Object> artifactPolicy,
            Integer priority,
            List<String> labels,
            String source,
            String createdBy,
            Integer maxRetriesPerDevice,
            Long queueTimeoutMs
    ) {
    }

    private record SendDeviceCommandArgs(
            String deviceId,
            String type,
            String attemptId,
            Long expireInMs
    ) {
    }

    private record CreateSingleDeviceRunArgs(
            String name,
            String description,
            String deviceId,
            String taskType,
            String profilePackage,
            Map<String, Object> taskPayload,
            Map<String, Object> runConfig,
            Map<String, Object> artifactPolicy,
            Integer priority,
            List<String> labels,
            String source,
            String createdBy,
            Integer maxRetriesPerDevice,
            Long queueTimeoutMs
    ) {
    }

    private record ProposeGovernedActionArgs(
            String proposalId,
            String actionToolName,
            Map<String, Object> arguments,
            String targetKind,
            String targetId,
            String rationale,
            Map<String, Object> preconditions,
            Double confidence
    ) {
    }

    private record RunPlanningCatalogResult(
            List<Phase3AiModels.AvailableDevicePool> availableDevicePools,
            List<Phase3AiModels.AvailableProfile> availableProfiles,
            Phase3AiModels.DefaultRunPolicy defaultRunPolicy,
            List<String> allowedTaskTypes
    ) {
    }

    private record RunAttemptCounts(
            int total,
            int running,
            int failed,
            int succeeded
    ) {
    }

    private record RunGovernanceSnapshotResult(
            String runId,
            String status,
            AdminApiModels.RunStatusCounts targetCounts,
            RunAttemptCounts attemptCounts,
            List<String> latestAttemptIds,
            List<String> blockers,
            long lastUpdatedAt
    ) {
    }

    private record RunBlockageSummaryResult(
            String runId,
            String blockageCategory,
            String blockageReason,
            boolean retryable,
            List<String> missingInputs,
            String recommendedAction
    ) {
    }

    private record RunRecoveryOptionsResult(
            String runId,
            List<String> allowedActions,
            String recommendedAction,
            boolean requiresUserInput,
            boolean requiresApproval,
            String explanation
    ) {
    }

    private record RunLineageSnapshotResult(
            String runId,
            AdminApiModels.ExperimentRunDetailResponse run,
            List<AdminApiModels.ExperimentRunTargetResponse> targets,
            List<AdminApiModels.AttemptSummary> attempts,
            List<ToolApiModels.AttemptArtifactResource> latestArtifacts,
            List<ToolApiModels.AuditTimelineEntry> auditRefs,
            List<String> blockers,
            List<String> currentGovernedOptions
    ) {
    }

    private record AttemptDiagnosisBundleResult(
            String attemptId,
            String status,
            List<AdminApiModels.RunEventResponse> keyEvents,
            String normalizedArtifactSummary,
            List<String> failureSignals,
            Map<String, Object> confidenceHints,
            String summary
    ) {
    }

    private record RecoveryGuidanceContextResult(
            String entityKind,
            String entityId,
            List<String> allowedActions,
            String recommendedAction,
            boolean requiresApproval,
            List<String> requiredInputs,
            List<String> prerequisites,
            List<String> stopConditions,
            String stopConditionsSummary,
            String whyNotOthers,
            String explanation,
            double confidence
    ) {
    }

    private record AttemptDetailResult(
            AdminApiModels.AttemptSummary attempt,
            List<AdminApiModels.RunEventResponse> events,
            List<ToolApiModels.AttemptArtifactResource> artifacts
    ) {
    }

    private record RunActionResult(String runId, boolean accepted, String status) {
    }

    private record GovernedProposalResult(
            String proposalId,
            String proposalState,
            String actionToolName,
            String targetKind,
            String targetId,
            Map<String, Object> preconditions,
            String rationale,
            String consistencyStatus,
            long executedAt,
            Object executedAction
    ) {
    }

    private record TaskActionResult(String taskId, boolean accepted, String status) {
    }
}

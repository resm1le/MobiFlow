package com.example.platform.control.application;

import com.example.platform.control.api.AdminApiModels.CreateExperimentRunRequest;
import com.example.platform.control.api.AdminApiModels.ExperimentRunDetailResponse;
import com.example.platform.control.api.AiRunPlanApiModels;
import com.example.platform.control.domain.DomainValues;
import com.example.platform.control.domain.PersistenceModels.AiRunPlanRequestEntity;
import com.example.platform.control.domain.PersistenceModels.AiRunPlanResultEntity;
import com.example.platform.control.infrastructure.mapper.AiRunPlanRequestMapper;
import com.example.platform.control.infrastructure.mapper.AiRunPlanResultMapper;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

import java.time.Clock;
import java.util.List;
import java.util.Map;

@Service
public class AiRunPlanningService {

    private static final String RUN_PLAN_SOURCE = "ai-run-planning";

    private final RunPlanningContextBuilder runPlanningContextBuilder;
    private final Phase3AiAuditService phase3AiAuditService;
    private final AiBridgeClient aiBridgeClient;
    private final RunDraftSemanticValidator runDraftSemanticValidator;
    private final AiRunPlanRequestMapper aiRunPlanRequestMapper;
    private final AiRunPlanResultMapper aiRunPlanResultMapper;
    private final ExperimentRunService experimentRunService;
    private final JsonCodec jsonCodec;
    private final Clock clock = Clock.systemUTC();

    public AiRunPlanningService(RunPlanningContextBuilder runPlanningContextBuilder,
                                Phase3AiAuditService phase3AiAuditService,
                                AiBridgeClient aiBridgeClient,
                                RunDraftSemanticValidator runDraftSemanticValidator,
                                AiRunPlanRequestMapper aiRunPlanRequestMapper,
                                AiRunPlanResultMapper aiRunPlanResultMapper,
                                ExperimentRunService experimentRunService,
                                JsonCodec jsonCodec) {
        this.runPlanningContextBuilder = runPlanningContextBuilder;
        this.phase3AiAuditService = phase3AiAuditService;
        this.aiBridgeClient = aiBridgeClient;
        this.runDraftSemanticValidator = runDraftSemanticValidator;
        this.aiRunPlanRequestMapper = aiRunPlanRequestMapper;
        this.aiRunPlanResultMapper = aiRunPlanResultMapper;
        this.experimentRunService = experimentRunService;
        this.jsonCodec = jsonCodec;
    }

    @Transactional
    public AiRunPlanApiModels.CreateRunPlanResponse createRunPlan(AiRunPlanApiModels.CreateRunPlanRequest request) {
        Phase3AiModels.RunPlanningContext context = runPlanningContextBuilder.build(
                request.goal(),
                request.constraints() == null ? Map.of() : request.constraints()
        );
        if (context.availableDevicePools().isEmpty() || context.availableProfiles().isEmpty()) {
            throw ControlApiExceptions.badRequest(ControlErrorCode.AI_RUN_PLAN_CONTEXT_UNAVAILABLE);
        }
        String requestId = phase3AiAuditService.recordRunPlanningRequest(context);
        try {
            AiBridgeModels.RunPlanResponse bridgeResponse = aiBridgeClient.createRunPlan(context);
            Phase3AiModels.RunDraftResult result = requireCanonicalRunDraftResult(bridgeResponse);
            Phase3AiModels.ValidationResult validation = runDraftSemanticValidator.validate(result);
            phase3AiAuditService.recordRunPlanningResult(requestId, result, validation, bridgeResponse.modelMeta());
            return new AiRunPlanApiModels.CreateRunPlanResponse(
                    requestId,
                    result.runDraft(),
                    result.warnings(),
                    result.reviewHints(),
                    new AiRunPlanApiModels.PlanValidationResponse(
                            validation.valid(),
                            validation.errors(),
                            validation.warnings()
                    ),
                    bridgeResponse.modelMeta() == null ? Map.of() : bridgeResponse.modelMeta()
            );
        } catch (ResponseStatusException exception) {
            phase3AiAuditService.markRunPlanningRequestFailed(requestId);
            throw exception;
        } catch (RuntimeException exception) {
            phase3AiAuditService.markRunPlanningRequestFailed(requestId);
            throw exception;
        }
    }

    @Transactional
    public ExperimentRunDetailResponse materializeRunPlan(String requestId, String createdBy) {
        AiRunPlanRequestEntity requestEntity = aiRunPlanRequestMapper.lockById(requestId);
        if (requestEntity == null) {
            throw ControlApiExceptions.notFound(ControlErrorCode.AI_RUN_PLAN_NOT_FOUND);
        }
        if (requestEntity.getMaterializedRunId() != null) {
            throw ControlApiExceptions.conflict(ControlErrorCode.AI_RUN_PLAN_ALREADY_MATERIALIZED);
        }
        if (!DomainValues.AI_RUN_PLAN_STATUS_READY.equals(requestEntity.getStatus())) {
            throw ControlApiExceptions.conflict(ControlErrorCode.AI_RUN_PLAN_NOT_READY);
        }

        AiRunPlanResultEntity resultEntity = aiRunPlanResultMapper.findById(requestId);
        if (resultEntity == null) {
            throw ControlApiExceptions.conflict(ControlErrorCode.AI_RUN_PLAN_NOT_READY);
        }
        Phase3AiModels.RunDraftResult storedResult = jsonCodec.read(resultEntity.getResultJson(), Phase3AiModels.RunDraftResult.class);
        Phase3AiModels.ValidationResult storedValidation = jsonCodec.read(resultEntity.getValidationJson(), Phase3AiModels.ValidationResult.class);
        if (storedResult == null || storedValidation == null) {
            throw ControlApiExceptions.badRequest(ControlErrorCode.AI_RUN_PLAN_INVALID);
        }

        Phase3AiModels.RunPlanningContext context = runPlanningContextBuilder.build(
                requestEntity.getGoalText(),
                jsonCodec.readMap(requestEntity.getConstraintsJson())
        );
        Phase3AiModels.ValidationResult currentValidation = runDraftSemanticValidator.validate(storedResult);
        if (!storedValidation.valid() || !currentValidation.valid()) {
            throw ControlApiExceptions.badRequest(ControlErrorCode.AI_RUN_PLAN_INVALID);
        }

        ExperimentRunDetailResponse run = experimentRunService.createRun(new CreateExperimentRunRequest(
                storedResult.runDraft().name(),
                storedResult.runDraft().description(),
                storedResult.runDraft().devicePoolId(),
                storedResult.runDraft().taskType(),
                storedResult.runDraft().profilePackage(),
                storedResult.runDraft().taskPayload(),
                toRunConfig(storedResult.runDraft().runConfig()),
                toArtifactPolicy(storedResult.runDraft().artifactPolicy()),
                storedResult.runDraft().priority(),
                storedResult.runDraft().labels(),
                RUN_PLAN_SOURCE,
                createdBy,
                storedResult.runDraft().maxRetriesPerDevice(),
                storedResult.runDraft().queueTimeoutMs()
        ));

        long now = clock.millis();
        requestEntity.setStatus(DomainValues.AI_RUN_PLAN_STATUS_MATERIALIZED);
        requestEntity.setMaterializedRunId(run.run().runId());
        requestEntity.setMaterializedBy(createdBy);
        requestEntity.setMaterializedAt(now);
        requestEntity.setUpdatedAt(now);
        aiRunPlanRequestMapper.updateMaterialization(requestEntity);
        return run;
    }

    @Transactional(readOnly = true)
    public AiRunPlanApiModels.RunPlanResponse getRunPlan(String requestId) {
        AiRunPlanRequestEntity requestEntity = aiRunPlanRequestMapper.findById(requestId);
        if (requestEntity == null) {
            throw ControlApiExceptions.notFound(ControlErrorCode.AI_RUN_PLAN_NOT_FOUND);
        }
        AiRunPlanResultEntity resultEntity = aiRunPlanResultMapper.findById(requestId);
        if (resultEntity == null || resultEntity.getResultJson() == null || resultEntity.getValidationJson() == null) {
            throw ControlApiExceptions.notFound(ControlErrorCode.AI_RUN_PLAN_NOT_FOUND);
        }
        Phase3AiModels.RunDraftResult result = jsonCodec.read(resultEntity.getResultJson(), Phase3AiModels.RunDraftResult.class);
        Phase3AiModels.ValidationResult validation = jsonCodec.read(resultEntity.getValidationJson(), Phase3AiModels.ValidationResult.class);
        if (result == null || validation == null) {
            throw ControlApiExceptions.notFound(ControlErrorCode.AI_RUN_PLAN_NOT_FOUND);
        }
        return new AiRunPlanApiModels.RunPlanResponse(
                requestEntity.getRequestId(),
                requestEntity.getStatus(),
                requestEntity.getGoalText(),
                jsonCodec.readMap(requestEntity.getConstraintsJson()),
                result.runDraft(),
                result.warnings(),
                result.reviewHints(),
                new AiRunPlanApiModels.PlanValidationResponse(
                        validation.valid(),
                        validation.errors(),
                        validation.warnings()
                ),
                resultEntity.getModelMetaJson() == null ? Map.of() : jsonCodec.readMap(resultEntity.getModelMetaJson()),
                requestEntity.getMaterializedRunId(),
                requestEntity.getMaterializedBy(),
                requestEntity.getMaterializedAt(),
                resultEntity.getCreatedAt()
        );
    }

    private Phase3AiModels.RunDraftResult requireCanonicalRunDraftResult(AiBridgeModels.RunPlanResponse response) {
        if (response == null || response.runDraft() == null) {
            throw ControlApiExceptions.badGateway(ControlErrorCode.AI_PROVIDER_FAILURE);
        }
        return new Phase3AiModels.RunDraftResult(
                response.runDraft(),
                response.warnings() == null ? List.of() : response.warnings(),
                response.reviewHints() == null ? List.of() : response.reviewHints()
        );
    }

    private com.example.platform.control.api.ExecutorApiModels.RunConfig toRunConfig(Map<String, Object> map) {
        return new com.example.platform.control.api.ExecutorApiModels.RunConfig(
                ((Number) map.get("loopCount")).intValue(),
                ((Number) map.get("budgetMs")).longValue(),
                ((Number) map.get("loopIntervalMs")).longValue(),
                Boolean.TRUE.equals(map.get("networkIsolationEnabled")),
                ((Number) map.get("pollIntervalMs")).longValue(),
                ((Number) map.get("heartbeatIntervalMs")).longValue()
        );
    }

    private com.example.platform.control.api.ExecutorApiModels.ArtifactPolicy toArtifactPolicy(Map<String, Object> map) {
        return new com.example.platform.control.api.ExecutorApiModels.ArtifactPolicy(
                Boolean.TRUE.equals(map.get("uploadLog")),
                Boolean.TRUE.equals(map.get("uploadScreenshot")),
                Boolean.TRUE.equals(map.get("uploadDump"))
        );
    }
}

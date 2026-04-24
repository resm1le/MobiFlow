package com.example.platform.control.application;

import com.example.platform.control.api.AiFailureTriageApiModels;
import com.example.platform.control.domain.DomainValues;
import com.example.platform.control.domain.PersistenceModels.AiFailureTriageResultEntity;
import com.example.platform.control.infrastructure.mapper.AiFailureTriageResultMapper;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

import java.time.Clock;
import java.util.Map;

@Service
public class AiFailureTriageService {

    private final FailureTriageContextBuilder failureTriageContextBuilder;
    private final Phase3AiAuditService phase3AiAuditService;
    private final AiBridgeClient aiBridgeClient;
    private final FailureTriageSemanticValidator failureTriageSemanticValidator;
    private final AiFailureTriageResultMapper aiFailureTriageResultMapper;
    private final JsonCodec jsonCodec;
    private final Clock clock = Clock.systemUTC();

    public AiFailureTriageService(FailureTriageContextBuilder failureTriageContextBuilder,
                                  Phase3AiAuditService phase3AiAuditService,
                                  AiBridgeClient aiBridgeClient,
                                  FailureTriageSemanticValidator failureTriageSemanticValidator,
                                  AiFailureTriageResultMapper aiFailureTriageResultMapper,
                                  JsonCodec jsonCodec) {
        this.failureTriageContextBuilder = failureTriageContextBuilder;
        this.phase3AiAuditService = phase3AiAuditService;
        this.aiBridgeClient = aiBridgeClient;
        this.failureTriageSemanticValidator = failureTriageSemanticValidator;
        this.aiFailureTriageResultMapper = aiFailureTriageResultMapper;
        this.jsonCodec = jsonCodec;
    }

    @Transactional
    public AiFailureTriageApiModels.FailureTriageResponse createFailureTriage(String runTargetId) {
        Phase3AiModels.FailureTriageContext context = failureTriageContextBuilder.build(runTargetId);
        validateTargetEligibility(context);
        String triageResultId = phase3AiAuditService.recordFailureTriageContext(
                context.run().runId(),
                runTargetId,
                context.latestAttempt().attemptId(),
                context
        );
        try {
            AiBridgeModels.FailureTriageResponse bridgeResponse = aiBridgeClient.createFailureTriage(context);
            Phase3AiModels.FailureTriageResult result = requireCanonicalFailureTriageResult(bridgeResponse);
            Phase3AiModels.ValidationResult validation = failureTriageSemanticValidator.validate(result);
            phase3AiAuditService.recordFailureTriageResult(triageResultId, result, validation, bridgeResponse.modelMeta());
            return new AiFailureTriageApiModels.FailureTriageResponse(
                    triageResultId,
                    runTargetId,
                    result,
                    new AiFailureTriageApiModels.ValidationResponse(
                            validation.valid(),
                            validation.errors(),
                            validation.warnings()
                    ),
                    bridgeResponse.modelMeta() == null ? Map.of() : bridgeResponse.modelMeta(),
                    clock.millis()
            );
        } catch (ResponseStatusException exception) {
            phase3AiAuditService.markFailureTriageFailed(triageResultId);
            throw exception;
        } catch (RuntimeException exception) {
            phase3AiAuditService.markFailureTriageFailed(triageResultId);
            throw exception;
        }
    }

    @Transactional(readOnly = true)
    public AiFailureTriageApiModels.FailureTriageResponse getLatestFailureTriage(String runTargetId) {
        AiFailureTriageResultEntity entity = aiFailureTriageResultMapper.findLatestByRunTargetId(runTargetId);
        return toApiResponse(requireCompletedResult(entity));
    }

    @Transactional(readOnly = true)
    public AiFailureTriageApiModels.FailureTriageResponse getFailureTriage(String triageResultId) {
        AiFailureTriageResultEntity entity = aiFailureTriageResultMapper.findById(triageResultId);
        return toApiResponse(requireCompletedResult(entity));
    }

    private void validateTargetEligibility(Phase3AiModels.FailureTriageContext context) {
        if (context.target().latestAttemptId() == null || context.latestAttempt().attemptId() == null) {
            throw ControlApiExceptions.badRequest(ControlErrorCode.AI_FAILURE_TRIAGE_NOT_ALLOWED);
        }
        String status = context.target().status();
        if (!DomainValues.RUN_TARGET_STATUS_FAILED.equals(status)
                && !DomainValues.RUN_TARGET_STATUS_CANCELLED.equals(status)) {
            throw ControlApiExceptions.badRequest(ControlErrorCode.AI_FAILURE_TRIAGE_NOT_ALLOWED);
        }
    }

    private Phase3AiModels.FailureTriageResult requireCanonicalFailureTriageResult(AiBridgeModels.FailureTriageResponse response) {
        if (response == null || response.result() == null) {
            throw ControlApiExceptions.badGateway(ControlErrorCode.AI_PROVIDER_FAILURE);
        }
        return response.result();
    }

    private AiFailureTriageResultEntity requireCompletedResult(AiFailureTriageResultEntity entity) {
        if (entity == null || entity.getResultJson() == null || entity.getValidationJson() == null) {
            throw ControlApiExceptions.notFound(ControlErrorCode.AI_FAILURE_TRIAGE_NOT_FOUND);
        }
        return entity;
    }

    private AiFailureTriageApiModels.FailureTriageResponse toApiResponse(AiFailureTriageResultEntity entity) {
        Phase3AiModels.FailureTriageResult result = jsonCodec.read(entity.getResultJson(), Phase3AiModels.FailureTriageResult.class);
        Phase3AiModels.ValidationResult validation = jsonCodec.read(entity.getValidationJson(), Phase3AiModels.ValidationResult.class);
        if (result == null || validation == null) {
            throw ControlApiExceptions.notFound(ControlErrorCode.AI_FAILURE_TRIAGE_NOT_FOUND);
        }
        return new AiFailureTriageApiModels.FailureTriageResponse(
                entity.getTriageResultId(),
                entity.getRunTargetId(),
                result,
                new AiFailureTriageApiModels.ValidationResponse(
                        validation.valid(),
                        validation.errors(),
                        validation.warnings()
                ),
                entity.getModelMetaJson() == null ? Map.of() : jsonCodec.readMap(entity.getModelMetaJson()),
                entity.getCreatedAt()
        );
    }
}

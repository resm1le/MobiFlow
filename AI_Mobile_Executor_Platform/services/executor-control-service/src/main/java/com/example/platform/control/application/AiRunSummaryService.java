package com.example.platform.control.application;

import com.example.platform.control.api.AiRunSummaryApiModels;
import com.example.platform.control.domain.PersistenceModels.AiRunSummaryResultEntity;
import com.example.platform.control.infrastructure.mapper.AiRunSummaryResultMapper;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

import java.time.Clock;
import java.util.Map;

@Service
public class AiRunSummaryService {

    private final RunSummaryContextBuilder runSummaryContextBuilder;
    private final Phase3AiAuditService phase3AiAuditService;
    private final AiBridgeClient aiBridgeClient;
    private final RunSummarySemanticValidator runSummarySemanticValidator;
    private final AiRunSummaryResultMapper aiRunSummaryResultMapper;
    private final JsonCodec jsonCodec;
    private final Clock clock = Clock.systemUTC();

    public AiRunSummaryService(RunSummaryContextBuilder runSummaryContextBuilder,
                               Phase3AiAuditService phase3AiAuditService,
                               AiBridgeClient aiBridgeClient,
                               RunSummarySemanticValidator runSummarySemanticValidator,
                               AiRunSummaryResultMapper aiRunSummaryResultMapper,
                               JsonCodec jsonCodec) {
        this.runSummaryContextBuilder = runSummaryContextBuilder;
        this.phase3AiAuditService = phase3AiAuditService;
        this.aiBridgeClient = aiBridgeClient;
        this.runSummarySemanticValidator = runSummarySemanticValidator;
        this.aiRunSummaryResultMapper = aiRunSummaryResultMapper;
        this.jsonCodec = jsonCodec;
    }

    @Transactional
    public AiRunSummaryApiModels.RunSummaryResponse createRunSummary(String runId) {
        Phase3AiModels.RunSummaryContext context = runSummaryContextBuilder.build(runId);
        String summaryId = phase3AiAuditService.recordRunSummaryContext(runId, context);
        try {
            AiBridgeModels.RunSummaryResponse bridgeResponse = aiBridgeClient.createRunSummary(context);
            Phase3AiModels.RunSummaryResult result = requireCanonicalResult(bridgeResponse);
            Phase3AiModels.ValidationResult validation = runSummarySemanticValidator.validate(result);
            phase3AiAuditService.recordRunSummaryResult(summaryId, result, validation, bridgeResponse.modelMeta());
            return new AiRunSummaryApiModels.RunSummaryResponse(
                    summaryId,
                    runId,
                    result,
                    new AiRunSummaryApiModels.ValidationResponse(
                            validation.valid(),
                            validation.errors(),
                            validation.warnings()
                    ),
                    bridgeResponse.modelMeta() == null ? Map.of() : bridgeResponse.modelMeta(),
                    clock.millis()
            );
        } catch (ResponseStatusException exception) {
            phase3AiAuditService.markRunSummaryFailed(summaryId);
            throw exception;
        } catch (RuntimeException exception) {
            phase3AiAuditService.markRunSummaryFailed(summaryId);
            throw exception;
        }
    }

    @Transactional(readOnly = true)
    public AiRunSummaryApiModels.RunSummaryResponse getLatestRunSummary(String runId) {
        AiRunSummaryResultEntity entity = aiRunSummaryResultMapper.findLatestByRunId(runId);
        return toApiResponse(requireCompletedResult(entity));
    }

    @Transactional(readOnly = true)
    public AiRunSummaryApiModels.RunSummaryResponse getRunSummary(String summaryId) {
        AiRunSummaryResultEntity entity = aiRunSummaryResultMapper.findById(summaryId);
        return toApiResponse(requireCompletedResult(entity));
    }

    private Phase3AiModels.RunSummaryResult requireCanonicalResult(AiBridgeModels.RunSummaryResponse response) {
        if (response == null || response.result() == null) {
            throw ControlApiExceptions.badGateway(ControlErrorCode.AI_PROVIDER_FAILURE);
        }
        return response.result();
    }

    private AiRunSummaryResultEntity requireCompletedResult(AiRunSummaryResultEntity entity) {
        if (entity == null || entity.getResultJson() == null || entity.getValidationJson() == null) {
            throw ControlApiExceptions.notFound(ControlErrorCode.AI_RUN_SUMMARY_NOT_FOUND);
        }
        return entity;
    }

    private AiRunSummaryApiModels.RunSummaryResponse toApiResponse(AiRunSummaryResultEntity entity) {
        Phase3AiModels.RunSummaryResult result = jsonCodec.read(entity.getResultJson(), Phase3AiModels.RunSummaryResult.class);
        Phase3AiModels.ValidationResult validation = jsonCodec.read(entity.getValidationJson(), Phase3AiModels.ValidationResult.class);
        if (result == null || validation == null) {
            throw ControlApiExceptions.notFound(ControlErrorCode.AI_RUN_SUMMARY_NOT_FOUND);
        }
        return new AiRunSummaryApiModels.RunSummaryResponse(
                entity.getSummaryId(),
                entity.getRunId(),
                result,
                new AiRunSummaryApiModels.ValidationResponse(
                        validation.valid(),
                        validation.errors(),
                        validation.warnings()
                ),
                entity.getModelMetaJson() == null ? Map.of() : jsonCodec.readMap(entity.getModelMetaJson()),
                entity.getCreatedAt()
        );
    }
}

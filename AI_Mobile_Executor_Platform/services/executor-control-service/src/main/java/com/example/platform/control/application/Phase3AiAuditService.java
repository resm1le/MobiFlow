package com.example.platform.control.application;

import com.example.platform.control.domain.DomainValues;
import com.example.platform.control.domain.PersistenceModels.AiFailureTriageResultEntity;
import com.example.platform.control.domain.PersistenceModels.AiRunPlanRequestEntity;
import com.example.platform.control.domain.PersistenceModels.AiRunPlanResultEntity;
import com.example.platform.control.domain.PersistenceModels.AiRunSummaryResultEntity;
import com.example.platform.control.infrastructure.mapper.AiFailureTriageResultMapper;
import com.example.platform.control.infrastructure.mapper.AiRunPlanRequestMapper;
import com.example.platform.control.infrastructure.mapper.AiRunPlanResultMapper;
import com.example.platform.control.infrastructure.mapper.AiRunSummaryResultMapper;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Clock;
import java.util.Map;

@Service
public class Phase3AiAuditService {

    private final AiRunPlanRequestMapper aiRunPlanRequestMapper;
    private final AiRunPlanResultMapper aiRunPlanResultMapper;
    private final AiFailureTriageResultMapper aiFailureTriageResultMapper;
    private final AiRunSummaryResultMapper aiRunSummaryResultMapper;
    private final JsonCodec jsonCodec;
    private final IdGenerator idGenerator;
    private final Clock clock = Clock.systemUTC();

    public Phase3AiAuditService(AiRunPlanRequestMapper aiRunPlanRequestMapper,
                                AiRunPlanResultMapper aiRunPlanResultMapper,
                                AiFailureTriageResultMapper aiFailureTriageResultMapper,
                                AiRunSummaryResultMapper aiRunSummaryResultMapper,
                                JsonCodec jsonCodec,
                                IdGenerator idGenerator) {
        this.aiRunPlanRequestMapper = aiRunPlanRequestMapper;
        this.aiRunPlanResultMapper = aiRunPlanResultMapper;
        this.aiFailureTriageResultMapper = aiFailureTriageResultMapper;
        this.aiRunSummaryResultMapper = aiRunSummaryResultMapper;
        this.jsonCodec = jsonCodec;
        this.idGenerator = idGenerator;
    }

    @Transactional
    public String recordRunPlanningRequest(Phase3AiModels.RunPlanningContext context) {
        long now = clock.millis();
        String requestId = idGenerator.nextAiRunPlanRequestId();
        AiRunPlanRequestEntity entity = new AiRunPlanRequestEntity();
        entity.setRequestId(requestId);
        entity.setGoalText(context.goal());
        entity.setConstraintsJson(jsonCodec.write(context.constraints()));
        entity.setContextJson(jsonCodec.write(context));
        entity.setStatus(DomainValues.AI_RUN_PLAN_STATUS_CREATED);
        entity.setMaterializedRunId(null);
        entity.setMaterializedBy(null);
        entity.setMaterializedAt(null);
        entity.setCreatedAt(now);
        entity.setUpdatedAt(now);
        aiRunPlanRequestMapper.insert(entity);
        return requestId;
    }

    @Transactional
    public void markRunPlanningRequestFailed(String requestId) {
        aiRunPlanRequestMapper.updateStatus(requestId, DomainValues.AI_RUN_PLAN_STATUS_FAILED, clock.millis());
    }

    @Transactional
    public void recordRunPlanningResult(String requestId,
                                        Phase3AiModels.RunDraftResult result,
                                        Phase3AiModels.ValidationResult validation,
                                        Map<String, Object> modelMeta) {
        long now = clock.millis();
        AiRunPlanResultEntity entity = new AiRunPlanResultEntity();
        entity.setRequestId(requestId);
        entity.setResultJson(jsonCodec.write(result));
        entity.setValidationJson(jsonCodec.write(validation));
        entity.setModelMetaJson(jsonCodec.write(modelMeta == null ? Map.of() : modelMeta));
        entity.setStatus(validation.valid() ? DomainValues.AI_RUN_PLAN_STATUS_READY : DomainValues.AI_RUN_PLAN_STATUS_FAILED);
        entity.setCreatedAt(now);
        entity.setUpdatedAt(now);
        if (aiRunPlanResultMapper.findById(requestId) == null) {
            aiRunPlanResultMapper.insert(entity);
        } else {
            aiRunPlanResultMapper.upsert(entity);
        }
        aiRunPlanRequestMapper.updateStatus(requestId, entity.getStatus(), now);
    }

    @Transactional
    public String recordFailureTriageContext(String runId,
                                             String runTargetId,
                                             String attemptId,
                                             Phase3AiModels.FailureTriageContext context) {
        long now = clock.millis();
        String triageResultId = idGenerator.nextAiFailureTriageResultId();
        AiFailureTriageResultEntity entity = new AiFailureTriageResultEntity();
        entity.setTriageResultId(triageResultId);
        entity.setRunId(runId);
        entity.setRunTargetId(runTargetId);
        entity.setAttemptId(attemptId);
        entity.setContextJson(jsonCodec.write(context));
        entity.setStatus(DomainValues.AI_TRIAGE_STATUS_CREATED);
        entity.setCreatedAt(now);
        entity.setUpdatedAt(now);
        aiFailureTriageResultMapper.insert(entity);
        return triageResultId;
    }

    @Transactional
    public void recordFailureTriageResult(String triageResultId,
                                          Phase3AiModels.FailureTriageResult result,
                                          Phase3AiModels.ValidationResult validation,
                                          Map<String, Object> modelMeta) {
        AiFailureTriageResultEntity existing = aiFailureTriageResultMapper.findById(triageResultId);
        if (existing == null) {
            throw ControlApiExceptions.notFound(ControlErrorCode.AI_FAILURE_TRIAGE_NOT_FOUND);
        }
        long now = clock.millis();
        existing.setResultJson(jsonCodec.write(result));
        existing.setValidationJson(jsonCodec.write(validation));
        existing.setModelMetaJson(jsonCodec.write(modelMeta == null ? Map.of() : modelMeta));
        existing.setStatus(validation.valid() ? DomainValues.AI_TRIAGE_STATUS_READY : DomainValues.AI_TRIAGE_STATUS_FAILED);
        existing.setUpdatedAt(now);
        aiFailureTriageResultMapper.update(existing);
    }

    @Transactional
    public void markFailureTriageFailed(String triageResultId) {
        AiFailureTriageResultEntity existing = aiFailureTriageResultMapper.findById(triageResultId);
        if (existing == null) {
            throw ControlApiExceptions.notFound(ControlErrorCode.AI_FAILURE_TRIAGE_NOT_FOUND);
        }
        existing.setStatus(DomainValues.AI_TRIAGE_STATUS_FAILED);
        existing.setUpdatedAt(clock.millis());
        aiFailureTriageResultMapper.update(existing);
    }

    @Transactional
    public String recordRunSummaryContext(String runId, Phase3AiModels.RunSummaryContext context) {
        long now = clock.millis();
        String summaryId = idGenerator.nextAiRunSummaryId();
        AiRunSummaryResultEntity entity = new AiRunSummaryResultEntity();
        entity.setSummaryId(summaryId);
        entity.setRunId(runId);
        entity.setContextJson(jsonCodec.write(context));
        entity.setStatus(DomainValues.AI_RUN_SUMMARY_STATUS_CREATED);
        entity.setCreatedAt(now);
        entity.setUpdatedAt(now);
        aiRunSummaryResultMapper.insert(entity);
        return summaryId;
    }

    @Transactional
    public void recordRunSummaryResult(String summaryId,
                                       Phase3AiModels.RunSummaryResult result,
                                       Phase3AiModels.ValidationResult validation,
                                       Map<String, Object> modelMeta) {
        AiRunSummaryResultEntity existing = aiRunSummaryResultMapper.findById(summaryId);
        if (existing == null) {
            throw ControlApiExceptions.notFound(ControlErrorCode.AI_RUN_SUMMARY_NOT_FOUND);
        }
        existing.setResultJson(jsonCodec.write(result));
        existing.setValidationJson(jsonCodec.write(validation));
        existing.setModelMetaJson(jsonCodec.write(modelMeta == null ? Map.of() : modelMeta));
        existing.setStatus(validation.valid() ? DomainValues.AI_RUN_SUMMARY_STATUS_READY : DomainValues.AI_RUN_SUMMARY_STATUS_FAILED);
        existing.setUpdatedAt(clock.millis());
        aiRunSummaryResultMapper.update(existing);
    }

    @Transactional
    public void markRunSummaryFailed(String summaryId) {
        AiRunSummaryResultEntity existing = aiRunSummaryResultMapper.findById(summaryId);
        if (existing == null) {
            throw ControlApiExceptions.notFound(ControlErrorCode.AI_RUN_SUMMARY_NOT_FOUND);
        }
        existing.setStatus(DomainValues.AI_RUN_SUMMARY_STATUS_FAILED);
        existing.setUpdatedAt(clock.millis());
        aiRunSummaryResultMapper.update(existing);
    }
}

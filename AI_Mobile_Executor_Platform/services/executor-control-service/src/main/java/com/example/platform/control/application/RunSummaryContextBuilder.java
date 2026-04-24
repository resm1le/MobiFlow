package com.example.platform.control.application;

import com.example.platform.control.domain.DomainValues;
import com.example.platform.control.domain.PersistenceModels.ArtifactEntity;
import com.example.platform.control.domain.PersistenceModels.ExperimentRunEntity;
import com.example.platform.control.domain.PersistenceModels.ExperimentRunTargetEntity;
import com.example.platform.control.domain.PersistenceModels.RunEventEntity;
import com.example.platform.control.domain.PersistenceModels.TaskAttemptEntity;
import com.example.platform.control.infrastructure.mapper.ArtifactMapper;
import com.example.platform.control.infrastructure.mapper.ExperimentRunMapper;
import com.example.platform.control.infrastructure.mapper.ExperimentRunTargetMapper;
import com.example.platform.control.infrastructure.mapper.RunEventMapper;
import com.example.platform.control.infrastructure.mapper.TaskAttemptMapper;
import org.springframework.stereotype.Component;

import java.util.Comparator;
import java.util.List;

@Component
public class RunSummaryContextBuilder {

    private static final int REPRESENTATIVE_ATTEMPT_LIMIT = 5;
    private static final int KEY_EVENT_LIMIT = 30;
    private static final int ARTIFACT_LIMIT = 20;

    private final ExperimentRunMapper experimentRunMapper;
    private final ExperimentRunTargetMapper experimentRunTargetMapper;
    private final TaskAttemptMapper taskAttemptMapper;
    private final RunEventMapper runEventMapper;
    private final ArtifactMapper artifactMapper;
    private final JsonCodec jsonCodec;

    public RunSummaryContextBuilder(ExperimentRunMapper experimentRunMapper,
                                    ExperimentRunTargetMapper experimentRunTargetMapper,
                                    TaskAttemptMapper taskAttemptMapper,
                                    RunEventMapper runEventMapper,
                                    ArtifactMapper artifactMapper,
                                    JsonCodec jsonCodec) {
        this.experimentRunMapper = experimentRunMapper;
        this.experimentRunTargetMapper = experimentRunTargetMapper;
        this.taskAttemptMapper = taskAttemptMapper;
        this.runEventMapper = runEventMapper;
        this.artifactMapper = artifactMapper;
        this.jsonCodec = jsonCodec;
    }

    public Phase3AiModels.RunSummaryContext build(String runId) {
        ExperimentRunEntity run = experimentRunMapper.findById(runId);
        if (run == null) {
            throw ControlApiExceptions.notFound(ControlErrorCode.EXPERIMENT_RUN_NOT_FOUND);
        }
        List<ExperimentRunTargetEntity> targets = experimentRunTargetMapper.findByRunId(runId);
        List<TaskAttemptEntity> representativeAttempts = targets.stream()
                .map(ExperimentRunTargetEntity::getLatestAttemptId)
                .filter(attemptId -> attemptId != null && !attemptId.isBlank())
                .map(taskAttemptMapper::findById)
                .filter(attempt -> attempt != null)
                .sorted(Comparator.comparingLong(TaskAttemptEntity::getCreatedAt).reversed())
                .limit(REPRESENTATIVE_ATTEMPT_LIMIT)
                .toList();
        List<RunEventEntity> keyEvents = runEventMapper.findByRunId(runId).stream()
                .sorted(Comparator.comparingLong(RunEventEntity::getTs)
                        .thenComparing(event -> event.getId() == null ? Long.MAX_VALUE : event.getId()))
                .limit(KEY_EVENT_LIMIT)
                .toList();
        List<ArtifactEntity> artifacts = artifactMapper.findByRunId(runId).stream()
                .limit(ARTIFACT_LIMIT)
                .toList();
        return new Phase3AiModels.RunSummaryContext(
                toRunSummary(run),
                toCounts(targets),
                targets.stream().map(this::toRunTargetSummary).toList(),
                representativeAttempts.stream().map(this::toAttemptSummary).toList(),
                keyEvents.stream().map(this::toKeyEvent).toList(),
                artifacts.stream().map(this::toArtifactManifestItem).toList()
        );
    }

    private Phase3AiModels.RunSummary toRunSummary(ExperimentRunEntity run) {
        return new Phase3AiModels.RunSummary(
                run.getRunId(),
                run.getPoolId(),
                run.getStatus(),
                run.getFinalState(),
                run.getTaskType(),
                run.getProfilePackage(),
                run.getPriority(),
                jsonCodec.readStringList(run.getLabelsJson()),
                run.getMaxRetriesPerDevice(),
                run.getQueueTimeoutMs(),
                run.isCancelRequested(),
                run.getStartedAt(),
                run.getFinishedAt()
        );
    }

    private Phase3AiModels.RunCounts toCounts(List<ExperimentRunTargetEntity> targets) {
        int queued = 0;
        int running = 0;
        int retryPending = 0;
        int succeeded = 0;
        int failed = 0;
        int cancelled = 0;
        for (ExperimentRunTargetEntity target : targets) {
            switch (target.getStatus()) {
                case DomainValues.RUN_TARGET_STATUS_QUEUED -> queued++;
                case DomainValues.RUN_TARGET_STATUS_RUNNING -> running++;
                case DomainValues.RUN_TARGET_STATUS_RETRY_PENDING -> retryPending++;
                case DomainValues.RUN_TARGET_STATUS_SUCCEEDED -> succeeded++;
                case DomainValues.RUN_TARGET_STATUS_FAILED -> failed++;
                case DomainValues.RUN_TARGET_STATUS_CANCELLED -> cancelled++;
                default -> {
                }
            }
        }
        return new Phase3AiModels.RunCounts(targets.size(), queued, running, retryPending, succeeded, failed, cancelled);
    }

    private Phase3AiModels.RunTargetSummary toRunTargetSummary(ExperimentRunTargetEntity target) {
        return new Phase3AiModels.RunTargetSummary(
                target.getRunTargetId(),
                target.getDeviceId(),
                target.getStatus(),
                target.getAttemptCount(),
                target.getCurrentTaskId(),
                target.getLatestAttemptId(),
                target.getFailureReason(),
                target.getStartedAt(),
                target.getFinishedAt()
        );
    }

    private Phase3AiModels.AttemptSummary toAttemptSummary(TaskAttemptEntity attempt) {
        return new Phase3AiModels.AttemptSummary(
                attempt.getAttemptId(),
                attempt.getTaskId(),
                attempt.getDeviceId(),
                attempt.getRunId(),
                attempt.getStatus(),
                attempt.getFinalState(),
                attempt.getFailureReason(),
                jsonCodec.readMap(attempt.getPreflightSummaryJson()),
                jsonCodec.readMap(attempt.getFailureDetailJson()),
                attempt.getStartedAt(),
                attempt.getFinishedAt(),
                attempt.getCreatedAt()
        );
    }

    private Phase3AiModels.KeyEvent toKeyEvent(RunEventEntity event) {
        return new Phase3AiModels.KeyEvent(
                event.getEventType(),
                event.getState(),
                event.getCode(),
                event.getMessage(),
                event.getTs()
        );
    }

    private Phase3AiModels.ArtifactManifestItem toArtifactManifestItem(ArtifactEntity artifact) {
        return new Phase3AiModels.ArtifactManifestItem(
                artifact.getArtifactId(),
                artifact.getArtifactType(),
                artifact.getFileName(),
                artifact.getMimeType(),
                artifact.getSizeBytes(),
                artifact.getObjectKey()
        );
    }
}

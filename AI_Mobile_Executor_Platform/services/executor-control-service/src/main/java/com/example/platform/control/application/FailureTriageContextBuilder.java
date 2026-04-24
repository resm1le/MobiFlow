package com.example.platform.control.application;

import com.example.platform.control.domain.DomainValues;
import com.example.platform.control.domain.PersistenceModels.ArtifactEntity;
import com.example.platform.control.domain.PersistenceModels.DeviceEntity;
import com.example.platform.control.domain.PersistenceModels.DeviceRuntimeStateEntity;
import com.example.platform.control.domain.PersistenceModels.ExperimentRunEntity;
import com.example.platform.control.domain.PersistenceModels.ExperimentRunTargetEntity;
import com.example.platform.control.domain.PersistenceModels.RunEventEntity;
import com.example.platform.control.domain.PersistenceModels.TaskAttemptEntity;
import com.example.platform.control.infrastructure.mapper.ArtifactMapper;
import com.example.platform.control.infrastructure.mapper.DeviceMapper;
import com.example.platform.control.infrastructure.mapper.DeviceRuntimeStateMapper;
import com.example.platform.control.infrastructure.mapper.ExperimentRunMapper;
import com.example.platform.control.infrastructure.mapper.ExperimentRunTargetMapper;
import com.example.platform.control.infrastructure.mapper.RunEventMapper;
import com.example.platform.control.infrastructure.mapper.TaskAttemptMapper;
import org.springframework.stereotype.Component;

import java.util.Comparator;
import java.util.List;
import java.util.Map;

@Component
public class FailureTriageContextBuilder {

    private static final int HISTORY_LIMIT = 3;
    private static final int EVENT_LIMIT = 80;

    private final ExperimentRunMapper experimentRunMapper;
    private final ExperimentRunTargetMapper experimentRunTargetMapper;
    private final TaskAttemptMapper taskAttemptMapper;
    private final RunEventMapper runEventMapper;
    private final ArtifactMapper artifactMapper;
    private final DeviceMapper deviceMapper;
    private final DeviceRuntimeStateMapper runtimeStateMapper;
    private final JsonCodec jsonCodec;

    public FailureTriageContextBuilder(ExperimentRunMapper experimentRunMapper,
                                       ExperimentRunTargetMapper experimentRunTargetMapper,
                                       TaskAttemptMapper taskAttemptMapper,
                                       RunEventMapper runEventMapper,
                                       ArtifactMapper artifactMapper,
                                       DeviceMapper deviceMapper,
                                       DeviceRuntimeStateMapper runtimeStateMapper,
                                       JsonCodec jsonCodec) {
        this.experimentRunMapper = experimentRunMapper;
        this.experimentRunTargetMapper = experimentRunTargetMapper;
        this.taskAttemptMapper = taskAttemptMapper;
        this.runEventMapper = runEventMapper;
        this.artifactMapper = artifactMapper;
        this.deviceMapper = deviceMapper;
        this.runtimeStateMapper = runtimeStateMapper;
        this.jsonCodec = jsonCodec;
    }

    public Phase3AiModels.FailureTriageContext build(String runTargetId) {
        ExperimentRunTargetEntity target = experimentRunTargetMapper.findById(runTargetId);
        if (target == null) {
            throw ControlApiExceptions.notFound(ControlErrorCode.EXPERIMENT_RUN_NOT_FOUND);
        }
        ExperimentRunEntity run = experimentRunMapper.findById(target.getRunId());
        if (run == null) {
            throw ControlApiExceptions.notFound(ControlErrorCode.EXPERIMENT_RUN_NOT_FOUND);
        }
        TaskAttemptEntity latestAttempt = target.getLatestAttemptId() == null ? null : taskAttemptMapper.findById(target.getLatestAttemptId());
        if (latestAttempt == null) {
            throw ControlApiExceptions.notFound(ControlErrorCode.ATTEMPT_NOT_FOUND);
        }
        List<TaskAttemptEntity> attempts = taskAttemptMapper.findByRunTargetId(runTargetId, HISTORY_LIMIT);
        List<RunEventEntity> events = runEventMapper.findByAttemptId(latestAttempt.getAttemptId()).stream()
                .sorted(Comparator.comparingLong(RunEventEntity::getTs).thenComparing(event -> event.getId() == null ? Long.MAX_VALUE : event.getId()))
                .limit(EVENT_LIMIT)
                .toList();
        List<ArtifactEntity> artifacts = artifactMapper.findByAttemptId(latestAttempt.getAttemptId());
        return new Phase3AiModels.FailureTriageContext(
                toRunSummary(run),
                toRunTargetSummary(target),
                toAttemptSummary(latestAttempt),
                toAttemptHistorySummary(attempts),
                toFailureContext(latestAttempt, target),
                events.stream().map(this::toKeyEvent).toList(),
                artifacts.stream().map(this::toArtifactManifestItem).toList(),
                toDeviceOperationalSnapshot(target.getDeviceId(), latestAttempt)
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

    private Phase3AiModels.AttemptHistorySummary toAttemptHistorySummary(List<TaskAttemptEntity> attempts) {
        List<Phase3AiModels.AttemptHistoryEntry> recentAttempts = attempts.stream()
                .sorted(Comparator.comparingLong(TaskAttemptEntity::getCreatedAt).reversed())
                .limit(HISTORY_LIMIT)
                .map(attempt -> new Phase3AiModels.AttemptHistoryEntry(
                        attempt.getAttemptId(),
                        attempt.getStatus(),
                        attempt.getFinalState(),
                        attempt.getFailureReason(),
                        attempt.getFinishedAt(),
                        attempt.getDeviceId()
                ))
                .toList();
        boolean queueTimeoutObserved = attempts.stream().anyMatch(attempt -> "QUEUE_TIMEOUT".equals(attempt.getFailureReason()));
        boolean cancelObserved = attempts.stream().anyMatch(attempt ->
                "CANCELLED".equals(attempt.getFinalState()) || "RUN_CANCELLED".equals(attempt.getFailureReason()));
        return new Phase3AiModels.AttemptHistorySummary(attempts.size(), recentAttempts, queueTimeoutObserved, cancelObserved);
    }

    private Phase3AiModels.FailureContext toFailureContext(TaskAttemptEntity latestAttempt, ExperimentRunTargetEntity target) {
        Map<String, Object> preflight = jsonCodec.readMap(latestAttempt.getPreflightSummaryJson());
        Map<String, Object> failureDetail = jsonCodec.readMap(latestAttempt.getFailureDetailJson());
        String lastError = failureDetail.get("lastError") instanceof String text && !text.isBlank()
                ? text
                : latestAttempt.getFailureReason();
        boolean cancelled = "CANCELLED".equals(latestAttempt.getFinalState()) || "RUN_CANCELLED".equals(target.getFailureReason());
        boolean queueTimeout = "QUEUE_TIMEOUT".equals(target.getFailureReason()) || "QUEUE_TIMEOUT".equals(latestAttempt.getFailureReason());
        boolean leaseLost = DomainValues.ATTEMPT_STATUS_LEASE_EXPIRED.equals(latestAttempt.getStatus());
        boolean precheckFailed = DomainValues.ATTEMPT_STATUS_PRECHECK_FAILED.equals(latestAttempt.getStatus())
                || "PRECHECK_FAILED".equals(latestAttempt.getFinalState())
                || !preflight.isEmpty();
        return new Phase3AiModels.FailureContext(
                latestAttempt.getFinalState(),
                latestAttempt.getFailureReason(),
                lastError,
                queueTimeout,
                cancelled,
                leaseLost,
                precheckFailed,
                preflight,
                failureDetail
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

    private Phase3AiModels.DeviceOperationalSnapshot toDeviceOperationalSnapshot(String deviceId, TaskAttemptEntity latestAttempt) {
        DeviceEntity device = deviceMapper.findById(deviceId);
        DeviceRuntimeStateEntity runtime = runtimeStateMapper.findById(deviceId);
        Map<String, Object> health = runtime == null ? Map.of() : jsonCodec.readMap(runtime.getHealthJson());
        Map<String, Object> heartbeatHealth = nestedMap(health.get("healthSnapshot"));
        Map<String, Object> preflightSummary = jsonCodec.readMap(latestAttempt.getPreflightSummaryJson());
        Map<String, Object> failureDetail = jsonCodec.readMap(latestAttempt.getFailureDetailJson());
        Phase3AiModels.DeviceOperationalSnapshotType snapshotType;
        long capturedAt;
        if (!preflightSummary.isEmpty()) {
            snapshotType = Phase3AiModels.DeviceOperationalSnapshotType.PREFLIGHT;
            capturedAt = longValue(preflightSummary.get("capturedAt"), latestAttempt.getFinishedAt());
        } else if (!failureDetail.isEmpty()) {
            snapshotType = Phase3AiModels.DeviceOperationalSnapshotType.FAILURE;
            capturedAt = longValue(failureDetail.get("capturedAt"), latestAttempt.getFinishedAt());
        } else {
            snapshotType = Phase3AiModels.DeviceOperationalSnapshotType.HEARTBEAT;
            capturedAt = longValue(heartbeatHealth.get("capturedAt"), runtime == null ? null : runtime.getLastHeartbeatAt());
        }
        return new Phase3AiModels.DeviceOperationalSnapshot(
                snapshotType,
                capturedAt,
                deviceId,
                device == null ? null : device.getHostGroup(),
                device == null ? List.of() : jsonCodec.readStringList(device.getInstalledProfilesJson()),
                nestedMap(health.get("capabilities")),
                heartbeatHealth,
                preflightSummary,
                runtime == null ? null : runtime.getLastHeartbeatAt()
        );
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> nestedMap(Object value) {
        return value instanceof Map<?, ?> raw ? (Map<String, Object>) raw : Map.of();
    }

    private long longValue(Object value, Long fallback) {
        if (value instanceof Number number) {
            return number.longValue();
        }
        return fallback == null ? 0L : fallback;
    }
}

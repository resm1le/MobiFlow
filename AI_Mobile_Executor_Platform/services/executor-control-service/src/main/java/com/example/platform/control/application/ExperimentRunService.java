package com.example.platform.control.application;

import com.example.platform.control.api.AdminApiModels.AttemptSummary;
import com.example.platform.control.api.AdminApiModels.CreateDevicePoolRequest;
import com.example.platform.control.api.AdminApiModels.CreateExperimentRunRequest;
import com.example.platform.control.api.AdminApiModels.CreateHeterogeneousRunRequest;
import com.example.platform.control.api.AdminApiModels.CreateSingleDeviceRunRequest;
import com.example.platform.control.api.AdminApiModels.CreateTaskRequest;
import com.example.platform.control.api.AdminApiModels.DevicePoolResponse;
import com.example.platform.control.api.AdminApiModels.ExperimentRunDetailResponse;
import com.example.platform.control.api.AdminApiModels.ExperimentRunSummaryResponse;
import com.example.platform.control.api.AdminApiModels.ExperimentRunTargetResponse;
import com.example.platform.control.api.AdminApiModels.RunStatusCounts;
import com.example.platform.control.api.AdminApiModels.TaskResponse;
import com.example.platform.control.api.ExecutorApiModels.ArtifactPolicy;
import com.example.platform.control.api.ExecutorApiModels.RunConfig;
import com.example.platform.control.domain.DomainValues;
import com.example.platform.control.domain.PersistenceModels.DeviceEntity;
import com.example.platform.control.domain.PersistenceModels.DevicePoolEntity;
import com.example.platform.control.domain.PersistenceModels.DeviceRuntimeStateEntity;
import com.example.platform.control.domain.PersistenceModels.ExperimentRunEntity;
import com.example.platform.control.domain.PersistenceModels.ExperimentRunTargetEntity;
import com.example.platform.control.domain.PersistenceModels.TaskAttemptEntity;
import com.example.platform.control.domain.PersistenceModels.TaskEntity;
import com.example.platform.control.infrastructure.mapper.DeviceCommandMapper;
import com.example.platform.control.infrastructure.mapper.DeviceMapper;
import com.example.platform.control.infrastructure.mapper.DevicePoolMapper;
import com.example.platform.control.infrastructure.mapper.DeviceRuntimeStateMapper;
import com.example.platform.control.infrastructure.mapper.ExperimentRunMapper;
import com.example.platform.control.infrastructure.mapper.ExperimentRunTargetMapper;
import com.example.platform.control.infrastructure.mapper.TaskAttemptMapper;
import com.example.platform.control.infrastructure.mapper.TaskMapper;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Clock;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.function.Function;
import java.util.stream.Collectors;

@Service
public class ExperimentRunService {

    private static final String DEFAULT_CREATED_BY = "console";
    private static final int DEFAULT_MAX_RETRIES_PER_DEVICE = 0;
    private static final long DEFAULT_QUEUE_TIMEOUT_MS = 300_000L;

    private final DevicePoolMapper devicePoolMapper;
    private final ExperimentRunMapper experimentRunMapper;
    private final ExperimentRunTargetMapper experimentRunTargetMapper;
    private final DeviceMapper deviceMapper;
    private final DeviceRuntimeStateMapper runtimeStateMapper;
    private final TaskMapper taskMapper;
    private final TaskAttemptMapper taskAttemptMapper;
    private final DeviceCommandMapper commandMapper;
    private final JsonCodec jsonCodec;
    private final IdGenerator idGenerator;
    private final TaskRequestValidator taskRequestValidator;
    private final HeterogeneousDispatchResolver heterogeneousDispatchResolver;
    private final Clock clock = Clock.systemUTC();

    public ExperimentRunService(DevicePoolMapper devicePoolMapper,
                                ExperimentRunMapper experimentRunMapper,
                                ExperimentRunTargetMapper experimentRunTargetMapper,
                                DeviceMapper deviceMapper,
                                DeviceRuntimeStateMapper runtimeStateMapper,
                                TaskMapper taskMapper,
                                TaskAttemptMapper taskAttemptMapper,
                                DeviceCommandMapper commandMapper,
                                JsonCodec jsonCodec,
                                IdGenerator idGenerator,
                                TaskRequestValidator taskRequestValidator,
                                HeterogeneousDispatchResolver heterogeneousDispatchResolver) {
        this.devicePoolMapper = devicePoolMapper;
        this.experimentRunMapper = experimentRunMapper;
        this.experimentRunTargetMapper = experimentRunTargetMapper;
        this.deviceMapper = deviceMapper;
        this.runtimeStateMapper = runtimeStateMapper;
        this.taskMapper = taskMapper;
        this.taskAttemptMapper = taskAttemptMapper;
        this.commandMapper = commandMapper;
        this.jsonCodec = jsonCodec;
        this.idGenerator = idGenerator;
        this.taskRequestValidator = taskRequestValidator;
        this.heterogeneousDispatchResolver = heterogeneousDispatchResolver;
    }

    public List<DevicePoolResponse> listDevicePools() {
        return devicePoolMapper.findAll().stream()
                .map(this::toDevicePoolResponse)
                .toList();
    }

    public DevicePoolResponse getDevicePool(String poolId) {
        return toDevicePoolResponse(requireDevicePool(poolId));
    }

    @Transactional
    public DevicePoolResponse createDevicePool(CreateDevicePoolRequest request) {
        long now = clock.millis();
        DevicePoolEntity entity = new DevicePoolEntity();
        entity.setPoolId(idGenerator.nextDevicePoolId());
        entity.setName(requireNonBlank(request.name(), ControlErrorCode.DEVICE_POOL_INVALID));
        entity.setDescription(normalizeOptional(request.description()));
        entity.setHostGroup(normalizeOptional(request.hostGroup()));
        entity.setDeviceIdsJson(jsonCodec.write(normalizeStringList(request.deviceIds())));
        entity.setRequiredTagsJson(jsonCodec.write(normalizeStringList(request.requiredTags())));
        entity.setExcludedTagsJson(jsonCodec.write(normalizeStringList(request.excludedTags())));
        entity.setCreatedBy(defaulted(request.createdBy(), DEFAULT_CREATED_BY));
        entity.setCreatedAt(now);
        entity.setUpdatedAt(now);
        devicePoolMapper.insert(entity);
        return toDevicePoolResponse(entity);
    }

    public List<ExperimentRunSummaryResponse> listRuns() {
        return experimentRunMapper.findAll().stream()
                .map(this::toRunSummary)
                .toList();
    }

    public ExperimentRunDetailResponse getRun(String runId) {
        ExperimentRunEntity run = requireRun(runId);
        List<ExperimentRunTargetEntity> targets = experimentRunTargetMapper.findByRunId(runId);
        return toRunDetail(run, targets);
    }

    public List<ExperimentRunTargetResponse> listRunTargets(String runId) {
        requireRun(runId);
        return experimentRunTargetMapper.findByRunId(runId).stream()
                .map(this::toTargetResponse)
                .toList();
    }

    public ExperimentRunTargetResponse getRunTarget(String runTargetId) {
        ExperimentRunTargetEntity target = experimentRunTargetMapper.findById(runTargetId);
        if (target == null) {
            throw ControlApiExceptions.notFound(ControlErrorCode.RUN_TARGET_NOT_FOUND);
        }
        return toTargetResponse(target);
    }

    @Transactional
    public ExperimentRunDetailResponse createRun(CreateExperimentRunRequest request) {
        DevicePoolEntity pool = requireDevicePool(request.devicePoolId());
        TaskRequestValidator.NormalizedTaskRequest normalizedTask = normalizeRunTask(
                request.taskType(),
                request.profilePackage(),
                request.taskPayload(),
                request.runConfig(),
                request.artifactPolicy(),
                request.priority(),
                request.labels(),
                request.source(),
                request.createdBy()
        );
        int maxRetriesPerDevice = normalizeMaxRetriesPerDevice(request.maxRetriesPerDevice());
        long queueTimeoutMs = normalizeQueueTimeoutMs(request.queueTimeoutMs());

        List<DeviceEntity> selectedDevices = selectRunDevices(pool, normalizedTask.profilePackage());
        if (selectedDevices.isEmpty()) {
            throw ControlApiExceptions.badRequest(ControlErrorCode.EXPERIMENT_RUN_INVALID);
        }

        ExperimentRunEntity run = createRunEntity(
                requireNonBlank(request.name(), ControlErrorCode.EXPERIMENT_RUN_INVALID),
                request.description(),
                pool.getPoolId(),
                normalizedTask,
                maxRetriesPerDevice,
                queueTimeoutMs
        );

        for (DeviceEntity device : selectedDevices) {
            createInitialTargetTask(run, device.getDeviceId(), run.getCreatedAt());
        }
        return getRun(run.getRunId());
    }

    @Transactional
    public ExperimentRunDetailResponse createSingleDeviceRun(CreateSingleDeviceRunRequest request) {
        DeviceEntity device = requireDevice(request.deviceId());
        TaskRequestValidator.NormalizedTaskRequest normalizedTask = normalizeRunTask(
                request.taskType(),
                request.profilePackage(),
                request.taskPayload(),
                request.runConfig(),
                request.artifactPolicy(),
                request.priority(),
                request.labels(),
                request.source(),
                request.createdBy()
        );
        if (!jsonCodec.readStringList(device.getInstalledProfilesJson()).contains(normalizedTask.profilePackage())) {
            throw ControlApiExceptions.badRequest(ControlErrorCode.EXPERIMENT_RUN_INVALID);
        }

        ExperimentRunEntity run = createRunEntity(
                requireNonBlank(request.name(), ControlErrorCode.EXPERIMENT_RUN_INVALID),
                request.description(),
                null,
                normalizedTask,
                normalizeMaxRetriesPerDevice(request.maxRetriesPerDevice()),
                normalizeQueueTimeoutMs(request.queueTimeoutMs())
        );
        createInitialTargetTask(run, device.getDeviceId(), run.getCreatedAt());
        return getRun(run.getRunId());
    }

    @Transactional
    public ExperimentRunDetailResponse createHeterogeneousRun(CreateHeterogeneousRunRequest request) {
        String name = requireNonBlank(request.name(), ControlErrorCode.HETEROGENEOUS_RUN_INVALID);
        int maxRetriesPerDevice = normalizeMaxRetriesPerDevice(request.maxRetriesPerDevice());
        long queueTimeoutMs = normalizeQueueTimeoutMs(request.queueTimeoutMs());
        List<HeterogeneousDispatchResolver.ResolvedDispatchEntry> resolved = heterogeneousDispatchResolver.resolve(request);
        if (resolved.isEmpty()) {
            throw ControlApiExceptions.badRequest(ControlErrorCode.HETEROGENEOUS_RUN_INVALID);
        }

        TaskRequestValidator.NormalizedTaskRequest representative = resolved.get(0).task();
        Set<String> profiles = resolved.stream()
                .map(entry -> entry.task().profilePackage())
                .collect(Collectors.toCollection(LinkedHashSet::new));
        ExperimentRunEntity run = createRunEntity(
                name,
                request.description(),
                null,
                representative,
                profiles.size() == 1 ? profiles.iterator().next() : null,
                "{}",
                maxRetriesPerDevice,
                queueTimeoutMs
        );
        for (HeterogeneousDispatchResolver.ResolvedDispatchEntry entry : resolved) {
            for (String deviceId : entry.deviceIds()) {
                createInitialTargetTask(run, entry.sequenceId(), deviceId, entry.task(), run.getCreatedAt());
            }
        }
        return getRun(run.getRunId());
    }

    @Transactional
    public void cancelRun(String runId) {
        ExperimentRunEntity run = requireLockedRun(runId);
        long now = clock.millis();
        run.setCancelRequested(true);
        run.setStatus(DomainValues.RUN_STATUS_CANCELLING);
        run.setUpdatedAt(now);
        experimentRunMapper.update(run);

        for (ExperimentRunTargetEntity target : experimentRunTargetMapper.findByRunId(runId)) {
            if (DomainValues.TERMINAL_RUN_TARGET_STATUSES.contains(target.getStatus())) {
                continue;
            }
            TaskEntity task = target.getCurrentTaskId() == null ? null : taskMapper.findById(target.getCurrentTaskId());
            if (DomainValues.RUN_TARGET_STATUS_QUEUED.equals(target.getStatus())
                    || DomainValues.RUN_TARGET_STATUS_RETRY_PENDING.equals(target.getStatus())) {
                if (task != null && DomainValues.TASK_STATUS_QUEUED.equals(task.getStatus())) {
                    taskMapper.updateStatus(task.getTaskId(), DomainValues.TASK_STATUS_CANCELLED, task.getScheduleVersion(), now);
                }
                target.setStatus(DomainValues.RUN_TARGET_STATUS_CANCELLED);
                target.setFailureReason("RUN_CANCELLED");
                target.setFinishedAt(now);
                target.setUpdatedAt(now);
                experimentRunTargetMapper.update(target);
                continue;
            }
            if (DomainValues.RUN_TARGET_STATUS_RUNNING.equals(target.getStatus())) {
                TaskAttemptEntity latestAttempt = target.getLatestAttemptId() == null
                        ? null
                        : taskAttemptMapper.findById(target.getLatestAttemptId());
                if (latestAttempt != null
                        && DomainValues.ACTIVE_ATTEMPT_STATUSES.contains(latestAttempt.getStatus())
                        && commandMapper.countPendingByAttemptAndType(latestAttempt.getAttemptId(), "CANCEL_ATTEMPT", now) == 0) {
                    var command = new com.example.platform.control.domain.PersistenceModels.DeviceCommandEntity();
                    command.setDeviceId(latestAttempt.getDeviceId());
                    command.setAttemptId(latestAttempt.getAttemptId());
                    command.setType("CANCEL_ATTEMPT");
                    command.setStatus(DomainValues.COMMAND_STATUS_PENDING);
                    command.setIssuedAt(now);
                    commandMapper.insert(command);
                }
            }
        }
        refreshRunAggregate(runId, now);
    }

    @Transactional
    public void onTaskClaimed(TaskEntity task, TaskAttemptEntity attempt, long now) {
        if (task.getRunTargetId() == null) {
            return;
        }
        ExperimentRunTargetEntity target = experimentRunTargetMapper.lockById(task.getRunTargetId());
        if (target == null || !Objects.equals(target.getCurrentTaskId(), task.getTaskId())) {
            return;
        }
        target.setStatus(DomainValues.RUN_TARGET_STATUS_RUNNING);
        target.setLatestAttemptId(attempt.getAttemptId());
        target.setUpdatedAt(now);
        experimentRunTargetMapper.update(target);
        refreshRunAggregate(target.getRunId(), now);
    }

    @Transactional
    public void onAttemptStarted(TaskEntity task, TaskAttemptEntity attempt, long now) {
        if (task.getRunTargetId() == null) {
            return;
        }
        ExperimentRunTargetEntity target = experimentRunTargetMapper.lockById(task.getRunTargetId());
        if (target == null || !Objects.equals(target.getCurrentTaskId(), task.getTaskId())) {
            return;
        }
        target.setStatus(DomainValues.RUN_TARGET_STATUS_RUNNING);
        target.setLatestAttemptId(attempt.getAttemptId());
        if (target.getStartedAt() == null) {
            target.setStartedAt(now);
        }
        target.setUpdatedAt(now);
        experimentRunTargetMapper.update(target);
        refreshRunAggregate(target.getRunId(), now);
    }

    @Transactional
    public void onAttemptFinished(TaskEntity task, TaskAttemptEntity attempt, String finalState, String failureReason, long now) {
        if (task.getRunTargetId() == null) {
            return;
        }
        ExperimentRunTargetEntity target = experimentRunTargetMapper.lockById(task.getRunTargetId());
        if (target == null) {
            return;
        }
        ExperimentRunEntity run = requireLockedRun(target.getRunId());
        target.setLatestAttemptId(attempt.getAttemptId());
        if (target.getStartedAt() == null) {
            target.setStartedAt(attempt.getStartedAt() == null ? now : attempt.getStartedAt());
        }

        if (run.isCancelRequested() || "CANCELLED".equals(finalState)) {
            target.setStatus(DomainValues.RUN_TARGET_STATUS_CANCELLED);
            target.setFailureReason(failureReason == null ? "RUN_CANCELLED" : failureReason);
            target.setFinishedAt(now);
            target.setUpdatedAt(now);
            experimentRunTargetMapper.update(target);
            refreshRunAggregate(run.getRunId(), now);
            return;
        }

        if ("SUCCESS".equals(finalState)) {
            target.setStatus(DomainValues.RUN_TARGET_STATUS_SUCCEEDED);
            target.setFailureReason(null);
            target.setFinishedAt(now);
            target.setUpdatedAt(now);
            experimentRunTargetMapper.update(target);
            refreshRunAggregate(run.getRunId(), now);
            return;
        }

        if (target.getAttemptCount() <= run.getMaxRetriesPerDevice()) {
            TaskEntity retryTask = queueNextTargetTask(run, target, task, target.getAttemptCount() + 1, now);
            target.setStatus(DomainValues.RUN_TARGET_STATUS_RETRY_PENDING);
            target.setAttemptCount(target.getAttemptCount() + 1);
            target.setCurrentTaskId(retryTask.getTaskId());
            target.setFailureReason(failureReason);
            target.setUpdatedAt(now);
            target.setFinishedAt(null);
            experimentRunTargetMapper.update(target);
        } else {
            target.setStatus(DomainValues.RUN_TARGET_STATUS_FAILED);
            target.setFailureReason(failureReason);
            target.setFinishedAt(now);
            target.setUpdatedAt(now);
            experimentRunTargetMapper.update(target);
        }
        refreshRunAggregate(run.getRunId(), now);
    }

    @Transactional
    public void onQueuedRunTaskCancelled(TaskEntity task, long now) {
        if (task.getRunTargetId() == null) {
            return;
        }
        ExperimentRunTargetEntity target = experimentRunTargetMapper.lockById(task.getRunTargetId());
        if (target == null || !Objects.equals(target.getCurrentTaskId(), task.getTaskId())) {
            return;
        }
        target.setStatus(DomainValues.RUN_TARGET_STATUS_CANCELLED);
        target.setFailureReason("TASK_CANCELLED");
        target.setFinishedAt(now);
        target.setUpdatedAt(now);
        experimentRunTargetMapper.update(target);
        refreshRunAggregate(target.getRunId(), now);
    }

    @Transactional
    public int reconcileQueuedTimeouts(long now) {
        int affected = 0;
        for (ExperimentRunTargetEntity target : experimentRunTargetMapper.findPendingQueueTargets()) {
            ExperimentRunEntity run = requireLockedRun(target.getRunId());
            if (run.isCancelRequested()) {
                continue;
            }
            TaskEntity task = target.getCurrentTaskId() == null ? null : taskMapper.findById(target.getCurrentTaskId());
            if (task == null || !DomainValues.TASK_STATUS_QUEUED.equals(task.getStatus())) {
                continue;
            }
            if (now - task.getCreatedAt() < run.getQueueTimeoutMs()) {
                continue;
            }
            taskMapper.updateStatus(task.getTaskId(), DomainValues.TASK_STATUS_CANCELLED, task.getScheduleVersion(), now);
            if (target.getAttemptCount() <= run.getMaxRetriesPerDevice()) {
                TaskEntity retryTask = queueNextTargetTask(run, target, task, target.getAttemptCount() + 1, now);
                target.setStatus(DomainValues.RUN_TARGET_STATUS_RETRY_PENDING);
                target.setAttemptCount(target.getAttemptCount() + 1);
                target.setCurrentTaskId(retryTask.getTaskId());
                target.setFailureReason("QUEUE_TIMEOUT");
                target.setUpdatedAt(now);
                experimentRunTargetMapper.update(target);
            } else {
                target.setStatus(DomainValues.RUN_TARGET_STATUS_FAILED);
                target.setFailureReason("QUEUE_TIMEOUT");
                target.setFinishedAt(now);
                target.setUpdatedAt(now);
                experimentRunTargetMapper.update(target);
            }
            refreshRunAggregate(run.getRunId(), now);
            affected++;
        }
        return affected;
    }

    private void createInitialTargetTask(ExperimentRunEntity run, String deviceId, long now) {
        createInitialTargetTask(run, null, deviceId, new TargetTaskSpec(
                run.getTaskType(),
                run.getProfilePackage(),
                run.getTaskPayloadJson(),
                run.getRunConfigJson(),
                run.getArtifactPolicyJson(),
                run.getPriority(),
                run.getLabelsJson(),
                run.getSource(),
                run.getCreatedBy()
        ), now);
    }

    private void createInitialTargetTask(ExperimentRunEntity run,
                                         String sequenceId,
                                         String deviceId,
                                         TaskRequestValidator.NormalizedTaskRequest task,
                                         long now) {
        createInitialTargetTask(run, sequenceId, deviceId, new TargetTaskSpec(
                task.taskType(),
                task.profilePackage(),
                jsonCodec.write(task.taskPayload()),
                jsonCodec.write(task.runConfig()),
                jsonCodec.write(task.artifactPolicy()),
                task.priority(),
                jsonCodec.write(task.labels()),
                task.source(),
                task.createdBy()
        ), now);
    }

    private void createInitialTargetTask(ExperimentRunEntity run,
                                         String sequenceId,
                                         String deviceId,
                                         TargetTaskSpec spec,
                                         long now) {
        ExperimentRunTargetEntity target = new ExperimentRunTargetEntity();
        target.setRunTargetId(idGenerator.nextRunTargetId());
        target.setRunId(run.getRunId());
        target.setDeviceId(deviceId);
        target.setSequenceId(sequenceId);
        target.setStatus(DomainValues.RUN_TARGET_STATUS_QUEUED);
        target.setAttemptCount(1);
        target.setCreatedAt(now);
        target.setUpdatedAt(now);

        TaskEntity task = new TaskEntity();
        task.setTaskId(idGenerator.nextTaskId());
        task.setRunId(run.getRunId());
        task.setRunTargetId(target.getRunTargetId());
        task.setTargetDeviceId(deviceId);
        task.setTaskType(spec.taskType());
        task.setProfilePackage(spec.profilePackage());
        task.setTaskPayloadJson(spec.taskPayloadJson());
        task.setRunConfigJson(spec.runConfigJson());
        task.setArtifactPolicyJson(spec.artifactPolicyJson());
        task.setPriority(spec.priority());
        task.setLabelsJson(spec.labelsJson());
        task.setSource(spec.source());
        task.setScheduleVersion(null);
        task.setIdempotencyKey(run.getRunId() + ":" + target.getRunTargetId() + ":1");
        task.setStatus(DomainValues.TASK_STATUS_QUEUED);
        task.setCreatedBy(spec.createdBy());
        task.setCreatedAt(now);
        task.setUpdatedAt(now);
        taskMapper.insert(task);

        target.setCurrentTaskId(task.getTaskId());
        experimentRunTargetMapper.insert(target);
    }

    private List<DeviceEntity> selectRunDevices(DevicePoolEntity pool, String profilePackage) {
        Map<String, DeviceRuntimeStateEntity> runtimes = runtimeStateMapper.findAll().stream()
                .collect(Collectors.toMap(DeviceRuntimeStateEntity::getDeviceId, Function.identity()));
        Set<String> selectedIds = Set.copyOf(jsonCodec.readStringList(pool.getDeviceIdsJson()));
        Set<String> requiredTags = Set.copyOf(jsonCodec.readStringList(pool.getRequiredTagsJson()));
        Set<String> excludedTags = Set.copyOf(jsonCodec.readStringList(pool.getExcludedTagsJson()));
        return deviceMapper.findAll().stream()
                .filter(device -> matchesPool(device, runtimes.get(device.getDeviceId()), pool.getHostGroup(), selectedIds, requiredTags, excludedTags))
                .filter(device -> jsonCodec.readStringList(device.getInstalledProfilesJson()).contains(profilePackage))
                .toList();
    }

    private boolean matchesPool(DeviceEntity device,
                                DeviceRuntimeStateEntity runtime,
                                String hostGroup,
                                Set<String> selectedIds,
                                Set<String> requiredTags,
                                Set<String> excludedTags) {
        return ExperimentRunSelectors.matchesPool(device, runtime, hostGroup, selectedIds, requiredTags, excludedTags, jsonCodec);
    }

    private void refreshRunAggregate(String runId, long now) {
        ExperimentRunEntity run = requireLockedRun(runId);
        List<ExperimentRunTargetEntity> targets = experimentRunTargetMapper.findByRunId(runId);
        boolean anyRunning = targets.stream().anyMatch(target ->
                DomainValues.RUN_TARGET_STATUS_RUNNING.equals(target.getStatus())
                        || DomainValues.RUN_TARGET_STATUS_RETRY_PENDING.equals(target.getStatus()));
        boolean allTerminal = !targets.isEmpty() && targets.stream()
                .allMatch(target -> DomainValues.TERMINAL_RUN_TARGET_STATUSES.contains(target.getStatus()));

        if (run.isCancelRequested() && !allTerminal) {
            run.setStatus(DomainValues.RUN_STATUS_CANCELLING);
        } else if (allTerminal) {
            run.setStatus(DomainValues.RUN_STATUS_TERMINAL);
            run.setFinalState(deriveRunFinalState(targets));
            run.setFinishedAt(now);
        } else if (anyRunning) {
            run.setStatus(DomainValues.RUN_STATUS_RUNNING);
            if (run.getStartedAt() == null) {
                run.setStartedAt(now);
            }
        } else {
            run.setStatus(DomainValues.RUN_STATUS_QUEUED);
        }
        run.setUpdatedAt(now);
        experimentRunMapper.update(run);
    }

    private String deriveRunFinalState(List<ExperimentRunTargetEntity> targets) {
        long succeeded = targets.stream().filter(target -> DomainValues.RUN_TARGET_STATUS_SUCCEEDED.equals(target.getStatus())).count();
        long failed = targets.stream().filter(target -> DomainValues.RUN_TARGET_STATUS_FAILED.equals(target.getStatus())).count();
        long cancelled = targets.stream().filter(target -> DomainValues.RUN_TARGET_STATUS_CANCELLED.equals(target.getStatus())).count();
        if (succeeded == targets.size()) {
            return DomainValues.RUN_FINAL_STATE_SUCCEEDED;
        }
        if (cancelled == targets.size()) {
            return DomainValues.RUN_FINAL_STATE_CANCELLED;
        }
        if (failed == targets.size()) {
            return DomainValues.RUN_FINAL_STATE_FAILED;
        }
        return DomainValues.RUN_FINAL_STATE_PARTIAL;
    }

    private TaskEntity queueNextTargetTask(ExperimentRunEntity run,
                                           ExperimentRunTargetEntity target,
                                           TaskEntity previousTask,
                                           int attemptOrdinal,
                                           long now) {
        if (previousTask == null) {
            throw ControlApiExceptions.badRequest(ControlErrorCode.TASK_NOT_FOUND);
        }
        TaskEntity task = new TaskEntity();
        task.setTaskId(idGenerator.nextTaskId());
        task.setRunId(run.getRunId());
        task.setRunTargetId(target.getRunTargetId());
        task.setTargetDeviceId(target.getDeviceId());
        task.setTaskType(previousTask.getTaskType());
        task.setProfilePackage(previousTask.getProfilePackage());
        task.setTaskPayloadJson(previousTask.getTaskPayloadJson());
        task.setRunConfigJson(previousTask.getRunConfigJson());
        task.setArtifactPolicyJson(previousTask.getArtifactPolicyJson());
        task.setPriority(previousTask.getPriority());
        task.setLabelsJson(previousTask.getLabelsJson());
        task.setSource(previousTask.getSource());
        task.setScheduleVersion(null);
        task.setIdempotencyKey(run.getRunId() + ":" + target.getRunTargetId() + ":" + attemptOrdinal);
        task.setStatus(DomainValues.TASK_STATUS_QUEUED);
        task.setCreatedBy(previousTask.getCreatedBy());
        task.setCreatedAt(now);
        task.setUpdatedAt(now);
        taskMapper.insert(task);
        return task;
    }

    private TaskRequestValidator.NormalizedTaskRequest normalizeRunTask(String taskType,
                                                                        String profilePackage,
                                                                        Map<String, Object> taskPayload,
                                                                        RunConfig runConfig,
                                                                        ArtifactPolicy artifactPolicy,
                                                                        Integer priority,
                                                                        List<String> labels,
                                                                        String source,
                                                                        String createdBy) {
        return taskRequestValidator.validateAndNormalize(new CreateTaskRequest(
                taskType,
                profilePackage,
                taskPayload,
                runConfig,
                artifactPolicy,
                priority,
                labels,
                source,
                createdBy,
                null
        ));
    }

    private int normalizeMaxRetriesPerDevice(Integer maxRetriesPerDevice) {
        int normalized = maxRetriesPerDevice == null ? DEFAULT_MAX_RETRIES_PER_DEVICE : maxRetriesPerDevice;
        if (normalized < 0) {
            throw ControlApiExceptions.badRequest(ControlErrorCode.EXPERIMENT_RUN_INVALID);
        }
        return normalized;
    }

    private long normalizeQueueTimeoutMs(Long queueTimeoutMs) {
        long normalized = queueTimeoutMs == null ? DEFAULT_QUEUE_TIMEOUT_MS : queueTimeoutMs;
        if (normalized < 1_000) {
            throw ControlApiExceptions.badRequest(ControlErrorCode.EXPERIMENT_RUN_INVALID);
        }
        return normalized;
    }

    private ExperimentRunEntity createRunEntity(String name,
                                                String description,
                                                String poolId,
                                                TaskRequestValidator.NormalizedTaskRequest normalizedTask,
                                                int maxRetriesPerDevice,
                                                long queueTimeoutMs) {
        return createRunEntity(
                name,
                description,
                poolId,
                normalizedTask,
                normalizedTask.profilePackage(),
                jsonCodec.write(normalizedTask.taskPayload()),
                maxRetriesPerDevice,
                queueTimeoutMs
        );
    }

    private ExperimentRunEntity createRunEntity(String name,
                                                String description,
                                                String poolId,
                                                TaskRequestValidator.NormalizedTaskRequest normalizedTask,
                                                String profilePackage,
                                                String taskPayloadJson,
                                                int maxRetriesPerDevice,
                                                long queueTimeoutMs) {
        long now = clock.millis();
        ExperimentRunEntity run = new ExperimentRunEntity();
        run.setRunId(idGenerator.nextRunId());
        run.setName(name);
        run.setDescription(normalizeOptional(description));
        run.setPoolId(poolId);
        run.setStatus(DomainValues.RUN_STATUS_QUEUED);
        run.setTaskType(normalizedTask.taskType());
        run.setProfilePackage(profilePackage);
        run.setTaskPayloadJson(taskPayloadJson);
        run.setRunConfigJson(jsonCodec.write(normalizedTask.runConfig()));
        run.setArtifactPolicyJson(jsonCodec.write(normalizedTask.artifactPolicy()));
        run.setPriority(normalizedTask.priority());
        run.setLabelsJson(jsonCodec.write(normalizedTask.labels()));
        run.setSource(normalizedTask.source());
        run.setCreatedBy(normalizedTask.createdBy());
        run.setMaxRetriesPerDevice(maxRetriesPerDevice);
        run.setQueueTimeoutMs(queueTimeoutMs);
        run.setCancelRequested(false);
        run.setCreatedAt(now);
        run.setUpdatedAt(now);
        experimentRunMapper.insert(run);
        return run;
    }

    private DevicePoolEntity requireDevicePool(String poolId) {
        DevicePoolEntity pool = devicePoolMapper.findById(poolId);
        if (pool == null) {
            throw ControlApiExceptions.notFound(ControlErrorCode.DEVICE_POOL_NOT_FOUND);
        }
        return pool;
    }

    private DeviceEntity requireDevice(String deviceId) {
        DeviceEntity device = deviceMapper.findById(deviceId);
        if (device == null) {
            throw ControlApiExceptions.notFound(ControlErrorCode.DEVICE_NOT_FOUND);
        }
        return device;
    }

    private ExperimentRunEntity requireRun(String runId) {
        ExperimentRunEntity run = experimentRunMapper.findById(runId);
        if (run == null) {
            throw ControlApiExceptions.notFound(ControlErrorCode.EXPERIMENT_RUN_NOT_FOUND);
        }
        return run;
    }

    private ExperimentRunEntity requireLockedRun(String runId) {
        ExperimentRunEntity run = experimentRunMapper.lockById(runId);
        if (run == null) {
            throw ControlApiExceptions.notFound(ControlErrorCode.EXPERIMENT_RUN_NOT_FOUND);
        }
        return run;
    }

    private DevicePoolResponse toDevicePoolResponse(DevicePoolEntity entity) {
        return new DevicePoolResponse(
                entity.getPoolId(),
                entity.getName(),
                entity.getDescription(),
                entity.getHostGroup(),
                jsonCodec.readStringList(entity.getDeviceIdsJson()),
                jsonCodec.readStringList(entity.getRequiredTagsJson()),
                jsonCodec.readStringList(entity.getExcludedTagsJson()),
                entity.getCreatedBy(),
                entity.getCreatedAt(),
                entity.getUpdatedAt()
        );
    }

    private ExperimentRunSummaryResponse toRunSummary(ExperimentRunEntity run) {
        List<ExperimentRunTargetEntity> targets = experimentRunTargetMapper.findByRunId(run.getRunId());
        return new ExperimentRunSummaryResponse(
                run.getRunId(),
                run.getName(),
                run.getDescription(),
                run.getPoolId(),
                run.getStatus(),
                run.getFinalState(),
                run.getTaskType(),
                run.getProfilePackage(),
                run.getPriority(),
                jsonCodec.readStringList(run.getLabelsJson()),
                run.getSource(),
                run.getCreatedBy(),
                run.getMaxRetriesPerDevice(),
                run.getQueueTimeoutMs(),
                run.isCancelRequested(),
                run.getCreatedAt(),
                run.getUpdatedAt(),
                run.getStartedAt(),
                run.getFinishedAt(),
                toCounts(targets)
        );
    }

    private ExperimentRunDetailResponse toRunDetail(ExperimentRunEntity run, List<ExperimentRunTargetEntity> targets) {
        return new ExperimentRunDetailResponse(
                toRunSummary(run),
                jsonCodec.readMap(run.getTaskPayloadJson()),
                toRunConfig(run.getRunConfigJson()),
                toArtifactPolicy(run.getArtifactPolicyJson()),
                targets.stream().map(this::toTargetResponse).toList()
        );
    }

    private ExperimentRunTargetResponse toTargetResponse(ExperimentRunTargetEntity target) {
        TaskEntity task = target.getCurrentTaskId() == null ? null : taskMapper.findById(target.getCurrentTaskId());
        TaskAttemptEntity latestAttempt = target.getLatestAttemptId() == null ? null : taskAttemptMapper.findById(target.getLatestAttemptId());
        return new ExperimentRunTargetResponse(
                target.getRunTargetId(),
                target.getDeviceId(),
                target.getSequenceId(),
                target.getStatus(),
                target.getAttemptCount(),
                target.getCurrentTaskId(),
                target.getLatestAttemptId(),
                target.getFailureReason(),
                target.getStartedAt(),
                target.getFinishedAt(),
                task == null ? null : toTaskResponse(task, latestAttempt),
                latestAttempt == null ? null : toAttemptSummary(latestAttempt)
        );
    }

    private RunStatusCounts toCounts(List<ExperimentRunTargetEntity> targets) {
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
        return new RunStatusCounts(targets.size(), queued, running, retryPending, succeeded, failed, cancelled);
    }

    private TaskResponse toTaskResponse(TaskEntity task, TaskAttemptEntity latestAttempt) {
        return new TaskResponse(
                task.getTaskId(),
                task.getRunId(),
                task.getRunTargetId(),
                task.getTargetDeviceId(),
                task.getTaskType(),
                task.getProfilePackage(),
                jsonCodec.readMap(task.getTaskPayloadJson()),
                toRunConfig(task.getRunConfigJson()),
                toArtifactPolicy(task.getArtifactPolicyJson()),
                task.getPriority(),
                jsonCodec.readStringList(task.getLabelsJson()),
                task.getSource(),
                task.getScheduleVersion(),
                task.getIdempotencyKey(),
                task.getStatus(),
                task.getCreatedBy(),
                task.getCreatedAt(),
                task.getUpdatedAt(),
                latestAttempt == null ? null : toAttemptSummary(latestAttempt)
        );
    }

    private AttemptSummary toAttemptSummary(TaskAttemptEntity attempt) {
        return new AttemptSummary(
                attempt.getAttemptId(),
                attempt.getTaskId(),
                attempt.getDeviceId(),
                attempt.getRunId(),
                attempt.getStatus(),
                attempt.getFinalState(),
                attempt.getLeaseExpireAt(),
                attempt.getFailureReason(),
                attempt.getStartedAt(),
                attempt.getFinishedAt(),
                attempt.getCreatedAt(),
                attempt.getUpdatedAt()
        );
    }

    private RunConfig toRunConfig(String json) {
        Map<String, Object> map = jsonCodec.readMap(json);
        return new RunConfig(
                ((Number) map.getOrDefault("loopCount", 1)).intValue(),
                ((Number) map.getOrDefault("budgetMs", 60000)).longValue(),
                ((Number) map.getOrDefault("loopIntervalMs", 0)).longValue(),
                Boolean.TRUE.equals(map.get("networkIsolationEnabled")),
                ((Number) map.getOrDefault("pollIntervalMs", 15000)).longValue(),
                ((Number) map.getOrDefault("heartbeatIntervalMs", 30000)).longValue()
        );
    }

    private ArtifactPolicy toArtifactPolicy(String json) {
        Map<String, Object> map = jsonCodec.readMap(json);
        return new ArtifactPolicy(
                Boolean.TRUE.equals(map.get("uploadLog")),
                Boolean.TRUE.equals(map.get("uploadScreenshot")),
                Boolean.TRUE.equals(map.get("uploadDump"))
        );
    }

    private String requireNonBlank(String value, String errorCode) {
        String normalized = normalizeOptional(value);
        if (normalized == null) {
            throw ControlApiExceptions.badRequest(errorCode);
        }
        return normalized;
    }

    private String defaulted(String value, String fallback) {
        String normalized = normalizeOptional(value);
        return normalized == null ? fallback : normalized;
    }

    private String normalizeOptional(String value) {
        if (value == null) {
            return null;
        }
        String normalized = value.trim();
        return normalized.isEmpty() ? null : normalized;
    }

    private List<String> normalizeStringList(List<String> values) {
        if (values == null || values.isEmpty()) {
            return List.of();
        }
        Set<String> normalized = new LinkedHashSet<>();
        for (String value : values) {
            String trimmed = normalizeOptional(value);
            if (trimmed == null) {
                throw ControlApiExceptions.badRequest(ControlErrorCode.DEVICE_POOL_INVALID);
            }
            normalized.add(trimmed);
        }
        return new ArrayList<>(normalized);
    }

    private record TargetTaskSpec(
            String taskType,
            String profilePackage,
            String taskPayloadJson,
            String runConfigJson,
            String artifactPolicyJson,
            int priority,
            String labelsJson,
            String source,
            String createdBy
    ) {
    }
}

package com.example.platform.control.application;

import com.example.platform.control.api.ExecutorAuthContext;
import com.example.platform.control.api.ExecutorApiModels.ExecutorAckResponse;
import com.example.platform.control.api.ExecutorApiModels.ExecutorIdentityRequest;
import com.example.platform.control.api.ExecutorApiModels.ArtifactPolicy;
import com.example.platform.control.api.ExecutorApiModels.ClaimTaskResponse;
import com.example.platform.control.api.ExecutorApiModels.ClaimedTask;
import com.example.platform.control.api.ExecutorApiModels.Command;
import com.example.platform.control.api.ExecutorApiModels.EventsRequest;
import com.example.platform.control.api.ExecutorApiModels.FinishRequest;
import com.example.platform.control.api.ExecutorApiModels.HeartbeatResponse;
import com.example.platform.control.api.ExecutorApiModels.RunConfig;
import com.example.platform.control.api.ExecutorApiModels.StartRequest;
import com.example.platform.control.api.ExecutorApiModels.ExecutorWaypointSegmentsRequest;
import com.example.platform.control.api.ExecutorApiModels.ExecutorWaypointSegmentsResponse;
import com.example.platform.control.domain.DomainValues;
import com.example.platform.control.domain.PersistenceModels.DeviceCommandEntity;
import com.example.platform.control.domain.PersistenceModels.DeviceEntity;
import com.example.platform.control.domain.PersistenceModels.DeviceRuntimeStateEntity;
import com.example.platform.control.domain.PersistenceModels.RunEventEntity;
import com.example.platform.control.domain.PersistenceModels.TaskAttemptEntity;
import com.example.platform.control.domain.PersistenceModels.TaskEntity;
import com.example.platform.control.infrastructure.mapper.DeviceCommandMapper;
import com.example.platform.control.infrastructure.mapper.DeviceMapper;
import com.example.platform.control.infrastructure.mapper.DeviceRuntimeStateMapper;
import com.example.platform.control.infrastructure.mapper.RunEventMapper;
import com.example.platform.control.infrastructure.mapper.TaskAttemptMapper;
import com.example.platform.control.infrastructure.mapper.TaskMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Clock;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

@Service
public class ControlPlaneService {

    private static final Logger log = LoggerFactory.getLogger(ControlPlaneService.class);

    private final DeviceMapper deviceMapper;
    private final DeviceRuntimeStateMapper runtimeStateMapper;
    private final TaskMapper taskMapper;
    private final TaskAttemptMapper attemptMapper;
    private final DeviceCommandMapper commandMapper;
    private final RunEventMapper runEventMapper;
    private final JsonCodec jsonCodec;
    private final IdGenerator idGenerator;
    private final ControlProperties controlProperties;
    private final ControlStateRules controlStateRules;
    private final AttemptAccessValidator attemptAccessValidator;
    private final ExperimentRunService experimentRunService;
    private final WaypointTimelineService waypointTimelineService;
    private final Clock clock = Clock.systemUTC();

    public ControlPlaneService(DeviceMapper deviceMapper,
                               DeviceRuntimeStateMapper runtimeStateMapper,
                               TaskMapper taskMapper,
                               TaskAttemptMapper attemptMapper,
                               DeviceCommandMapper commandMapper,
                               RunEventMapper runEventMapper,
                               JsonCodec jsonCodec,
                               IdGenerator idGenerator,
                               ControlProperties controlProperties,
                               ControlStateRules controlStateRules,
                               AttemptAccessValidator attemptAccessValidator,
                               ExperimentRunService experimentRunService,
                               WaypointTimelineService waypointTimelineService) {
        this.deviceMapper = deviceMapper;
        this.runtimeStateMapper = runtimeStateMapper;
        this.taskMapper = taskMapper;
        this.attemptMapper = attemptMapper;
        this.commandMapper = commandMapper;
        this.runEventMapper = runEventMapper;
        this.jsonCodec = jsonCodec;
        this.idGenerator = idGenerator;
        this.controlProperties = controlProperties;
        this.controlStateRules = controlStateRules;
        this.attemptAccessValidator = attemptAccessValidator;
        this.experimentRunService = experimentRunService;
        this.waypointTimelineService = waypointTimelineService;
    }

    @Transactional
    public ExecutorAckResponse register(ExecutorAuthContext authContext, ExecutorIdentityRequest request) {
        long now = clock.millis();
        validateIdentity(authContext, request);
        upsertDeviceAndRuntime(authContext, request, now, false, null, null, null, null, null);
        return new ExecutorAckResponse(true, now, controlProperties.getConfigVersion());
    }

    @Transactional
    public HeartbeatResponse heartbeat(ExecutorAuthContext authContext, ExecutorIdentityRequest request) {
        long now = clock.millis();
        validateIdentity(authContext, request);
        TaskAttemptEntity activeAttempt = resolveAttempt(request.deviceId(), request.currentAttemptId());
        Long leaseExpireAt = null;
        if (activeAttempt != null) {
            leaseExpireAt = renewLease(activeAttempt, now);
            if (leaseExpireAt == null) {
                activeAttempt = null;
            }
        }
        DeliveryResult deliveryResult = deliverPendingCommands(request.deviceId(), now);
        List<Command> commands = new ArrayList<>(deliveryResult.commands());
        if (request.currentAttemptId() != null && !request.currentAttemptId().isBlank() && activeAttempt == null) {
            log.info("heartbeat.cancel_missing_active deviceId={} attemptId={}",
                    request.deviceId(),
                    request.currentAttemptId());
            commands.add(new Command("CANCEL_ATTEMPT", request.currentAttemptId()));
        }

        TaskEntity task = activeAttempt == null ? null : taskMapper.findById(activeAttempt.getTaskId());
        refreshHeartbeatState(authContext, request, now, activeAttempt, task, leaseExpireAt, deliveryResult.lastCommand());
        DeviceRuntimeStateEntity runtime = runtimeStateMapper.findById(request.deviceId());
        return new HeartbeatResponse(true, now, controlProperties.getConfigVersion(), heartbeatRunConfig(runtime, activeAttempt), commands);
    }

    @Transactional
    public ClaimTaskResponse claim(ExecutorAuthContext authContext, ExecutorIdentityRequest request) {
        long now = clock.millis();
        validateIdentity(authContext, request);
        DeviceRuntimeStateEntity runtime = runtimeStateMapper.lockByDeviceId(request.deviceId());
        if (!controlStateRules.isClaimAllowed(runtime)) {
            log.info("claim.rejected deviceId={} runtimeStatus={} busy={} registered={} online={}",
                    request.deviceId(),
                    runtime == null ? null : runtime.getStatus(),
                    runtime != null && runtime.isBusy(),
                    runtime != null && runtime.isRegistered(),
                    runtime != null && runtime.isOnline());
            return new ClaimTaskResponse(false, null);
        }
        upsertDevice(request, now);

        Set<String> installedProfiles = Set.copyOf(request.installedProfiles());
        TaskEntity selected = taskMapper.findClaimableQueuedTasks(request.deviceId(), 20).stream()
                .filter(task -> installedProfiles.contains(task.getProfilePackage()))
                .findFirst()
                .orElse(null);
        if (selected == null) {
            log.info("claim.empty deviceId={} installedProfiles={} scheduleVersion={}",
                    request.deviceId(),
                    request.installedProfiles(),
                    controlProperties.getScheduleVersion());
            return new ClaimTaskResponse(false, null);
        }

        String attemptId = idGenerator.nextAttemptId();
        String runId = selected.getRunId() == null ? idGenerator.nextRunId() : selected.getRunId();
        long leaseExpireAt = now + controlProperties.getLeaseMs();

        TaskAttemptEntity attempt = new TaskAttemptEntity();
        attempt.setAttemptId(attemptId);
        attempt.setTaskId(selected.getTaskId());
        attempt.setDeviceId(request.deviceId());
        attempt.setRunId(runId);
        attempt.setStatus(DomainValues.ATTEMPT_STATUS_LEASED);
        attempt.setLeaseExpireAt(leaseExpireAt);
        attempt.setCreatedAt(now);
        attempt.setUpdatedAt(now);
        attemptMapper.insert(attempt);

        taskMapper.updateStatus(selected.getTaskId(), DomainValues.TASK_STATUS_RUNNING, controlProperties.getScheduleVersion(), now);
        runtimeStateMapper.updateBusyState(
                request.deviceId(),
                true,
                runtime.getStatus(),
                selected.getTaskId(),
                attemptId,
                selected.getTaskType(),
                leaseExpireAt,
                runtime.getLastCommand(),
                now
        );
        log.info("claim.accepted deviceId={} taskId={} attemptId={} scheduleVersion={}",
                request.deviceId(),
                selected.getTaskId(),
                attemptId,
                controlProperties.getScheduleVersion());
        experimentRunService.onTaskClaimed(selected, attempt, now);

        ClaimedTask task = new ClaimedTask(
                selected.getTaskId(),
                attemptId,
                runId,
                selected.getTaskType(),
                selected.getProfilePackage(),
                jsonCodec.readMap(selected.getTaskPayloadJson()),
                toRunConfig(selected.getRunConfigJson()),
                toArtifactPolicy(selected.getArtifactPolicyJson()),
                selected.getPriority(),
                jsonCodec.readStringList(selected.getLabelsJson()),
                ArtifactUploadMode.DIRECT_PUT_V2,
                leaseExpireAt,
                controlProperties.getScheduleVersion(),
                selected.getIdempotencyKey(),
                selected.getSource()
        );
        return new ClaimTaskResponse(true, task);
    }

    @Transactional
    public void start(ExecutorAuthContext authContext, String attemptId, StartRequest request) {
        TaskAttemptEntity attempt = attemptAccessValidator.requireOwnedAttempt(authContext, attemptId);
        attemptAccessValidator.validateAttemptReference(attempt, attemptId, request.attemptId());
        attemptAccessValidator.validateTaskReference(attempt, request.taskId());
        attemptAccessValidator.validateRunReference(attempt, request.runId());
        controlStateRules.validateAttemptCanStart(attempt);
        TaskEntity task = requireTask(attempt.getTaskId());
        validateStartRequest(task, request);
        long now = clock.millis();
        long leaseExpireAt = now + controlProperties.getLeaseMs();
        attemptMapper.markRunning(attemptId, request.runId(), DomainValues.ATTEMPT_STATUS_RUNNING, leaseExpireAt, now, now);
        DeviceRuntimeStateEntity runtime = runtimeStateMapper.findById(attempt.getDeviceId());
        runtimeStateMapper.updateBusyState(
                attempt.getDeviceId(),
                true,
                runtimeStatus(runtime),
                task.getTaskId(),
                attemptId,
                task.getTaskType(),
                leaseExpireAt,
                null,
                now
        );
        log.info("attempt.start taskId={} attemptId={} deviceId={} scheduleVersion={}",
                task.getTaskId(),
                attemptId,
                attempt.getDeviceId(),
                task.getScheduleVersion());
        TaskAttemptEntity startedAttempt = attemptMapper.findById(attemptId);
        experimentRunService.onAttemptStarted(task, startedAttempt, now);
    }

    @Transactional
    public void recordEvents(ExecutorAuthContext authContext, String attemptId, EventsRequest request) {
        TaskAttemptEntity attempt = attemptAccessValidator.requireOwnedAttempt(authContext, attemptId);
        controlStateRules.validateAttemptCanRecordEvents(attempt);
        List<RunEventEntity> events = new ArrayList<>(request.events().size());
        for (var eventRequest : request.events()) {
            attemptAccessValidator.validateAttemptReference(attempt, attemptId, eventRequest.attemptId());
            attemptAccessValidator.validateTaskReference(attempt, eventRequest.taskId());
            attemptAccessValidator.validateDeviceReference(attempt, authContext, eventRequest.deviceId());
            attemptAccessValidator.validateRunReference(attempt, eventRequest.runId());
            RunEventEntity event = new RunEventEntity();
            event.setAttemptId(attemptId);
            event.setTaskId(attempt.getTaskId());
            event.setDeviceId(attempt.getDeviceId());
            event.setRunId(eventRequest.runId());
            event.setScenarioId(eventRequest.scenarioId());
            event.setStepIndex(eventRequest.stepIndex());
            event.setActionIndex(eventRequest.actionIndex());
            event.setEventType(eventRequest.eventType());
            event.setState(eventRequest.state());
            event.setCode(eventRequest.code());
            event.setMessage(eventRequest.message());
            event.setTs(eventRequest.ts());
            events.add(event);
        }
        if (!events.isEmpty()) {
            runEventMapper.insertBatch(events);
        }
    }

    @Transactional
    public ExecutorWaypointSegmentsResponse recordWaypointSegments(
            ExecutorAuthContext authContext,
            String attemptId,
            ExecutorWaypointSegmentsRequest request) {
        attemptAccessValidator.requireOwnedAttempt(authContext, attemptId);
        WaypointTimelineService.WaypointTimelineRecord record = waypointTimelineService.recordForAttempt(
                attemptId,
                authContext.deviceId(),
                null,
                request.waypointSegments().stream()
                        .map(segment -> new WaypointTimelineService.WaypointSegmentInput(
                                segment.stepId(),
                                segment.behaviorLabel(),
                                segment.enteredAtMs(),
                                segment.arrivedAtMs(),
                                segment.dwellMs(),
                                null,
                                null
                        ))
                        .toList()
        );
        return new ExecutorWaypointSegmentsResponse(
                record.runTargetId(),
                record.attemptId(),
                record.events().size()
        );
    }

    @Transactional
    public void finish(ExecutorAuthContext authContext, String attemptId, FinishRequest request) {
        TaskAttemptEntity attempt = attemptAccessValidator.requireOwnedAttempt(authContext, attemptId);
        attemptAccessValidator.validateAttemptReference(attempt, attemptId, request.attemptId());
        attemptAccessValidator.validateTaskReference(attempt, request.taskId());
        attemptAccessValidator.validateRunReference(attempt, request.runId());
        controlStateRules.validateAttemptCanFinish(attempt);
        TaskEntity task = requireTask(attempt.getTaskId());
        long now = clock.millis();
        String attemptStatus = DomainValues.toAttemptStatusFromFinalState(request.status());
        int finished = attemptMapper.finishIfActive(
                attemptId,
                attemptStatus,
                request.status(),
                request.message(),
                request.preflightSummary() == null ? null : jsonCodec.write(request.preflightSummary()),
                request.failureDetail() == null ? null : jsonCodec.write(request.failureDetail()),
                now,
                now
        );
        if (finished != 1) {
            log.info("attempt.finish_rejected taskId={} attemptId={} deviceId={} finalState={}",
                    task.getTaskId(),
                    attemptId,
                    attempt.getDeviceId(),
                    request.status());
            throw ControlApiExceptions.badRequest(ControlErrorCode.ATTEMPT_STATE_INVALID);
        }
        taskMapper.updateStatus(task.getTaskId(), DomainValues.toTaskStatusFromFinalState(request.status()), task.getScheduleVersion(), now);
        DeviceRuntimeStateEntity runtime = runtimeStateMapper.findById(attempt.getDeviceId());
        runtimeStateMapper.updateBusyState(
                attempt.getDeviceId(),
                false,
                controlStateRules.releasedRuntimeStatus(runtime),
                null,
                null,
                null,
                null,
                runtime == null ? null : runtime.getLastCommand(),
                now
        );
        log.info("attempt.finish taskId={} attemptId={} deviceId={} finalState={} scheduleVersion={}",
                task.getTaskId(),
                attemptId,
                attempt.getDeviceId(),
                request.status(),
                task.getScheduleVersion());
        TaskAttemptEntity finishedAttempt = attemptMapper.findById(attemptId);
        experimentRunService.onAttemptFinished(task, finishedAttempt, request.status(), request.message(), now);
    }

    private void upsertDeviceAndRuntime(ExecutorAuthContext authContext,
                                        ExecutorIdentityRequest request,
                                        long now,
                                        boolean busy,
                                        String currentTaskId,
                                        String currentAttemptId,
                                        String currentTaskType,
                                        Long leaseExpireAt,
                                        String lastCommand) {
        upsertDevice(request, now);
        DeviceRuntimeStateEntity existing = runtimeStateMapper.findById(request.deviceId());
        DeviceRuntimeStateEntity runtime = new DeviceRuntimeStateEntity();
        runtime.setDeviceId(request.deviceId());
        runtime.setRegistered(true);
        runtime.setOnline(true);
        runtime.setBusy(busy);
        runtime.setStatus(existing != null && DomainValues.DEVICE_STATUS_QUIESCED.equals(existing.getStatus())
                ? DomainValues.DEVICE_STATUS_QUIESCED
                : DomainValues.DEVICE_STATUS_ONLINE);
        runtime.setCurrentTaskId(currentTaskId);
        runtime.setCurrentAttemptId(currentAttemptId);
        runtime.setCurrentTaskType(currentTaskType);
        runtime.setConfigVersion(controlProperties.getConfigVersion());
        runtime.setLeaseExpireAt(leaseExpireAt);
        runtime.setLastHeartbeatAt(now);
        runtime.setLastCommand(lastCommand != null ? lastCommand : existing == null ? null : existing.getLastCommand());
        Map<String, Object> health = new LinkedHashMap<>();
        health.put("authConfigured", authContext.authConfigured());
        health.put("capabilities", request.capabilities());
        health.put("currentAttemptId", request.currentAttemptId());
        health.put("installedProfiles", request.installedProfiles());
        health.put("tags", request.tags());
        if (request.healthSnapshot() != null) {
            health.put("healthSnapshot", request.healthSnapshot());
        }
        runtime.setHealthJson(jsonCodec.write(health));
        runtime.setUpdatedAt(now);
        runtimeStateMapper.upsert(runtime);
    }

    private void refreshHeartbeatState(ExecutorAuthContext authContext,
                                       ExecutorIdentityRequest request,
                                       long now,
                                       TaskAttemptEntity activeAttempt,
                                       TaskEntity task,
                                       Long leaseExpireAt,
                                       String lastCommand) {
        upsertDeviceIfChanged(request, now);
        String healthJson = heartbeatHealthJson(authContext, request);
        String effectiveLastCommand = lastCommand != null ? lastCommand : existingLastCommand(request.deviceId());
        int updated = runtimeStateMapper.refreshHeartbeat(
                request.deviceId(),
                controlProperties.getConfigVersion(),
                leaseExpireAt,
                now,
                effectiveLastCommand,
                healthJson,
                now
        );
        if (updated != 1) {
            upsertDeviceAndRuntime(
                    authContext,
                    request,
                    now,
                    activeAttempt != null,
                    activeAttempt == null ? null : activeAttempt.getTaskId(),
                    activeAttempt == null ? null : activeAttempt.getAttemptId(),
                    task == null ? null : task.getTaskType(),
                    leaseExpireAt,
                    effectiveLastCommand
            );
        }
    }

    private void upsertDevice(ExecutorIdentityRequest request, long now) {
        DeviceEntity device = new DeviceEntity();
        device.setDeviceId(request.deviceId());
        device.setProtocolVersion(request.protocolVersion());
        device.setExecutorVersion(request.executorVersion());
        device.setBrand(request.brand());
        device.setModel(request.model());
        device.setAndroidVersion(request.androidVersion());
        device.setScreenWidth(request.screenWidth());
        device.setScreenHeight(request.screenHeight());
        device.setInstalledProfilesJson(jsonCodec.write(request.installedProfiles()));
        device.setTagsJson(jsonCodec.write(request.tags()));
        device.setHostGroup(request.hostGroup());
        device.setCreatedAt(now);
        device.setUpdatedAt(now);
        deviceMapper.upsert(device);
    }

    private void upsertDeviceIfChanged(ExecutorIdentityRequest request, long now) {
        DeviceEntity existing = deviceMapper.findById(request.deviceId());
        if (existing == null || deviceFactsChanged(existing, request)) {
            upsertDevice(request, now);
        }
    }

    private boolean deviceFactsChanged(DeviceEntity existing, ExecutorIdentityRequest request) {
        return !Objects.equals(existing.getProtocolVersion(), request.protocolVersion())
                || !Objects.equals(existing.getExecutorVersion(), request.executorVersion())
                || !Objects.equals(existing.getBrand(), request.brand())
                || !Objects.equals(existing.getModel(), request.model())
                || !Objects.equals(existing.getAndroidVersion(), request.androidVersion())
                || existing.getScreenWidth() != request.screenWidth()
                || existing.getScreenHeight() != request.screenHeight()
                || !Objects.equals(existing.getInstalledProfilesJson(), jsonCodec.write(request.installedProfiles()))
                || !Objects.equals(existing.getTagsJson(), jsonCodec.write(request.tags()))
                || !Objects.equals(existing.getHostGroup(), request.hostGroup());
    }

    private String heartbeatHealthJson(ExecutorAuthContext authContext, ExecutorIdentityRequest request) {
        Map<String, Object> health = new LinkedHashMap<>();
        health.put("authConfigured", authContext.authConfigured());
        health.put("capabilities", request.capabilities());
        health.put("currentAttemptId", request.currentAttemptId());
        health.put("installedProfiles", request.installedProfiles());
        health.put("tags", request.tags());
        if (request.healthSnapshot() != null) {
            health.put("healthSnapshot", request.healthSnapshot());
        }
        return jsonCodec.write(health);
    }

    private String existingLastCommand(String deviceId) {
        DeviceRuntimeStateEntity runtime = runtimeStateMapper.findById(deviceId);
        return runtime == null ? null : runtime.getLastCommand();
    }

    private DeliveryResult deliverPendingCommands(String deviceId, long now) {
        List<Command> commands = new ArrayList<>();
        String lastCommand = null;
        for (DeviceCommandEntity command : commandMapper.findPendingByDevice(deviceId, now)) {
            commands.add(new Command(command.getType(), command.getAttemptId()));
            commandMapper.updateStatus(command.getCommandId(), DomainValues.COMMAND_STATUS_DELIVERED);
            lastCommand = command.getType();
            log.info("command.delivered deviceId={} attemptId={} commandId={} type={}",
                    deviceId,
                    command.getAttemptId(),
                    command.getCommandId(),
                    command.getType());
        }
        return new DeliveryResult(commands, lastCommand);
    }

    private Long renewLease(TaskAttemptEntity attempt, long now) {
        long leaseExpireAt = now + controlProperties.getLeaseMs();
        int renewed = attemptMapper.renewLease(attempt.getAttemptId(), attempt.getDeviceId(), leaseExpireAt, now);
        if (renewed != 1) {
            log.info("lease.renew_lost taskId={} attemptId={} deviceId={}",
                    attempt.getTaskId(),
                    attempt.getAttemptId(),
                    attempt.getDeviceId());
            return null;
        }
        attempt.setLeaseExpireAt(leaseExpireAt);
        attempt.setUpdatedAt(now);
        log.info("lease.renew taskId={} attemptId={} deviceId={}",
                attempt.getTaskId(),
                attempt.getAttemptId(),
                attempt.getDeviceId());
        return leaseExpireAt;
    }

    private void validateIdentity(ExecutorAuthContext authContext, ExecutorIdentityRequest request) {
        if (!authContext.deviceId().equals(request.deviceId())
                || !authContext.protocolVersion().equals(request.protocolVersion())) {
            throw ControlApiExceptions.badRequest(ControlErrorCode.EXECUTOR_IDENTITY_MISMATCH);
        }
    }

    private void validateStartRequest(TaskEntity task, StartRequest request) {
        if (!Objects.equals(task.getTaskType(), request.taskType())
                || !Objects.equals(task.getProfilePackage(), request.profilePackage())
                || !Objects.equals(task.getSource(), request.source())) {
            throw ControlApiExceptions.badRequest(ControlErrorCode.EXECUTOR_IDENTITY_MISMATCH);
        }
    }

    private TaskAttemptEntity resolveAttempt(String deviceId, String attemptId) {
        if (attemptId == null || attemptId.isBlank()) {
            return null;
        }
        return attemptMapper.countActiveAttempt(deviceId, attemptId) > 0 ? attemptMapper.findById(attemptId) : null;
    }

    private TaskAttemptEntity requireAttempt(String attemptId) {
        return attemptAccessValidator.requireAttempt(attemptId);
    }

    private TaskEntity requireTask(String taskId) {
        TaskEntity task = taskMapper.findById(taskId);
        if (task == null) {
            throw ControlApiExceptions.notFound(ControlErrorCode.TASK_NOT_FOUND);
        }
        return task;
    }

    private RunConfig defaultRunConfig() {
        ControlProperties.DefaultRunConfig config = controlProperties.getDefaultRunConfig();
        return new RunConfig(
                config.getLoopCount(),
                config.getBudgetMs(),
                config.getLoopIntervalMs(),
                config.isNetworkIsolationEnabled(),
                config.getPollIntervalMs(),
                config.getHeartbeatIntervalMs()
        );
    }

    private RunConfig heartbeatRunConfig(DeviceRuntimeStateEntity runtime, TaskAttemptEntity activeAttempt) {
        ControlProperties.DefaultRunConfig config = controlProperties.getDefaultRunConfig();
        if (activeAttempt != null) {
            return defaultRunConfig();
        }
        if (runtime != null && DomainValues.DEVICE_STATUS_QUIESCED.equals(runtime.getStatus()) && !runtime.isBusy()) {
            return new RunConfig(
                    config.getLoopCount(),
                    config.getBudgetMs(),
                    config.getLoopIntervalMs(),
                    config.isNetworkIsolationEnabled(),
                    config.getPollIntervalMs(),
                    config.getQuiescedHeartbeatIntervalMs()
            );
        }
        if (runtime == null || !runtime.isBusy()) {
            return new RunConfig(
                    config.getLoopCount(),
                    config.getBudgetMs(),
                    config.getLoopIntervalMs(),
                    config.isNetworkIsolationEnabled(),
                    config.getIdlePollIntervalMs(),
                    config.getIdleHeartbeatIntervalMs()
            );
        }
        return defaultRunConfig();
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

    private String runtimeStatus(DeviceRuntimeStateEntity runtime) {
        if (runtime == null) {
            return DomainValues.DEVICE_STATUS_ONLINE;
        }
        if (DomainValues.DEVICE_STATUS_QUIESCED.equals(runtime.getStatus())) {
            return DomainValues.DEVICE_STATUS_QUIESCED;
        }
        if (DomainValues.DEVICE_STATUS_OFFLINE.equals(runtime.getStatus())) {
            return DomainValues.DEVICE_STATUS_OFFLINE;
        }
        return DomainValues.DEVICE_STATUS_ONLINE;
    }

    private record DeliveryResult(List<Command> commands, String lastCommand) {
    }
}

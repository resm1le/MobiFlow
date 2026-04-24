package com.example.platform.control.application;

import com.example.platform.control.api.AdminApiModels.ArtifactResponse;
import com.example.platform.control.api.AdminApiModels.AttemptDetailResponse;
import com.example.platform.control.api.AdminApiModels.AttemptSummary;
import com.example.platform.control.api.AdminApiModels.CommandAcceptedResponse;
import com.example.platform.control.api.AdminApiModels.CreateCommandRequest;
import com.example.platform.control.api.AdminApiModels.CreateTaskRequest;
import com.example.platform.control.api.AdminApiModels.DeviceResponse;
import com.example.platform.control.api.AdminApiModels.RunEventResponse;
import com.example.platform.control.api.AdminApiModels.TaskResponse;
import com.example.platform.control.api.ExecutorApiModels.ArtifactPolicy;
import com.example.platform.control.api.ExecutorApiModels.RunConfig;
import com.example.platform.control.domain.DomainValues;
import com.example.platform.control.domain.PersistenceModels.ArtifactEntity;
import com.example.platform.control.domain.PersistenceModels.DeviceCommandEntity;
import com.example.platform.control.domain.PersistenceModels.DeviceEntity;
import com.example.platform.control.domain.PersistenceModels.DeviceRuntimeStateEntity;
import com.example.platform.control.domain.PersistenceModels.RunEventEntity;
import com.example.platform.control.domain.PersistenceModels.TaskAttemptEntity;
import com.example.platform.control.domain.PersistenceModels.TaskEntity;
import com.example.platform.control.infrastructure.mapper.ArtifactMapper;
import com.example.platform.control.infrastructure.mapper.DeviceCommandMapper;
import com.example.platform.control.infrastructure.mapper.DeviceMapper;
import com.example.platform.control.infrastructure.mapper.DeviceRuntimeStateMapper;
import com.example.platform.control.infrastructure.mapper.RunEventMapper;
import com.example.platform.control.infrastructure.mapper.TaskAttemptMapper;
import com.example.platform.control.infrastructure.mapper.TaskMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

import java.io.InputStream;
import java.time.Clock;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

@Service
public class AdminApiService {

    private static final Logger log = LoggerFactory.getLogger(AdminApiService.class);

    private final DeviceMapper deviceMapper;
    private final DeviceRuntimeStateMapper runtimeStateMapper;
    private final TaskMapper taskMapper;
    private final TaskAttemptMapper attemptMapper;
    private final DeviceCommandMapper commandMapper;
    private final RunEventMapper runEventMapper;
    private final ArtifactMapper artifactMapper;
    private final ArtifactObjectStore artifactObjectStore;
    private final JsonCodec jsonCodec;
    private final IdGenerator idGenerator;
    private final ControlStateRules controlStateRules;
    private final TaskRequestValidator taskRequestValidator;
    private final ExperimentRunService experimentRunService;
    private final Clock clock = Clock.systemUTC();

    public AdminApiService(DeviceMapper deviceMapper,
                           DeviceRuntimeStateMapper runtimeStateMapper,
                           TaskMapper taskMapper,
                           TaskAttemptMapper attemptMapper,
                           DeviceCommandMapper commandMapper,
                           RunEventMapper runEventMapper,
                           ArtifactMapper artifactMapper,
                           ArtifactObjectStore artifactObjectStore,
                           JsonCodec jsonCodec,
                           IdGenerator idGenerator,
                           ControlStateRules controlStateRules,
                           TaskRequestValidator taskRequestValidator,
                           ExperimentRunService experimentRunService) {
        this.deviceMapper = deviceMapper;
        this.runtimeStateMapper = runtimeStateMapper;
        this.taskMapper = taskMapper;
        this.attemptMapper = attemptMapper;
        this.commandMapper = commandMapper;
        this.runEventMapper = runEventMapper;
        this.artifactMapper = artifactMapper;
        this.artifactObjectStore = artifactObjectStore;
        this.jsonCodec = jsonCodec;
        this.idGenerator = idGenerator;
        this.controlStateRules = controlStateRules;
        this.taskRequestValidator = taskRequestValidator;
        this.experimentRunService = experimentRunService;
    }

    public List<DeviceResponse> listDevices() {
        Map<String, DeviceRuntimeStateEntity> runtimes = runtimeStateMapper.findAll().stream()
                .collect(Collectors.toMap(DeviceRuntimeStateEntity::getDeviceId, Function.identity()));
        return deviceMapper.findAll().stream()
                .map(device -> toDeviceResponse(device, runtimes.get(device.getDeviceId())))
                .toList();
    }

    public DeviceResponse getDevice(String deviceId) {
        DeviceEntity device = requireDevice(deviceId);
        return toDeviceResponse(device, runtimeStateMapper.findById(deviceId));
    }

    public List<AttemptSummary> getDeviceAttempts(String deviceId) {
        requireDevice(deviceId);
        return attemptMapper.findByDeviceId(deviceId).stream()
                .map(this::toAttemptSummary)
                .toList();
    }

    @Transactional
    public DeviceResponse resumeDevice(String deviceId) {
        DeviceEntity device = requireDevice(deviceId);
        DeviceRuntimeStateEntity runtime = runtimeStateMapper.findById(deviceId);
        controlStateRules.validateRuntimeCanResume(runtime);
        long now = clock.millis();
        int updated = runtimeStateMapper.updateAssignmentIfCurrent(
                deviceId,
                runtime.getCurrentAttemptId(),
                runtime.isBusy(),
                controlStateRules.resumedRuntimeStatus(runtime),
                runtime.getCurrentTaskId(),
                runtime.getCurrentAttemptId(),
                runtime.getCurrentTaskType(),
                runtime.getLeaseExpireAt(),
                now
        );
        DeviceRuntimeStateEntity updatedRuntime = runtimeStateMapper.findById(deviceId);
        log.info("device.resume deviceId={} attemptId={} updated={} status={}",
                deviceId,
                runtime.getCurrentAttemptId(),
                updated == 1,
                updatedRuntime == null ? null : updatedRuntime.getStatus());
        return toDeviceResponse(device, updatedRuntime);
    }

    public List<AttemptSummary> listAttempts() {
        return attemptMapper.findAll().stream()
                .map(this::toAttemptSummary)
                .toList();
    }

    @Transactional
    public CommandAcceptedResponse enqueueCommand(String deviceId, CreateCommandRequest request) {
        requireDevice(deviceId);
        if (!DomainValues.ALLOWED_COMMAND_TYPES.contains(request.type())) {
            throw ControlApiExceptions.badRequest(ControlErrorCode.COMMAND_NOT_ALLOWED);
        }
        if ("CANCEL_ATTEMPT".equals(request.type()) && (request.attemptId() == null || request.attemptId().isBlank())) {
            throw ControlApiExceptions.badRequest(ControlErrorCode.COMMAND_NOT_ALLOWED);
        }
        long now = clock.millis();
        DeviceCommandEntity command = new DeviceCommandEntity();
        command.setDeviceId(deviceId);
        command.setType(request.type());
        command.setAttemptId(request.attemptId());
        command.setStatus(DomainValues.COMMAND_STATUS_PENDING);
        command.setIssuedAt(now);
        command.setExpireAt(request.expireInMs() == null ? null : now + request.expireInMs());
        commandMapper.insert(command);
        log.info("command.enqueue deviceId={} attemptId={} commandId={} type={}",
                deviceId,
                request.attemptId(),
                command.getCommandId(),
                request.type());
        if ("QUIESCE".equals(request.type())) {
            DeviceRuntimeStateEntity runtime = runtimeStateMapper.findById(deviceId);
            if (runtime != null) {
                runtimeStateMapper.updateBusyState(
                        deviceId,
                        runtime.isBusy(),
                        DomainValues.DEVICE_STATUS_QUIESCED,
                        runtime.getCurrentTaskId(),
                        runtime.getCurrentAttemptId(),
                        runtime.getCurrentTaskType(),
                        runtime.getLeaseExpireAt(),
                        runtime.getLastCommand(),
                        now
                );
            }
        }
        return new CommandAcceptedResponse(deviceId, request.type(), request.attemptId());
    }

    @Transactional
    public TaskResponse createTask(CreateTaskRequest request) {
        TaskRequestValidator.NormalizedTaskRequest normalized = taskRequestValidator.validateAndNormalize(request);
        long now = clock.millis();
        TaskEntity task = new TaskEntity();
        task.setTaskId(idGenerator.nextTaskId());
        task.setTaskType(normalized.taskType());
        task.setProfilePackage(normalized.profilePackage());
        task.setTaskPayloadJson(jsonCodec.write(normalized.taskPayload()));
        task.setRunConfigJson(jsonCodec.write(normalized.runConfig()));
        task.setArtifactPolicyJson(jsonCodec.write(normalized.artifactPolicy()));
        task.setPriority(normalized.priority());
        task.setLabelsJson(jsonCodec.write(normalized.labels()));
        task.setSource(normalized.source());
        task.setScheduleVersion(null);
        task.setIdempotencyKey(normalized.idempotencyKey() == null
                ? task.getTaskId()
                : normalized.idempotencyKey());
        task.setStatus(DomainValues.TASK_STATUS_QUEUED);
        task.setCreatedBy(normalized.createdBy());
        task.setCreatedAt(now);
        task.setUpdatedAt(now);
        taskMapper.insert(task);
        return toTaskResponse(task, null);
    }

    public List<TaskResponse> listTasks() {
        return taskMapper.findAll().stream()
                .map(task -> toTaskResponse(task, attemptMapper.findLatestByTaskId(task.getTaskId())))
                .toList();
    }

    public TaskResponse getTask(String taskId) {
        TaskEntity task = requireTask(taskId);
        return toTaskResponse(task, attemptMapper.findLatestByTaskId(taskId));
    }

    @Transactional
    public void cancelTask(String taskId) {
        TaskEntity task = requireLockedTask(taskId);
        long now = clock.millis();
        TaskAttemptEntity latestAttempt = DomainValues.TASK_STATUS_RUNNING.equals(task.getStatus())
                ? attemptMapper.findLatestByTaskId(taskId)
                : null;
        ControlStateRules.CancelAction cancelAction = controlStateRules.validateTaskCancellation(task, latestAttempt);
        if (cancelAction == ControlStateRules.CancelAction.CANCEL_DIRECTLY) {
            taskMapper.updateStatus(taskId, DomainValues.TASK_STATUS_CANCELLED, task.getScheduleVersion(), now);
            experimentRunService.onQueuedRunTaskCancelled(task, now);
            log.info("task.cancel_direct taskId={} scheduleVersion={}", taskId, task.getScheduleVersion());
            return;
        }
        if (attemptMapper.countActiveAttempt(latestAttempt.getDeviceId(), latestAttempt.getAttemptId()) != 1) {
            log.info("task.cancel_rejected taskId={} attemptId={} deviceId={} reason=attempt_not_active",
                    taskId,
                    latestAttempt.getAttemptId(),
                    latestAttempt.getDeviceId());
            throw ControlApiExceptions.badRequest(ControlErrorCode.TASK_STATE_INVALID);
        }
        if (commandMapper.countPendingByAttemptAndType(latestAttempt.getAttemptId(), "CANCEL_ATTEMPT", now) > 0) {
            log.info("task.cancel_noop taskId={} attemptId={} deviceId={} reason=command_already_pending",
                    taskId,
                    latestAttempt.getAttemptId(),
                    latestAttempt.getDeviceId());
            return;
        }
        DeviceCommandEntity command = new DeviceCommandEntity();
        command.setDeviceId(latestAttempt.getDeviceId());
        command.setType("CANCEL_ATTEMPT");
        command.setAttemptId(latestAttempt.getAttemptId());
        command.setStatus(DomainValues.COMMAND_STATUS_PENDING);
        command.setIssuedAt(now);
        commandMapper.insert(command);
        log.info("task.cancel_enqueued taskId={} attemptId={} deviceId={} commandId={}",
                taskId,
                latestAttempt.getAttemptId(),
                latestAttempt.getDeviceId(),
                command.getCommandId());
    }

    public AttemptDetailResponse getAttempt(String attemptId) {
        TaskAttemptEntity attempt = requireAttempt(attemptId);
        return new AttemptDetailResponse(toAttemptSummary(attempt), getAttemptEvents(attemptId), getAttemptArtifacts(attemptId));
    }

    public List<RunEventResponse> getAttemptEvents(String attemptId) {
        requireAttempt(attemptId);
        return runEventMapper.findByAttemptId(attemptId).stream()
                .map(this::toRunEventResponse)
                .toList();
    }

    public List<ArtifactResponse> getAttemptArtifacts(String attemptId) {
        requireAttempt(attemptId);
        return artifactMapper.findByAttemptId(attemptId).stream()
                .map(this::toArtifactResponse)
                .toList();
    }

    public ArtifactDownload downloadAttemptArtifact(String attemptId, String artifactId) {
        requireAttempt(attemptId);
        ArtifactEntity artifact = artifactMapper.findByAttemptIdAndArtifactId(attemptId, artifactId);
        if (artifact == null) {
            throw ControlApiExceptions.notFound(ControlErrorCode.ARTIFACT_NOT_FOUND);
        }
        try {
            return new ArtifactDownload(
                    artifact.getFileName(),
                    artifact.getMimeType(),
                    artifactObjectStore.open(artifact.getObjectKey())
            );
        } catch (ArtifactObjectMissingException exception) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, ControlErrorCode.ARTIFACT_OBJECT_MISSING, exception);
        } catch (ResponseStatusException exception) {
            throw exception;
        } catch (ArtifactObjectStoreException exception) {
            throw ControlApiExceptions.internal(ControlErrorCode.ARTIFACT_DOWNLOAD_FAILED, exception);
        }
    }

    private DeviceEntity requireDevice(String deviceId) {
        DeviceEntity device = deviceMapper.findById(deviceId);
        if (device == null) {
            throw ControlApiExceptions.notFound(ControlErrorCode.DEVICE_NOT_FOUND);
        }
        return device;
    }

    private TaskEntity requireTask(String taskId) {
        TaskEntity task = taskMapper.findById(taskId);
        if (task == null) {
            throw ControlApiExceptions.notFound(ControlErrorCode.TASK_NOT_FOUND);
        }
        return task;
    }

    private TaskEntity requireLockedTask(String taskId) {
        TaskEntity task = taskMapper.lockById(taskId);
        if (task == null) {
            throw ControlApiExceptions.notFound(ControlErrorCode.TASK_NOT_FOUND);
        }
        return task;
    }

    private TaskAttemptEntity requireAttempt(String attemptId) {
        TaskAttemptEntity attempt = attemptMapper.findById(attemptId);
        if (attempt == null) {
            throw ControlApiExceptions.notFound(ControlErrorCode.ATTEMPT_NOT_FOUND);
        }
        return attempt;
    }

    private DeviceResponse toDeviceResponse(DeviceEntity device, DeviceRuntimeStateEntity runtime) {
        return new DeviceResponse(
                device.getDeviceId(),
                device.getProtocolVersion(),
                device.getExecutorVersion(),
                device.getBrand(),
                device.getModel(),
                device.getAndroidVersion(),
                device.getScreenWidth(),
                device.getScreenHeight(),
                jsonCodec.readStringList(device.getInstalledProfilesJson()),
                jsonCodec.readStringList(device.getTagsJson()),
                device.getHostGroup(),
                runtime != null && runtime.isRegistered(),
                runtime != null && runtime.isOnline(),
                runtime != null && runtime.isBusy(),
                runtime == null ? DomainValues.DEVICE_STATUS_OFFLINE : runtime.getStatus(),
                runtime == null ? null : runtime.getCurrentTaskId(),
                runtime == null ? null : runtime.getCurrentAttemptId(),
                runtime == null ? null : runtime.getCurrentTaskType(),
                runtime == null ? null : runtime.getConfigVersion(),
                runtime != null && Boolean.TRUE.equals(jsonCodec.readMap(runtime.getHealthJson()).get("authConfigured")),
                runtime == null ? null : runtime.getLeaseExpireAt(),
                runtime == null ? 0 : runtime.getLastHeartbeatAt(),
                runtime == null ? null : runtime.getLastCommand(),
                runtime == null ? Map.of() : jsonCodec.readMap(runtime.getHealthJson()),
                runtime == null ? device.getUpdatedAt() : runtime.getUpdatedAt()
        );
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

    private RunEventResponse toRunEventResponse(RunEventEntity event) {
        return new RunEventResponse(
                event.getId(),
                event.getAttemptId(),
                event.getTaskId(),
                event.getDeviceId(),
                event.getRunId(),
                event.getScenarioId(),
                event.getStepIndex(),
                event.getActionIndex(),
                event.getEventType(),
                event.getState(),
                event.getCode(),
                event.getMessage(),
                event.getTs()
        );
    }

    private ArtifactResponse toArtifactResponse(ArtifactEntity artifact) {
        return new ArtifactResponse(
                artifact.getArtifactId(),
                artifact.getAttemptId(),
                artifact.getTaskId(),
                artifact.getRunId(),
                artifact.getArtifactType(),
                artifact.getFileName(),
                artifact.getMimeType(),
                artifact.getSizeBytes(),
                artifact.getObjectKey(),
                "/api/attempts/" + artifact.getAttemptId() + "/artifacts/" + artifact.getArtifactId() + "/download",
                artifact.getCreatedAt()
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

    public record ArtifactDownload(
            String fileName,
            String mimeType,
            InputStream inputStream
    ) {
    }
}

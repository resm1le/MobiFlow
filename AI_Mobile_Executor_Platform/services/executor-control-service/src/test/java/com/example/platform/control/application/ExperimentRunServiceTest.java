package com.example.platform.control.application;

import com.example.platform.control.api.AdminApiModels.CreateExperimentRunRequest;
import com.example.platform.control.api.AdminApiModels.CreateHeterogeneousRunRequest;
import com.example.platform.control.api.AdminApiModels.CreateSingleDeviceRunRequest;
import com.example.platform.control.api.AdminApiModels.DeviceSelector;
import com.example.platform.control.api.AdminApiModels.HeterogeneousDispatchEntry;
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
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.mockito.Mockito;
import org.springframework.web.server.ResponseStatusException;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class ExperimentRunServiceTest {

    private DevicePoolMapper devicePoolMapper;
    private ExperimentRunMapper experimentRunMapper;
    private ExperimentRunTargetMapper experimentRunTargetMapper;
    private DeviceMapper deviceMapper;
    private DeviceRuntimeStateMapper runtimeStateMapper;
    private TaskMapper taskMapper;
    private TaskAttemptMapper taskAttemptMapper;
    private DeviceCommandMapper commandMapper;
    private IdGenerator idGenerator;
    private ExperimentRunService experimentRunService;

    @BeforeEach
    void setUp() {
        devicePoolMapper = Mockito.mock(DevicePoolMapper.class);
        experimentRunMapper = Mockito.mock(ExperimentRunMapper.class);
        experimentRunTargetMapper = Mockito.mock(ExperimentRunTargetMapper.class);
        deviceMapper = Mockito.mock(DeviceMapper.class);
        runtimeStateMapper = Mockito.mock(DeviceRuntimeStateMapper.class);
        taskMapper = Mockito.mock(TaskMapper.class);
        taskAttemptMapper = Mockito.mock(TaskAttemptMapper.class);
        commandMapper = Mockito.mock(DeviceCommandMapper.class);
        idGenerator = Mockito.mock(IdGenerator.class);
        JsonCodec jsonCodec = new JsonCodec(new ObjectMapper());
        TaskRequestValidator taskRequestValidator = new TaskRequestValidator();
        experimentRunService = new ExperimentRunService(
                devicePoolMapper,
                experimentRunMapper,
                experimentRunTargetMapper,
                deviceMapper,
                runtimeStateMapper,
                taskMapper,
                taskAttemptMapper,
                commandMapper,
                jsonCodec,
                idGenerator,
                taskRequestValidator,
                new HeterogeneousDispatchResolver(deviceMapper, runtimeStateMapper, taskRequestValidator, jsonCodec)
        );
    }

    @Test
    void createRunCreatesQueuedTaskPerSelectedDevice() {
        DevicePoolEntity pool = devicePool("pool-1");
        when(devicePoolMapper.findById("pool-1")).thenReturn(pool);
        when(runtimeStateMapper.findAll()).thenReturn(List.of(
                runtime("device-1", true, true, DomainValues.DEVICE_STATUS_ONLINE),
                runtime("device-2", true, true, DomainValues.DEVICE_STATUS_ONLINE),
                runtime("device-3", true, false, DomainValues.DEVICE_STATUS_OFFLINE)
        ));
        when(deviceMapper.findAll()).thenReturn(List.of(
                device("device-1", "default", List.of("lab"), List.of("com.google.android.apps.maps")),
                device("device-2", "default", List.of("lab"), List.of("com.google.android.apps.maps")),
                device("device-3", "default", List.of("lab"), List.of("com.google.android.apps.maps"))
        ));
        when(idGenerator.nextRunId()).thenReturn("run-1");
        when(idGenerator.nextRunTargetId()).thenReturn("target-1", "target-2");
        when(idGenerator.nextTaskId()).thenReturn("task-1", "task-2");

        Map<String, TaskEntity> tasksById = new LinkedHashMap<>();
        List<ExperimentRunTargetEntity> storedTargets = new ArrayList<>();
        ArgumentCaptor<ExperimentRunEntity> runCaptor = ArgumentCaptor.forClass(ExperimentRunEntity.class);
        doAnswer(invocation -> {
            TaskEntity task = invocation.getArgument(0);
            tasksById.put(task.getTaskId(), task);
            return null;
        }).when(taskMapper).insert(any(TaskEntity.class));
        doAnswer(invocation -> {
            ExperimentRunTargetEntity target = invocation.getArgument(0);
            storedTargets.add(target);
            return null;
        }).when(experimentRunTargetMapper).insert(any(ExperimentRunTargetEntity.class));
        doAnswer(invocation -> null).when(experimentRunMapper).insert(runCaptor.capture());
        when(experimentRunMapper.findById("run-1")).thenAnswer(invocation -> runCaptor.getValue());
        when(experimentRunTargetMapper.findByRunId("run-1")).thenAnswer(invocation -> storedTargets);
        when(taskMapper.findById(any())).thenAnswer(invocation -> tasksById.get(invocation.getArgument(0)));

        var response = experimentRunService.createRun(createRunRequest());

        assertEquals("run-1", response.run().runId());
        assertEquals(2, response.run().counts().totalTargets());
        assertEquals(2, storedTargets.size());
        assertEquals(2, tasksById.size());
        assertEquals("task-1", storedTargets.get(0).getCurrentTaskId());
        assertEquals("task-2", storedTargets.get(1).getCurrentTaskId());
        assertEquals("device-1", tasksById.get("task-1").getTargetDeviceId());
        assertEquals("device-2", tasksById.get("task-2").getTargetDeviceId());
        assertEquals("run-1", tasksById.get("task-1").getRunId());
        assertEquals("target-1", tasksById.get("task-1").getRunTargetId());
    }

    @Test
    void createRunRejectsWhenNoMatchingDeviceExists() {
        when(devicePoolMapper.findById("pool-1")).thenReturn(devicePool("pool-1"));
        when(runtimeStateMapper.findAll()).thenReturn(List.of(
                runtime("device-1", true, false, DomainValues.DEVICE_STATUS_OFFLINE)
        ));
        when(deviceMapper.findAll()).thenReturn(List.of(
                device("device-1", "default", List.of(), List.of("com.google.android.apps.maps"))
        ));

        ResponseStatusException exception = assertThrows(
                ResponseStatusException.class,
                () -> experimentRunService.createRun(createRunRequest())
        );

        assertEquals(ControlErrorCode.EXPERIMENT_RUN_INVALID, exception.getReason());
        verify(experimentRunMapper, never()).insert(any());
    }

    @Test
    void createSingleDeviceRunCreatesSingleTargetBoundToRequestedDevice() {
        DeviceEntity device = device("device-1", "default", List.of("lab"), List.of("com.google.android.apps.maps"));
        when(deviceMapper.findById("device-1")).thenReturn(device);
        when(idGenerator.nextRunId()).thenReturn("run-single-1");
        when(idGenerator.nextRunTargetId()).thenReturn("target-single-1");
        when(idGenerator.nextTaskId()).thenReturn("task-single-1");

        Map<String, TaskEntity> tasksById = new LinkedHashMap<>();
        List<ExperimentRunTargetEntity> storedTargets = new ArrayList<>();
        ArgumentCaptor<ExperimentRunEntity> runCaptor = ArgumentCaptor.forClass(ExperimentRunEntity.class);
        doAnswer(invocation -> {
            TaskEntity task = invocation.getArgument(0);
            tasksById.put(task.getTaskId(), task);
            return null;
        }).when(taskMapper).insert(any(TaskEntity.class));
        doAnswer(invocation -> {
            ExperimentRunTargetEntity target = invocation.getArgument(0);
            storedTargets.add(target);
            return null;
        }).when(experimentRunTargetMapper).insert(any(ExperimentRunTargetEntity.class));
        doAnswer(invocation -> null).when(experimentRunMapper).insert(runCaptor.capture());
        when(experimentRunMapper.findById("run-single-1")).thenAnswer(invocation -> runCaptor.getValue());
        when(experimentRunTargetMapper.findByRunId("run-single-1")).thenAnswer(invocation -> storedTargets);
        when(taskMapper.findById(any())).thenAnswer(invocation -> tasksById.get(invocation.getArgument(0)));

        var response = experimentRunService.createSingleDeviceRun(createSingleDeviceRunRequest());

        assertEquals("run-single-1", response.run().runId());
        assertEquals(1, response.run().counts().totalTargets());
        assertEquals(1, storedTargets.size());
        assertEquals(1, tasksById.size());
        assertEquals("task-single-1", storedTargets.get(0).getCurrentTaskId());
        assertEquals("device-1", storedTargets.get(0).getDeviceId());
        assertEquals("device-1", tasksById.get("task-single-1").getTargetDeviceId());
        assertEquals(null, response.run().poolId());
    }

    @Test
    void createSingleDeviceRunRejectsWhenDeviceMissingRequiredProfile() {
        when(deviceMapper.findById("device-1")).thenReturn(device("device-1", "default", List.of(), List.of("com.demo.other")));

        ResponseStatusException exception = assertThrows(
                ResponseStatusException.class,
                () -> experimentRunService.createSingleDeviceRun(createSingleDeviceRunRequest())
        );

        assertEquals(ControlErrorCode.EXPERIMENT_RUN_INVALID, exception.getReason());
        verify(experimentRunMapper, never()).insert(any());
    }

    @Test
    void createHeterogeneousRunPersistsPerTargetSequenceAndTaskSpec() {
        when(deviceMapper.findAll()).thenReturn(List.of(
                device("device-1", "default", List.of("lab"), List.of("com.tencent.mm")),
                device("device-2", "default", List.of("lab"), List.of("com.tencent.mm")),
                device("device-3", "default", List.of("lab"), List.of("com.tencent.mm")),
                device("device-4", "default", List.of("lab"), List.of("com.demo.video")),
                device("device-5", "default", List.of("lab"), List.of("com.demo.video"))
        ));
        when(runtimeStateMapper.findAll()).thenReturn(List.of(
                runtime("device-1", true, true, DomainValues.DEVICE_STATUS_ONLINE),
                runtime("device-2", true, true, DomainValues.DEVICE_STATUS_ONLINE),
                runtime("device-3", true, true, DomainValues.DEVICE_STATUS_ONLINE),
                runtime("device-4", true, true, DomainValues.DEVICE_STATUS_ONLINE),
                runtime("device-5", true, true, DomainValues.DEVICE_STATUS_ONLINE)
        ));
        when(idGenerator.nextRunId()).thenReturn("run-heterogeneous");
        when(idGenerator.nextRunTargetId()).thenReturn("target-1", "target-2", "target-3", "target-4", "target-5");
        when(idGenerator.nextTaskId()).thenReturn("task-1", "task-2", "task-3", "task-4", "task-5");

        Map<String, TaskEntity> tasks = new LinkedHashMap<>();
        List<ExperimentRunTargetEntity> targets = new ArrayList<>();
        ArgumentCaptor<ExperimentRunEntity> runCaptor = ArgumentCaptor.forClass(ExperimentRunEntity.class);
        doAnswer(invocation -> { TaskEntity task = invocation.getArgument(0); tasks.put(task.getTaskId(), task); return null; })
                .when(taskMapper).insert(any(TaskEntity.class));
        doAnswer(invocation -> { targets.add(invocation.getArgument(0)); return null; })
                .when(experimentRunTargetMapper).insert(any(ExperimentRunTargetEntity.class));
        doAnswer(invocation -> null).when(experimentRunMapper).insert(runCaptor.capture());
        when(experimentRunMapper.findById("run-heterogeneous")).thenAnswer(invocation -> runCaptor.getValue());
        when(experimentRunTargetMapper.findByRunId("run-heterogeneous")).thenReturn(targets);
        when(taskMapper.findById(any())).thenAnswer(invocation -> tasks.get(invocation.getArgument(0)));

        var response = experimentRunService.createHeterogeneousRun(new CreateHeterogeneousRunRequest(
                "mixed", null, "PLUGIN_RUN",
                new RunConfig(1, 60_000, 0, false, 15_000, 30_000),
                new ArtifactPolicy(true, true, true), 100, List.of("pcap"), "agent", "agent", 1, 300_000L,
                List.of(
                        new HeterogeneousDispatchEntry(
                                "wechat.text_chat.v1", "com.tencent.mm",
                                waypointPayload("wechat.text_chat.v1", "wechat_text_chat", "com.tencent.mm"),
                                new DeviceSelector(3, List.of(), List.of("lab"), List.of())),
                        new HeterogeneousDispatchEntry(
                                "demo.video_call.v1", "com.demo.video",
                                waypointPayload("demo.video_call.v1", "demo_video_call", "com.demo.video"),
                                new DeviceSelector(2, List.of(), List.of("lab"), List.of()))
                )
        ));

        assertEquals(5, response.targets().size());
        assertEquals(null, response.run().profilePackage());
        assertEquals(Map.of(), response.taskPayload());
        assertEquals(List.of("wechat.text_chat.v1", "wechat.text_chat.v1", "wechat.text_chat.v1", "demo.video_call.v1", "demo.video_call.v1"),
                targets.stream().map(ExperimentRunTargetEntity::getSequenceId).toList());
        assertEquals(List.of("com.tencent.mm", "com.tencent.mm", "com.tencent.mm", "com.demo.video", "com.demo.video"),
                tasks.values().stream().map(TaskEntity::getProfilePackage).toList());
    }

    @Test
    void onAttemptFinishedQueuesRetryTaskWhenRetryBudgetAllows() {
        ExperimentRunEntity run = new ExperimentRunEntity();
        run.setRunId("run-1");
        run.setTaskType("demo.navigate");
        run.setProfilePackage("com.google.android.apps.maps");
        run.setTaskPayloadJson("{\"target\":\"IKEA\"}");
        run.setRunConfigJson("{\"loopCount\":1,\"budgetMs\":60000,\"loopIntervalMs\":0,\"networkIsolationEnabled\":false,\"pollIntervalMs\":15000,\"heartbeatIntervalMs\":30000}");
        run.setArtifactPolicyJson("{\"uploadLog\":true,\"uploadScreenshot\":true,\"uploadDump\":true}");
        run.setPriority(100);
        run.setLabelsJson("[\"demo\"]");
        run.setSource("console-run");
        run.setCreatedBy("console");
        run.setMaxRetriesPerDevice(1);
        run.setStatus(DomainValues.RUN_STATUS_RUNNING);

        ExperimentRunTargetEntity target = new ExperimentRunTargetEntity();
        target.setRunTargetId("target-1");
        target.setRunId("run-1");
        target.setDeviceId("device-1");
        target.setStatus(DomainValues.RUN_TARGET_STATUS_RUNNING);
        target.setAttemptCount(1);
        target.setCurrentTaskId("task-1");

        TaskEntity task = new TaskEntity();
        task.setTaskId("task-1");
        task.setRunId("run-1");
        task.setRunTargetId("target-1");
        task.setTaskType("PLUGIN_RUN");
        task.setProfilePackage("com.target.profile");
        task.setTaskPayloadJson("{\"goal\":\"target-specific\"}");
        task.setRunConfigJson("{\"loopCount\":2}");
        task.setArtifactPolicyJson("{\"uploadLog\":true}");
        task.setPriority(77);
        task.setLabelsJson("[\"target\"]");
        task.setSource("target-source");
        task.setCreatedBy("target-owner");

        TaskAttemptEntity attempt = new TaskAttemptEntity();
        attempt.setAttemptId("attempt-1");
        attempt.setTaskId("task-1");
        attempt.setRunId("run-1");
        attempt.setStartedAt(1L);

        when(experimentRunTargetMapper.lockById("target-1")).thenReturn(target);
        when(experimentRunMapper.lockById("run-1")).thenReturn(run);
        when(experimentRunTargetMapper.findByRunId("run-1")).thenAnswer(invocation -> List.of(target));
        when(idGenerator.nextTaskId()).thenReturn("task-2");

        ArgumentCaptor<TaskEntity> taskCaptor = ArgumentCaptor.forClass(TaskEntity.class);

        experimentRunService.onAttemptFinished(task, attempt, "FAILED", "network", 10L);

        verify(taskMapper).insert(taskCaptor.capture());
        assertEquals(DomainValues.RUN_TARGET_STATUS_RETRY_PENDING, target.getStatus());
        assertEquals(2, target.getAttemptCount());
        assertEquals("task-2", target.getCurrentTaskId());
        assertEquals("attempt-1", target.getLatestAttemptId());
        assertEquals("device-1", taskCaptor.getValue().getTargetDeviceId());
        assertEquals("run-1", taskCaptor.getValue().getRunId());
        assertEquals("target-1", taskCaptor.getValue().getRunTargetId());
        assertEquals("com.target.profile", taskCaptor.getValue().getProfilePackage());
        assertEquals("{\"goal\":\"target-specific\"}", taskCaptor.getValue().getTaskPayloadJson());
        assertEquals(77, taskCaptor.getValue().getPriority());
        assertEquals("target-owner", taskCaptor.getValue().getCreatedBy());
        assertEquals(DomainValues.RUN_STATUS_RUNNING, run.getStatus());
    }

    @Test
    void queuedTimeoutRetryClonesCurrentTargetTaskSpec() {
        ExperimentRunEntity run = new ExperimentRunEntity();
        run.setRunId("run-1");
        run.setStatus(DomainValues.RUN_STATUS_QUEUED);
        run.setMaxRetriesPerDevice(1);
        run.setQueueTimeoutMs(1_000);

        ExperimentRunTargetEntity target = new ExperimentRunTargetEntity();
        target.setRunTargetId("target-1");
        target.setRunId("run-1");
        target.setDeviceId("device-1");
        target.setStatus(DomainValues.RUN_TARGET_STATUS_QUEUED);
        target.setAttemptCount(1);
        target.setCurrentTaskId("task-1");

        TaskEntity previous = new TaskEntity();
        previous.setTaskId("task-1");
        previous.setStatus(DomainValues.TASK_STATUS_QUEUED);
        previous.setCreatedAt(0);
        previous.setTaskType("PLUGIN_RUN");
        previous.setProfilePackage("com.target.profile");
        previous.setTaskPayloadJson("{\"goal\":\"target-specific\"}");
        previous.setRunConfigJson("{\"loopCount\":2}");
        previous.setArtifactPolicyJson("{\"uploadLog\":true}");
        previous.setPriority(77);
        previous.setLabelsJson("[\"target\"]");
        previous.setSource("target-source");
        previous.setCreatedBy("target-owner");

        when(experimentRunTargetMapper.findPendingQueueTargets()).thenReturn(List.of(target));
        when(experimentRunMapper.lockById("run-1")).thenReturn(run);
        when(taskMapper.findById("task-1")).thenReturn(previous);
        when(experimentRunTargetMapper.findByRunId("run-1")).thenReturn(List.of(target));
        when(idGenerator.nextTaskId()).thenReturn("task-2");
        ArgumentCaptor<TaskEntity> taskCaptor = ArgumentCaptor.forClass(TaskEntity.class);

        assertEquals(1, experimentRunService.reconcileQueuedTimeouts(2_000));

        verify(taskMapper).insert(taskCaptor.capture());
        assertEquals("com.target.profile", taskCaptor.getValue().getProfilePackage());
        assertEquals("{\"goal\":\"target-specific\"}", taskCaptor.getValue().getTaskPayloadJson());
        assertEquals("target-owner", taskCaptor.getValue().getCreatedBy());
    }

    @Test
    void cancelRunCancelsQueuedTargetsAndSignalsRunningAttempts() {
        ExperimentRunEntity run = new ExperimentRunEntity();
        run.setRunId("run-1");
        run.setStatus(DomainValues.RUN_STATUS_QUEUED);
        run.setCancelRequested(false);

        ExperimentRunTargetEntity queuedTarget = new ExperimentRunTargetEntity();
        queuedTarget.setRunTargetId("target-queued");
        queuedTarget.setRunId("run-1");
        queuedTarget.setStatus(DomainValues.RUN_TARGET_STATUS_QUEUED);
        queuedTarget.setCurrentTaskId("task-queued");

        ExperimentRunTargetEntity runningTarget = new ExperimentRunTargetEntity();
        runningTarget.setRunTargetId("target-running");
        runningTarget.setRunId("run-1");
        runningTarget.setStatus(DomainValues.RUN_TARGET_STATUS_RUNNING);
        runningTarget.setLatestAttemptId("attempt-1");
        runningTarget.setCurrentTaskId("task-running");

        TaskEntity queuedTask = new TaskEntity();
        queuedTask.setTaskId("task-queued");
        queuedTask.setStatus(DomainValues.TASK_STATUS_QUEUED);

        TaskAttemptEntity runningAttempt = new TaskAttemptEntity();
        runningAttempt.setAttemptId("attempt-1");
        runningAttempt.setDeviceId("device-1");
        runningAttempt.setStatus(DomainValues.ATTEMPT_STATUS_RUNNING);

        when(experimentRunMapper.lockById("run-1")).thenReturn(run);
        when(experimentRunTargetMapper.findByRunId("run-1")).thenAnswer(invocation -> List.of(queuedTarget, runningTarget));
        when(taskMapper.findById("task-queued")).thenReturn(queuedTask);
        when(taskMapper.findById("task-running")).thenReturn(task("task-running"));
        when(taskAttemptMapper.findById("attempt-1")).thenReturn(runningAttempt);
        when(commandMapper.countPendingByAttemptAndType(eq("attempt-1"), eq("CANCEL_ATTEMPT"), anyLong())).thenReturn(0);

        experimentRunService.cancelRun("run-1");

        verify(taskMapper).updateStatus(eq("task-queued"), eq(DomainValues.TASK_STATUS_CANCELLED), eq(null), anyLong());
        verify(commandMapper).insert(any());
        assertEquals(DomainValues.RUN_TARGET_STATUS_CANCELLED, queuedTarget.getStatus());
        assertEquals(DomainValues.RUN_STATUS_CANCELLING, run.getStatus());
        assertEquals(true, run.isCancelRequested());
    }

    private CreateExperimentRunRequest createRunRequest() {
        return new CreateExperimentRunRequest(
                "Maps batch",
                "demo",
                "pool-1",
                "demo.navigate",
                "com.google.android.apps.maps",
                Map.of("target", "IKEA"),
                new RunConfig(1, 60_000, 0, false, 15_000, 30_000),
                new ArtifactPolicy(true, true, true),
                100,
                List.of("demo"),
                "console-run",
                "console",
                0,
                300_000L
        );
    }

    private CreateSingleDeviceRunRequest createSingleDeviceRunRequest() {
        return new CreateSingleDeviceRunRequest(
                "Maps single",
                "single device",
                "device-1",
                "demo.navigate",
                "com.google.android.apps.maps",
                Map.of("target", "IKEA"),
                new RunConfig(1, 60_000, 0, false, 15_000, 30_000),
                new ArtifactPolicy(true, true, true),
                100,
                List.of("single"),
                "agent-run",
                "agent",
                0,
                300_000L
        );
    }

    private DevicePoolEntity devicePool(String poolId) {
        DevicePoolEntity pool = new DevicePoolEntity();
        pool.setPoolId(poolId);
        pool.setName("pool");
        pool.setDeviceIdsJson("[]");
        pool.setRequiredTagsJson("[]");
        pool.setExcludedTagsJson("[]");
        return pool;
    }

    private DeviceEntity device(String deviceId, String hostGroup, List<String> tags, List<String> profiles) {
        DeviceEntity device = new DeviceEntity();
        device.setDeviceId(deviceId);
        device.setHostGroup(hostGroup);
        device.setTagsJson(json(tags));
        device.setInstalledProfilesJson(json(profiles));
        return device;
    }

    private DeviceRuntimeStateEntity runtime(String deviceId, boolean registered, boolean online, String status) {
        DeviceRuntimeStateEntity runtime = new DeviceRuntimeStateEntity();
        runtime.setDeviceId(deviceId);
        runtime.setRegistered(registered);
        runtime.setOnline(online);
        runtime.setStatus(status);
        return runtime;
    }

    private TaskEntity task(String taskId) {
        TaskEntity task = new TaskEntity();
        task.setTaskId(taskId);
        task.setStatus(DomainValues.TASK_STATUS_RUNNING);
        return task;
    }

    private Map<String, Object> waypointPayload(String sequenceId, String behaviorLabel, String profilePackage) {
        return Map.of(
                "goal", "run " + sequenceId,
                "waypoint_sequence", Map.of(
                        "sequence_id", sequenceId,
                        "behavior_label", behaviorLabel,
                        "profile_package", profilePackage,
                        "waypoints", List.of(Map.of(
                                "waypoint_id", "ready",
                                "description", "Reach ready state.",
                                "arrival_spec", Map.of(
                                        "verification_id", "verify:ready",
                                        "target_kind", "task",
                                        "target_id", "ready",
                                        "success_checks", List.of(Map.of(
                                                "check_id", "ready-visible",
                                                "description", "Ready state is visible."
                                        ))
                                )
                        ))
                )
        );
    }

    private String json(List<String> values) {
        if (values.isEmpty()) {
            return "[]";
        }
        return "[\"" + String.join("\",\"", values) + "\"]";
    }
}

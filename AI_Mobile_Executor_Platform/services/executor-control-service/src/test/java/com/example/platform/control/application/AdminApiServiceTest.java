package com.example.platform.control.application;

import com.example.platform.control.api.AdminApiModels.CreateCommandRequest;
import com.example.platform.control.api.AdminApiModels.CreateTaskRequest;
import com.example.platform.control.api.ExecutorApiModels.ArtifactPolicy;
import com.example.platform.control.api.ExecutorApiModels.RunConfig;
import com.example.platform.control.domain.PersistenceModels.ArtifactEntity;
import com.example.platform.control.domain.DomainValues;
import com.example.platform.control.domain.PersistenceModels.DeviceRuntimeStateEntity;
import com.example.platform.control.domain.PersistenceModels.TaskAttemptEntity;
import com.example.platform.control.domain.PersistenceModels.TaskEntity;
import com.example.platform.control.domain.PersistenceModels.RunEventEntity;
import com.example.platform.control.infrastructure.mapper.ArtifactMapper;
import com.example.platform.control.infrastructure.mapper.DeviceCommandMapper;
import com.example.platform.control.infrastructure.mapper.DeviceMapper;
import com.example.platform.control.infrastructure.mapper.DeviceRuntimeStateMapper;
import com.example.platform.control.infrastructure.mapper.RunEventMapper;
import com.example.platform.control.infrastructure.mapper.TaskAttemptMapper;
import com.example.platform.control.infrastructure.mapper.TaskMapper;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.mockito.Mockito;
import org.springframework.web.server.ResponseStatusException;

import java.io.ByteArrayInputStream;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyBoolean;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class AdminApiServiceTest {

    private DeviceMapper deviceMapper;
    private DeviceRuntimeStateMapper runtimeStateMapper;
    private TaskMapper taskMapper;
    private TaskAttemptMapper attemptMapper;
    private DeviceCommandMapper commandMapper;
    private ArtifactMapper artifactMapper;
    private RunEventMapper runEventMapper;
    private ArtifactObjectStore artifactObjectStore;
    private IdGenerator idGenerator;
    private ControlStateRules controlStateRules;
    private TaskRequestValidator taskRequestValidator;
    private ExperimentRunService experimentRunService;
    private AdminApiService adminApiService;

    @BeforeEach
    void setUp() {
        deviceMapper = Mockito.mock(DeviceMapper.class);
        runtimeStateMapper = Mockito.mock(DeviceRuntimeStateMapper.class);
        taskMapper = Mockito.mock(TaskMapper.class);
        attemptMapper = Mockito.mock(TaskAttemptMapper.class);
        commandMapper = Mockito.mock(DeviceCommandMapper.class);
        runEventMapper = Mockito.mock(RunEventMapper.class);
        artifactMapper = Mockito.mock(ArtifactMapper.class);
        artifactObjectStore = Mockito.mock(ArtifactObjectStore.class);
        idGenerator = Mockito.mock(IdGenerator.class);
        controlStateRules = new ControlStateRules();
        taskRequestValidator = new TaskRequestValidator();
        experimentRunService = Mockito.mock(ExperimentRunService.class);

        JsonCodec jsonCodec = new JsonCodec(new ObjectMapper());
        adminApiService = new AdminApiService(
                deviceMapper,
                runtimeStateMapper,
                taskMapper,
                attemptMapper,
                commandMapper,
                runEventMapper,
                artifactMapper,
                artifactObjectStore,
                jsonCodec,
                idGenerator,
                controlStateRules,
                taskRequestValidator,
                experimentRunService
        );
    }

    @Test
    void rejectsLegacySlugProfilePackage() {
        CreateTaskRequest request = createTaskRequest("googlemaps");

        ResponseStatusException exception = assertThrows(ResponseStatusException.class, () -> adminApiService.createTask(request));

        assertEquals("PROFILE_PACKAGE_INVALID", exception.getReason());
    }

    @Test
    void persistsAndroidPackageNameProfilePackage() {
        when(idGenerator.nextTaskId()).thenReturn("task-123");
        CreateTaskRequest request = createTaskRequest("com.google.android.apps.maps");

        adminApiService.createTask(request);

        ArgumentCaptor<TaskEntity> taskCaptor = ArgumentCaptor.forClass(TaskEntity.class);
        verify(taskMapper).insert(taskCaptor.capture());
        assertEquals("com.google.android.apps.maps", taskCaptor.getValue().getProfilePackage());
    }

    @Test
    void attemptEventsExposeStructuredPayloadAndKeepLegacyPayloadNull() {
        RunEventEntity waypoint = new RunEventEntity();
        waypoint.setAttemptId("attempt-1");
        waypoint.setTaskId("task-1");
        waypoint.setDeviceId("device-1");
        waypoint.setRunId("run-1");
        waypoint.setEventType("WAYPOINT_SEGMENT");
        waypoint.setMessage("waypoint_segment:0:COMPLETE");
        waypoint.setPayloadJson("{\"step_id\":\"logged_in\",\"deviceId\":\"device-1\"}");
        waypoint.setTs(1_500);
        RunEventEntity legacy = new RunEventEntity();
        legacy.setAttemptId("attempt-1");
        legacy.setTaskId("task-1");
        legacy.setDeviceId("device-1");
        legacy.setRunId("run-1");
        legacy.setEventType("STEP");
        legacy.setMessage("legacy");
        legacy.setTs(1_000);
        when(attemptMapper.findById("attempt-1")).thenReturn(new TaskAttemptEntity());
        when(runEventMapper.findByAttemptId("attempt-1")).thenReturn(List.of(legacy, waypoint));

        var events = adminApiService.getAttemptEvents("attempt-1");

        assertEquals(null, events.get(0).payload());
        assertEquals("logged_in", events.get(1).payload().get("step_id"));
        assertEquals("device-1", events.get(1).payload().get("deviceId"));
    }

    @Test
    void rejectsTaskWithoutEffectiveArtifactPolicy() {
        CreateTaskRequest request = new CreateTaskRequest(
                "demo.navigate",
                "com.google.android.apps.maps",
                Map.of("target", "IKEA"),
                new RunConfig(1, 60_000, 0, false, 15_000, 30_000),
                new ArtifactPolicy(false, false, false),
                100,
                List.of("demo"),
                "console",
                "tester",
                null
        );

        ResponseStatusException exception = assertThrows(ResponseStatusException.class, () -> adminApiService.createTask(request));

        assertEquals(ControlErrorCode.TASK_STATE_INVALID, exception.getReason());
    }

    @Test
    void cancelsRunningTaskByEnqueueingCancelAttemptCommand() {
        TaskEntity task = new TaskEntity();
        task.setTaskId("task-1");
        task.setStatus(DomainValues.TASK_STATUS_RUNNING);
        when(taskMapper.lockById("task-1")).thenReturn(task);

        TaskAttemptEntity attempt = new TaskAttemptEntity();
        attempt.setAttemptId("attempt-1");
        attempt.setTaskId("task-1");
        attempt.setDeviceId("device-1");
        attempt.setStatus(DomainValues.ATTEMPT_STATUS_RUNNING);
        when(attemptMapper.findLatestByTaskId("task-1")).thenReturn(attempt);
        when(attemptMapper.countActiveAttempt("device-1", "attempt-1")).thenReturn(1);
        when(commandMapper.countPendingByAttemptAndType(eq("attempt-1"), eq("CANCEL_ATTEMPT"), anyLong())).thenReturn(0);

        adminApiService.cancelTask("task-1");

        ArgumentCaptor<com.example.platform.control.domain.PersistenceModels.DeviceCommandEntity> commandCaptor =
                ArgumentCaptor.forClass(com.example.platform.control.domain.PersistenceModels.DeviceCommandEntity.class);
        verify(commandMapper).insert(commandCaptor.capture());
        assertEquals("device-1", commandCaptor.getValue().getDeviceId());
        assertEquals("CANCEL_ATTEMPT", commandCaptor.getValue().getType());
        assertEquals("attempt-1", commandCaptor.getValue().getAttemptId());
    }

    @Test
    void quiesceCommandSetsRuntimeStatusToQuiesced() {
        when(deviceMapper.findById("device-1")).thenReturn(device("device-1"));
        DeviceRuntimeStateEntity runtime = new DeviceRuntimeStateEntity();
        runtime.setDeviceId("device-1");
        runtime.setOnline(true);
        runtime.setBusy(false);
        runtime.setStatus(DomainValues.DEVICE_STATUS_ONLINE);
        when(runtimeStateMapper.findById("device-1")).thenReturn(runtime);

        adminApiService.enqueueCommand("device-1", new CreateCommandRequest("QUIESCE", null, 30000L));

        verify(runtimeStateMapper).updateBusyState(anyString(), anyBoolean(), anyString(), any(), any(), any(), any(), any(), anyLong());
    }

    @Test
    void resumeDeviceRestoresOnlineStatusWithoutClearingAssignment() {
        when(deviceMapper.findById("device-1")).thenReturn(device("device-1"));
        DeviceRuntimeStateEntity runtime = new DeviceRuntimeStateEntity();
        runtime.setDeviceId("device-1");
        runtime.setOnline(true);
        runtime.setBusy(true);
        runtime.setStatus(DomainValues.DEVICE_STATUS_QUIESCED);
        runtime.setCurrentTaskId("task-1");
        runtime.setCurrentAttemptId("attempt-1");
        runtime.setCurrentTaskType("demo.navigate");
        runtime.setLeaseExpireAt(123L);
        runtime.setLastCommand("QUIESCE");
        when(runtimeStateMapper.updateAssignmentIfCurrent(
                eq("device-1"),
                eq("attempt-1"),
                eq(true),
                eq(DomainValues.DEVICE_STATUS_ONLINE),
                eq("task-1"),
                eq("attempt-1"),
                eq("demo.navigate"),
                eq(123L),
                anyLong()
        )).thenReturn(1);
        when(runtimeStateMapper.findById("device-1")).thenReturn(runtime, updatedRuntime("device-1", DomainValues.DEVICE_STATUS_ONLINE, true));

        var response = adminApiService.resumeDevice("device-1");

        verify(runtimeStateMapper).updateAssignmentIfCurrent(anyString(), anyString(), anyBoolean(), anyString(), any(), any(), any(), any(), anyLong());
        assertEquals(DomainValues.DEVICE_STATUS_ONLINE, response.status());
        assertEquals("task-1", response.currentTaskId());
        assertEquals("attempt-1", response.currentAttemptId());
        assertTrue(response.busy());
    }

    @Test
    void resumeDeviceRestoresOfflineStatusWhenRuntimeIsOffline() {
        when(deviceMapper.findById("device-2")).thenReturn(device("device-2"));
        DeviceRuntimeStateEntity runtime = new DeviceRuntimeStateEntity();
        runtime.setDeviceId("device-2");
        runtime.setOnline(false);
        runtime.setBusy(false);
        runtime.setStatus(DomainValues.DEVICE_STATUS_QUIESCED);
        when(runtimeStateMapper.updateAssignmentIfCurrent(
                eq("device-2"),
                isNull(),
                eq(false),
                eq(DomainValues.DEVICE_STATUS_OFFLINE),
                isNull(),
                isNull(),
                isNull(),
                isNull(),
                anyLong()
        )).thenReturn(1);
        when(runtimeStateMapper.findById("device-2")).thenReturn(runtime, updatedRuntime("device-2", DomainValues.DEVICE_STATUS_OFFLINE, false));

        var response = adminApiService.resumeDevice("device-2");

        assertEquals(DomainValues.DEVICE_STATUS_OFFLINE, response.status());
        assertEquals(false, response.online());
    }

    @Test
    void resumeDeviceRejectsNonQuiescedRuntime() {
        when(deviceMapper.findById("device-3")).thenReturn(device("device-3"));
        DeviceRuntimeStateEntity runtime = new DeviceRuntimeStateEntity();
        runtime.setDeviceId("device-3");
        runtime.setOnline(true);
        runtime.setBusy(false);
        runtime.setStatus(DomainValues.DEVICE_STATUS_ONLINE);
        when(runtimeStateMapper.findById("device-3")).thenReturn(runtime);

        ResponseStatusException exception = assertThrows(ResponseStatusException.class, () ->
                adminApiService.resumeDevice("device-3"));

        verify(runtimeStateMapper, Mockito.never()).updateAssignmentIfCurrent(anyString(), any(), anyBoolean(), anyString(), any(), any(), any(), any(), anyLong());
        assertEquals(ControlErrorCode.DEVICE_STATE_INVALID, exception.getReason());
    }

    @Test
    void cancelTaskRejectsRunningTaskWithoutActiveAttempt() {
        TaskEntity task = new TaskEntity();
        task.setTaskId("task-2");
        task.setStatus(DomainValues.TASK_STATUS_RUNNING);
        when(taskMapper.lockById("task-2")).thenReturn(task);

        TaskAttemptEntity attempt = new TaskAttemptEntity();
        attempt.setAttemptId("attempt-2");
        attempt.setDeviceId("device-2");
        attempt.setStatus(DomainValues.ATTEMPT_STATUS_SUCCEEDED);
        when(attemptMapper.findLatestByTaskId("task-2")).thenReturn(attempt);
        when(attemptMapper.countActiveAttempt(eq("device-2"), eq("attempt-2"))).thenReturn(0);

        ResponseStatusException exception = assertThrows(ResponseStatusException.class, () -> adminApiService.cancelTask("task-2"));

        assertEquals(ControlErrorCode.TASK_STATE_INVALID, exception.getReason());
        verify(commandMapper, Mockito.never()).insert(any());
    }

    @Test
    void cancelTaskDoesNotDuplicatePendingCancelCommand() {
        TaskEntity task = new TaskEntity();
        task.setTaskId("task-3");
        task.setStatus(DomainValues.TASK_STATUS_RUNNING);
        when(taskMapper.lockById("task-3")).thenReturn(task);

        TaskAttemptEntity attempt = new TaskAttemptEntity();
        attempt.setAttemptId("attempt-3");
        attempt.setTaskId("task-3");
        attempt.setDeviceId("device-3");
        attempt.setStatus(DomainValues.ATTEMPT_STATUS_RUNNING);
        when(attemptMapper.findLatestByTaskId("task-3")).thenReturn(attempt);
        when(attemptMapper.countActiveAttempt("device-3", "attempt-3")).thenReturn(1);
        when(commandMapper.countPendingByAttemptAndType(eq("attempt-3"), eq("CANCEL_ATTEMPT"), anyLong())).thenReturn(1);

        adminApiService.cancelTask("task-3");

        verify(commandMapper, Mockito.never()).insert(any());
    }

    @Test
    void resumeDeviceDoesNotRestoreStaleAssignmentWhenConditionalUpdateLosesRace() {
        when(deviceMapper.findById("device-4")).thenReturn(device("device-4"));
        DeviceRuntimeStateEntity runtime = new DeviceRuntimeStateEntity();
        runtime.setDeviceId("device-4");
        runtime.setOnline(true);
        runtime.setBusy(true);
        runtime.setStatus(DomainValues.DEVICE_STATUS_QUIESCED);
        runtime.setCurrentTaskId("task-4");
        runtime.setCurrentAttemptId("attempt-4");
        runtime.setCurrentTaskType("demo.navigate");
        runtime.setLeaseExpireAt(123L);
        runtime.setLastCommand("QUIESCE");
        DeviceRuntimeStateEntity clearedRuntime = new DeviceRuntimeStateEntity();
        clearedRuntime.setDeviceId("device-4");
        clearedRuntime.setOnline(true);
        clearedRuntime.setBusy(false);
        clearedRuntime.setStatus(DomainValues.DEVICE_STATUS_ONLINE);
        clearedRuntime.setConfigVersion("cfg-v1");
        clearedRuntime.setLastHeartbeatAt(456L);
        clearedRuntime.setUpdatedAt(789L);
        clearedRuntime.setHealthJson("{\"authConfigured\":true}");
        when(runtimeStateMapper.findById("device-4")).thenReturn(runtime, clearedRuntime);
        when(runtimeStateMapper.updateAssignmentIfCurrent(
                eq("device-4"),
                eq("attempt-4"),
                eq(true),
                eq(DomainValues.DEVICE_STATUS_ONLINE),
                eq("task-4"),
                eq("attempt-4"),
                eq("demo.navigate"),
                eq(123L),
                anyLong()
        )).thenReturn(0);

        var response = adminApiService.resumeDevice("device-4");

        assertEquals(DomainValues.DEVICE_STATUS_ONLINE, response.status());
        assertEquals(null, response.currentTaskId());
        assertEquals(null, response.currentAttemptId());
        assertEquals(false, response.busy());
    }

    @Test
    void getAttemptArtifactsIncludesDownloadPath() {
        TaskAttemptEntity attempt = new TaskAttemptEntity();
        attempt.setAttemptId("attempt-1");
        when(attemptMapper.findById("attempt-1")).thenReturn(attempt);

        ArtifactEntity artifact = new ArtifactEntity();
        artifact.setArtifactId("artifact-1");
        artifact.setAttemptId("attempt-1");
        artifact.setTaskId("task-1");
        artifact.setRunId("run-1");
        artifact.setArtifactType("run_log");
        artifact.setFileName("run.log");
        artifact.setMimeType("text/plain");
        artifact.setSizeBytes(4L);
        artifact.setObjectKey("artifacts/task-1/attempt-1/artifact-1/run.log");
        artifact.setCreatedAt(1L);
        when(artifactMapper.findByAttemptId("attempt-1")).thenReturn(List.of(artifact));

        var response = adminApiService.getAttemptArtifacts("attempt-1");

        assertEquals("/api/attempts/attempt-1/artifacts/artifact-1/download", response.get(0).downloadPath());
    }

    @Test
    void downloadAttemptArtifactReturnsMetadataAndStream() {
        TaskAttemptEntity attempt = new TaskAttemptEntity();
        attempt.setAttemptId("attempt-1");
        when(attemptMapper.findById("attempt-1")).thenReturn(attempt);

        ArtifactEntity artifact = new ArtifactEntity();
        artifact.setArtifactId("artifact-1");
        artifact.setAttemptId("attempt-1");
        artifact.setObjectKey("artifacts/task-1/attempt-1/artifact-1/run.log");
        artifact.setFileName("run.log");
        artifact.setMimeType("text/plain");
        when(artifactMapper.findByAttemptIdAndArtifactId("attempt-1", "artifact-1")).thenReturn(artifact);
        when(artifactObjectStore.open("artifacts/task-1/attempt-1/artifact-1/run.log"))
                .thenReturn(new ByteArrayInputStream("demo".getBytes()));

        var response = adminApiService.downloadAttemptArtifact("attempt-1", "artifact-1");

        assertEquals("run.log", response.fileName());
        assertEquals("text/plain", response.mimeType());
    }

    @Test
    void downloadAttemptArtifactReturnsObjectMissingWhenStorageIsGone() {
        TaskAttemptEntity attempt = new TaskAttemptEntity();
        attempt.setAttemptId("attempt-1");
        when(attemptMapper.findById("attempt-1")).thenReturn(attempt);

        ArtifactEntity artifact = new ArtifactEntity();
        artifact.setArtifactId("artifact-1");
        artifact.setAttemptId("attempt-1");
        artifact.setObjectKey("artifacts/task-1/attempt-1/artifact-1/run.log");
        when(artifactMapper.findByAttemptIdAndArtifactId("attempt-1", "artifact-1")).thenReturn(artifact);
        when(artifactObjectStore.open("artifacts/task-1/attempt-1/artifact-1/run.log"))
                .thenThrow(new ArtifactObjectMissingException("missing"));

        ResponseStatusException exception = assertThrows(
                ResponseStatusException.class,
                () -> adminApiService.downloadAttemptArtifact("attempt-1", "artifact-1")
        );

        assertEquals("ARTIFACT_OBJECT_MISSING", exception.getReason());
    }

    private CreateTaskRequest createTaskRequest(String profilePackage) {
        return new CreateTaskRequest(
                "demo.navigate",
                profilePackage,
                Map.of("destination", "IKEA"),
                new RunConfig(1, 60000, 0, false, 15000, 30000),
                new ArtifactPolicy(true, true, true),
                100,
                List.of("demo"),
                "manual",
                "tester",
                "idempotency-key"
        );
    }

    private com.example.platform.control.domain.PersistenceModels.DeviceEntity device(String deviceId) {
        com.example.platform.control.domain.PersistenceModels.DeviceEntity device =
                new com.example.platform.control.domain.PersistenceModels.DeviceEntity();
        device.setDeviceId(deviceId);
        return device;
    }

    private DeviceRuntimeStateEntity updatedRuntime(String deviceId, String status, boolean busy) {
        DeviceRuntimeStateEntity runtime = new DeviceRuntimeStateEntity();
        runtime.setDeviceId(deviceId);
        runtime.setOnline(DomainValues.DEVICE_STATUS_ONLINE.equals(status));
        runtime.setBusy(busy);
        runtime.setStatus(status);
        runtime.setCurrentTaskId("task-1");
        runtime.setCurrentAttemptId("attempt-1");
        runtime.setCurrentTaskType("demo.navigate");
        runtime.setLeaseExpireAt(123L);
        runtime.setLastHeartbeatAt(456L);
        runtime.setUpdatedAt(789L);
        runtime.setHealthJson("{\"authConfigured\":true}");
        return runtime;
    }
}

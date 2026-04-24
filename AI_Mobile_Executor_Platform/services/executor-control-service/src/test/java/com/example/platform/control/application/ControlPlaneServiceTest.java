package com.example.platform.control.application;

import com.example.platform.control.api.ExecutorAuthContext;
import com.example.platform.control.api.ExecutorApiModels.ExecutorIdentityRequest;
import com.example.platform.control.api.ExecutorApiModels.Capabilities;
import com.example.platform.control.api.ExecutorApiModels.ClaimTaskResponse;
import com.example.platform.control.api.ExecutorApiModels.EventsRequest;
import com.example.platform.control.api.ExecutorApiModels.HeartbeatResponse;
import com.example.platform.control.api.ExecutorApiModels.RunEvent;
import com.example.platform.control.domain.DomainValues;
import com.example.platform.control.domain.PersistenceModels.DeviceEntity;
import com.example.platform.control.domain.PersistenceModels.DeviceRuntimeStateEntity;
import com.example.platform.control.domain.PersistenceModels.TaskAttemptEntity;
import com.example.platform.control.domain.PersistenceModels.TaskEntity;
import com.example.platform.control.infrastructure.mapper.DeviceCommandMapper;
import com.example.platform.control.infrastructure.mapper.DeviceMapper;
import com.example.platform.control.infrastructure.mapper.DeviceRuntimeStateMapper;
import com.example.platform.control.infrastructure.mapper.RunEventMapper;
import com.example.platform.control.infrastructure.mapper.TaskAttemptMapper;
import com.example.platform.control.infrastructure.mapper.TaskMapper;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.web.server.ResponseStatusException;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyBoolean;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class ControlPlaneServiceTest {

    private DeviceMapper deviceMapper;
    private DeviceRuntimeStateMapper runtimeStateMapper;
    private TaskMapper taskMapper;
    private TaskAttemptMapper attemptMapper;
    private DeviceCommandMapper commandMapper;
    private RunEventMapper runEventMapper;
    private IdGenerator idGenerator;
    private ControlProperties controlProperties;
    private ControlStateRules controlStateRules;
    private AttemptAccessValidator attemptAccessValidator;
    private ExperimentRunService experimentRunService;
    private ControlPlaneService controlPlaneService;

    @BeforeEach
    void setUp() {
        deviceMapper = Mockito.mock(DeviceMapper.class);
        runtimeStateMapper = Mockito.mock(DeviceRuntimeStateMapper.class);
        taskMapper = Mockito.mock(TaskMapper.class);
        attemptMapper = Mockito.mock(TaskAttemptMapper.class);
        commandMapper = Mockito.mock(DeviceCommandMapper.class);
        runEventMapper = Mockito.mock(RunEventMapper.class);
        idGenerator = Mockito.mock(IdGenerator.class);
        controlProperties = new ControlProperties();
        controlProperties.setScheduleVersion("sched-v1");
        controlProperties.setLeaseMs(60000);
        controlStateRules = new ControlStateRules();
        attemptAccessValidator = new AttemptAccessValidator(attemptMapper);
        experimentRunService = Mockito.mock(ExperimentRunService.class);

        JsonCodec jsonCodec = new JsonCodec(new ObjectMapper());
        controlPlaneService = new ControlPlaneService(
                deviceMapper,
                runtimeStateMapper,
                taskMapper,
                attemptMapper,
                commandMapper,
                runEventMapper,
                jsonCodec,
                idGenerator,
                controlProperties,
                controlStateRules,
                attemptAccessValidator,
                experimentRunService
        );
    }

    @Test
    void claimsTaskWhenInstalledProfilesContainAndroidPackageName() {
        when(runtimeStateMapper.lockByDeviceId("device-1")).thenReturn(activeRuntime());
        when(taskMapper.findClaimableQueuedTasks("device-1", 20)).thenReturn(List.of(queuedTask("com.google.android.apps.maps")));
        when(idGenerator.nextAttemptId()).thenReturn("attempt-1");
        when(idGenerator.nextRunId()).thenReturn("run-generated-1");

        ClaimTaskResponse response = controlPlaneService.claim(authContext(), identityRequest(List.of("com.google.android.apps.maps")));

        assertTrue(response.hasTask());
        assertNotNull(response.task());
        assertEquals("com.google.android.apps.maps", response.task().profilePackage());
        assertEquals(ArtifactUploadMode.DIRECT_PUT_V2, response.task().artifactUploadMode());
        verify(taskMapper).updateStatus(anyString(), anyString(), anyString(), anyLong());
        verify(attemptMapper).insert(any());
        verify(runtimeStateMapper).updateBusyState(anyString(), anyBoolean(), anyString(), anyString(), anyString(), anyString(), any(), isNull(), anyLong());
    }

    @Test
    void claimsTargetedTaskForTargetDevice() {
        when(runtimeStateMapper.lockByDeviceId("device-1")).thenReturn(activeRuntime("device-1"));
        when(taskMapper.findClaimableQueuedTasks("device-1", 20)).thenReturn(List.of(queuedTask("com.google.android.apps.maps", "device-1")));
        when(idGenerator.nextAttemptId()).thenReturn("attempt-1");
        when(idGenerator.nextRunId()).thenReturn("run-generated-1");

        ClaimTaskResponse response = controlPlaneService.claim(authContext("device-1"), identityRequest("device-1", List.of("com.google.android.apps.maps")));

        assertTrue(response.hasTask());
        assertEquals("task-1", response.task().taskId());
        assertEquals("com.google.android.apps.maps", response.task().profilePackage());
    }

    @Test
    void doesNotClaimTaskTargetedToAnotherDevice() {
        when(runtimeStateMapper.lockByDeviceId("device-2")).thenReturn(activeRuntime("device-2"));
        when(taskMapper.findClaimableQueuedTasks("device-2", 20)).thenReturn(List.of());

        ClaimTaskResponse response = controlPlaneService.claim(authContext("device-2"), identityRequest("device-2", List.of("com.google.android.apps.maps")));

        assertFalse(response.hasTask());
        verify(taskMapper).findClaimableQueuedTasks("device-2", 20);
        verify(attemptMapper, never()).insert(any());
    }

    @Test
    void doesNotClaimLegacySlugTaskWhenDeviceReportsAndroidPackageName() {
        when(runtimeStateMapper.lockByDeviceId("device-1")).thenReturn(activeRuntime());
        when(taskMapper.findClaimableQueuedTasks("device-1", 20)).thenReturn(List.of(queuedTask("googlemaps")));

        ClaimTaskResponse response = controlPlaneService.claim(authContext(), identityRequest(List.of("com.google.android.apps.maps")));

        assertFalse(response.hasTask());
    }

    @Test
    void heartbeatRenewsLeaseForActiveAttempt() {
        TaskAttemptEntity attempt = new TaskAttemptEntity();
        attempt.setAttemptId("attempt-1");
        attempt.setTaskId("task-1");
        attempt.setDeviceId("device-1");
        attempt.setStatus(DomainValues.ATTEMPT_STATUS_RUNNING);
        attempt.setLeaseExpireAt(1000L);
        when(attemptMapper.countActiveAttempt("device-1", "attempt-1")).thenReturn(1);
        when(attemptMapper.findById("attempt-1")).thenReturn(attempt);
        when(attemptMapper.renewLease(eq("attempt-1"), eq("device-1"), anyLong(), anyLong())).thenReturn(1);
        when(taskMapper.findById("task-1")).thenReturn(queuedTask("com.google.android.apps.maps"));
        when(commandMapper.findPendingByDevice(anyString(), anyLong())).thenReturn(List.of());
        when(deviceMapper.findById("device-1")).thenReturn(deviceEntity());
        when(runtimeStateMapper.refreshHeartbeat(anyString(), anyString(), any(), anyLong(), any(), anyString(), anyLong())).thenReturn(1);
        when(runtimeStateMapper.findById("device-1")).thenReturn(activeRuntime());

        HeartbeatResponse response = controlPlaneService.heartbeat(authContext(), identityRequest(List.of("com.google.android.apps.maps"), "attempt-1"));

        assertTrue(response.registered());
        verify(attemptMapper).renewLease(anyString(), anyString(), anyLong(), anyLong());
        verify(runtimeStateMapper).refreshHeartbeat(anyString(), anyString(), any(), anyLong(), any(), anyString(), anyLong());
        verify(runtimeStateMapper, never()).upsert(any());
        verify(deviceMapper, never()).upsert(any());
    }

    @Test
    void heartbeatReturnsCancelWhenLeaseRenewLosesRace() {
        TaskAttemptEntity attempt = new TaskAttemptEntity();
        attempt.setAttemptId("attempt-1");
        attempt.setTaskId("task-1");
        attempt.setDeviceId("device-1");
        attempt.setStatus(DomainValues.ATTEMPT_STATUS_RUNNING);
        when(attemptMapper.countActiveAttempt("device-1", "attempt-1")).thenReturn(1);
        when(attemptMapper.findById("attempt-1")).thenReturn(attempt);
        when(attemptMapper.renewLease(eq("attempt-1"), eq("device-1"), anyLong(), anyLong())).thenReturn(0);
        when(commandMapper.findPendingByDevice(anyString(), anyLong())).thenReturn(List.of());
        when(deviceMapper.findById("device-1")).thenReturn(deviceEntity());
        when(runtimeStateMapper.refreshHeartbeat(anyString(), anyString(), any(), anyLong(), any(), anyString(), anyLong())).thenReturn(1);
        when(runtimeStateMapper.findById("device-1")).thenReturn(activeRuntime());

        HeartbeatResponse response = controlPlaneService.heartbeat(authContext(), identityRequest(List.of("com.google.android.apps.maps"), "attempt-1"));

        assertEquals(1, response.commands().size());
        assertEquals("CANCEL_ATTEMPT", response.commands().get(0).type());
        verify(taskMapper, never()).findById(anyString());
    }

    @Test
    void heartbeatUpsertsDeviceFactsWhenIdentityChanges() {
        when(commandMapper.findPendingByDevice(anyString(), anyLong())).thenReturn(List.of());
        when(deviceMapper.findById("device-1")).thenReturn(deviceEntity());
        when(runtimeStateMapper.refreshHeartbeat(anyString(), anyString(), any(), anyLong(), any(), anyString(), anyLong())).thenReturn(1);
        when(runtimeStateMapper.findById("device-1")).thenReturn(activeRuntime());

        controlPlaneService.heartbeat(authContext(), new ExecutorIdentityRequest(
                "device-1",
                "v1",
                "1.1",
                "google",
                "Pixel 6",
                "13",
                1080,
                2400,
                new Capabilities(true, true, true, true, true, true),
                List.of("com.google.android.apps.maps"),
                List.of("debug"),
                "default",
                null,
                null
        ));

        verify(deviceMapper).upsert(any());
    }

    @Test
    void heartbeatReturnsIdleIntervalsWhenDeviceIsIdle() {
        DeviceRuntimeStateEntity runtime = activeRuntime();
        when(commandMapper.findPendingByDevice(anyString(), anyLong())).thenReturn(List.of());
        when(deviceMapper.findById("device-1")).thenReturn(deviceEntity());
        when(runtimeStateMapper.refreshHeartbeat(anyString(), anyString(), any(), anyLong(), any(), anyString(), anyLong())).thenReturn(1);
        when(runtimeStateMapper.findById("device-1")).thenReturn(runtime);

        HeartbeatResponse response = controlPlaneService.heartbeat(authContext(), identityRequest(List.of("com.google.android.apps.maps")));

        assertEquals(controlProperties.getDefaultRunConfig().getIdlePollIntervalMs(), response.runConfig().pollIntervalMs());
        assertEquals(controlProperties.getDefaultRunConfig().getIdleHeartbeatIntervalMs(), response.runConfig().heartbeatIntervalMs());
    }

    @Test
    void heartbeatReturnsQuiescedIntervalsWhenDeviceIsQuiesced() {
        DeviceRuntimeStateEntity runtime = activeRuntime();
        runtime.setStatus(DomainValues.DEVICE_STATUS_QUIESCED);
        when(commandMapper.findPendingByDevice(anyString(), anyLong())).thenReturn(List.of());
        when(deviceMapper.findById("device-1")).thenReturn(deviceEntity());
        when(runtimeStateMapper.refreshHeartbeat(anyString(), anyString(), any(), anyLong(), any(), anyString(), anyLong())).thenReturn(1);
        when(runtimeStateMapper.findById("device-1")).thenReturn(runtime);

        HeartbeatResponse response = controlPlaneService.heartbeat(authContext(), identityRequest(List.of("com.google.android.apps.maps")));

        assertEquals(controlProperties.getDefaultRunConfig().getPollIntervalMs(), response.runConfig().pollIntervalMs());
        assertEquals(controlProperties.getDefaultRunConfig().getQuiescedHeartbeatIntervalMs(), response.runConfig().heartbeatIntervalMs());
    }

    @Test
    void recordEventsPersistsSingleBatchInsert() {
        TaskAttemptEntity attempt = new TaskAttemptEntity();
        attempt.setAttemptId("attempt-1");
        attempt.setTaskId("task-1");
        attempt.setDeviceId("device-1");
        when(attemptMapper.findById("attempt-1")).thenReturn(attempt);

        attempt.setStatus(DomainValues.ATTEMPT_STATUS_RUNNING);

        controlPlaneService.recordEvents(authContext(), "attempt-1", new EventsRequest(List.of(
                new RunEvent("attempt-1", "task-1", "device-1", "run-1", "scenario-1", 1, 1, "STEP_END", "ok", null, "first", 1000L),
                new RunEvent("attempt-1", "task-1", "device-1", "run-1", "scenario-1", 1, 2, "ACTION_END", "ok", null, "second", 1001L)
        )));

        verify(runEventMapper).insertBatch(any());
        verify(runEventMapper, never()).insert(any());
    }

    @Test
    void claimSkipsQuiescedRuntime() {
        DeviceRuntimeStateEntity runtime = activeRuntime();
        runtime.setStatus(DomainValues.DEVICE_STATUS_QUIESCED);
        when(runtimeStateMapper.lockByDeviceId("device-1")).thenReturn(runtime);

        ClaimTaskResponse response = controlPlaneService.claim(authContext(), identityRequest(List.of("com.google.android.apps.maps")));

        assertFalse(response.hasTask());
        verify(taskMapper, Mockito.never()).findClaimableQueuedTasks(anyString(), org.mockito.ArgumentMatchers.anyInt());
    }

    @Test
    void startRejectsInactiveAttempt() {
        TaskAttemptEntity attempt = new TaskAttemptEntity();
        attempt.setAttemptId("attempt-1");
        attempt.setTaskId("task-1");
        attempt.setDeviceId("device-1");
        attempt.setRunId("run-1");
        attempt.setStatus(DomainValues.ATTEMPT_STATUS_SUCCEEDED);
        when(attemptMapper.findById("attempt-1")).thenReturn(attempt);

        ResponseStatusException exception = assertThrows(
                ResponseStatusException.class,
                () -> controlPlaneService.start(authContext(), "attempt-1", new com.example.platform.control.api.ExecutorApiModels.StartRequest(
                        "task-1",
                        "attempt-1",
                        "run-1",
                        "com.google.android.apps.maps",
                        "demo.navigate",
                        "manual"
                ))
        );

        assertEquals(ControlErrorCode.ATTEMPT_STATE_INVALID, exception.getReason());
    }

    @Test
    void finishRejectsInactiveAttempt() {
        TaskAttemptEntity attempt = new TaskAttemptEntity();
        attempt.setAttemptId("attempt-1");
        attempt.setTaskId("task-1");
        attempt.setDeviceId("device-1");
        attempt.setRunId("run-1");
        attempt.setStatus(DomainValues.ATTEMPT_STATUS_SUCCEEDED);
        when(attemptMapper.findById("attempt-1")).thenReturn(attempt);

        ResponseStatusException exception = assertThrows(
                ResponseStatusException.class,
                () -> controlPlaneService.finish(authContext(), "attempt-1", new com.example.platform.control.api.ExecutorApiModels.FinishRequest(
                        "task-1",
                        "attempt-1",
                        "run-1",
                        "SUCCEEDED",
                        null,
                        null,
                        "done"
                ))
        );

        assertEquals(ControlErrorCode.ATTEMPT_STATE_INVALID, exception.getReason());
    }

    @Test
    void finishRejectsWhenAttemptBecomesInactiveBeforeWrite() {
        TaskAttemptEntity attempt = new TaskAttemptEntity();
        attempt.setAttemptId("attempt-1");
        attempt.setTaskId("task-1");
        attempt.setDeviceId("device-1");
        attempt.setRunId("run-1");
        attempt.setStatus(DomainValues.ATTEMPT_STATUS_RUNNING);
        when(attemptMapper.findById("attempt-1")).thenReturn(attempt);
        when(taskMapper.findById("task-1")).thenReturn(queuedTask("com.google.android.apps.maps"));
        when(attemptMapper.finishIfActive(anyString(), anyString(), anyString(), anyString(), any(), any(), anyLong(), anyLong())).thenReturn(0);

        ResponseStatusException exception = assertThrows(
                ResponseStatusException.class,
                () -> controlPlaneService.finish(authContext(), "attempt-1", new com.example.platform.control.api.ExecutorApiModels.FinishRequest(
                        "task-1",
                        "attempt-1",
                        "run-1",
                        "SUCCEEDED",
                        null,
                        null,
                        "done"
                ))
        );

        assertEquals(ControlErrorCode.ATTEMPT_STATE_INVALID, exception.getReason());
        verify(taskMapper, never()).updateStatus(anyString(), anyString(), anyString(), anyLong());
        verify(runtimeStateMapper, never()).updateBusyState(anyString(), anyBoolean(), anyString(), any(), any(), any(), any(), any(), anyLong());
    }

    @Test
    void startRejectsNonOwnedAttempt() {
        TaskAttemptEntity attempt = new TaskAttemptEntity();
        attempt.setAttemptId("attempt-1");
        attempt.setTaskId("task-1");
        attempt.setDeviceId("device-2");
        attempt.setRunId("run-1");
        attempt.setStatus(DomainValues.ATTEMPT_STATUS_LEASED);
        when(attemptMapper.findById("attempt-1")).thenReturn(attempt);

        ResponseStatusException exception = assertThrows(
                ResponseStatusException.class,
                () -> controlPlaneService.start(authContext(), "attempt-1", new com.example.platform.control.api.ExecutorApiModels.StartRequest(
                        "task-1",
                        "attempt-1",
                        "run-1",
                        "com.google.android.apps.maps",
                        "demo.navigate",
                        "manual"
                ))
        );

        assertEquals(ControlErrorCode.ATTEMPT_OWNERSHIP_INVALID, exception.getReason());
    }

    @Test
    void recordEventsRejectsIdentityMismatch() {
        TaskAttemptEntity attempt = new TaskAttemptEntity();
        attempt.setAttemptId("attempt-1");
        attempt.setTaskId("task-1");
        attempt.setRunId("run-1");
        attempt.setDeviceId("device-1");
        attempt.setStatus(DomainValues.ATTEMPT_STATUS_RUNNING);
        when(attemptMapper.findById("attempt-1")).thenReturn(attempt);

        ResponseStatusException exception = assertThrows(
                ResponseStatusException.class,
                () -> controlPlaneService.recordEvents(authContext(), "attempt-1", new EventsRequest(List.of(
                        new RunEvent("attempt-1", "task-1", "device-2", "run-1", "scenario-1", 1, 1, "STEP_END", "ok", null, "first", 1000L)
                )))
        );

        assertEquals(ControlErrorCode.EXECUTOR_IDENTITY_MISMATCH, exception.getReason());
        verify(runEventMapper, never()).insertBatch(any());
    }

    private ExecutorAuthContext authContext() {
        return authContext("device-1");
    }

    private ExecutorAuthContext authContext(String deviceId) {
        return new ExecutorAuthContext(deviceId, "v1", System.currentTimeMillis(), "nonce-1", false);
    }

    private ExecutorIdentityRequest identityRequest(List<String> installedProfiles) {
        return identityRequest("device-1", installedProfiles, null);
    }

    private ExecutorIdentityRequest identityRequest(List<String> installedProfiles, String currentAttemptId) {
        return identityRequest("device-1", installedProfiles, currentAttemptId);
    }

    private ExecutorIdentityRequest identityRequest(String deviceId, List<String> installedProfiles) {
        return identityRequest(deviceId, installedProfiles, null);
    }

    private ExecutorIdentityRequest identityRequest(String deviceId, List<String> installedProfiles, String currentAttemptId) {
        return new ExecutorIdentityRequest(
                deviceId,
                "v1",
                "1.0",
                "google",
                "Pixel 6",
                "13",
                1080,
                2400,
                new Capabilities(true, true, true, true, true, true),
                installedProfiles,
                List.of("debug"),
                "default",
                null,
                currentAttemptId
        );
    }

    private DeviceRuntimeStateEntity activeRuntime() {
        return activeRuntime("device-1");
    }

    private DeviceRuntimeStateEntity activeRuntime(String deviceId) {
        DeviceRuntimeStateEntity runtime = new DeviceRuntimeStateEntity();
        runtime.setDeviceId(deviceId);
        runtime.setRegistered(true);
        runtime.setOnline(true);
        runtime.setBusy(false);
        runtime.setStatus(DomainValues.DEVICE_STATUS_ONLINE);
        runtime.setConfigVersion("cfg-v1");
        return runtime;
    }

    private DeviceEntity deviceEntity() {
        DeviceEntity device = new DeviceEntity();
        device.setDeviceId("device-1");
        device.setProtocolVersion("v1");
        device.setExecutorVersion("1.0");
        device.setBrand("google");
        device.setModel("Pixel 6");
        device.setAndroidVersion("13");
        device.setScreenWidth(1080);
        device.setScreenHeight(2400);
        device.setInstalledProfilesJson("[\"com.google.android.apps.maps\"]");
        device.setTagsJson("[\"debug\"]");
        device.setHostGroup("default");
        return device;
    }

    private TaskEntity queuedTask(String profilePackage) {
        return queuedTask(profilePackage, null);
    }

    private TaskEntity queuedTask(String profilePackage, String targetDeviceId) {
        TaskEntity task = new TaskEntity();
        task.setTaskId("task-1");
        task.setTaskType("demo.navigate");
        task.setProfilePackage(profilePackage);
        task.setTargetDeviceId(targetDeviceId);
        task.setTaskPayloadJson("{\"destination\":\"IKEA\"}");
        task.setRunConfigJson("{\"loopCount\":1,\"budgetMs\":60000,\"loopIntervalMs\":0,\"networkIsolationEnabled\":false,\"pollIntervalMs\":15000,\"heartbeatIntervalMs\":30000}");
        task.setArtifactPolicyJson("{\"uploadLog\":true,\"uploadScreenshot\":true,\"uploadDump\":true}");
        task.setPriority(100);
        task.setLabelsJson("[\"demo\"]");
        task.setSource("manual");
        task.setIdempotencyKey("idem-1");
        task.setStatus(DomainValues.TASK_STATUS_QUEUED);
        return task;
    }
}
